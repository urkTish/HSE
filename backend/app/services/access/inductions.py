"""Induction courses and records (spec 2-access-permits §3.3, §3.4, §4.3, §5.2 IN-1…IN-13),
the eligibility endpoint and hook-provider listing (ZP-3, HK-3, HK-4)."""

import base64
import binascii
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    DeploymentStatus,
    EligibilityContext,
    HookKind,
    HookPolicy,
    InductionDelivererRole,
    InductionResult,
    InductionStatus,
    InductionType,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, field_error, not_found, validation_error
from app.core.hse_enums import AttachmentOwner
from app.models import (
    Deployment,
    InductionCourse,
    InductionRecord,
    InductionRetrainingNote,
    Project,
    Worker,
    Zone,
    ZoneAccessProfile,
)
from app.schemas.hse_common import ApiWarning
from app.schemas.inductions import (
    EligibilityResult,
    HookProviderInfo,
    InductionAttendee,
    InductionCourseCreate,
    InductionCourseList,
    InductionCourseRead,
    InductionCourseUpdate,
    InductionCourseVersionPublish,
    InductionRecordCreate,
    InductionRecordPage,
    InductionRecordRead,
    InductionRecordUpdate,
    InductionRetrainingNoteRead,
    InductionSessionCreate,
    InductionSessionResult,
)
from app.schemas.inductions import InductionRetrainingNote as RetrainingNoteIn
from app.services import attachments, audit, notify, projects
from app.services.access import common, eligibility, hooks, lifecycle, profiles, reasons, workers
from app.services.common import duplicate, paginate
from app.services.hse_common import Refs, contractor_reps, make_ref, next_seq, user_roles
from app.services.permissions import Principal, engagement_descendants, forbidden_error

C = Capability
ATTEMPT_WINDOW_DAYS = 30
EDIT_LOCK_HOURS = 24
ROLE_OF = {
    Role.hse_manager: InductionDelivererRole.hse_manager,
    Role.hse_officer: InductionDelivererRole.hse_officer,
    Role.contractor_hse_rep: InductionDelivererRole.contractor_hse_rep,
}


def _version_key(v: str) -> tuple[int, int]:
    major, minor = v.split(".")
    return int(major), int(minor)


# ---- courses ------------------------------------------------------------------------------------


