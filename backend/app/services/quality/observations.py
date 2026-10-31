"""Quality observations (spec 8-quality §A.10.1, Q-OBS-01 / -02). Kept apart from the Phase 1
safety observations: they never enter HSE KPIs and never count as NCRs. An observation is open →
actioned (a quality CA, or escalated to an NCR with source `observation`) → closed (RPM
`observation.close`, reason)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, CapabilityScope, EntityType
from app.core.errors import not_found
from app.core.hse_enums import CaSourceType
from app.core.quality.common import (
    QLinkKind,
    QNcrCategory,
    QNcrSourceType,
    QObservationStatus,
    QRecordType,
)
from app.models import Project, Site
from app.models.quality import QObservation
from app.schemas.hse_common import ApiWarning
from app.services import audit
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs, check_engagement, check_site_zone, id_warnings
from app.services.permissions import Principal, deny, forbidden_error
from app.services.quality import common as qc
from app.services.quality import links, numbering, rpm, signoff

C = Capability
S = CapabilityScope
OS = QObservationStatus
RT = QRecordType.observation


def can_view(p: Principal, o: QObservation) -> bool:
    if p.user.id == o.raised_by_user_id:
        return True
    g = p.grant(o.project_id, C.quality_view)
    return (
        qc.covers(g, o.site_id, o.engagement_id)
        if g is not None and g.scope != S.responsible
        else False
    )


def get_obs(db: Session, p: Principal, obs_id: uuid.UUID) -> QObservation:
    o = db.get(QObservation, obs_id)
    if o is None or not p.can_see_project(o.project_id) or not can_view(p, o):
        raise deny(
            db, p, EntityType.q_observation, obs_id, o.project_id if o else None, "Observation"
        )
    return o


def read(
    db: Session, p: Principal, o: QObservation, warnings: list[ApiWarning] | None = None
) -> dict[str, Any]:
    from app.services.quality.ncr import capa  # noqa: PLC0415
    from app.services.quality.ncr.core import read_only_viewer  # noqa: PLC0415

    refs = Refs(db)
    hide = read_only_viewer(p, o.project_id)
    site = db.get(Site, o.site_id)
    raiser = refs.user(o.raised_by_user_id) if not hide else None
    return {
        "id": o.id,
        "project_id": o.project_id,
        "obs_no": o.obs_no,
        "site_id": o.site_id,
        "site_code": site.code if site else None,
        "zone_id": o.zone_id,
        "system_id": o.system_id,
        "location_ref": o.location_ref,
        "engagement_id": o.engagement_id,
        "category": o.category,
        "description": o.description,
        "suggested_action": o.suggested_action,
        "raised_by": raiser.model_dump() if raiser else None,
        "raised_at": o.raised_at,
        "status": o.status,
        "status_reason": o.status_reason,
        "closed_at": o.closed_at,
        "ncr_id": o.ncr_id,
        "actions": [] if hide else capa.summary(db, CaSourceType.quality_observation, o.id),
        "links": links.links_for(db, p, RT, o.id),
        "warnings": [w.model_dump() for w in (warnings or [])],
    }


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    qc.require_profile(db, project)
    g = p.require(project.id, C.ncr_raise)
    if g.scope == S.responsible or not qc.covers(g, body["site_id"], body.get("engagement_id")):
        raise forbidden_error("This site or contractor is outside your scope.")
    check_site_zone(db, project, body["site_id"], body.get("zone_id"))
    if body.get("engagement_id"):
        check_engagement(db, project, body["engagement_id"])
    at = now()
    o = QObservation(
        project_id=project.id,
        obs_no=numbering.assign(db, project, RT),
        site_id=body["site_id"],
        zone_id=body.get("zone_id"),
        system_id=body.get("system_id"),
        location_ref=body.get("location_ref"),
        engagement_id=body.get("engagement_id"),
        category=QNcrCategory(body["category"]),
        description=body["description"].strip(),
        suggested_action=body.get("suggested_action"),
        raised_by_user_id=p.user.id,
        raised_at=at,
        raised_date=qc.project_day(project, at),
        status=OS.open,
        created_by_user_id=p.user.id,
    )
    db.add(o)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.q_observation,
        entity_id=o.id,
        project_id=project.id,
        after={"obs_no": o.obs_no},
    )
    return read(db, p, o, id_warnings(description=o.description))


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[QObservationStatus] | None = None,
    mine: bool = False,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    g = p.grant(project.id, C.quality_view)
    if g is None and p.grant(project.id, C.ncr_raise) is None:
        raise forbidden_error()
    Q = QObservation  # noqa: N806
    own = Q.raised_by_user_id == p.user.id
    if g is None or g.scope == S.responsible:
        cond: Any = own
    else:
        conds: list[Any] = []
        if g.site_ids is not None:
            conds.append(Q.site_id.in_(list(g.site_ids)) if g.site_ids else false())
        if g.engagement_ids is not None:
            engs = list(g.engagement_ids)
            conds.append(Q.engagement_id.in_(engs) if engs else false())
        cond = or_(and_(*conds), own) if conds else Q.id.is_not(None)
    stmt = select(Q).where(Q.project_id == project.id, cond)
    if statuses:
        stmt = stmt.where(Q.status.in_(statuses))
    if mine:
        stmt = stmt.where(own)
    items, total = paginate(db, stmt.order_by(Q.raised_at.desc()), page, page_size)
    return {
        "items": [read(db, p, o) for o in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def to_ncr(db: Session, p: Principal, obs_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Q-OBS-01: escalate to an NCR (source `observation`, `raised_from` link); the observation
    becomes `actioned`."""
    from app.services.quality.ncr import core  # noqa: PLC0415

    o = get_obs(db, p, obs_id)
    if o.status != OS.open:
        raise invalid_transition("Observation", o.status, "NCR")
    n, warnings = core.create(
        db,
        p,
        o.project_id,
        {
            **body,
            "source_type": QNcrSourceType.observation.value,
            "source_id": o.id,
        },
    )
    o.status = OS.actioned
    o.ncr_id = n.id
    o.status_reason = f"Escalated to an NCR ({n.ncr_no or 'draft'})."
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(o.project_id),
        entity_type=EntityType.q_observation,
        entity_id=o.id,
        project_id=o.project_id,
        before={"status": OS.open},
        after={"status": OS.actioned},
        details={"ncr_id": str(n.id)},
    )
    return core.read(db, p, n, warnings)


