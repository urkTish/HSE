"""Phase 0 contractor status → Phase 2 access cascades (spec 2-access-permits LC-7, LC-8, WA-3)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import CredentialReason, DeploymentStatus, ValidityStatus
from app.core.clock import now, today
from app.core.enums import ContractorStatus, EntityType, NotificationKind, Role
from app.models import Avp, Contractor, Deployment, ProjectEngagement, Worker
from app.services import notify
from app.services.access import lifecycle, waps, workers


def on_contractor_status(
    db: Session, c: Contractor, to_status: ContractorStatus, actor: uuid.UUID | None
) -> None:
    """LC-7 / WA-3: Suspended or Blacklisted → its Active WAPs suspend (`contractor_suspended`);
    reinstatement re-evaluates blockers but never resumes a WAP. LC-8: Blacklisted → its
    deployments demobilised, all its workers' and vehicles' credentials revoked
    (`contractor_blacklisted`), custody → Return Due, HSE Officers told to inform the pass
    office. Descendant engagements are only flagged (Phase 0 rule 27c)."""
    eng_ids = list(
        db.scalars(select(ProjectEngagement.id).where(ProjectEngagement.contractor_id == c.id))
    )
    if not eng_ids:
        return
    if to_status == ContractorStatus.blacklisted:
        _blacklist(db, c, eng_ids, actor)
    waps.refresh_for_engagements(db, eng_ids)
    db.flush()


def _blacklist(
    db: Session, c: Contractor, eng_ids: list[uuid.UUID], actor: uuid.UUID | None
) -> None:
    reason = CredentialReason.contractor_blacklisted
    at = now()
    day = today()
    deps = list(db.scalars(select(Deployment).where(Deployment.engagement_id.in_(eng_ids))))
    projects: set[uuid.UUID] = set()
    for d in deps:
        if d.status != DeploymentStatus.demobilised:
            workers.demobilise(db, d, day, reason, actor)
        projects.add(d.project_id)
    for wid in {d.worker_id for d in deps}:
        w = db.get(Worker, wid)
        if w is not None:
            workers.revoke_all(db, w, reason, actor, engagement_ids=set(eng_ids))
    for a in db.scalars(
        select(Avp).where(
            Avp.engagement_id.in_(eng_ids),
            Avp.validity_status.in_(
                [ValidityStatus.active, ValidityStatus.suspended, ValidityStatus.pending]
            ),
        )
    ):
        lifecycle.revoke(db, a, reason, None, actor, at=at)
        projects.add(a.project_id)
    for pid in projects:
        notify.notify(
            db,
            notify.users_with_role(db, Role.hse_officer, [pid]),
            NotificationKind.contractor_blacklisted_passes,
            f"{c.short_code} blacklisted: inform the pass office (credentials revoked)",
            f"تم إدراج {c.short_code} في القائمة السوداء: أبلغ مكتب التصاريح",
            None,
            None,
            EntityType.contractor,
            c.id,
            pid,
        )