def course_read(db: Session, c: InductionCourse) -> InductionCourseRead:
    s = common.settings(db, c.project_id)
    eff = max(c.pass_mark_pct or 0, s.induction_pass_mark_pct) if c.test_required else None
    return InductionCourseRead(
        id=c.id,
        project_id=c.project_id,
        code=c.code,
        induction_type=c.induction_type,
        name_en=c.name_en,
        name_ar=c.name_ar,
        version=c.version,
        version_published_on=c.version_published_on,
        requires_reinduction=c.requires_reinduction,
        validity_months=c.validity_months,
        validity_days=c.validity_days,
        min_duration_minutes=c.min_duration_minutes,
        test_required=c.test_required,
        pass_mark_pct=c.pass_mark_pct,
        effective_pass_mark_pct=eff,
        languages_offered=list(c.languages_offered or []),
        prerequisite_codes=list(c.prerequisite_codes or []),
        delivered_by_roles=list(c.delivered_by_roles or []),
        active=c.active,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def get_course(db: Session, p: Principal, course_id: uuid.UUID) -> InductionCourse:
    c = db.get(InductionCourse, course_id)
    if c is None:
        raise not_found("Induction course")
    projects.get_visible(db, p, c.project_id)
    return c


def list_courses(
    db: Session, p: Principal, project_id: uuid.UUID, active: bool | None
) -> InductionCourseList:
    project = projects.get_visible(db, p, project_id)
    stmt = select(InductionCourse).where(InductionCourse.project_id == project.id)
    if active is not None:
        stmt = stmt.where(InductionCourse.active.is_(active))
    return InductionCourseList(
        items=[course_read(db, c) for c in db.scalars(stmt.order_by(InductionCourse.code))]
    )


def read_course(db: Session, p: Principal, course_id: uuid.UUID) -> InductionCourseRead:
    return course_read(db, get_course(db, p, course_id))


def _validate_course(
    db: Session,
    project_id: uuid.UUID,
    code: str,
    kind: InductionType,
    months: int | None,
    days: int | None,
    prereqs: list[str],
    roles: list[str],
) -> None:
    if kind == InductionType.visitor:
        if not days:
            raise validation_error("validity_days", "Visitor courses need validity_days (1-7).")
    elif not months:
        raise validation_error("validity_months", "validity_months is required (1-36).")
    elif days:
        raise validation_error("validity_days", "validity_days is for visitor courses only.")
    codes = set(
        db.scalars(select(InductionCourse.code).where(InductionCourse.project_id == project_id))
    )
    for c in prereqs:
        if c == code or c not in codes:
            raise validation_error("prerequisite_codes", f"Unknown prerequisite course {c}.")
    if InductionDelivererRole.contractor_hse_rep.value in roles:
        airside_use = kind == InductionType.airside
        if kind == InductionType.zone_specific:
            airside_use = any(
                code in (prof.required_inductions or [])
                for prof, zone in _profiles_with_zones(db, project_id)
                if zone.zone_type.value == "airside"
            )
        if airside_use:
            raise ApiError(
                422,
                ErrorCode.DELIVERER_NOT_ALLOWED,
                "Airside courses (and zone courses used on airside zones) cannot be delivered "
                "by Contractor HSE Reps (IN-3).",
                "لا يسمح بتقديم دورات الجانب الجوي من ممثل المقاول.",
            )


def _profiles_with_zones(
    db: Session, project_id: uuid.UUID
) -> list[tuple[ZoneAccessProfile, Zone]]:
    return [
        (prof, zone)
        for prof, zone in db.execute(
            select(ZoneAccessProfile, Zone)
            .join(Zone, Zone.id == ZoneAccessProfile.zone_id)
            .where(ZoneAccessProfile.project_id == project_id)
        ).tuples()
    ]


def _course_snapshot(c: InductionCourse) -> dict[str, Any]:
    return {
        "code": c.code,
        "induction_type": c.induction_type,
        "name_en": c.name_en,
        "name_ar": c.name_ar,
        "version": c.version,
        "requires_reinduction": c.requires_reinduction,
        "validity_months": c.validity_months,
        "validity_days": c.validity_days,
        "min_duration_minutes": c.min_duration_minutes,
        "test_required": c.test_required,
        "pass_mark_pct": c.pass_mark_pct,
        "languages_offered": list(c.languages_offered or []),
        "prerequisite_codes": list(c.prerequisite_codes or []),
        "delivered_by_roles": list(c.delivered_by_roles or []),
        "active": c.active,
    }


def create_course(
    db: Session, p: Principal, project_id: uuid.UUID, body: InductionCourseCreate
) -> InductionCourseRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, C.induction_course_manage)
    code = body.code.strip().upper()
    if db.scalar(
        select(InductionCourse.id).where(
            InductionCourse.project_id == project.id, InductionCourse.code == code
        )
    ):
        raise duplicate("code", "A course with this code already exists.")
    roles = [r.value for r in body.delivered_by_roles]
    _validate_course(
        db,
        project.id,
        code,
        body.induction_type,
        body.validity_months,
        body.validity_days,
        body.prerequisite_codes,
        roles,
    )
    c = InductionCourse(
        id=uuid.uuid4(),
        project_id=project.id,
        code=code,
        induction_type=body.induction_type,
        name_en=body.name_en,
        name_ar=body.name_ar,
        version=body.version,
        version_published_on=today(),
        requires_reinduction=False,
        validity_months=body.validity_months,
        validity_days=body.validity_days,
        min_duration_minutes=body.min_duration_minutes,
        test_required=body.test_required,
        pass_mark_pct=body.pass_mark_pct,
        languages_offered=[x.value for x in body.languages_offered],
        prerequisite_codes=list(dict.fromkeys(body.prerequisite_codes)),
        delivered_by_roles=roles,
        active=body.active,
        created_by_user_id=p.user.id,
    )
    db.add(c)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.induction_course,
        entity_id=c.id,
        project_id=project.id,
        after=_course_snapshot(c),
    )
    return course_read(db, c)


