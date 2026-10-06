"""Safety observations (spec 1-dashboard §3.6, §4.3, rules O-1…O-5)."""

import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, and_, exists, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import (
    SAFE_OBSERVATIONS,
    AttachmentOwner,
    CaSourceType,
    ObservationCategory,
    ObservationStatus,
    ObservationType,
    RiskRating,
)
from app.models import Attachment, CorrectiveAction, Observation, Project
from app.schemas.hse_common import ApiWarning
from app.schemas.observations import (
    ObservationCloseRequest,
    ObservationCreate,
    ObservationPage,
    ObservationRead,
    ObservationUpdate,
)
from app.services import audit, projects
from app.services import corrective_actions as ca_svc
from app.services.common import ensure_open, invalid_transition, paginate
from app.services.hse_common import (
    Refs,
    check_engagement,
    check_site_zone,
    covers,
    id_warnings,
    make_ref,
    next_seq,
    project_today,
)
from app.services.incidents import local_date
from app.services.permissions import Principal, deny, engagement_descendants, forbidden_error

ST = ObservationStatus
IMMUTABLE_AFTER = timedelta(hours=24)


def is_safe(t: ObservationType) -> bool:
    return t in SAFE_OBSERVATIONS


def can_view(p: Principal, o: Observation) -> bool:
    if o.observer_id == p.user.id:
        return True
    return covers(
        p.grant(o.project_id, Capability.incident_view), o.site_id, o.observed_engagement_id
    )


def get_obs(db: Session, p: Principal, obs_id: uuid.UUID) -> Observation:
    o = db.get(Observation, obs_id)
    if o is None or not can_view(p, o):
        raise deny(
            db, p, EntityType.observation, obs_id, o.project_id if o else None, "Observation"
        )
    return o


def scoped_query(p: Principal, project: Project) -> Select[Any]:
    Ob = Observation  # noqa: N806
    stmt = select(Ob).where(Ob.project_id == project.id)
    own = Ob.observer_id == p.user.id
    g = p.grant(project.id, Capability.incident_view)
    if g is None:
        return stmt.where(own)
    conds: list[Any] = []
    if g.site_ids is not None:
        conds.append(Ob.site_id.in_(g.site_ids) if g.site_ids else false())
    if g.engagement_ids is not None:
        engs = list(g.engagement_ids)
        conds.append(Ob.observed_engagement_id.in_(engs) if engs else false())
    if conds:
        stmt = stmt.where(or_(and_(*conds), own))
    return stmt


def reads(
    db: Session,
    p: Principal,
    items: Sequence[Observation],
    warnings: list[ApiWarning] | None = None,
) -> list[ObservationRead]:
    if not items:
        return []
    refs = Refs(db).load(
        sites=[o.site_id for o in items],
        zones=[o.zone_id for o in items],
        engs=[o.observed_engagement_id for o in items],
        users=[o.observer_id for o in items],
    )
    project = db.get(Project, items[0].project_id)
    assert project is not None  # noqa: S101
    day = project_today(project)
    cas = ca_svc.summaries(db, CaSourceType.observation, [o.id for o in items], day)
    counts = dict(
        db.execute(
            select(Attachment.owner_id, func.count())
            .where(
                Attachment.owner_type == AttachmentOwner.observation,
                Attachment.owner_id.in_([o.id for o in items]),
            )
            .group_by(Attachment.owner_id)
        ).all()
    )
    see_anon = p.grant(items[0].project_id, Capability.observer_identity_view) is not None
    out = []
    for o in items:
        fields: dict[str, Any] = {
            "id": o.id,
            "ref": o.ref,
            "project_id": o.project_id,
            "site": refs.site(o.site_id),
            "zone": refs.zone(o.zone_id),
            "observed_at": o.observed_at,
            "anonymous": o.anonymous,
            "observed_engagement": refs.eng_required(o.observed_engagement_id),
            "obs_type": o.obs_type,
            "category": o.category,
            "risk_rating": o.risk_rating,
            "description": o.description,
            "stop_work_applied": o.stop_work_applied,
            "immediate_action": o.immediate_action,
            "closed_on_spot": o.closed_on_spot,
            "status": o.status,
            "closure_comment": o.closure_comment,
            "closed_at": o.closed_at,
            "ca_due_by": (
                o.created_at + timedelta(hours=24)
                if o.risk_rating == RiskRating.high
                and not is_safe(o.obs_type)
                and not o.closed_on_spot
                else None
            ),
            "corrective_actions": cas.get(o.id, []),
            "attachment_count": int(counts.get(o.id, 0)),
            "warnings": warnings or [],
            "created_at": o.created_at,
            "updated_at": o.updated_at,
        }
        if not o.anonymous or see_anon:  # O-5: key absent otherwise
            fields["observer"] = refs.user(o.observer_id)
        out.append(ObservationRead(**fields))
    return out


