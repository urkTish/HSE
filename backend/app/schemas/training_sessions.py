"""Training sessions, nominations, attendance and assessment (spec 5-training §3.6, §3.7, §4.4,
§4.5, §6.3, SS-1…SS-10, AT-1…AT-7)."""

import uuid
from datetime import date, datetime, time

from pydantic import Field

from app.core.access_enums import WorkerLanguage
from app.core.train_enums import (
    AttendanceResult,
    DeliveryMode,
    NominationStatus,
    PracticalResult,
    SessionAction,
    SessionStatus,
    SessionVoidReason,
    TrainerRole,
    UnderstoodLanguage,
)
from app.schemas.access_common import WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, EngagementRef, SiteRef, UserRef, ZoneRef
from app.schemas.training_common import (
    COURSE_CODE,
    P5_HINT,
    CourseRef,
    Hours,
    ScorePct,
    TrainingProviderRef,
    TrainingRecordRef,
)


class SessionTrainer(StrictInput):
    """Exactly one of user_id / worker_id / external_name. Internal and contractor_internal
    sessions: an Active authorisation for the course and role on every day (422
    TRAINER_NOT_AUTHORISED, TA-2) and an in-force record of the course (422
    TRAINER_NOT_TRAINED, TA-3). External: `external_name` as printed (TA-5)."""

    user_id: uuid.UUID | None = None
    worker_id: uuid.UUID | None = None
    external_name: str | None = Field(default=None, min_length=1, max_length=120)
    roles: list[TrainerRole] = Field(min_length=1)


class SessionTrainerRead(ApiModel):
    user: UserRef | None
    worker: WorkerRef | None
    external_name: str | None
    roles: list[TrainerRole]
    authorisation_no: str | None


class SessionLocation(StrictInput):
    """{site_id, zone_id?} on the project, or `offsite_text`."""

    site_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    offsite_text: str | None = Field(default=None, max_length=200)


class SessionLocationRead(ApiModel):
    site: SiteRef | None
    zone: ZoneRef | None
    offsite_text: str | None


class SessionDay(StrictInput):
    """SS-2: end > start; net minutes ≤ session_day_max_net_hours × 60 (422
    SESSION_DAY_TOO_LONG); Σ net ≥ course min (422 SESSION_TOO_SHORT)."""

    date: date
    start_time: time
    end_time: time
    break_minutes: int = Field(ge=0, le=240)


class SessionDayRead(ApiModel):
    day_no: int
    date: date
    start_time: time
    end_time: time
    break_minutes: int
    net_minutes: int = Field(description="§6.3: end − start − break.")


class SessionFields(StrictInput):
    provider_id: uuid.UUID
    delivery_mode: DeliveryMode
    trainers: list[SessionTrainer] = Field(min_length=1)
    location: SessionLocation
    language: WorkerLanguage
    interpreter_languages: list[WorkerLanguage] = Field(default_factory=list)
    days: list[SessionDay] = Field(min_length=1, max_length=15)
    capacity: int = Field(ge=1, le=60, description="≤ course.max_class_size.")


class SessionCreate(SessionFields):
    """Capability 132 → Draft. Course active and not induction_link (422
    INDUCTION_OWNED_BY_PHASE2 / COURSE_INACTIVE). Contractor HSE Rep: own contractor_internal
    provider only (TA-6)."""

    course_code: str = Field(pattern=COURSE_CODE)


class SessionFromPlan(StrictInput):
    """GP-4 (capability 132): a Draft session pre-filled with refresher-plan nominees (same
    course, language group) up to max_class_size. Nominees still pass SS-6 at Schedule."""

    course_code: str = Field(pattern=COURSE_CODE)
    record_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Plan items to include; empty = all not_booked."
    )
    language: WorkerLanguage | None = None
    session: SessionFields


class SessionUpdate(PatchInput):
    """Draft: any field. Scheduled (before the first day): reschedule days, trainers,
    location, capacity — re-checks SS-1…SS-6 and re-notifies (§4.4). Otherwise 409
    SESSION_NOT_EDITABLE."""

    non_nullable = frozenset(
        {"provider_id", "delivery_mode", "trainers", "location", "language", "days", "capacity"}
    )

    provider_id: uuid.UUID | None = None
    delivery_mode: DeliveryMode | None = None
    trainers: list[SessionTrainer] | None = Field(default=None, min_length=1)
    location: SessionLocation | None = None
    language: WorkerLanguage | None = None
    interpreter_languages: list[WorkerLanguage] | None = None
    days: list[SessionDay] | None = Field(default=None, min_length=1, max_length=15)
    capacity: int | None = Field(default=None, ge=1, le=60)


class SessionTransitionRequest(StrictInput):
    """`schedule` (SS-1…SS-4; days must start after now — 422 SESSION_IN_PAST);
    `record_delivered` (SS-5: HSE Officer / Manager; last day ≥ today −
    session_backdate_max_days — 422 BACKDATED_SESSION); `cancel` (reason; terminal; SS-10)."""

    action: SessionAction
    reason: str | None = Field(default=None, max_length=500, description=P5_HINT)


class SessionClose(StrictInput):
    """SS-8 (capability 135; closer ≠ every trainer/assessor — 422 SOD_CONFLICT): every
    nomination final (422 NOMINATIONS_INCOMPLETE); attendance sheet unless every attendee
    signed on the device (422 ATTENDANCE_SHEET_REQUIRED). Issues records atomically (TR-14)."""

    attendance_sheet_attachment_id: uuid.UUID | None = Field(
        default=None, description="Owner training_attendance_sheet (PDF/JPG ≤ 10 MB)."
    )