def update_course(
    db: Session, p: Principal, course_id: uuid.UUID, body: InductionCourseUpdate
) -> InductionCourseRead:
    c = get_course(db, p, course_id)
    p.require(c.project_id, C.induction_course_manage)
    before = _course_snapshot(c)
    ch = body.changes()
    for k in ("languages_offered", "delivered_by_roles"):
        if k in ch:
            ch[k] = [getattr(x, "value", x) for x in ch[k]]
    for k, v in ch.items():
        setattr(c, k, v)
    _validate_course(
        db,
        c.project_id,
        c.code,
        c.induction_type,
        c.validity_months,
        c.validity_days,
        list(c.prerequisite_codes or []),
        list(c.delivered_by_roles or []),
    )
    c.updated_by_user_id = p.user.id
    c.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, _course_snapshot(c))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(c.project_id),
            entity_type=EntityType.induction_course,
            entity_id=c.id,
            project_id=c.project_id,
            before=bf,
            after=af,
        )
    return course_read(db, c)


def publish_version(
    db: Session, p: Principal, course_id: uuid.UUID, body: InductionCourseVersionPublish
) -> InductionCourseRead:
    """IN-9."""
    c = get_course(db, p, course_id)
    p.require(c.project_id, C.induction_course_manage)
    if _version_key(body.version) <= _version_key(c.version):
        raise validation_error("version", f"The new version must be later than {c.version}.")
    on = body.published_on or today()
    before = {"version": c.version, "requires_reinduction": c.requires_reinduction}
    c.version = body.version
    c.version_published_on = on
    c.requires_reinduction = body.requires_reinduction
    c.updated_by_user_id = p.user.id
    c.updated_at = now()
    affected = 0
    if body.requires_reinduction:
        s = common.settings(db, c.project_id)
        due = on + timedelta(days=s.reinduction_grace_days)
        engs: set[uuid.UUID] = set()
        for r in db.scalars(
            select(InductionRecord).where(
                InductionRecord.course_id == c.id,
                InductionRecord.status.in_([InductionStatus.valid, InductionStatus.suspended]),
                InductionRecord.course_version != body.version,
            )
        ):
            r.reinduction_due_on = due
            affected += 1
            if r.engagement_id:
                engs.add(r.engagement_id)
        users: set[uuid.UUID] = set(notify.users_with_role(db, Role.hse_officer, [c.project_id]))
        for e in engs:
            users.update(contractor_reps(db, c.project_id, e))
        if affected:
            notify.notify(
                db,
                users,
                NotificationKind.reinduction_due,
                f"Re-induction due: {c.code} v{c.version} by {due.isoformat()}",
                f"إعادة التعريف مطلوبة: {c.code} الإصدار {c.version} قبل {due.isoformat()}",
                f"{affected} valid records of older versions expire on {due.isoformat()} "
                "unless re-inducted.",
                f"{affected} سجلات سارية من إصدارات سابقة تنتهي في {due.isoformat()}.",
                EntityType.induction_course,
                c.id,
                c.project_id,
            )
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(c.project_id),
        entity_type=EntityType.induction_course,
        entity_id=c.id,
        project_id=c.project_id,
        before=before,
        after={
            "version": c.version,
            "requires_reinduction": c.requires_reinduction,
            "published_on": on.isoformat(),
        },
        details={"reinduction_records": affected},
    )
    return course_read(db, c)


# ---- records ------------------------------------------------------------------------------------


def _score(v: Decimal | None) -> str | None:
    return None if v is None else f"{v:.2f}"


