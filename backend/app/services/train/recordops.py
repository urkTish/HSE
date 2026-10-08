"""Record operations shared by sessions, external records and imports (spec 5-training TR-10,
TR-14): numbering, session-issued records with their TR QR token, supersession."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import QrKind, QrTokenStatus
from app.core.cert_enums import VerificationStatus
from app.core.clock import now, today
from app.core.enums import AuditAction, EntityType
from app.core.train_enums import (
    PracticalResult,
    TrainingRecordSource,
    TrainingRecordStatus,
    TrainingStatusReason,
    TrainingVerificationMethod,
    TrainingVerificationOutcome,
)
from app.models import (
    QrToken,
    TrainingCourse,
    TrainingNomination,
    TrainingRecord,
    TrainingSession,
    TrainingVerification,
)
from app.services.access import common as acommon
from app.services.cert import common as cc
from app.services.permissions import Principal
from app.services.train import common
from app.services.train import hook as thook
from app.services.train import validity as tval

RS = TrainingRecordStatus
SCORE_FIELDS = ("theory_score_pct",)


def snap(r: TrainingRecord) -> dict[str, object]:
    """Audit snapshot without scores (P5-5: audit diffs never show scores)."""
    return cc.snap(r, exclude=SCORE_FIELDS)


def audit(
    db: Session,
    p: Principal | None,
    action: AuditAction,
    r: TrainingRecord,
    before: dict[str, object] | None = None,
    details: dict[str, object] | None = None,
) -> None:
    cc.record(
        db,
        p,
        action,
        EntityType.training_record,
        r,
        r.project_id,
        before,
        details,
        after=snap(r),
    )


def next_cert_no(db: Session, project_code: str, year: int) -> str:
    prefix = f"TRC-{project_code}-{year}-"
    db.execute(select(func.pg_advisory_xact_lock(5_000_003)))
    rows = db.scalars(
        select(TrainingRecord.certificate_no).where(
            TrainingRecord.certificate_no.like(prefix + "%")
        )
    )
    top = 0
    for x in rows:
        try:
            top = max(top, int(x[len(prefix) :]))
        except ValueError:
            continue
    return f"{prefix}{top + 1:05d}"


def new_record(
    db: Session,
    worker_id: uuid.UUID,
    c: TrainingCourse,
    source: TrainingRecordSource,
    provider_id: uuid.UUID,
    completed_on: date,
    certificate_no: str,
    status: TrainingRecordStatus,
    project_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
    printed_expiry: date | None = None,
) -> TrainingRecord:
    vu, lf = tval.stored_validity(c, completed_on, printed_expiry)
    seq = common.next_record_seq(db)
    r = TrainingRecord(
        id=uuid.uuid4(),
        seq=seq,
        record_no=common.record_no(seq),
        worker_id=worker_id,
        course_code=c.code,
        source=source,
        provider_id=provider_id,
        project_id=project_id,
        engagement_id=engagement_id,
        certificate_no=certificate_no,
        completed_on=completed_on,
        printed_expiry=printed_expiry,
        valid_until=vu,
        limiting_factor=lf,
        status=status,
        verification_status=VerificationStatus.not_verified,
        alerts_sent=[],
        project_sponsored=False,
        historic=False,
        prerequisite_evidenced=False,
        identity_confirmed_by_provider=False,
        anonymised=False,
    )
    db.add(r)
    return r


def issue_from_session(
    db: Session,
    p: Principal,
    s: TrainingSession,
    n: TrainingNomination,
    c: TrainingCourse,
    project_code: str,
    at: datetime,
) -> TrainingRecord:
    """TR-14: Accepted, verified (session_record), TRC number, QR token kind TR."""
    hours = Decimal(sum(int(v) for v in (n.minutes_by_day or {}).values())) / Decimal(60)
    r = new_record(
        db,
        n.worker_id,
        c,
        TrainingRecordSource.session,
        s.provider_id,
        s.last_day,
        next_cert_no(db, project_code, s.last_day.year),
        RS.accepted,
        s.project_id,
        n.engagement_id,
    )
    r.session_id = s.id
    r.theory_score_pct = n.theory_score_pct
    r.practical_result = n.practical_result if c.practical_required else None
    r.hours = hours.quantize(Decimal("0.01"))
    r.verification_status = VerificationStatus.verified
    r.reviewed_by_user_id = p.user.id
    r.reviewed_at = at
    r.verified_at = at
    r.in_force_from = at
    r.status_changed_at = at
    cc.stamp(r, p, create=True)
    db.flush()
    db.add(
        TrainingVerification(
            id=uuid.uuid4(),
            record_id=r.id,
            project_id=s.project_id,
            provider_id=s.provider_id,
            method=TrainingVerificationMethod.session_record,
            channel_used="platform session",
            outcome=TrainingVerificationOutcome.confirmed,
            differences=[],
            reference=s.session_no,
            performed_by_user_id=p.user.id,
            performed_at=at,
            counts_as_verification=True,
            verification_status_after=VerificationStatus.verified,
            created_at=at,
        )
    )
    db.add(
        QrToken(
            id=uuid.uuid4(),
            token=acommon.new_qr_token(),
            kind=QrKind.TR,
            project_id=s.project_id,
            subject_id=r.id,
            printed_ref=r.certificate_no,
            status=QrTokenStatus.active,
            created_at=at,
        )
    )
    n.record_id = r.id
    db.flush()
    audit(db, p, AuditAction.create, r, details={"source": "session", "session": s.session_no})
    supersede_older(db, p, r)
    return r


def supersede_older(db: Session, p: Principal | None, new: TrainingRecord) -> list[TrainingRecord]:
    """TR-10: when `new` is in force, older Accepted records of the same course (and, for a
    renewal course, of the course it renews) become Superseded."""
    c = common.course(db, new.course_code)
    codes = {new.course_code}
    if c is not None and c.renews_only:
        codes |= set(c.satisfies or [])
    for x in common.courses(db).values():
        if x.renewal_course_code == new.course_code:
            codes.add(x.code)
    d = today()
    out = []
    for old in db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.worker_id == new.worker_id,
            TrainingRecord.course_code.in_(codes),
            TrainingRecord.status == RS.accepted,
            TrainingRecord.id != new.id,
        )
    ):
        if old.completed_on > new.completed_on:
            continue
        before = snap(old)
        old.status = RS.superseded
        old.status_reason = TrainingStatusReason.newer_record
        old.superseded_by_id = new.id
        old.superseded_on = d
        old.status_changed_at = now()
        old.ended_on = d
        audit(db, p, AuditAction.status_change, old, before, {"superseded_by": new.record_no})
        out.append(old)
    db.flush()
    thook.clear_cache(db)
    return out


def practical_label(x: PracticalResult | None) -> str | None:
    return x.value if x is not None else None