def add_action(
    db: Session, p: Principal, obs_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    from app.services.quality.ncr import capa  # noqa: PLC0415

    o = get_obs(db, p, obs_id)
    project = qc.get_project(db, p, o.project_id)
    qc.writable(project, p)
    qc.require_cover(p, project.id, C.ncr_manage, o.site_id, o.engagement_id)
    if o.status == OS.closed:
        raise invalid_transition("Observation", o.status, "action")
    if o.engagement_id is None and not body.get("responsible_engagement_id"):
        raise qc.field_err("responsible_engagement_id", "The responsible contractor is required.")
    _ca, warnings = capa.create_for(db, p, project, CaSourceType.quality_observation, o, body, None)
    if o.status == OS.open:
        o.status = OS.actioned
    db.flush()
    return read(db, p, o, warnings)


def close(db: Session, p: Principal, obs_id: uuid.UUID, why: str | None) -> dict[str, Any]:
    o = get_obs(db, p, obs_id)
    project: Project = qc.get_project(db, p, o.project_id)
    qc.writable(project, p)
    if o.status == OS.closed:
        raise invalid_transition("Observation", o.status, OS.closed)
    text = qc.reason(why, 10)
    ctx = rpm.Ctx(o.site_id, o.engagement_id, qc.ids(o.raised_by_user_id))
    rule, capacity = rpm.check_signer(db, p, project, RT, "close", ctx, record_id=o.id)
    signoff.sign(db, p, project, RT, o.id, "close", "approved", text, rule, capacity)
    src = o.status
    o.status = OS.closed
    o.status_reason = text
    o.closed_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(o.project_id),
        entity_type=EntityType.q_observation,
        entity_id=o.id,
        project_id=o.project_id,
        before={"status": src},
        after={"status": OS.closed},
    )
    return read(db, p, o)


def get_row(db: Session, obs_id: uuid.UUID) -> QObservation:
    o = db.get(QObservation, obs_id)
    if o is None:
        raise not_found("Observation")
    return o


_ = QLinkKind