def record_read(
    db: Session,
    p: Principal | None,
    r: InductionRecord,
    refs: Refs | None = None,
    warnings: list[ApiWarning] | None = None,
) -> InductionRecordRead:
    refs = refs or Refs(db)
    w = db.get(Worker, r.worker_id)
    c = db.get(InductionCourse, r.course_id)
    assert w is not None and c is not None  # noqa: S101
    vu = lifecycle.induction_valid_until(r)
    live = r.status in (InductionStatus.valid, InductionStatus.suspended)
    return InductionRecordRead(
        id=r.id,
        induction_no=r.induction_no,
        project_id=r.project_id,
        worker=common.worker_ref(w, common.can_see_names(p, r.project_id)),
        engagement=refs.eng(r.engagement_id),
        course_id=c.id,
        course_code=c.code,
        induction_type=r.induction_type,
        course_version=r.course_version,
        session_ref=r.session_ref,
        delivered_at=r.delivered_at,
        delivered_by=refs.user(r.delivered_by_user_id) or attachments.UNKNOWN,
        delivery_language=r.delivery_language,
        interpreter_used=r.interpreter_used,
        language_mismatch=r.language_mismatch,
        duration_minutes=r.duration_minutes,
        test_score_pct=_score(r.test_score_pct),
        attempt_no=r.attempt_no,
        result=r.result,
        privacy_notice_version=r.privacy_notice_version,
        signature_attachment_id=r.signature_attachment_id,
        valid_from=r.valid_from,
        valid_until=r.valid_until,
        reinduction_due_on=r.reinduction_due_on,
        days_left=common.days_left(vu) if live else None,
        helmet_sticker_no=r.helmet_sticker_no,
        status=r.status,
        warnings=warnings or [],
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def get_record(db: Session, p: Principal, induction_id: uuid.UUID) -> InductionRecord:
    r = db.get(InductionRecord, induction_id)
    if r is None:
        raise not_found("Induction record")
    projects.get_visible(db, p, r.project_id)
    d = db.get(Deployment, r.deployment_id)
    assert d is not None  # noqa: S101
    if workers.dep_covered(p, d, C.worker_view) is None:
        raise forbidden_error("This record is outside your scope.")
    return r


def read_record(db: Session, p: Principal, induction_id: uuid.UUID) -> InductionRecordRead:
    return record_read(db, p, get_record(db, p, induction_id))


def list_records(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    worker_id: uuid.UUID | None,
    course_ids: list[uuid.UUID] | None,
    induction_type: InductionType | None,
    statuses: list[InductionStatus] | None,
    engagement_ids: list[uuid.UUID] | None,
    include_subcontractors: bool,
    language_mismatch: bool | None,
    expiring_within_days: int | None,
    delivered_from: date | None,
    delivered_to: date | None,
    session_ref: str | None,
) -> InductionRecordPage:
    project = projects.get_visible(db, p, project_id)
    if p.grant(project.id, C.worker_view) is None:
        raise forbidden_error()
    stmt = (
        select(InductionRecord)
        .join(Deployment, Deployment.id == InductionRecord.deployment_id)
        .where(InductionRecord.project_id == project.id, workers.dep_clause(p, C.worker_view))
    )
    conds: list[ColumnElement[bool]] = []
    if worker_id:
        conds.append(InductionRecord.worker_id == worker_id)
    if course_ids:
        conds.append(InductionRecord.course_id.in_(course_ids))
    if induction_type:
        conds.append(InductionRecord.induction_type == induction_type)
    if statuses:
        conds.append(InductionRecord.status.in_(statuses))
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        conds.append(InductionRecord.engagement_id.in_(ids))
    if language_mismatch is not None:
        conds.append(InductionRecord.language_mismatch.is_(language_mismatch))
    if expiring_within_days is not None:
        day = today()
        conds += [
            InductionRecord.status.in_([InductionStatus.valid, InductionStatus.suspended]),
            InductionRecord.valid_until <= day + timedelta(days=expiring_within_days),
        ]
    if delivered_from:
        conds.append(InductionRecord.delivered_on >= delivered_from)
    if delivered_to:
        conds.append(InductionRecord.delivered_on <= delivered_to)
    if session_ref:
        conds.append(InductionRecord.session_ref == session_ref)
    stmt = stmt.where(*conds).order_by(
        InductionRecord.delivered_at.desc(), InductionRecord.seq.desc()
    )
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db).load(
        users=[r.delivered_by_user_id for r in rows], engs=[r.engagement_id for r in rows]
    )
    return InductionRecordPage(
        items=[record_read(db, p, r, refs) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _deliverer_roles(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> set[str]:
    return {ROLE_OF[r].value for r in user_roles(db, user_id, project_id) if r in ROLE_OF}


def _deliverer_error(msg: str) -> ApiError:
    return ApiError(
        403,
        ErrorCode.DELIVERER_NOT_ALLOWED,
        msg,
        "لا يسمح لهذا المستخدم بتقديم هذه الدورة.",
    )


def _signature(content_b64: str) -> bytes:
    raw = content_b64.split(",", 1)[1] if content_b64.startswith("data:") else content_b64
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise validation_error("signature_png_base64", "Not valid base64.") from exc
    if not data.startswith(b"\x89PNG"):
        raise validation_error("signature_png_base64", "The signature must be a PNG image.")
    return data


def _passed(course: InductionCourse, s_pass: int, score: Decimal | None) -> bool:
    if not course.test_required:
        return True
    assert score is not None  # noqa: S101
    return score >= Decimal(max(course.pass_mark_pct or 0, s_pass))


def _valid_prereq(
    db: Session, worker_id: uuid.UUID, project_id: uuid.UUID, code: str, on: date
) -> bool:
    for r in db.scalars(
        select(InductionRecord)
        .join(InductionCourse, InductionCourse.id == InductionRecord.course_id)
        .where(
            InductionRecord.worker_id == worker_id,
            InductionRecord.project_id == project_id,
            InductionCourse.code == code,
            InductionRecord.status == InductionStatus.valid,
        )
    ):
        vu = lifecycle.induction_valid_until(r)
        if r.valid_from and r.valid_from <= on and (vu is None or vu >= on):
            return True
    return False


def _attempts(
    db: Session, worker_id: uuid.UUID, course_id: uuid.UUID, project_id: uuid.UUID, at: datetime
) -> tuple[int, int, datetime | None]:
    """(records in the 30-day window, failed attempts since the last re-training note, last
    failed attempt time)."""
    since = at - timedelta(days=ATTEMPT_WINDOW_DAYS)
    base = (
        InductionRecord.worker_id == worker_id,
        InductionRecord.course_id == course_id,
        InductionRecord.project_id == project_id,
        InductionRecord.delivered_at > since,
        InductionRecord.delivered_at <= at,
    )
    n = db.scalar(select(func.count()).select_from(InductionRecord).where(*base)) or 0
    note_at = db.scalar(
        select(func.max(InductionRetrainingNote.recorded_at)).where(
            InductionRetrainingNote.worker_id == worker_id,
            InductionRetrainingNote.course_id == course_id,
        )
    )
    fstmt = select(InductionRecord.delivered_at).where(
        *base, InductionRecord.result == InductionResult.failed
    )
    if note_at is not None:
        fstmt = fstmt.where(InductionRecord.created_at > note_at)
    failed = sorted(db.scalars(fstmt))
    return int(n), len(failed), failed[-1] if failed else None


def _record(
    db: Session,
    p: Principal,
    course: InductionCourse,
    project: Project,
    a: InductionAttendee,
    delivered_at: datetime,
    deliverer_id: uuid.UUID,
    duration: int,
    session_ref: str | None,
    prefix: str,
) -> tuple[InductionRecord, list[ApiWarning]]:
    def err(field: str, msg: str) -> ApiError:
        return validation_error(f"{prefix}{field}", msg)

    s = common.settings(db, project.id)
    w = db.get(Worker, a.worker_id)
    if w is None:
        raise err("worker_id", "Unknown worker.")
    d = db.scalar(
        select(Deployment).where(
            Deployment.worker_id == w.id,
            Deployment.project_id == project.id,
            Deployment.status.in_([DeploymentStatus.pending_induction, DeploymentStatus.mobilised]),
        )
    )
    if d is None:
        raise err("worker_id", "The worker has no open deployment on this project.")
    common.require_cap(p, project.id, C.induction_record, d.site_ids, d.engagement_id)
    if w.user_id is not None and deliverer_id == w.user_id:
        raise _deliverer_error("A worker cannot deliver their own induction (IN-12).")
    if a.delivery_language.value not in (course.languages_offered or []):
        raise err("delivery_language", "The course is not offered in this language.")
    if duration < course.min_duration_minutes:
        raise ApiError(
            422,
            ErrorCode.INDUCTION_TOO_SHORT,
            f"{course.code} needs at least {course.min_duration_minutes} minutes (IN-7).",
            f"تتطلب الدورة {course.min_duration_minutes} دقيقة على الأقل.",
            errors=[field_error("duration_minutes", "Below the course minimum.")],
        )
    score: Decimal | None = None
    if course.test_required:
        if a.test_score_pct is None:
            raise err("test_score_pct", "A test score is required for this course.")
        score = Decimal(a.test_score_pct)
        if score > 100:
            raise err("test_score_pct", "Score must be between 0 and 100.")
    elif a.test_score_pct is not None:
        raise err("test_score_pct", "This course has no test.")
    on = common.local_day(delivered_at)
    for code in course.prerequisite_codes or []:
        if not _valid_prereq(db, w.id, project.id, code, on):
            raise ApiError(
                422,
                ErrorCode.INDUCTION_PREREQUISITE,
                f"{course.code} needs a valid {code} induction first (IN-4).",
                f"تتطلب الدورة {course.code} تعريفاً سارياً في {code} أولاً.",
                meta={"missing": code},
            )
    n, failed, last_failed = _attempts(db, w.id, course.id, project.id, delivered_at)
    if failed >= s.induction_max_attempts_30d:
        raise ApiError(
            422,
            ErrorCode.INDUCTION_ATTEMPTS_EXCEEDED,
            f"{failed} failed attempts in 30 days: an HSE Officer must record a re-training note "
            "first (IN-5).",
            "تم تجاوز عدد المحاولات المسموح به؛ يلزم تسجيل ملاحظة إعادة تدريب.",
        )
    wait = s.induction_retest_wait_hours
    if wait and last_failed is not None and delivered_at < last_failed + timedelta(hours=wait):
        raise ApiError(
            422,
            ErrorCode.INDUCTION_ATTEMPTS_EXCEEDED,
            f"A new attempt is allowed {wait} h after the last failed one.",
            f"يسمح بمحاولة جديدة بعد {wait} ساعة من آخر محاولة.",
        )
    if a.helmet_sticker_no and db.scalar(
        select(InductionRecord.id).where(
            InductionRecord.project_id == project.id,
            InductionRecord.helmet_sticker_no == a.helmet_sticker_no,
        )
    ):
        raise duplicate(f"{prefix}helmet_sticker_no", "This helmet sticker number is in use.")
    passed = _passed(course, s.induction_pass_mark_pct, score)
    mismatch = a.delivery_language.value != w.primary_language and not a.interpreter_used
    year = delivered_at.year
    seq = next_seq(db, InductionRecord, project.id, year)
    r = InductionRecord(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        induction_no=make_ref("IND", project.code, year, seq, 5),
        project_id=project.id,
        worker_id=w.id,
        deployment_id=d.id,
        engagement_id=d.engagement_id,
        course_id=course.id,
        induction_type=course.induction_type,
        course_version=course.version,
        session_ref=session_ref,
        delivered_at=delivered_at,
        delivered_on=on,
        delivered_by_user_id=deliverer_id,
        delivery_language=a.delivery_language,
        interpreter_used=a.interpreter_used,
        language_mismatch=mismatch,
        duration_minutes=duration,
        test_score_pct=score,
        attempt_no=n + 1,
        result=InductionResult.passed if passed else InductionResult.failed,
        privacy_notice_version=a.privacy_notice_version,
        valid_from=on if passed else None,
        valid_until=(
            common.validity_until(
                on,
                course.validity_months,
                course.validity_days if course.induction_type == InductionType.visitor else None,
            )
            if passed
            else None
        ),
        helmet_sticker_no=a.helmet_sticker_no,
        status=InductionStatus.valid if passed else InductionStatus.failed,
        status_changed_at=now(),
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    sig = attachments.store(
        db,
        AttachmentOwner.induction_signature,
        r.id,
        project.id,
        f"{r.induction_no}-signature.png",
        _signature(a.signature_png_base64),
        "image/png",
        p.user.id,
    )
    r.signature_attachment_id = sig.id
    if passed:
        # IN-8: supersede older live records of the same course
        for old in db.scalars(
            select(InductionRecord).where(
                InductionRecord.worker_id == w.id,
                InductionRecord.course_id == course.id,
                InductionRecord.project_id == project.id,
                InductionRecord.id != r.id,
                InductionRecord.status.in_([InductionStatus.valid, InductionStatus.suspended]),
            )
        ):
            old.status = InductionStatus.superseded
            old.status_changed_at = now()
            lifecycle.close_all(db, old, None, now())
        if course.induction_type == InductionType.general_site:
            workers.mobilise(db, d, on)
    warnings: list[ApiWarning] = []
    if mismatch:
        en, ar = reasons.GATE_TEXT[reasons.G.LANGUAGE_MISMATCH]
        warnings.append(
            ApiWarning(
                code="LANGUAGE_MISMATCH", message=en, message_ar=ar, field="delivery_language"
            )
        )
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.induction_record,
        entity_id=r.id,
        project_id=project.id,
        after={
            "induction_no": r.induction_no,
            "worker_no": w.worker_no,
            "course": course.code,
            "result": r.result.value,
            "valid_until": r.valid_until.isoformat() if r.valid_until else None,
        },
    )
    return r, warnings


def _prepare(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    course_id: uuid.UUID,
    delivered_at: datetime,
    deliverer: uuid.UUID | None,
) -> tuple[InductionCourse, Project, uuid.UUID]:
    p.ensure_writer()
    projects.get_visible(db, p, project_id)
    course = db.get(InductionCourse, course_id)
    if course is None or course.project_id != project_id:
        raise validation_error("course_id", "Unknown course.")
    project = projects.get_visible(db, p, course.project_id)
    if p.grant(project.id, C.induction_record) is None:
        p.require(project.id, C.induction_record)
    if not course.active:
        raise validation_error("course_id", "The course is inactive.")
    if delivered_at > now():
        raise validation_error("delivered_at", "delivered_at cannot be in the future (IN-12).")
    allowed = set(course.delivered_by_roles or [])
    caller_roles = (
        {InductionDelivererRole.hse_manager.value}
        if p.is_manager
        else _deliverer_roles(db, p.user.id, project.id)
    )
    if not caller_roles & allowed:
        raise _deliverer_error(
            f"{course.code} can be recorded only by: {', '.join(sorted(allowed))} (IN-3)."
        )
    deliverer_id = deliverer or p.user.id
    if deliverer_id != p.user.id and not _deliverer_roles(db, deliverer_id, project.id) & allowed:
        raise _deliverer_error("The deliverer's role is not allowed for this course.")
    return course, project, deliverer_id


def create_record(
    db: Session, p: Principal, project_id: uuid.UUID, body: InductionRecordCreate
) -> InductionRecordRead:
    course, project, deliverer = _prepare(
        db, p, project_id, body.course_id, body.delivered_at, body.delivered_by_user_id
    )
    r, warns = _record(
        db,
        p,
        course,
        project,
        body,
        body.delivered_at,
        deliverer,
        body.duration_minutes,
        body.session_ref,
        "",
    )
    return record_read(db, p, r, warnings=warns)


def create_session(
    db: Session, p: Principal, project_id: uuid.UUID, body: InductionSessionCreate
) -> InductionSessionResult:
    course, project, deliverer = _prepare(
        db, p, project_id, body.course_id, body.delivered_at, body.delivered_by_user_id
    )
    ids = [a.worker_id for a in body.attendees]
    if len(set(ids)) != len(ids):
        raise validation_error("attendees", "A worker is listed twice.")
    out: list[InductionRecordRead] = []
    errors = []
    sp = db.begin_nested()
    for i, a in enumerate(body.attendees):
        try:
            r, warns = _record(
                db,
                p,
                course,
                project,
                a,
                body.delivered_at,
                deliverer,
                body.duration_minutes,
                body.session_ref,
                f"attendees.{i}.",
            )
            out.append(record_read(db, p, r, warnings=warns))
        except ApiError as e:
            if e.status_code == 403:
                sp.rollback()
                raise
            for fe in e.errors or []:
                errors.append(fe)
            if not e.errors:
                errors.append(field_error(f"attendees.{i}", f"{e.code.value}: {e.message}"))
    if errors:
        sp.rollback()
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "The session was not saved: fix the listed attendees.",
            "لم يتم حفظ الجلسة: يرجى تصحيح بيانات الحضور المذكورين.",
            errors=errors,
        )
    sp.commit()
    return InductionSessionResult(items=out)


def _rec_snapshot(r: InductionRecord) -> dict[str, Any]:
    return {
        "delivery_language": r.delivery_language,
        "interpreter_used": r.interpreter_used,
        "language_mismatch": r.language_mismatch,
        "helmet_sticker_no": r.helmet_sticker_no,
        "session_ref": r.session_ref,
    }


def update_record(
    db: Session, p: Principal, induction_id: uuid.UUID, body: InductionRecordUpdate
) -> InductionRecordRead:
    """IN-11: within 24 h by capability 51; afterwards HSE Manager only, with a reason."""
    r = get_record(db, p, induction_id)
    d = db.get(Deployment, r.deployment_id)
    assert d is not None  # noqa: S101
    common.require_cap(p, r.project_id, C.induction_record, d.site_ids, d.engagement_id)
    ch = body.changes()
    reason = ch.pop("edit_reason", None)
    if now() - r.created_at > timedelta(hours=EDIT_LOCK_HOURS) and not (p.is_manager and reason):
        raise ApiError(
            422,
            ErrorCode.INDUCTION_EDIT_LOCKED,
            "Records older than 24 h can be corrected only by the HSE Manager with a reason.",
            "لا يمكن تعديل السجل بعد 24 ساعة إلا من مدير السلامة مع ذكر السبب.",
        )
    before = _rec_snapshot(r)
    if ch.get("helmet_sticker_no"):
        other = db.scalar(
            select(InductionRecord.id).where(
                InductionRecord.project_id == r.project_id,
                InductionRecord.helmet_sticker_no == ch["helmet_sticker_no"],
                InductionRecord.id != r.id,
            )
        )
        if other:
            raise duplicate("helmet_sticker_no", "This helmet sticker number is in use.")
    for k, v in ch.items():
        setattr(r, k, v)
    if "delivery_language" in ch or "interpreter_used" in ch:
        c = db.get(InductionCourse, r.course_id)
        if c and r.delivery_language.value not in (c.languages_offered or []):
            raise validation_error(
                "delivery_language", "The course is not offered in this language."
            )
        w = db.get(Worker, r.worker_id)
        r.language_mismatch = bool(
            w and r.delivery_language.value != w.primary_language and not r.interpreter_used
        )
    r.updated_by_user_id = p.user.id
    r.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, _rec_snapshot(r))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(r.project_id),
            entity_type=EntityType.induction_record,
            entity_id=r.id,
            project_id=r.project_id,
            before=bf,
            after=af,
            details={"reason": reason} if reason else None,
        )
    return record_read(db, p, r)


