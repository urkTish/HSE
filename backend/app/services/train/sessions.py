"""Training sessions, nominations, attendance, assessment, close and void (spec 5-training §3.6,
§3.7, §4.4, §4.5, §6.3, SS-1…SS-10, AT-1…AT-7, TA-2…TA-6, TR-14)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import WorkerLanguage, WorkerStatus
from app.core.clock import now, today
from app.core.enums import AuditAction, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.train_enums import (
    AttendanceResult,
    CourseCategory,
    DeliveryMode,
    NominationStatus,
    PracticalResult,
    SessionAction,
    SessionStatus,
    TrainerRole,
    TrainingProviderKind,
    TrainingRecordStatus,
    TrainingStatusReason,
    UnderstoodLanguage,
)
from app.models import (
    Deployment,
    Site,
    TrainingCourse,
    TrainingNomination,
    TrainingProvider,
    TrainingRecord,
    TrainingRetrainingNote,
    TrainingSession,
    User,
    Worker,
    Zone,
)
from app.schemas.hse_common import ApiWarning
from app.schemas.training_sessions import (
    AssessmentUpdate,
    AttendanceSignature,
    AttendanceUpdate,
    NominationCreate,
    NominationList,
    NominationRead,
    NominationWithdraw,
    SessionClose,
    SessionCounts,
    SessionCreate,
    SessionDayRead,
    SessionFields,
    SessionFromPlan,
    SessionListItem,
    SessionLocationRead,
    SessionPage,
    SessionRead,
    SessionTrainerRead,
    SessionTransitionRequest,
    SessionUpdate,
    SessionVoid,
    SessionVoidRead,
)
from app.services.access import common as acommon
from app.services.cert import alerts
from app.services.cert import common as cc
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error
from app.services.train import common, recordops
from app.services.train import hook as thook
from app.services.train import providers as tprov
from app.services.train import trainers as ttrain
from app.services.train import validity as tval

C = common.C
SS = SessionStatus
NS = NominationStatus
AR = AttendanceResult
LIVE_SESSION = (SS.draft, SS.scheduled, SS.in_progress, SS.delivered)


def _err(code: ErrorCode, en: str, ar: str, status: int = 422, **meta: Any) -> ApiError:
    return ApiError(status, code, en, ar, meta=meta or None)


def _warn(code: str, en: str, ar: str, field: str | None = None) -> ApiWarning:
    return ApiWarning(code=code, message=en, message_ar=ar, field=field)


# ---- day maths (§6.3) ---------------------------------------------------------------------------


def _t(x: Any) -> time:
    return x if isinstance(x, time) else time.fromisoformat(str(x))


def net(day: dict[str, Any]) -> int:
    s, e = _t(day["start_time"]), _t(day["end_time"])
    return (e.hour * 60 + e.minute) - (s.hour * 60 + s.minute) - int(day["break_minutes"])


def day_dates(s: TrainingSession) -> list[date]:
    return [date.fromisoformat(x["date"]) for x in s.days]


def _norm_days(days: Iterable[Any]) -> list[dict[str, Any]]:
    out = []
    for x in days:
        d = x if isinstance(x, dict) else x.model_dump()
        out.append(
            {
                "date": (d["date"] if isinstance(d["date"], str) else d["date"].isoformat()),
                "start_time": _t(d["start_time"]).strftime("%H:%M"),
                "end_time": _t(d["end_time"]).strftime("%H:%M"),
                "break_minutes": int(d["break_minutes"]),
            }
        )
    out.sort(key=lambda x: x["date"])
    return out


def _check_days(c: TrainingCourse, days: list[dict[str, Any]], max_net: Decimal) -> int:
    seen = set()
    total = 0
    for i, d in enumerate(days):
        if d["date"] in seen:
            raise validation_error(f"days.{i}.date", "Each day may appear once.")
        seen.add(d["date"])
        if _t(d["end_time"]) <= _t(d["start_time"]):
            raise validation_error(f"days.{i}.end_time", "End must be after start.")
        m = net(d)
        if m <= 0:
            raise validation_error(f"days.{i}.break_minutes", "The break is longer than the day.")
        if m > int(max_net * 60):
            raise _err(
                ErrorCode.SESSION_DAY_TOO_LONG,
                f"A session day may have at most {int(max_net * 60)} net minutes ({m}).",
                f"لا يتجاوز اليوم التدريبي {int(max_net * 60)} دقيقة صافية.",
                net_minutes=m,
                max_minutes=int(max_net * 60),
            )
        total += m
    need = int((c.min_duration_hours or Decimal(0)) * 60)
    if total < need:
        raise _err(
            ErrorCode.SESSION_TOO_SHORT,
            f"The session has {total} net minutes; the course needs {need}.",
            f"مدة الجلسة {total} دقيقة صافية؛ تتطلب الدورة {need}.",
            net_minutes=total,
            min_minutes=need,
        )
    return total


# ---- loading and refs ---------------------------------------------------------------------------


def get(db: Session, session_id: uuid.UUID) -> TrainingSession:
    s = db.get(TrainingSession, session_id)
    if s is None:
        raise not_found("Training session")
    return s


def nominations(db: Session, s: TrainingSession, live: bool = False) -> list[TrainingNomination]:
    q = select(TrainingNomination).where(TrainingNomination.session_id == s.id)
    rows = list(db.scalars(q.order_by(TrainingNomination.nominated_at, TrainingNomination.id)))
    if live:
        rows = [n for n in rows if n.status != NS.withdrawn]
    return rows


def trainer_user_ids(
    db: Session, s: TrainingSession, role: TrainerRole | None = None
) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for t in s.trainers or []:
        if role is not None and role.value not in (t.get("roles") or []):
            continue
        if t.get("user_id"):
            out.add(uuid.UUID(t["user_id"]))
        elif t.get("worker_id"):
            w = db.get(Worker, uuid.UUID(t["worker_id"]))
            if w is not None and w.user_id is not None:
                out.add(w.user_id)
    return out


def trainer_worker_ids(db: Session, s: TrainingSession) -> set[uuid.UUID]:
    out = {uuid.UUID(t["worker_id"]) for t in s.trainers or [] if t.get("worker_id")}
    for t in s.trainers or []:
        if t.get("user_id"):
            w = db.scalar(select(Worker).where(Worker.user_id == uuid.UUID(t["user_id"])))
            if w is not None:
                out.add(w.id)
    return out


def _close_due(db: Session, s: TrainingSession) -> date | None:
    if s.status not in (SS.delivered, SS.in_progress, SS.scheduled):
        return None
    st = common.settings(db, s.project_id)
    return s.last_day + timedelta(days=st.session_close_deadline_days)


def _close_overdue(db: Session, s: TrainingSession) -> bool:
    due = _close_due(db, s)
    return s.status == SS.delivered and due is not None and today() > due


def counts(rows: list[TrainingNomination]) -> SessionCounts:
    def n(f: Any) -> int:
        return sum(1 for x in rows if f(x))

    return SessionCounts(
        nominated=n(lambda x: x.status != NS.withdrawn),
        attended=n(lambda x: x.status == NS.attended),
        partial=n(lambda x: x.status == NS.partial),
        absent=n(lambda x: x.status == NS.absent),
        withdrawn=n(lambda x: x.status == NS.withdrawn),
        passed=n(lambda x: x.result == AR.passed),
        failed=n(lambda x: x.result == AR.failed),
        incomplete=n(lambda x: x.result == AR.incomplete),
        pending=n(lambda x: x.result == AR.pending and x.status != NS.withdrawn),
    )


def _allowed(db: Session, p: Principal, s: TrainingSession) -> list[str]:
    out = []
    g = p.grant(s.project_id, C.training_session_manage)
    hse = common.is_hse(p, s.project_id)
    if g is not None:
        if s.status == SS.draft:
            out += ["schedule", "cancel", "edit"]
            if hse:
                out.append("record_delivered")
        elif s.status == SS.scheduled:
            out += ["cancel"]
            if today() < s.first_day:
                out.append("edit")
    if s.status in (SS.draft, SS.scheduled) and p.grant(s.project_id, C.training_nominate):
        out.append("nominate")
    if s.status == SS.delivered and p.grant(s.project_id, C.training_session_close):
        out.append("close")
    if s.status == SS.closed and p.is_manager:
        out.append("void")
    return out


def blockers(db: Session, s: TrainingSession) -> list[ApiWarning]:
    """Current SS-1 / TA-2 problems of a live session (e.g. after a suspension)."""
    if s.status not in (SS.draft, SS.scheduled, SS.in_progress):
        return []
    out: list[ApiWarning] = []
    c = common.course(db, s.course_code)
    pv = db.get(TrainingProvider, s.provider_id)
    if c is None or pv is None:
        return out
    days = day_dates(s)
    for d in days:
        a = tprov.acceptable(
            db, pv, c, d, s.project_id, [n.worker_id for n in nominations(db, s, True)]
        )
        if not a.ok and a.reason is not None:
            en, ar = tprov.UNACCEPTABLE_TEXT[a.reason]
            out.append(_warn(ErrorCode.PROVIDER_NOT_ACCEPTABLE.value, f"{en} ({d})", ar))
            break
    if common.is_internalish(pv):
        for t in s.trainers or []:
            uid = uuid.UUID(t["user_id"]) if t.get("user_id") else None
            wid = uuid.UUID(t["worker_id"]) if t.get("worker_id") else None
            for role in t.get("roles") or []:
                if (
                    ttrain.authorisation_for(
                        db, s.project_id, pv.id, c.code, TrainerRole(role), uid, wid, days
                    )
                    is None
                ):
                    out.append(
                        _warn(
                            ErrorCode.TRAINER_NOT_AUTHORISED.value,
                            "A trainer is no longer authorised for this session.",
                            "لم يعد أحد المدربين مفوضاً لهذه الجلسة.",
                        )
                    )
                    return out
    return out


def read(db: Session, p: Principal, s: TrainingSession) -> SessionRead:
    refs = Refs(db)
    c = common.course_or_404(db, s.course_code)
    pv = common.provider_or_404(db, s.provider_id)
    show = common.names(p, s.project_id)
    trs = []
    for t in s.trainers or []:
        w = db.get(Worker, uuid.UUID(t["worker_id"])) if t.get("worker_id") else None
        auth_no = None
        if t.get("authorisation_id"):
            from app.models import TrainerAuthorisation  # noqa: PLC0415

            a = db.get(TrainerAuthorisation, uuid.UUID(t["authorisation_id"]))
            auth_no = a.authorisation_no if a else None
        trs.append(
            SessionTrainerRead(
                user=refs.user(uuid.UUID(t["user_id"])) if t.get("user_id") else None,
                worker=common.worker_ref(w, show) if w else None,
                external_name=t.get("external_name"),
                roles=[TrainerRole(r) for r in t.get("roles") or []],
                authorisation_no=auth_no,
            )
        )
    days = [
        SessionDayRead(
            day_no=i + 1,
            date=date.fromisoformat(x["date"]),
            start_time=_t(x["start_time"]),
            end_time=_t(x["end_time"]),
            break_minutes=int(x["break_minutes"]),
            net_minutes=net(x),
        )
        for i, x in enumerate(s.days)
    ]
    void = None
    if s.voided_at is not None and s.void_reason_code is not None:
        by = refs.user(s.voided_by_user_id)
        assert by is not None  # noqa: S101
        void = SessionVoidRead(
            reason_code=s.void_reason_code,
            reason_text=s.void_reason_text if common.is_hse(p, s.project_id) else None,
            by=by,
            at=s.voided_at,
        )
    creator = refs.user(s.created_by_user_id) or cc.UNKNOWN_USER
    return SessionRead(
        id=s.id,
        session_no=s.session_no,
        project_id=s.project_id,
        course=common.course_ref(c),
        provider=common.provider_ref(pv, p, s.project_id),
        delivery_mode=s.delivery_mode,
        trainers=trs,
        location=SessionLocationRead(
            site=refs.site(s.site_id) if s.site_id else None,
            zone=refs.zone(s.zone_id),
            offsite_text=s.offsite_text,
        ),
        language=s.language,
        interpreter_languages=[WorkerLanguage(x) for x in s.interpreter_languages or []],
        days=days,
        net_minutes_total=s.net_minutes_total,
        capacity=s.capacity,
        status=s.status,
        status_reason=s.status_reason,
        close_due_on=_close_due(db, s),
        close_overdue=_close_overdue(db, s),
        attendance_sheet_attachment_id=s.attendance_sheet_attachment_id,
        closed_by=refs.user(s.closed_by_user_id),
        closed_at=s.closed_at,
        void=void,
        counts=counts(nominations(db, s)),
        blockers=blockers(db, s),
        allowed_actions=_allowed(db, p, s),
        created_by=creator,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def list_sessions(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: list[SessionStatus] | None,
    course_code: str | None,
    provider_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
    close_overdue: bool | None,
    trainer_user_id: uuid.UUID | None,
) -> SessionPage:
    common.visible_project(db, p, project_id)
    if p.grant(project_id, C.training_catalogue_view) is None:
        raise forbidden_error()
    stmt = (
        select(TrainingSession)
        .where(TrainingSession.project_id == project_id)
        .order_by(TrainingSession.first_day.desc(), TrainingSession.session_no.desc())
    )
    if status:
        stmt = stmt.where(TrainingSession.status.in_(status))
    if course_code:
        stmt = stmt.where(TrainingSession.course_code == course_code)
    if provider_id:
        stmt = stmt.where(TrainingSession.provider_id == provider_id)
    if date_from:
        stmt = stmt.where(TrainingSession.last_day >= date_from)
    if date_to:
        stmt = stmt.where(TrainingSession.first_day <= date_to)
    if trainer_user_id:
        stmt = stmt.where(TrainingSession.trainer_user_ids.any(trainer_user_id))  # type: ignore[arg-type]
    if close_overdue is not None:
        st = common.settings(db, project_id)
        lim = today() - timedelta(days=st.session_close_deadline_days)
        cond = (TrainingSession.status == SS.delivered) & (TrainingSession.last_day < lim)
        stmt = stmt.where(cond if close_overdue else ~cond)
    rows, total = paginate(db, stmt, page, page_size)
    items = []
    for s in rows:
        c = common.course_or_404(db, s.course_code)
        pv = common.provider_or_404(db, s.provider_id)
        site = db.get(Site, s.site_id) if s.site_id else None
        n = db.scalar(
            select(func.count())
            .select_from(TrainingNomination)
            .where(TrainingNomination.session_id == s.id, TrainingNomination.status != NS.withdrawn)
        )
        items.append(
            SessionListItem(
                id=s.id,
                session_no=s.session_no,
                course=common.course_ref(c),
                provider_code=pv.provider_code,
                language=s.language,
                first_day=s.first_day,
                last_day=s.last_day,
                site_code=site.code if site else None,
                status=s.status,
                capacity=s.capacity,
                nominated=int(n or 0),
                close_overdue=_close_overdue(db, s),
            )
        )
    return SessionPage(items=items, total=total, page=page, page_size=page_size)


def get_session(db: Session, p: Principal, session_id: uuid.UUID) -> SessionRead:
    s = get(db, session_id)
    if (
        not p.can_see_project(s.project_id)
        or p.grant(s.project_id, C.training_catalogue_view) is None
    ):
        raise not_found("Training session")
    advance(db, s)
    return read(db, p, s)


# ---- validation (SS-1…SS-4, TA-2…TA-6, CC-5) ----------------------------------------------------


def _course_for_session(db: Session, code: str) -> TrainingCourse:
    c = common.course(db, code)
    if c is None:
        raise validation_error("course_code", "Unknown course.")
    if c.category == CourseCategory.induction_link:
        raise _err(
            ErrorCode.INDUCTION_OWNED_BY_PHASE2,
            "Inductions are delivered and recorded in Phase 2 (access).",
            "التعريفات تُقدَّم وتُسجَّل في المرحلة 2 (الدخول).",
        )
    if not c.active:
        raise _err(ErrorCode.COURSE_INACTIVE, "The course is inactive.", "الدورة غير فعالة.")
    return c


def _is_rep(p: Principal, project_id: uuid.UUID) -> bool:
    return common.contractor_only(p, project_id)


def _validate(
    db: Session,
    p: Principal,
    s: TrainingSession,
    c: TrainingCourse,
    worker_ids: list[uuid.UUID],
) -> None:
    st = common.settings(db, s.project_id)
    pv = common.provider_or_404(db, s.provider_id)
    if s.delivery_mode.value not in (c.delivery_modes or []):
        if c.practical_required and s.delivery_mode == DeliveryMode.e_learning:
            raise _err(
                ErrorCode.PRACTICAL_REQUIRED,
                "This course has a practical assessment: e-learning alone is not allowed.",
                "لهذه الدورة تقييم عملي: لا يُسمح بالتعلم الإلكتروني وحده.",
            )
        raise validation_error("delivery_mode", "Not a delivery mode of this course.")
    if s.language.value not in (c.languages_offered or []):
        raise validation_error("language", "The course is not offered in this language.")
    if c.max_class_size is not None and s.capacity > c.max_class_size:
        raise validation_error("capacity", f"At most {c.max_class_size} (course class size).")
    if len(s.days) > 15:
        raise validation_error("days", "At most 15 days.")
    s.net_minutes_total = _check_days(c, s.days, st.session_day_max_net_hours)
    # location
    if s.site_id is None and not s.offsite_text:
        raise validation_error("location", "Give a site (and zone) or an off-site location.")
    if s.site_id is not None:
        site = db.get(Site, s.site_id)
        if site is None or site.project_id != s.project_id:
            raise validation_error("location.site_id", "Not a site of this project.")
        if s.zone_id is not None:
            z = db.get(Zone, s.zone_id)
            if z is None or z.site_id != site.id:
                raise validation_error("location.zone_id", "Not a zone of this site.")
    elif s.zone_id is not None:
        raise validation_error("location.zone_id", "A zone needs its site.")
    # TA-6: Contractor HSE Rep sessions only under their own contractor_internal provider
    if _is_rep(p, s.project_id):
        own = p.user.employer_contractor_id
        if pv.kind != TrainingProviderKind.contractor_internal or pv.contractor_id != own:
            raise forbidden_error(
                "Contractor HSE Reps schedule sessions of their own training unit."
            )
    days = day_dates(s)
    tprov.require_acceptable(db, pv, c, days, s.project_id, worker_ids)
    # trainers
    if not s.trainers:
        raise validation_error("trainers", "Name at least one trainer.")
    if not any("trainer" in (t.get("roles") or []) for t in s.trainers):
        raise validation_error("trainers", "Name at least one trainer (role trainer).")
    if c.practical_required and not any("assessor" in (t.get("roles") or []) for t in s.trainers):
        raise _err(
            ErrorCode.ASSESSOR_REQUIRED,
            "A course with a practical assessment needs an assessor.",
            "تتطلب الدورة ذات التقييم العملي مقيِّماً.",
        )
    internal = common.is_internalish(pv)
    for i, t in enumerate(s.trainers):
        uid = uuid.UUID(t["user_id"]) if t.get("user_id") else None
        wid = uuid.UUID(t["worker_id"]) if t.get("worker_id") else None
        ext = t.get("external_name")
        if sum(x is not None and x != "" for x in (uid, wid, ext)) != 1:
            raise validation_error(f"trainers.{i}", "Exactly one of user, worker or name.")
        if not internal:
            if not ext:
                raise validation_error(
                    f"trainers.{i}.external_name", "External trainers are named as printed."
                )
            continue
        if ext:
            raise _err(
                ErrorCode.TRAINER_NOT_AUTHORISED,
                "Internal sessions need authorised trainers (platform users or workers).",
                "تتطلب الجلسات الداخلية مدربين مفوضين.",
            )
        if uid is not None and db.get(User, uid) is None:
            raise validation_error(f"trainers.{i}.user_id", "Unknown user.")
        if wid is not None and db.get(Worker, wid) is None:
            raise validation_error(f"trainers.{i}.worker_id", "Unknown worker.")
        auth_id = None
        for role in t.get("roles") or []:
            a = ttrain.authorisation_for(
                db, s.project_id, pv.id, c.code, TrainerRole(role), uid, wid, days
            )
            if a is None:
                raise _err(
                    ErrorCode.TRAINER_NOT_AUTHORISED,
                    f"The trainer holds no active authorisation for {c.code} ({role}) on every "
                    "session day.",
                    f"لا يملك المدرب تفويضاً سارياً للدورة {c.code} في كل أيام الجلسة.",
                    trainer_index=i,
                    role=role,
                )
            auth_id = auth_id or str(a.id)
        t["authorisation_id"] = auth_id
        if "trainer" in (t.get("roles") or []) and not ttrain.trained(
            db, s.project_id, c, uid, wid, days
        ):
            raise _err(
                ErrorCode.TRAINER_NOT_TRAINED,
                f"The trainer has no in-force {c.code} record on every session day.",
                f"لا يملك المدرب سجلاً سارياً للدورة {c.code} في كل أيام الجلسة.",
                trainer_index=i,
            )
    tw = trainer_worker_ids(db, s)
    if set(worker_ids) & tw:
        raise common.sod("A trainer or assessor cannot attend the same session.")


def _apply_fields(s: TrainingSession, data: dict[str, Any]) -> None:
    for k, v in data.items():
        if k == "trainers":
            s.trainers = [
                {
                    "user_id": str(t["user_id"]) if t.get("user_id") else None,
                    "worker_id": str(t["worker_id"]) if t.get("worker_id") else None,
                    "external_name": t.get("external_name"),
                    "roles": [getattr(r, "value", r) for r in t["roles"]],
                    "authorisation_id": None,
                }
                for t in v
            ]
            s.trainer_user_ids = [uuid.UUID(t["user_id"]) for t in s.trainers if t["user_id"]]
            s.trainer_worker_ids = [uuid.UUID(t["worker_id"]) for t in s.trainers if t["worker_id"]]
        elif k == "location":
            s.site_id = v.get("site_id")
            s.zone_id = v.get("zone_id")
            s.offsite_text = v.get("offsite_text")
        elif k == "days":
            s.days = _norm_days(v)
            s.first_day = date.fromisoformat(s.days[0]["date"])
            s.last_day = date.fromisoformat(s.days[-1]["date"])
            s.starts_at = acommon.at_local(s.first_day, _t(s.days[0]["start_time"]))
            s.ends_at = acommon.at_local(s.last_day, _t(s.days[-1]["end_time"]))
            s.net_minutes_total = sum(net(x) for x in s.days)
        elif k == "interpreter_languages":
            s.interpreter_languages = [getattr(x, "value", x) for x in v or []]
        elif k in ("language", "delivery_mode", "provider_id", "capacity"):
            setattr(s, k, v)


def _next_seq(db: Session, project_id: uuid.UUID, year: int) -> int:
    db.execute(select(func.pg_advisory_xact_lock(5_000_004)))
    top = db.scalar(
        select(func.coalesce(func.max(TrainingSession.seq), 0)).where(
            TrainingSession.project_id == project_id, TrainingSession.year == year
        )
    )
    return int(top or 0) + 1


def _manage(p: Principal, project_id: uuid.UUID) -> None:
    p.require(project_id, C.training_session_manage)


def _create(
    db: Session, p: Principal, project_id: uuid.UUID, code: str, body: SessionFields
) -> TrainingSession:
    proj = common.visible_project(db, p, project_id)
    _manage(p, project_id)
    c = _course_for_session(db, code)
    s = TrainingSession(
        id=uuid.uuid4(),
        project_id=project_id,
        course_code=c.code,
        status=SS.draft,
        alerts_sent=[],
        interpreter_languages=[],
    )
    _apply_fields(s, body.model_dump())
    _validate(db, p, s, c, [])
    s.year = s.first_day.year
    s.seq = _next_seq(db, project_id, s.year)
    s.session_no = f"TRS-{proj.code}-{s.year}-{s.seq:05d}"
    cc.stamp(s, p, create=True)
    db.add(s)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.training_session, s, project_id)
    return s


def create_session(
    db: Session, p: Principal, project_id: uuid.UUID, body: SessionCreate
) -> SessionRead:
    s = _create(db, p, project_id, body.course_code, body)
    return read(db, p, s)


def create_from_plan(
    db: Session, p: Principal, project_id: uuid.UUID, body: SessionFromPlan
) -> SessionRead:
    """GP-4: Draft with plan nominees (not_booked items of the course and language)."""
    from app.services.train import gaps  # noqa: PLC0415

    s = _create(db, p, project_id, body.course_code, body.session)
    c = common.course_or_404(db, body.course_code)
    wanted = {body.course_code}
    for x in common.courses(db).values():
        if x.renewal_course_code == body.course_code or body.course_code in (x.satisfies or []):
            wanted.add(x.code)
    cap = min(s.capacity, c.max_class_size or s.capacity)
    picked: list[uuid.UUID] = []
    for r, _df, _why in sorted(
        gaps.plan_items(db, project_id, today()),
        key=lambda x: x[0].valid_until or date.max,
    ):
        if r.record is None or r.booked is not None:
            continue
        if body.record_ids and r.record.id not in body.record_ids:
            continue
        if not body.record_ids and r.record.course_code not in wanted:
            continue
        w = db.get(Worker, r.dep.worker_id)
        if w is None or (body.language is not None and w.primary_language != body.language):
            continue
        if w.id in picked:
            continue
        if _nominee_errors(db, p, s, c, w, len(picked), check_capacity=False):
            continue
        picked.append(w.id)
        if len(picked) >= cap:
            break
    for wid in picked:
        _add_nomination(db, p, s, c, wid)
    db.flush()
    return read(db, p, s)


def update_session(
    db: Session, p: Principal, session_id: uuid.UUID, body: SessionUpdate
) -> SessionRead:
    s = get(db, session_id)
    _manage(p, s.project_id)
    if s.status not in (SS.draft, SS.scheduled) or (
        s.status == SS.scheduled and today() >= s.first_day
    ):
        raise _err(
            ErrorCode.SESSION_NOT_EDITABLE,
            "The session can no longer be edited.",
            "لم يعد من الممكن تعديل الجلسة.",
            status=409,
        )
    c = common.course_or_404(db, s.course_code)
    before = cc.snap(s)
    data = body.model_dump(exclude_unset=True)
    if s.status == SS.scheduled and set(data) - {"days", "trainers", "location", "capacity",
                                                  "interpreter_languages"}:  # fmt: skip
        raise _err(
            ErrorCode.SESSION_NOT_EDITABLE,
            "A scheduled session may change only days, trainers, location and capacity.",
            "يمكن تغيير الأيام والمدربين والمكان والسعة فقط للجلسة المجدولة.",
            status=409,
        )
    _apply_fields(s, data)
    live = nominations(db, s, True)
    if len(live) > s.capacity:
        raise _err(
            ErrorCode.SESSION_FULL, "More nominees than the capacity.", "المرشحون أكثر من السعة."
        )
    _validate(db, p, s, c, [n.worker_id for n in live])
    if s.status == SS.scheduled:
        if s.starts_at <= now():
            raise _in_past()
        for n in live:
            errs = _prereq_missing(db, n.worker_id, c, s.first_day, s.project_id)
            if errs:
                raise _err(
                    ErrorCode.TRAINING_PREREQUISITE,
                    f"A nominee lacks prerequisites on the new first day: {', '.join(errs)}.",
                    "يفتقد أحد المرشحين متطلبات مسبقة في اليوم الأول الجديد.",
                    missing=errs,
                    worker_id=str(n.worker_id),
                )
    cc.stamp(s, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.training_session, s, s.project_id, before)
    if s.status == SS.scheduled and "days" in data:
        _notify(db, s, "rescheduled", "أعيدت جدولة")
    return read(db, p, s)


def _in_past() -> ApiError:
    return _err(
        ErrorCode.SESSION_IN_PAST,
        "Scheduled days must start in the future; record a past session as delivered.",
        "يجب أن تبدأ الأيام المجدولة في المستقبل؛ سجّل الجلسة السابقة كمنفذة.",
    )


def _notify(db: Session, s: TrainingSession, what_en: str, what_ar: str) -> None:
    users: set[uuid.UUID] = set()
    for n in nominations(db, s):
        users |= alerts.reps(db, s.project_id, n.engagement_id)
    users |= trainer_user_ids(db, s)
    alerts.send(
        db,
        users,
        NotificationKind.training_session_update,
        f"Training session {s.session_no} ({s.course_code}) {what_en}: {s.first_day}",
        f"الجلسة التدريبية {s.session_no} ({s.course_code}) {what_ar}: {s.first_day}",
        EntityType.training_session,
        s.id,
        s.project_id,
        email=True,
    )


def transition(
    db: Session, p: Principal, session_id: uuid.UUID, body: SessionTransitionRequest
) -> SessionRead:
    s = get(db, session_id)
    _manage(p, s.project_id)
    c = common.course_or_404(db, s.course_code)
    before = cc.snap(s)
    at = now()
    live = nominations(db, s, True)
    if body.action == SessionAction.schedule:
        if s.status != SS.draft:
            raise invalid_transition("Training session", s.status, SS.scheduled)
        _course_for_session(db, s.course_code)
        if s.starts_at <= at:
            raise _in_past()
        _validate(db, p, s, c, [n.worker_id for n in live])
        s.status = SS.scheduled
        s.scheduled_at = at
        s.status_reason = None
    elif body.action == SessionAction.record_delivered:
        if s.status != SS.draft:
            raise invalid_transition("Training session", s.status, SS.delivered)
        if not common.is_hse(p, s.project_id):
            raise forbidden_error("Only HSE Officers or the HSE Manager record past sessions.")
        st = common.settings(db, s.project_id)
        d = today()
        if s.ends_at > at:
            raise validation_error("days", "The session has not ended yet.")
        if s.last_day < d - timedelta(days=st.session_backdate_max_days):
            raise _err(
                ErrorCode.BACKDATED_SESSION,
                f"A past session may be recorded up to {st.session_backdate_max_days} days after "
                "its last day.",
                f"يمكن تسجيل الجلسة السابقة خلال {st.session_backdate_max_days} أيام من آخر يوم.",
            )
        _validate(db, p, s, c, [n.worker_id for n in live])
        s.status = SS.delivered
        s.scheduled_at = s.scheduled_at or at
        s.delivered_at = at
    else:
        if s.status not in (SS.draft, SS.scheduled):
            raise invalid_transition("Training session", s.status, SS.cancelled)
        s.status_reason = common.reason(body.reason, 10)
        was_scheduled = s.status == SS.scheduled
        s.status = SS.cancelled
        s.cancelled_at = at
        for n in live:
            n.status = NS.withdrawn
            n.withdrawn_at = at
            n.withdraw_reason = "session cancelled"
        if was_scheduled:
            _notify(db, s, "cancelled", "أُلغيت")
    cc.stamp(s, p)
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.training_session, s, s.project_id, before,
        {"action": body.action.value},
    )  # fmt: skip
    if body.action == SessionAction.schedule:
        _notify(db, s, "scheduled", "جُدولت")
    return read(db, p, s)


def advance(db: Session, s: TrainingSession, at: datetime | None = None) -> bool:
    """System transitions (§4.4): Scheduled → In Progress at the first start, → Delivered at the
    last end."""
    at = at or now()
    changed = False
    if s.status == SS.scheduled and at >= s.starts_at:
        s.status = SS.in_progress
        changed = True
    if s.status == SS.in_progress and at >= s.ends_at:
        s.status = SS.delivered
        s.delivered_at = s.ends_at
        changed = True
    if changed:
        s.updated_at = at
        db.flush()
    return changed


# ---- nominations (SS-6, AT-5, AT-6) -------------------------------------------------------------


def understood(w: Worker, s: TrainingSession) -> UnderstoodLanguage:
    lang = w.primary_language.value if w.primary_language else None
    if lang == s.language.value:
        return UnderstoodLanguage.session_language
    if lang in (s.interpreter_languages or []):
        return UnderstoodLanguage.interpreter
    return UnderstoodLanguage.none


def _prereq_missing(
    db: Session, worker_id: uuid.UUID, c: TrainingCourse, d: date, project_id: uuid.UUID
) -> list[str]:
    if not c.prerequisite_codes:
        return []
    recs = thook.worker_records(db, worker_id)
    ctx = thook.eval_ctx(db, project_id)
    out = []
    for code in c.prerequisite_codes:
        if not tval.best(recs, common.satisfiers(db, code), d, ctx).met:
            out.append(code)
    return out


def _attempts(
    db: Session, worker_id: uuid.UUID, c: TrainingCourse, project_id: uuid.UUID, d: date
) -> tuple[int, int]:
    """(attempts in the 30 days before d, failed attempts since the latest re-training note)."""
    since = d - timedelta(days=30)
    note = db.scalar(
        select(func.max(TrainingRetrainingNote.created_at)).where(
            TrainingRetrainingNote.worker_id == worker_id,
            TrainingRetrainingNote.course_code == c.code,
        )
    )
    total = 0
    failed = 0
    for n, s in db.execute(
        select(TrainingNomination, TrainingSession)
        .join(TrainingSession, TrainingSession.id == TrainingNomination.session_id)
        .where(
            TrainingNomination.worker_id == worker_id,
            TrainingSession.course_code == c.code,
            TrainingSession.last_day >= since,
            TrainingSession.status.in_([SS.closed, SS.delivered]),
        )
    ):
        if n.result not in (AR.passed, AR.failed):
            continue
        total += 1
        if n.result == AR.failed and (note is None or (s.closed_at or s.ends_at) > note):
            failed += 1
    return total, failed


def _clash(db: Session, worker_id: uuid.UUID, s: TrainingSession) -> str | None:
    mine = {x["date"] for x in s.days}
    for _n, other in db.execute(
        select(TrainingNomination, TrainingSession)
        .join(TrainingSession, TrainingSession.id == TrainingNomination.session_id)
        .where(
            TrainingNomination.worker_id == worker_id,
            TrainingNomination.status != NS.withdrawn,
            TrainingSession.id != s.id,
            TrainingSession.status.in_([SS.draft, SS.scheduled, SS.in_progress]),
            TrainingSession.last_day >= s.first_day,
            TrainingSession.first_day <= s.last_day,
        )
    ):
        if mine & {x["date"] for x in other.days}:
            return other.session_no
    return None


def _nominee_errors(
    db: Session,
    p: Principal,
    s: TrainingSession,
    c: TrainingCourse,
    w: Worker,
    already: int,
    check_capacity: bool = True,
) -> list[dict[str, Any]]:
    errs: list[dict[str, Any]] = []
    wid = str(w.id)
    dep = common.deployment(db, w.id, s.project_id)
    if dep is None or dep.status not in common.LIVE_DEP:
        return [{"worker_id": wid, "code": ErrorCode.NOT_FOUND.value}]
    g = p.grant(s.project_id, C.training_nominate)
    if not common.covers_dep(g, dep):
        return [{"worker_id": wid, "code": ErrorCode.FORBIDDEN.value}]
    if w.status == WorkerStatus.banned:
        errs.append({"worker_id": wid, "code": ErrorCode.WORKER_BANNED.value})
    if w.status == WorkerStatus.anonymised:
        errs.append({"worker_id": wid, "code": ErrorCode.NOT_FOUND.value})
    if w.id in trainer_worker_ids(db, s):
        errs.append({"worker_id": wid, "code": ErrorCode.SOD_CONFLICT.value})
    missing = _prereq_missing(db, w.id, c, s.first_day, s.project_id)
    if missing:
        errs.append(
            {"worker_id": wid, "code": ErrorCode.TRAINING_PREREQUISITE.value, "missing": missing}
        )
    other = _clash(db, w.id, s)
    if other:
        errs.append({"worker_id": wid, "code": ErrorCode.SCHEDULE_CLASH.value, "session_no": other})
    st = common.settings(db, s.project_id)
    _total, failed = _attempts(db, w.id, c, s.project_id, s.first_day)
    if failed >= st.training_max_attempts_30d:
        errs.append(
            {"worker_id": wid, "code": ErrorCode.TRAINING_ATTEMPTS_EXCEEDED.value,
             "course_code": c.code}
        )  # fmt: skip
    pv = common.provider_or_404(db, s.provider_id)
    if pv.kind == TrainingProviderKind.contractor_internal:
        a = tprov.acceptable(db, pv, c, s.first_day, s.project_id, [w.id])
        if not a.ok and a.reason is not None and a.reason.value == "NOT_OWN_TREE":
            errs.append({"worker_id": wid, "code": ErrorCode.NOT_OWN_TREE.value})
    if check_capacity and already >= s.capacity:
        errs.append({"worker_id": wid, "code": ErrorCode.SESSION_FULL.value})
    return errs


def _add_nomination(
    db: Session, p: Principal, s: TrainingSession, c: TrainingCourse, wid: uuid.UUID
) -> TrainingNomination:
    w = db.get(Worker, wid)
    assert w is not None  # noqa: S101
    dep = common.deployment(db, wid, s.project_id)
    total, _f = _attempts(db, wid, c, s.project_id, s.first_day)
    existing = db.scalar(
        select(TrainingNomination).where(
            TrainingNomination.session_id == s.id, TrainingNomination.worker_id == wid
        )
    )
    at = now()
    n = existing or TrainingNomination(id=uuid.uuid4(), session_id=s.id, worker_id=wid)
    n.deployment_id = dep.id if dep else None
    n.engagement_id = dep.engagement_id if dep else None
    n.contractor_worker = common.is_contractor_worker(w)
    n.nominated_by_user_id = p.user.id
    n.nominated_at = at
    n.status = NS.nominated
    n.minutes_by_day = {}
    n.understood_language = understood(w, s)
    n.attempt_no = total + 1
    n.result = AR.pending
    n.withdrawn_at = None
    n.withdraw_reason = None
    cc.stamp(n, p, create=existing is None)
    if existing is None:
        db.add(n)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.training_nomination, n, s.project_id)
    return n


def _lang_warn(db: Session, s: TrainingSession, c: TrainingCourse, w: Worker) -> ApiWarning | None:
    if understood(w, s) != UnderstoodLanguage.none:
        return None
    return _warn(
        ErrorCode.LANGUAGE_MISMATCH.value,
        f"{w.worker_no} does not understand the session language and no interpreter is listed.",
        f"{w.worker_no} لا يفهم لغة الجلسة ولا يوجد مترجم.",
    )


def create_nominations(
    db: Session, p: Principal, session_id: uuid.UUID, body: NominationCreate
) -> NominationList:
    s = get(db, session_id)
    p.require(s.project_id, C.training_nominate)
    if s.status not in (SS.draft, SS.scheduled):
        raise invalid_transition("Training session", s.status, "nominate")
    c = common.course_or_404(db, s.course_code)
    live = nominations(db, s, True)
    have = {n.worker_id for n in live}
    count = len(live)
    errs: list[dict[str, Any]] = []
    todo: list[Worker] = []
    for wid in dict.fromkeys(body.worker_ids):
        if wid in have:
            continue
        w = db.get(Worker, wid)
        if w is None:
            errs.append({"worker_id": str(wid), "code": ErrorCode.NOT_FOUND.value})
            continue
        e = _nominee_errors(db, p, s, c, w, count)
        if e:
            errs.extend(e)
        else:
            todo.append(w)
            count += 1
    if errs:
        codes = sorted({e["code"] for e in errs})
        first = codes[0] if len(codes) == 1 else None
        code = (
            ErrorCode(first)
            if first and first in ErrorCode.__members__
            else ErrorCode.VALIDATION_ERROR
        )
        if any(e["code"] == ErrorCode.FORBIDDEN.value for e in errs):
            raise forbidden_error("A worker is outside your scope.")
        missing = sorted({m for e in errs for m in e.get("missing", [])})
        msg = "Some workers cannot be nominated: " + ", ".join(codes)
        if missing:
            msg += f" (missing {', '.join(missing)})"
        raise ApiError(
            422, code, msg, "لا يمكن ترشيح بعض العمال.", meta={"errors": errs, "missing": missing}
        )
    warnings: list[ApiWarning] = []
    out = []
    for w in todo:
        n = _add_nomination(db, p, s, c, w.id)
        wn = _lang_warn(db, s, c, w)
        if wn:
            warnings.append(wn)
        out.append(n)
    return NominationList(items=[nomination_read(db, p, s, n) for n in out], warnings=warnings)


def _nom(db: Session, nomination_id: uuid.UUID) -> tuple[TrainingNomination, TrainingSession]:
    n = db.get(TrainingNomination, nomination_id)
    if n is None:
        raise not_found("Nomination")
    return n, get(db, n.session_id)


def withdraw(
    db: Session, p: Principal, nomination_id: uuid.UUID, body: NominationWithdraw
) -> NominationRead:
    n, s = _nom(db, nomination_id)
    g = p.require(s.project_id, C.training_nominate)
    dep = db.get(Deployment, n.deployment_id) if n.deployment_id else None
    if not common.covers_dep(g, dep):
        raise forbidden_error()
    if (
        n.status != NS.nominated
        or today() >= s.first_day
        or s.status not in (SS.draft, SS.scheduled)
    ):
        raise invalid_transition("Nomination", n.status, NS.withdrawn)
    before = cc.snap(n)
    n.status = NS.withdrawn
    n.withdrawn_at = now()
    n.withdraw_reason = body.reason
    cc.stamp(n, p)
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.training_nomination, n, s.project_id, before
    )
    return nomination_read(db, p, s, n)


# ---- attendance and assessment (SS-7, AT-1…AT-4) ------------------------------------------------


def _can_record(db: Session, p: Principal, s: TrainingSession) -> None:
    p.ensure_writer()
    if p.user.id in trainer_user_ids(db, s):
        return
    g = p.grant(s.project_id, C.training_attendance_record)
    if g is None:
        raise forbidden_error()
    if common.contractor_only(p, s.project_id):
        pv = common.provider_or_404(db, s.provider_id)
        if pv.contractor_id is None or pv.contractor_id != p.user.employer_contractor_id:
            raise forbidden_error("Contractor HSE Reps record attendance of their own sessions.")


def complete(s: TrainingSession, n: TrainingNomination) -> bool:
    mins = n.minutes_by_day or {}
    return all(int(mins.get(str(i + 1), 0)) >= net(d) for i, d in enumerate(s.days))


def record_attendance(
    db: Session, p: Principal, session_id: uuid.UUID, body: AttendanceUpdate
) -> NominationList:
    s = get(db, session_id)
    advance(db, s)
    _can_record(db, p, s)
    if s.status not in (SS.in_progress, SS.delivered, SS.scheduled):
        raise invalid_transition("Training session", s.status, "attendance")
    d = today()
    by_id = {n.id: n for n in nominations(db, s)}
    out = []
    for e in body.entries:
        n = by_id.get(e.nomination_id)
        if n is None or n.status == NS.withdrawn:
            raise validation_error("entries", "Unknown or withdrawn nomination.")
        if e.status not in (NS.attended, NS.partial, NS.absent):
            raise validation_error("entries.status", "attended, partial or absent.")
        mins = dict(n.minutes_by_day or {})
        for day_no, m in e.minutes_by_day.items():
            if day_no < 1 or day_no > len(s.days):
                raise validation_error("entries.minutes_by_day", f"No session day {day_no}.")
            day = s.days[day_no - 1]
            if date.fromisoformat(day["date"]) > d:
                raise _err(
                    ErrorCode.ATTENDANCE_DAY_NOT_REACHED,
                    f"Day {day_no} has not been reached.",
                    f"لم يحن اليوم {day_no} بعد.",
                )
            if m < 0 or m > net(day):
                raise validation_error(
                    "entries.minutes_by_day", f"0 … {net(day)} minutes on day {day_no}."
                )
            mins[str(day_no)] = int(m)
        if e.status == NS.absent:
            mins = dict.fromkeys(mins, 0)
        before = cc.snap(n, exclude=("theory_score_pct",))
        n.minutes_by_day = mins
        n.status = e.status
        if e.status == NS.attended and len(mins) == len(s.days) and not complete(s, n):
            n.status = NS.partial
        cc.stamp(n, p)
        db.flush()
        cc.record(
            db, p, AuditAction.update, EntityType.training_nomination, n, s.project_id, before,
            after=cc.snap(n, exclude=("theory_score_pct",)),
        )  # fmt: skip
        out.append(n)
    return NominationList(items=[nomination_read(db, p, s, n) for n in out])


def record_assessments(
    db: Session, p: Principal, session_id: uuid.UUID, body: AssessmentUpdate
) -> NominationList:
    s = get(db, session_id)
    advance(db, s)
    _can_record(db, p, s)
    if s.status not in (SS.in_progress, SS.delivered):
        raise invalid_transition("Training session", s.status, "assessment")
    c = common.course_or_404(db, s.course_code)
    by_id = {n.id: n for n in nominations(db, s)}
    trainers = trainer_user_ids(db, s)
    assessors = trainer_user_ids(db, s, TrainerRole.assessor)
    out = []
    for e in body.entries:
        n = by_id.get(e.nomination_id)
        if n is None or n.status == NS.withdrawn:
            raise validation_error("entries", "Unknown or withdrawn nomination.")
        before = cc.snap(n, exclude=("theory_score_pct",))
        if e.theory_score_pct is not None:
            if not c.theory_required:
                raise validation_error("entries.theory_score_pct", "No theory test on this course.")
            n.theory_score_pct = Decimal(e.theory_score_pct)
        if e.practical_result is not None:
            if not c.practical_required:
                raise validation_error("entries.practical_result", "No practical on this course.")
            if p.user.id in trainers and p.user.id not in assessors:
                raise _err(
                    ErrorCode.ASSESSOR_REQUIRED,
                    "Only an assessor of the session records the practical result.",
                    "يسجل نتيجة التقييم العملي مقيِّم الجلسة فقط.",
                )
            n.practical_result = e.practical_result
            n.practical_by_user_id = p.user.id
        cc.stamp(n, p)
        db.flush()
        cc.record(
            db, p, AuditAction.update, EntityType.training_nomination, n, s.project_id, before,
            {"assessment": True}, after=cc.snap(n, exclude=("theory_score_pct",)),
        )  # fmt: skip
        out.append(n)
    return NominationList(items=[nomination_read(db, p, s, n) for n in out])


def sign(
    db: Session, p: Principal, nomination_id: uuid.UUID, body: AttendanceSignature
) -> NominationRead:
    n, s = _nom(db, nomination_id)
    _can_record(db, p, s)
    n.signature_attachment_id = body.signature_attachment_id
    cc.stamp(n, p)
    db.flush()
    cc.record(
        db, p, AuditAction.update, EntityType.training_nomination, n, s.project_id,
        details={"signature": "attached"},
        after={"signature_attachment_id": str(n.signature_attachment_id)},
    )  # fmt: skip
    return nomination_read(db, p, s, n)


# ---- close (SS-8, AT-1…AT-6, TR-14) and void (SS-9) ---------------------------------------------


def _result(
    db: Session, s: TrainingSession, c: TrainingCourse, n: TrainingNomination
) -> tuple[AttendanceResult, str | None]:
    if n.status in (NS.absent, NS.withdrawn):
        return AR.incomplete, None
    if not complete(s, n):
        return AR.incomplete, ErrorCode.ATTENDANCE_INSUFFICIENT.value
    st = common.settings(db, s.project_id)
    if c.category.value in (st.language_block_categories or []) and n.understood_language == (
        UnderstoodLanguage.none
    ):
        return AR.failed, ErrorCode.LANGUAGE_NOT_UNDERSTOOD.value
    ok = True
    if c.theory_required:
        ok = (
            ok
            and n.theory_score_pct is not None
            and n.theory_score_pct >= Decimal(common.effective_pass_mark(c, st))
        )
    if c.practical_required:
        ok = ok and n.practical_result == PracticalResult.pass_
    return (AR.passed, None) if ok else (AR.failed, None)


def close(db: Session, p: Principal, session_id: uuid.UUID, body: SessionClose) -> SessionRead:
    s = get(db, session_id)
    advance(db, s)
    p.require(s.project_id, C.training_session_close)
    if s.status != SS.delivered:
        raise invalid_transition("Training session", s.status, SS.closed)
    if p.user.id in trainer_user_ids(db, s):
        raise common.sod("The person closing the session cannot be its trainer or assessor.")
    c = common.course_or_404(db, s.course_code)
    rows = nominations(db, s)
    pending = [n for n in rows if n.status == NS.nominated]
    missing = []
    for n in rows:
        unscored = (c.theory_required and n.theory_score_pct is None) or (
            c.practical_required and n.practical_result is None
        )
        if n.status in (NS.attended, NS.partial) and complete(s, n) and unscored:
            missing.append(n)
    if pending or missing:
        raise _err(
            ErrorCode.NOMINATIONS_INCOMPLETE,
            "Every nominee needs a final attendance status and, when complete, the assessment.",
            "يحتاج كل مرشح إلى حالة حضور نهائية ونتيجة تقييم عند اكتمال الحضور.",
            nominations=[str(n.id) for n in pending + missing],
            worker_ids=[str(n.worker_id) for n in pending + missing],
        )
    sheet = body.attendance_sheet_attachment_id or s.attendance_sheet_attachment_id
    present = [n for n in rows if n.status in (NS.attended, NS.partial)]
    if sheet is None and any(n.signature_attachment_id is None for n in present):
        raise _err(
            ErrorCode.ATTENDANCE_SHEET_REQUIRED,
            "Attach the signed attendance sheet (not every attendee signed on the device).",
            "أرفق كشف الحضور الموقّع (لم يوقع جميع الحاضرين على الجهاز).",
        )
    before = cc.snap(s)
    at = now()
    proj = common.project(db, s.project_id)
    issued: list[uuid.UUID] = []
    st = common.settings(db, s.project_id)
    for n in rows:
        if n.status == NS.withdrawn:
            continue
        res, why = _result(db, s, c, n)
        if n.status == NS.attended and why == ErrorCode.ATTENDANCE_INSUFFICIENT.value:
            n.status = NS.partial
        n.result = res
        n.result_reason = why
        if res == AR.passed:
            recordops.issue_from_session(db, p, s, n, c, proj.code, at)
            issued.append(n.worker_id)
        elif res == AR.failed:
            _total, failed = _attempts(db, n.worker_id, c, s.project_id, s.last_day)
            if failed + 1 >= st.training_max_attempts_30d:
                _alert_attempts(db, s, n)
    s.status = SS.closed
    s.closed_by_user_id = p.user.id
    s.closed_at = at
    s.attendance_sheet_attachment_id = sheet
    cc.stamp(s, p)
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.training_session, s, s.project_id, before,
        {"action": "close", "records_issued": len(issued)},
    )  # fmt: skip
    if issued:
        from app.services.cert import events  # noqa: PLC0415

        events.publish(db, "training.record_changed", worker_ids=issued)
    return read(db, p, s)


def _alert_attempts(db: Session, s: TrainingSession, n: TrainingNomination) -> None:
    w = db.get(Worker, n.worker_id)
    users = alerts.officers(db, s.project_id) | alerts.reps(db, s.project_id, n.engagement_id)
    alerts.send(
        db,
        users,
        NotificationKind.training_attempts_exceeded,
        f"{w.worker_no if w else 'Worker'}: attempts limit reached for {s.course_code}",
        f"{w.worker_no if w else 'عامل'}: بلغ الحد الأقصى للمحاولات في {s.course_code}",
        EntityType.training_session,
        s.id,
        s.project_id,
    )


def void(db: Session, p: Principal, session_id: uuid.UUID, body: SessionVoid) -> SessionRead:
    s = get(db, session_id)
    p.ensure_writer()
    if not p.is_manager:
        raise forbidden_error()
    if s.status != SS.closed:
        raise invalid_transition("Training session", s.status, SS.voided)
    before = cc.snap(s)
    at = now()
    s.status = SS.voided
    s.void_reason_code = body.reason_code
    s.void_reason_text = body.reason_text
    s.voided_by_user_id = p.user.id
    s.voided_at = at
    holders: set[uuid.UUID] = set()
    for r in db.scalars(select(TrainingRecord).where(TrainingRecord.session_id == s.id)):
        if r.status in (TrainingRecordStatus.revoked, TrainingRecordStatus.rejected):
            continue
        rb = recordops.snap(r)
        r.status = TrainingRecordStatus.revoked
        r.status_reason = TrainingStatusReason.session_voided
        r.status_changed_at = at
        r.ended_on = today()
        holders.add(r.worker_id)
        recordops.audit(db, p, AuditAction.status_change, r, rb, {"cascade": "session_voided"})
        from app.core.access_enums import QrTokenStatus  # noqa: PLC0415
        from app.models import QrToken  # noqa: PLC0415

        for t in db.scalars(select(QrToken).where(QrToken.subject_id == r.id)):
            t.status = QrTokenStatus.revoked
    cc.stamp(s, p)
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.training_session, s, s.project_id, before,
        {"action": "void", "records_revoked": len(holders)},
    )  # fmt: skip
    from app.services.cert import events  # noqa: PLC0415

    events.publish(db, "training.session_voided", project_id=s.project_id, worker_ids=holders)
    events.publish(db, "training.record_changed", worker_ids=holders)
    users = alerts.officers(db, s.project_id)
    for n in nominations(db, s):
        if n.worker_id in holders:
            users |= alerts.reps(db, s.project_id, n.engagement_id)
    from app.schemas.training_common import NOT_ACCEPTED_AR, NOT_ACCEPTED_EN  # noqa: PLC0415

    alerts.send(
        db,
        users,
        NotificationKind.training_session_voided,
        f"{s.session_no}: {NOT_ACCEPTED_EN}",
        f"{s.session_no}: {NOT_ACCEPTED_AR}",
        EntityType.training_session,
        s.id,
        s.project_id,
        email=True,
    )
    return read(db, p, s)


# ---- nominations read (AT-7) --------------------------------------------------------------------


def scores_visible(db: Session, p: Principal, s: TrainingSession, n: TrainingNomination) -> bool:
    if p.is_manager or common.is_hse(p, s.project_id):
        return True
    if p.user.id in trainer_user_ids(db, s):
        return True
    if Role.contractor_hse_rep in common.roles_on(p, s.project_id):
        g = p.grant(s.project_id, C.training_record_view)
        dep = db.get(Deployment, n.deployment_id) if n.deployment_id else None
        return common.covers_dep(g, dep)
    return False


def nomination_read(
    db: Session, p: Principal, s: TrainingSession, n: TrainingNomination
) -> NominationRead:
    refs = Refs(db)
    w = db.get(Worker, n.worker_id)
    assert w is not None  # noqa: S101
    rec = db.get(TrainingRecord, n.record_id) if n.record_id else None
    show_scores = scores_visible(db, p, s, n)
    mins = {int(k): int(v) for k, v in (n.minutes_by_day or {}).items()}
    by = refs.user(n.nominated_by_user_id) or cc.UNKNOWN_USER
    warn = []
    c = common.course(db, s.course_code)
    if c is not None and n.status != NS.withdrawn:
        x = _lang_warn(db, s, c, w)
        if x:
            warn.append(x)
    return NominationRead(
        id=n.id,
        session_id=s.id,
        worker=common.worker_ref(w, common.names(p, s.project_id)),
        engagement=refs.eng(n.engagement_id) if n.engagement_id else None,
        worker_language=w.primary_language,
        understood_language=n.understood_language,
        status=n.status,
        minutes_by_day=mins,
        attended_hours=(Decimal(sum(mins.values())) / Decimal(60)).quantize(Decimal("0.01")),
        attendance_complete=complete(s, n),
        theory_score_pct=n.theory_score_pct if show_scores else None,
        practical_result=n.practical_result if show_scores else None,
        attempt_no=n.attempt_no,
        result=n.result,
        result_reason=n.result_reason,
        signed_on_device=n.signature_attachment_id is not None,
        record=common.record_ref(rec) if rec else None,
        nominated_by=by,
        nominated_at=n.nominated_at,
        warnings=warn,
    )


def list_nominations(db: Session, p: Principal, session_id: uuid.UUID) -> NominationList:
    s = get(db, session_id)
    g = p.grant(s.project_id, C.training_record_view)
    if g is None and p.user.id not in trainer_user_ids(db, s):
        raise forbidden_error()
    out = []
    for n in nominations(db, s):
        dep = db.get(Deployment, n.deployment_id) if n.deployment_id else None
        if (
            g is not None
            and not common.covers_dep(g, dep)
            and p.user.id not in trainer_user_ids(db, s)
        ):
            continue
        out.append(nomination_read(db, p, s, n))
    return NominationList(items=out)