class SessionVoid(StrictInput):
    """SS-9 (capability 145): Closed → Voided; every issued record Revoked (hard stop)."""

    reason_code: SessionVoidReason
    reason_text: str = Field(min_length=20, max_length=500, description=P5_HINT)


class SessionVoidRead(ApiModel):
    reason_code: SessionVoidReason
    reason_text: str | None = Field(description="HSE Manager / Officer only (P5-4).")
    by: UserRef
    at: datetime


class SessionCounts(ApiModel):
    nominated: int
    attended: int
    partial: int
    absent: int
    withdrawn: int
    passed: int
    failed: int
    incomplete: int
    pending: int


class SessionRead(ApiModel):
    id: uuid.UUID
    session_no: str = Field(examples=["TRS-ANIA-EXP-2026-00057"])
    project_id: uuid.UUID
    course: CourseRef
    provider: TrainingProviderRef
    delivery_mode: DeliveryMode
    trainers: list[SessionTrainerRead]
    location: SessionLocationRead
    language: WorkerLanguage
    interpreter_languages: list[WorkerLanguage]
    days: list[SessionDayRead]
    net_minutes_total: int
    capacity: int
    status: SessionStatus
    status_reason: str | None
    close_due_on: date | None = Field(description="Last day + session_close_deadline_days.")
    close_overdue: bool
    attendance_sheet_attachment_id: uuid.UUID | None
    closed_by: UserRef | None
    closed_at: datetime | None
    void: SessionVoidRead | None
    counts: SessionCounts
    blockers: list[ApiWarning] = Field(
        description="Current SS-1…SS-4 / TA-2 problems (e.g. TRAINER_NOT_AUTHORISED after a "
        "suspension, PROVIDER_NOT_ACCEPTABLE)."
    )
    allowed_actions: list[str] = Field(
        examples=[["schedule", "cancel", "close"]],
        description="Of schedule, record_delivered, cancel, close, void, edit, nominate.",
    )
    created_by: UserRef
    created_at: datetime
    updated_at: datetime


class SessionListItem(ApiModel):
    """Calendar rows (capability 125: no attendee names)."""

    id: uuid.UUID
    session_no: str
    course: CourseRef
    provider_code: str
    language: WorkerLanguage
    first_day: date
    last_day: date
    site_code: str | None
    status: SessionStatus
    capacity: int
    nominated: int
    close_overdue: bool


class SessionPage(Page[SessionListItem]):
    pass


# ---- nominations and attendance (§3.7) ---------------------------------------------------------


class NominationCreate(StrictInput):
    """Capability 133 (C scope for Contractor HSE Reps). All-or-nothing: any failing worker →
    422 with `meta.errors` [{worker_id, code, course_code?}] — codes WORKER_BANNED,
    TRAINING_PREREQUISITE, SCHEDULE_CLASH, TRAINING_ATTEMPTS_EXCEEDED, SESSION_FULL,
    SOD_CONFLICT (a trainer), NOT_FOUND (no Mobilised / Pending Induction deployment).
    Language (AT-6) → warning LANGUAGE_MISMATCH."""

    worker_ids: list[uuid.UUID] = Field(min_length=1, max_length=60)


class NominationWithdraw(StrictInput):
    reason: str | None = Field(default=None, max_length=300, description=P5_HINT)


class NominationRead(ApiModel):
    """Scores and practical results only for HSE Manager / Officer, the session's trainers and
    the worker's Contractor HSE Rep (AT-7, P5-5); others get them null."""

    id: uuid.UUID
    session_id: uuid.UUID
    worker: WorkerRef
    engagement: EngagementRef | None
    worker_language: WorkerLanguage | None
    understood_language: UnderstoodLanguage
    status: NominationStatus
    minutes_by_day: dict[int, int]
    attended_hours: Hours
    attendance_complete: bool
    theory_score_pct: ScorePct | None
    practical_result: PracticalResult | None
    attempt_no: int
    result: AttendanceResult
    result_reason: str | None = Field(
        description="ATTENDANCE_INSUFFICIENT, LANGUAGE_NOT_UNDERSTOOD, …"
    )
    signed_on_device: bool
    record: TrainingRecordRef | None
    nominated_by: UserRef
    nominated_at: datetime
    warnings: list[ApiWarning]


class NominationList(ApiModel):
    items: list[NominationRead]
    warnings: list[ApiWarning] = Field(default_factory=list)


class AttendanceEntry(StrictInput):
    """SS-7: days ≤ today only (422 ATTENDANCE_DAY_NOT_REACHED); minutes 0 … the day's net."""

    nomination_id: uuid.UUID
    status: NominationStatus = Field(description="attended | partial | absent.")
    minutes_by_day: dict[int, int] = Field(default_factory=dict)


class AttendanceUpdate(StrictInput):
    """PUT /training-sessions/{id}/attendance (capability 134 or a user trainer of the
    session). Rows not listed are unchanged."""

    entries: list[AttendanceEntry] = Field(min_length=1)


class AssessmentEntry(StrictInput):
    """theory_score_pct iff course.theory_required and attendance complete; practical_result
    iff practical_required, recorded by an assessor of the session (422 ASSESSOR_REQUIRED)."""

    nomination_id: uuid.UUID
    theory_score_pct: ScorePct | None = None
    practical_result: PracticalResult | None = None


class AssessmentUpdate(StrictInput):
    entries: list[AssessmentEntry] = Field(min_length=1)


class AttendanceSignature(StrictInput):
    """On-device attendee signature (drawn image as an attachment)."""

    signature_attachment_id: uuid.UUID = Field(
        description="Owner training_attendance_signature (personal bucket, never exported)."
    )
