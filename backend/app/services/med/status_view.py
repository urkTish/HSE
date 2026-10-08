"""Worker fitness status per code (HK6-6 at `at`, tiered OH-2) and the per-worker data-subject
report (P6-9)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookProviderStatus
from app.core.clock import now
from app.core.enums import AuditAction, EntityType
from app.core.hse_enums import ExportPurpose
from app.core.med_enums import FitnessCheckStatus, HookBand
from app.models import Deployment, FitnessAssessment, FitnessHold, FitnessReferral
from app.schemas.medical import (
    FitnessDataSubjectReport,
    FitnessHoldBrief,
    FitnessReferralBrief,
    WorkerFitnessItem,
    WorkerFitnessRead,
)
from app.services import audit
from app.services.med import assessments, common, engine
from app.services.med import reference as ref
from app.services.med import requirements as rq
from app.services.permissions import Principal, deny, forbidden_error

P = HookProviderStatus


def band(chk: engine.Check) -> tuple[HookBand, tuple[str, str]]:
    if chk.status in (P.met, P.expiring):
        if chk.conditions:
            return HookBand.restriction_applies, ref.RESTRICTION_APPLIES
        return HookBand.cleared, ref.CLEARED
    return HookBand.not_eligible, ref.NOT_ELIGIBLE


def worker_fitness(
    db: Session, p: Principal, worker_id: uuid.UUID, project_id: uuid.UUID, at: datetime | None
) -> WorkerFitnessRead:
    common.visible_project(db, p, project_id)
    w = common.worker(db, worker_id)
    dep = common.deployment(db, worker_id, project_id)
    t = common.tier(p, project_id, dep)
    if dep is None or t < 1:
        raise deny(db, p, EntityType.worker, worker_id, project_id, "Worker")
    at = at or now()
    d = common.local_day(at)
    f = rq.load(db, project_id, d, deployment_ids=[dep.id], mobilised_only=False, at=at)
    required = [r.code for r in rq.evaluate_dep(f, dep)]
    wf = engine.load_one(db, worker_id)
    codes = list(dict.fromkeys(required + [c for c in ref.CODES if c in wf.lines]))
    ctx = engine.ctx_for(db, project_id)
    items = []
    for code in codes:
        chk = engine.check(ctx, wf, code, at)
        b, (en, ar) = band(chk)
        fc = common.code(db, code)
        item = WorkerFitnessItem(
            code=code,
            name_en=fc.name_en if fc else code,
            name_ar=fc.name_ar if fc else code,
            required=code in required,
            status=FitnessCheckStatus(chk.status.value)
            if chk.status.value in {s.value for s in FitnessCheckStatus}
            else FitnessCheckStatus.not_met,
            band=b,
            text_en=en,
            text_ar=ar,
            valid_until=chk.valid_until if chk.ok else None,
        )
        if t >= 2:
            item.hard_stop = chk.hard_stop
            row = chk.row
            if row is not None:
                item.outcome = row.line.outcome
                item.restrictions = [
                    assessments.restriction_read(x) for x in row.line.restrictions or []
                ]
                item.restriction_review_date = row.line.restriction_review_date
                item.unfit_review_date = row.line.unfit_review_date
            item.valid_until = chk.valid_until
        if t >= 3:
            item.reason_code = chk.reason
            item.assessment_no = chk.ref if chk.row is not None else None
        items.append(item)
    out = WorkerFitnessRead(
        worker=common.worker_ref(w, common.names(p, project_id)),
        project_id=project_id,
        as_of=at,
        tier=common.tier_enum(t),
        items=items,
    )
    if t >= 2:
        out.on_hold = bool(engine.active_holds(wf, at))
        fields = ["outcome", "restrictions", "review_dates"]
        if t >= 3:
            fields += ["reason_code", "assessment_no"]
        common.sensitive_read(db, p, EntityType.worker, worker_id, project_id, fields)
        common.sensitive_read(db, p, EntityType.worker, worker_id, project_id, ["fitness_hold"])
    return out


def subject_report(
    db: Session, p: Principal, worker_id: uuid.UUID, purpose: ExportPurpose
) -> FitnessDataSubjectReport:
    w = common.worker(db, worker_id)
    projects = {
        a.project_id
        for a in db.scalars(
            select(FitnessAssessment).where(FitnessAssessment.worker_id == worker_id)
        )
    }
    dep_projects = set(
        db.scalars(select(Deployment.project_id).where(Deployment.worker_id == worker_id))
    )
    pids = projects | dep_projects
    if not any(p.grant(pid, common.C.fitness_subject_report) is not None for pid in pids):
        raise forbidden_error()
    rows = list(
        db.scalars(
            select(FitnessAssessment)
            .where(FitnessAssessment.worker_id == worker_id)
            .order_by(FitnessAssessment.examined_on)
        )
    )
    holds = list(
        db.scalars(
            select(FitnessHold)
            .where(FitnessHold.worker_id == worker_id)
            .order_by(FitnessHold.started_at)
        )
    )
    refs = list(
        db.scalars(
            select(FitnessReferral)
            .where(FitnessReferral.worker_id == worker_id)
            .order_by(FitnessReferral.raised_at)
        )
    )
    audit.record(
        db,
        AuditAction.export,
        p.actor(next(iter(pids), None)),
        entity_type=EntityType.worker,
        entity_id=worker_id,
        details={"dataset": "fitness_subject_report", "purpose": purpose.value},
    )
    return FitnessDataSubjectReport(
        worker=common.worker_ref(w, True),
        generated_at=now(),
        assessments=[assessments.read_model(db, p, a, 3, audit_read=False) for a in rows],
        holds=[
            FitnessHoldBrief(
                hold_no=h.hold_no,
                status=h.status,
                reason=h.reason,
                started_at=h.started_at,
                released_at=h.released_at,
            )
            for h in holds
        ],
        referrals=[
            FitnessReferralBrief(
                referral_no=r.referral_no,
                status=r.status,
                reason=r.reason,
                raised_at=r.raised_at,
                assessed_at=r.assessed_at,
            )
            for r in refs
        ],
    )
