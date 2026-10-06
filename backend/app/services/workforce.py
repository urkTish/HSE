"""Workforce daily returns and month locks (spec 1-dashboard §3.1, §4.1, §5.1)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, ContractorStatus, EntityType, Role
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import (
    MonthLockStatus,
    Shift,
    TierClass,
    WorkforceSource,
    WorkforceStatus,
)
from app.kpi.periods import add_months, month_end, month_start
from app.models import PeriodLock, Project, ProjectEngagement, WorkforceReturn
from app.schemas.hse_common import ApiWarning
from app.schemas.workforce import (
    BulkItemError,
    BulkVerifyResult,
    WorkforceMonthList,
    WorkforceMonthRead,
    WorkforceReturnCreate,
    WorkforceReturnPage,
    WorkforceReturnRead,
    WorkforceReturnUpdate,
)
from app.services import audit, hse_settings, notify, projects
from app.services.common import ensure_open, invalid_transition, paginate, require_reason
from app.services.hse_common import (
    Refs,
    check_engagement,
    check_site_zone,
    covers,
    ensure_unlocked,
    id_warnings,
    mark_restated,
    project_today,
    require_in_scope,
)
from app.services.permissions import Principal, deny, engagement_descendants, forbidden_error

S = WorkforceStatus
COUNTED = (S.submitted, S.verified, S.locked)
SNAPSHOT_FIELDS = (
    "site_id",
    "zone_id",
    "engagement_id",
    "work_date",
    "shift",
    "no_work",
    "headcount",
    "man_hours",
    "toolbox_talks",
    "toolbox_attendees",
    "inductions",
    "training_hours",
    "remarks",
    "status",
)


def snapshot(r: WorkforceReturn) -> dict[str, Any]:
    return {k: getattr(r, k) for k in SNAPSHOT_FIELDS}


def to_read(r: WorkforceReturn, refs: Refs) -> WorkforceReturnRead:
    eng = refs.eng_required(r.engagement_id)
    return WorkforceReturnRead(
        id=r.id,
        project_id=r.project_id,
        site=refs.site(r.site_id),
        zone=refs.zone(r.zone_id),
        engagement=eng,
        tier_class=TierClass.direct if eng.tier == 1 else TierClass.subcontractor,
        work_date=r.work_date,
        shift=r.shift,
        no_work=r.no_work,
        headcount=r.headcount,
        man_hours=r.man_hours,
        toolbox_talks=r.toolbox_talks,
        toolbox_attendees=r.toolbox_attendees,
        inductions=r.inductions,
        training_hours=r.training_hours,
        remarks=r.remarks,
        source=r.source,
        import_batch_id=r.import_batch_id,
        status=r.status,
        created_by=refs.user(r.created_by_user_id),
        verified_by=refs.user(r.verified_by_user_id),
        verified_at=r.verified_at,
        warnings=[ApiWarning(**w) for w in (r.warnings or [])],
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _refs_for(db: Session, rows: list[WorkforceReturn]) -> Refs:
    return Refs(db).load(
        sites=[r.site_id for r in rows],
        zones=[r.zone_id for r in rows],
        engs=[r.engagement_id for r in rows],
        users=[u for r in rows for u in (r.created_by_user_id, r.verified_by_user_id)],
    )


def read(db: Session, r: WorkforceReturn) -> WorkforceReturnRead:
    return to_read(r, _refs_for(db, [r]))


# ---- validation ----------------------------------------------------------------------------------


def validate_values(
    db: Session,
    project: Project,
    eng: ProjectEngagement,
    site_id: uuid.UUID,
    work_date: date,
    headcount: int,
    man_hours: Decimal,
    no_work: bool,
) -> list[ApiWarning]:
    """Field rules of §3.1 shared by create and update; returns non-blocking warnings."""
    s = hse_settings.get(db, project.id)
    if site_id not in (eng.site_ids or []):
        raise validation_error("site_id", "The site is not in this engagement's sites.")
    if work_date > project_today(project):
        raise validation_error("work_date", "work_date cannot be in the future.")
    if work_date < project.start_date:
        raise validation_error("work_date", "work_date is before the project start date.")
    if work_date < eng.mobilisation_date or (
        eng.demobilisation_date is not None and work_date > eng.demobilisation_date
    ):
        raise ApiError(
            422,
            ErrorCode.OUTSIDE_MOBILISATION,
            "work_date is outside the engagement's mobilisation–demobilisation dates.",
            "تاريخ العمل خارج فترة تعبئة المقاول.",
        )
    if no_work and (headcount or man_hours):
        raise validation_error("no_work", "no_work requires headcount = 0 and man_hours = 0.")
    if headcount == 0 and man_hours > 0:
        raise validation_error("man_hours", "headcount = 0 requires man_hours = 0.")
    if man_hours > Decimal(headcount * s.max_hours_per_person_day):
        raise validation_error(
            "man_hours",
            f"man_hours exceeds headcount × {s.max_hours_per_person_day} h.",
        )
    warnings: list[ApiWarning] = []
    if headcount and man_hours / headcount > s.warn_hours_per_person_day:
        warnings.append(
            ApiWarning(
                code="W01",
                message=f"More than {s.warn_hours_per_person_day} h per person.",
                message_ar=f"أكثر من {s.warn_hours_per_person_day} ساعة للفرد.",
                field="man_hours",
            )
        )
    if eng.contractor.status == ContractorStatus.suspended:
        warnings.append(
            ApiWarning(
                code="W03",
                message="Contractor is suspended; hours are still recorded.",
                message_ar="المقاول موقوف؛ يتم تسجيل الساعات.",
            )
        )
    return warnings


def _duplicate(
    db: Session,
    project_id: uuid.UUID,
    work_date: date,
    site_id: uuid.UUID,
    zone_id: uuid.UUID | None,
    eng_id: uuid.UUID,
    shift: Shift,
    exclude: uuid.UUID | None = None,
) -> bool:
    W = WorkforceReturn  # noqa: N806
    stmt = select(W.id).where(
        W.project_id == project_id,
        W.work_date == work_date,
        W.site_id == site_id,
        W.zone_id.is_(None) if zone_id is None else W.zone_id == zone_id,
        W.engagement_id == eng_id,
        W.shift == shift,
    )
    if exclude:
        stmt = stmt.where(W.id != exclude)
    return db.scalar(stmt.limit(1)) is not None


def duplicate_error() -> ApiError:
    return ApiError(
        409,
        ErrorCode.DUPLICATE_RETURN,
        "A return already exists for this date, site, zone, contractor and shift.",
        "يوجد بيان بنفس التاريخ والموقع والمنطقة والمقاول والوردية.",
    )


# ---- CRUD ----------------------------------------------------------------------------------------


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: WorkforceReturnCreate
) -> WorkforceReturnRead:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    require_in_scope(p, project.id, Capability.workforce_edit, body.site_id, body.engagement_id)
    check_site_zone(db, project, body.site_id, body.zone_id)
    eng = check_engagement(db, project, body.engagement_id)
    warnings = validate_values(
        db, project, eng, body.site_id, body.work_date, body.headcount, body.man_hours, body.no_work
    )
    warnings += id_warnings(remarks=body.remarks)
    ensure_unlocked(db, project.id, body.work_date)
    if _duplicate(db, project.id, body.work_date, body.site_id, body.zone_id, eng.id, body.shift):
        raise duplicate_error()
    r = WorkforceReturn(
        project_id=project.id,
        site_id=body.site_id,
        zone_id=body.zone_id,
        engagement_id=eng.id,
        work_date=body.work_date,
        shift=body.shift,
        no_work=body.no_work,
        headcount=body.headcount,
        man_hours=body.man_hours,
        toolbox_talks=body.toolbox_talks,
        toolbox_attendees=body.toolbox_attendees,
        inductions=body.inductions,
        training_hours=body.training_hours,
        remarks=body.remarks,
        source=WorkforceSource.manual,
        status=S.submitted if body.submit else S.draft,
        warnings=[w.model_dump() for w in warnings if w.code != "POSSIBLE_ID_NUMBER"],
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    mark_restated(db, p, project.id, r.work_date, "workforce return created")
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.workforce_return,
        entity_id=r.id,
        project_id=project.id,
        after=snapshot(r),
    )
    out = read(db, r)
    out.warnings = warnings
    return out


def get_row(db: Session, p: Principal, return_id: uuid.UUID) -> WorkforceReturn:
    r = db.get(WorkforceReturn, return_id)
    if r is None:
        raise deny(db, p, EntityType.workforce_return, return_id, None, "Workforce return")
    g = p.grant(r.project_id, Capability.workforce_view)
    if not covers(g, r.site_id, r.engagement_id):
        raise deny(db, p, EntityType.workforce_return, r.id, r.project_id, "Workforce return")
    return r


def get(db: Session, p: Principal, return_id: uuid.UUID) -> WorkforceReturnRead:
    return read(db, get_row(db, p, return_id))


def update(
    db: Session, p: Principal, return_id: uuid.UUID, body: WorkforceReturnUpdate
) -> WorkforceReturnRead:
    r = get_row(db, p, return_id)
    project = db.get(Project, r.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    require_in_scope(p, project.id, Capability.workforce_edit, r.site_id, r.engagement_id)
    if r.status == S.locked:
        ensure_unlocked(db, project.id, r.work_date)
        raise invalid_transition("Workforce return", r.status, "edit")
    if r.status == S.verified:
        raise invalid_transition("Workforce return", r.status, "edit")
    ensure_unlocked(db, project.id, r.work_date)
    before = snapshot(r)
    data = body.changes()
    if "zone_id" in data:
        check_site_zone(db, project, r.site_id, data["zone_id"])
    for k, v in data.items():
        setattr(r, k, v)
    eng = check_engagement(db, project, r.engagement_id)
    warnings = validate_values(
        db, project, eng, r.site_id, r.work_date, r.headcount, r.man_hours, r.no_work
    )
    if r.toolbox_attendees > r.headcount * 2:
        raise validation_error("toolbox_attendees", "toolbox_attendees must be ≤ headcount × 2.")
    if r.training_hours > r.man_hours:
        raise validation_error("training_hours", "training_hours must be ≤ man_hours.")
    if _duplicate(
        db, project.id, r.work_date, r.site_id, r.zone_id, r.engagement_id, r.shift, exclude=r.id
    ):
        raise duplicate_error()
    r.warnings = [w.model_dump() for w in warnings]
    db.flush()
    mark_restated(db, p, project.id, r.work_date, "workforce return edited")
    b, a = audit.diff(before, snapshot(r))
    audit.record(
        db,
        AuditAction.update,
        p.actor(project.id),
        entity_type=EntityType.workforce_return,
        entity_id=r.id,
        project_id=project.id,
        before=b,
        after=a,
    )
    out = read(db, r)
    out.warnings = warnings + id_warnings(remarks=r.remarks)
    return out


def delete(db: Session, p: Principal, return_id: uuid.UUID) -> None:
    r = get_row(db, p, return_id)
    require_in_scope(p, r.project_id, Capability.workforce_edit, r.site_id, r.engagement_id)
    if r.status != S.draft:
        raise invalid_transition("Workforce return", r.status, "deleted")
    if (
        r.created_by_user_id != p.user.id
        and p.grant(r.project_id, Capability.workforce_verify) is None
    ):
        raise forbidden_error("Only the creator or an HSE Officer may delete a draft return.")
    before = snapshot(r)
    db.delete(r)
    db.flush()
    audit.record(
        db,
        AuditAction.archive,
        p.actor(r.project_id),
        entity_type=EntityType.workforce_return,
        entity_id=r.id,
        project_id=r.project_id,
        before=before,
        details={"deleted": True},
    )


# ---- transitions ---------------------------------------------------------------------------------


def _verify(db: Session, p: Principal, r: WorkforceReturn) -> None:
    require_in_scope(p, r.project_id, Capability.workforce_verify, r.site_id, r.engagement_id)
    if r.status != S.submitted:
        raise invalid_transition("Workforce return", r.status, S.verified)
    if r.created_by_user_id == p.user.id:
        raise ApiError(
            409,
            ErrorCode.VERIFIER_IS_CREATOR,
            "You created this return; another verifier must verify it.",
            "أنشأت هذا البيان؛ يجب أن يعتمده شخص آخر.",
        )
    ensure_unlocked(db, r.project_id, r.work_date)
    r.status = S.verified
    r.verified_by_user_id = p.user.id
    r.verified_at = now()


def transition(
    db: Session, p: Principal, return_id: uuid.UUID, to: WorkforceStatus, reason: str | None
) -> WorkforceReturnRead:
    r = get_row(db, p, return_id)
    project = db.get(Project, r.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    src = r.status
    before = snapshot(r)
    if src == S.draft and to == S.submitted:
        require_in_scope(p, project.id, Capability.workforce_edit, r.site_id, r.engagement_id)
        ensure_unlocked(db, project.id, r.work_date)
        eng = check_engagement(db, project, r.engagement_id)
        validate_values(
            db, project, eng, r.site_id, r.work_date, r.headcount, r.man_hours, r.no_work
        )
        r.status = S.submitted
    elif src == S.submitted and to == S.draft:
        require_in_scope(p, project.id, Capability.workforce_edit, r.site_id, r.engagement_id)
        if (
            r.created_by_user_id != p.user.id
            and p.grant(project.id, Capability.workforce_verify) is None
        ):
            raise forbidden_error("Only the creator or an HSE Officer may return it to draft.")
        ensure_unlocked(db, project.id, r.work_date)
        r.status = S.draft
    elif src == S.submitted and to == S.verified:
        _verify(db, p, r)
    elif src == S.verified and to == S.submitted:
        require_in_scope(p, project.id, Capability.workforce_verify, r.site_id, r.engagement_id)
        reason = require_reason(reason, "correct a verified return")
        ensure_unlocked(db, project.id, r.work_date)
        r.status = S.submitted
        r.verified_by_user_id = None
        r.verified_at = None
    elif src == S.locked and to == S.verified:
        p.require(project.id, Capability.workforce_unlock)
        reason = require_reason(reason, "unlock a locked return")
        r.status = S.verified
        mark_restated(db, p, project.id, r.work_date, "locked return unlocked for correction")
    else:
        raise invalid_transition("Workforce return", src, to)
    db.flush()
    if src != S.locked:
        mark_restated(db, p, project.id, r.work_date, f"return {src.value} → {to.value}")
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id),
        entity_type=EntityType.workforce_return,
        entity_id=r.id,
        project_id=project.id,
        before=before,
        after=snapshot(r),
        details={"reason": reason} if reason else None,
    )
    return read(db, r)


def bulk_verify(
    db: Session, p: Principal, project_id: uuid.UUID, ids: list[uuid.UUID]
) -> BulkVerifyResult:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    p.require(project.id, Capability.workforce_verify)
    verified, failed = [], []
    rows = {r.id: r for r in db.scalars(select(WorkforceReturn).where(WorkforceReturn.id.in_(ids)))}
    for rid in ids:
        r = rows.get(rid)
        if r is None or r.project_id != project.id:
            failed.append(
                BulkItemError(
                    id=rid, code=ErrorCode.NOT_FOUND.value, message="Workforce return not found."
                )
            )
            continue
        before = snapshot(r)
        try:
            with db.begin_nested():
                _verify(db, p, r)
        except ApiError as e:
            failed.append(
                BulkItemError(id=rid, code=e.code.value, message=e.message, message_ar=e.message_ar)
            )
            continue
        verified.append(rid)
        audit.record(
            db,
            AuditAction.status_change,
            p.actor(project.id),
            entity_type=EntityType.workforce_return,
            entity_id=r.id,
            project_id=project.id,
            before=before,
            after=snapshot(r),
            details={"bulk": True},
        )
    db.flush()
    return BulkVerifyResult(verified=verified, failed=failed)


# ---- list ----------------------------------------------------------------------------------------


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    site_ids: list[uuid.UUID] | None = None,
    zone_id: uuid.UUID | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = False,
    shift: Shift | None = None,
    statuses: list[WorkforceStatus] | None = None,
    source: WorkforceSource | None = None,
    import_batch_id: uuid.UUID | None = None,
    has_warnings: bool | None = None,
    sort: str = "-work_date",
) -> WorkforceReturnPage:
    project = projects.get_visible(db, p, project_id)
    g = p.grant(project.id, Capability.workforce_view)
    if g is None:
        raise forbidden_error()
    W = WorkforceReturn  # noqa: N806
    stmt: Select[Any] = select(W).where(W.project_id == project.id)
    if g.site_ids is not None:
        stmt = stmt.where(W.site_id.in_(g.site_ids))
    if g.engagement_ids is not None:
        stmt = stmt.where(W.engagement_id.in_(g.engagement_ids))
    if date_from:
        stmt = stmt.where(W.work_date >= date_from)
    if date_to:
        stmt = stmt.where(W.work_date <= date_to)
    if site_ids:
        stmt = stmt.where(W.site_id.in_(site_ids))
    if zone_id:
        stmt = stmt.where(W.zone_id == zone_id)
    if engagement_ids:
        ids: set[uuid.UUID] = set()
        for e in engagement_ids:
            ids |= engagement_descendants(db, e) if include_subcontractors else {e}
        stmt = stmt.where(W.engagement_id.in_(ids))
    if shift:
        stmt = stmt.where(W.shift == shift)
    if statuses:
        stmt = stmt.where(W.status.in_(statuses))
    if source:
        stmt = stmt.where(W.source == source)
    if import_batch_id:
        stmt = stmt.where(W.import_batch_id == import_batch_id)
    if has_warnings is not None:
        empty = func.jsonb_array_length(W.warnings) == 0
        stmt = stmt.where(~empty if has_warnings else empty)
    col = W.man_hours if "man_hours" in sort else W.work_date
    stmt = stmt.order_by(col.desc() if sort.startswith("-") else col.asc(), W.id)
    items, total = paginate(db, stmt, page, page_size)
    refs = _refs_for(db, list(items))
    return WorkforceReturnPage(
        items=[to_read(r, refs) for r in items], total=total, page=page, page_size=page_size
    )


# ---- months --------------------------------------------------------------------------------------


def _month_read(
    db: Session, project: Project, m: date, lock: PeriodLock | None, refs: Refs
) -> WorkforceMonthRead:
    s = hse_settings.get(db, project.id)
    W = WorkforceReturn  # noqa: N806
    counts = dict(
        db.execute(
            select(W.status, func.count())
            .where(W.project_id == project.id, W.work_date >= m, W.work_date <= month_end(m))
            .group_by(W.status)
        ).all()
    )
    mh = db.scalar(
        select(func.coalesce(func.sum(W.man_hours), 0)).where(
            W.project_id == project.id,
            W.work_date >= m,
            W.work_date <= month_end(m),
            W.status.in_(COUNTED),
        )
    )
    nxt = add_months(m, 1)
    return WorkforceMonthRead(
        project_id=project.id,
        month=m.strftime("%Y-%m"),
        status=MonthLockStatus.locked if lock and lock.locked else MonthLockStatus.open,
        auto_lock_date=nxt.replace(day=min(s.month_lock_day, 28)),
        locked_at=lock.locked_at if lock and lock.locked else None,
        locked_by=refs.user(lock.locked_by_user_id) if lock and lock.locked else None,
        restated=bool(lock and lock.restated),
        restated_at=lock.restated_at if lock else None,
        rows_by_status={st: int(counts.get(st, 0)) for st in WorkforceStatus},
        man_hours=Decimal(mh or 0),
    )


def parse_month(month: str) -> date:
    y, m = month.split("-")
    return date(int(y), int(m), 1)


def list_months(
    db: Session, p: Principal, project_id: uuid.UUID, year: int | None
) -> WorkforceMonthList:
    project = projects.get_visible(db, p, project_id)
    if p.grant(project.id, Capability.workforce_view) is None:
        raise forbidden_error()
    last = month_start(project_today(project))
    m = month_start(project.start_date)
    months = []
    while m <= last:
        if year is None or m.year == year:
            months.append(m)
        m = add_months(m, 1)
    locks = {
        x.month: x
        for x in db.scalars(select(PeriodLock).where(PeriodLock.project_id == project.id))
    }
    refs = Refs(db)
    return WorkforceMonthList(
        items=[_month_read(db, project, mm, locks.get(mm), refs) for mm in reversed(months)]
    )


def lock_month(
    db: Session, p: Principal | None, project: Project, m: date, reason: str | None = None
) -> PeriodLock:
    """Lock a month: submitted/verified rows → locked (HSE Manager or the auto-lock job)."""
    lock = db.get(PeriodLock, (project.id, m))
    if lock is None:
        lock = PeriodLock(project_id=project.id, month=m, locked=False, restated=False)
        db.add(lock)
    if lock.locked:
        raise ApiError(
            409, ErrorCode.INVALID_TRANSITION, "The month is already locked.", "الشهر مقفل مسبقاً."
        )
    lock.locked = True
    lock.locked_at = now()
    lock.locked_by_user_id = p.user.id if p else None
    W = WorkforceReturn  # noqa: N806
    rows = db.scalars(
        select(W).where(
            W.project_id == project.id,
            W.work_date >= m,
            W.work_date <= month_end(m),
            W.status.in_([S.submitted, S.verified]),
        )
    ).all()
    for r in rows:
        r.status = S.locked
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id) if p else audit.SYSTEM,
        entity_type=EntityType.workforce_month,
        project_id=project.id,
        details={
            "month": m.strftime("%Y-%m"),
            "locked": True,
            "rows": len(rows),
            "reason": reason,
            "automatic": p is None,
        },
    )
    return lock


def lock(
    db: Session, p: Principal, project_id: uuid.UUID, month: str, reason: str | None
) -> WorkforceMonthRead:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    p.require(project.id, Capability.workforce_lock)
    m = parse_month(month)
    if m > month_start(project_today(project)):
        raise validation_error("month", "A future month cannot be locked.")
    row = lock_month(db, p, project, m, reason)
    return _month_read(db, project, m, row, Refs(db))


def unlock(
    db: Session, p: Principal, project_id: uuid.UUID, month: str, reason: str
) -> WorkforceMonthRead:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    p.require(project.id, Capability.workforce_unlock)
    reason = require_reason(reason, "unlock a month")
    m = parse_month(month)
    row = db.get(PeriodLock, (project.id, m))
    if row is None or not row.locked:
        raise ApiError(
            409, ErrorCode.INVALID_TRANSITION, "The month is not locked.", "الشهر غير مقفل."
        )
    row.locked = False
    row.unlock_reason = reason
    W = WorkforceReturn  # noqa: N806
    rows = db.scalars(
        select(W).where(
            W.project_id == project.id,
            W.work_date >= m,
            W.work_date <= month_end(m),
            W.status == S.locked,
        )
    ).all()
    for r in rows:
        r.status = S.verified
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id),
        entity_type=EntityType.workforce_month,
        project_id=project.id,
        details={"month": month, "locked": False, "rows": len(rows), "reason": reason},
    )
    return _month_read(db, project, m, row, Refs(db))


def month_lock_candidates(db: Session, project: Project, day: date) -> list[date]:
    """Months due for automatic lock on ``day`` (month_lock_day of the following month)."""
    s = hse_settings.get(db, project.id)
    prev = add_months(month_start(day), -1)
    if day.day < s.month_lock_day:
        return []
    row = db.get(PeriodLock, (project.id, prev))
    if row is not None and (row.locked or row.locked_at is not None):
        return []  # locked, or unlocked by the HSE Manager after a lock: never re-lock silently
    if prev < month_start(project.start_date):
        return []
    return [prev]


def officers(db: Session, project_id: uuid.UUID) -> list[uuid.UUID]:
    return notify.users_with_role(db, Role.hse_officer, [project_id])