def read(db: Session, p: Principal, obs_id: uuid.UUID) -> ObservationRead:
    return reads(db, p, [get_obs(db, p, obs_id)])[0]


def _validate(o: Observation) -> None:
    if is_safe(o.obs_type):
        o.risk_rating = None
        o.closed_on_spot = None
        return
    if o.risk_rating is None:
        raise validation_error(
            "risk_rating", "The risk rating is required for unsafe observations."
        )
    if not (o.immediate_action or "").strip():
        raise validation_error("immediate_action", "Describe the immediate action taken.")
    if o.closed_on_spot is None:
        o.closed_on_spot = False


def _snapshot(o: Observation) -> dict[str, Any]:
    keys = (
        "zone_id",
        "obs_type",
        "category",
        "risk_rating",
        "description",
        "stop_work_applied",
        "immediate_action",
        "closed_on_spot",
        "status",
    )
    return {k: getattr(o, k) for k in keys}


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: ObservationCreate
) -> ObservationRead:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    g = p.require(project.id, Capability.observation_create)
    if not g.covers_site(body.site_id):  # O-1: site scope only for creating
        raise forbidden_error("This site is outside your scope.")
    check_site_zone(db, project, body.site_id, body.zone_id)
    check_engagement(db, project, body.observed_engagement_id, "observed_engagement_id")
    if body.observed_at > now() + timedelta(minutes=5):
        raise validation_error("observed_at", "The observation cannot be in the future.")
    year = local_date(project, body.observed_at).year
    seq = next_seq(db, Observation, project.id, year)
    o = Observation(
        project_id=project.id,
        ref=make_ref("OBS", project.code, year, seq, 5),
        year=year,
        seq=seq,
        site_id=body.site_id,
        zone_id=body.zone_id,
        observed_at=body.observed_at,
        observed_date=local_date(project, body.observed_at),
        observer_id=p.user.id,
        anonymous=body.anonymous,
        observed_engagement_id=body.observed_engagement_id,
        obs_type=body.obs_type,
        category=body.category,
        risk_rating=body.risk_rating,
        description=body.description,
        stop_work_applied=body.stop_work_applied,
        immediate_action=body.immediate_action,
        closed_on_spot=body.closed_on_spot,
        no_ca_alert_sent=False,
    )
    _validate(o)
    if is_safe(o.obs_type) or o.closed_on_spot:
        o.status = ST.closed
        o.closed_at = now()
        o.closed_date = o.observed_date
        o.closed_by_user_id = p.user.id
    else:
        o.status = ST.open
    db.add(o)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.observation,
        entity_id=o.id,
        project_id=project.id,
        after=_snapshot(o),
    )
    warnings = id_warnings(description=o.description, immediate_action=o.immediate_action)
    return reads(db, p, [o], warnings)[0]


def _can_close(p: Principal, o: Observation) -> bool:
    return covers(
        p.grant(o.project_id, Capability.observation_close), o.site_id, o.observed_engagement_id
    )