def retraining_note(
    db: Session, p: Principal, project_id: uuid.UUID, body: RetrainingNoteIn
) -> InductionRetrainingNoteRead:
    """IN-5: an HSE Officer (or the HSE Manager) unlocks further attempts."""
    project = projects.get_visible(db, p, project_id)
    p.ensure_writer()
    if not p.is_manager and Role.hse_officer not in user_roles(db, p.user.id, project.id):
        raise forbidden_error("Only an HSE Officer can record a re-training note.")
    course = db.get(InductionCourse, body.course_id)
    if course is None or course.project_id != project.id:
        raise validation_error("course_id", "Unknown course.")
    w = db.get(Worker, body.worker_id)
    if w is None:
        raise validation_error("worker_id", "Unknown worker.")
    n = InductionRetrainingNote(
        id=uuid.uuid4(),
        project_id=project.id,
        worker_id=w.id,
        course_id=course.id,
        note=body.note,
        recorded_by_user_id=p.user.id,
        recorded_at=now(),
    )
    db.add(n)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.induction_record,
        entity_id=n.id,
        project_id=project.id,
        details={"retraining_note": True, "worker_no": w.worker_no, "course": course.code},
    )
    return InductionRetrainingNoteRead(
        id=n.id,
        worker_id=w.id,
        course_id=course.id,
        note=n.note,
        recorded_by=Refs(db).user(p.user.id) or attachments.UNKNOWN,
        recorded_at=n.recorded_at,
    )


# ---- jobs ---------------------------------------------------------------------------------------


def expire_records(db: Session, day: date | None = None) -> int:
    """§4.3 Valid/Suspended → Expired when today > valid_until or on reinduction_due_on (IN-9).
    Idempotent."""
    day = day or today()
    n = 0
    for r in db.scalars(
        select(InductionRecord).where(
            InductionRecord.status.in_([InductionStatus.valid, InductionStatus.suspended])
        )
    ):
        vu = lifecycle.induction_valid_until(r)
        if vu is not None and day > vu:
            r.status = InductionStatus.expired
            r.status_changed_at = now()
            lifecycle.close_all(db, r, None, now())
            n += 1
    db.flush()
    return n


# ---- eligibility and hook providers ------------------------------------------------------------


def worker_eligibility(
    db: Session,
    p: Principal,
    worker_id: uuid.UUID,
    zone_id: uuid.UUID,
    at: datetime | None,
    context: EligibilityContext,
) -> EligibilityResult:
    w = workers.get_worker(db, p, worker_id)
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise not_found("Zone")
    projects.get_visible(db, p, zone.project_id)
    if p.grant(zone.project_id, C.worker_view) is None:
        raise forbidden_error()
    ev = eligibility.evaluate(db, w, zone, at or now(), context)
    return eligibility.to_result(db, ev, True)


def hook_providers(db: Session, p: Principal, project_id: uuid.UUID) -> list[HookProviderInfo]:
    project = projects.get_visible(db, p, project_id)
    s = common.settings(db, project.id)
    return [
        HookProviderInfo(
            kind=k,
            registered=hooks.is_registered(k),
            policy=HookPolicy((s.hook_policy or {}).get(k.value, HookPolicy.warn.value)),
            available_from_phase=hooks.AVAILABLE_FROM_PHASE[k],
        )
        for k in HookKind
    ]


__all__ = ["profiles"]