def update(
    db: Session, p: Principal, obs_id: uuid.UUID, body: ObservationUpdate
) -> ObservationRead:
    o = get_obs(db, p, obs_id)
    project = db.get(Project, o.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.ensure_writer()
    if o.observer_id != p.user.id and not _can_close(p, o):
        raise forbidden_error()
    if is_safe(o.obs_type) and now() - o.created_at > IMMUTABLE_AFTER:
        raise ApiError(
            409,
            ErrorCode.SAFE_OBSERVATION_IMMUTABLE,
            "Safe observations cannot be changed 24 hours after submission (O-3).",
            "لا يمكن تعديل الملاحظة الآمنة بعد 24 ساعة من تقديمها.",
        )
    if o.status == ST.closed and not is_safe(o.obs_type):
        raise invalid_transition("Observation", o.status, "edited")
    ch = body.changes()
    before = _snapshot(o)
    was_safe = is_safe(o.obs_type)
    for k in (
        "obs_type",
        "category",
        "risk_rating",
        "description",
        "stop_work_applied",
        "immediate_action",
    ):
        if k in ch:
            setattr(o, k, ch[k])
    if "zone_id" in ch:
        check_site_zone(db, project, o.site_id, ch["zone_id"])
        o.zone_id = ch["zone_id"]
    _validate(o)
    if was_safe != is_safe(o.obs_type):
        if is_safe(o.obs_type):
            o.status, o.closed_at, o.closed_date = ST.closed, now(), project_today(project)
        else:
            has_ca = db.scalar(
                select(
                    exists().where(
                        CorrectiveAction.source_type == CaSourceType.observation,
                        CorrectiveAction.source_id == o.id,
                    )
                )
            )
            o.status = ST.action_raised if has_ca else ST.open
            o.closed_at = o.closed_date = None
    o.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, _snapshot(o))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(o.project_id),
            entity_type=EntityType.observation,
            entity_id=o.id,
            project_id=o.project_id,
            before=bf,
            after=af,
        )
    warnings = id_warnings(description=o.description, immediate_action=o.immediate_action)
    return reads(db, p, [o], warnings)[0]


def close(
    db: Session, p: Principal, obs_id: uuid.UUID, body: ObservationCloseRequest
) -> ObservationRead:
    o = get_obs(db, p, obs_id)
    project = db.get(Project, o.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.require(o.project_id, Capability.observation_close)
    if not _can_close(p, o):
        raise forbidden_error()
    if o.status != ST.open:
        raise invalid_transition("Observation", o.status, ST.closed)
    o.status = ST.closed
    o.closure_comment = body.comment
    o.closed_at = now()
    o.closed_date = project_today(project)
    o.closed_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(o.project_id),
        entity_type=EntityType.observation,
        entity_id=o.id,
        project_id=o.project_id,
        before={"status": ST.open},
        after={"status": ST.closed},
        details={"comment": body.comment},
    )
    return reads(db, p, [o])[0]


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    statuses: list[ObservationStatus] | None = None,
    obs_types: list[ObservationType] | None = None,
    category: ObservationCategory | None = None,
    risk_rating: RiskRating | None = None,
    site_ids: list[uuid.UUID] | None = None,
    zone_ids: list[uuid.UUID] | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    without_ca_over_hours: int | None = None,
    mine: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = "-observed_at",
) -> ObservationPage:
    project = projects.get_visible(db, p, project_id)
    Ob = Observation  # noqa: N806
    stmt = scoped_query(p, project)
    if statuses:
        stmt = stmt.where(Ob.status.in_(statuses))
    if obs_types:
        stmt = stmt.where(Ob.obs_type.in_(obs_types))
    if category:
        stmt = stmt.where(Ob.category == category)
    if risk_rating:
        stmt = stmt.where(Ob.risk_rating == risk_rating)
    if site_ids:
        stmt = stmt.where(Ob.site_id.in_(site_ids))
    if zone_ids:
        stmt = stmt.where(Ob.zone_id.in_(zone_ids))
    if engagement_ids:
        engs: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                engs |= engagement_descendants(db, e)
        stmt = stmt.where(Ob.observed_engagement_id.in_(engs))
    if without_ca_over_hours:
        stmt = stmt.where(
            Ob.status == ST.open,
            Ob.risk_rating == RiskRating.high,
            Ob.closed_on_spot.is_(False),
            Ob.created_at < now() - timedelta(hours=without_ca_over_hours),
        )
    if mine:
        stmt = stmt.where(Ob.observer_id == p.user.id)
    if date_from:
        stmt = stmt.where(Ob.observed_date >= date_from)
    if date_to:
        stmt = stmt.where(Ob.observed_date <= date_to)
    order = Ob.observed_at.asc() if sort == "observed_at" else Ob.observed_at.desc()
    stmt = stmt.order_by(order, Ob.ref)
    items, total = paginate(db, stmt, page, page_size)
    return ObservationPage(
        items=reads(db, p, list(items)), total=total, page=page, page_size=page_size
    )
