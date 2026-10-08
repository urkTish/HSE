"""Phase 5 project settings, enabling training hooks and the training hours report (spec
5-training §3.16, §4.7, HK5-1, HK5-5, TH-1…TH-9, §8.4)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.train_enums import CourseCategory, TrainingHoursSource
from app.schemas.common import ApiModel, StrictInput
from app.schemas.hse_common import DecimalStr, EngagementRef, UserRef


class TrainingSettingsRead(ApiModel):
    """§3.16 (HSE Manager edits, capability 145; everyone with 125 reads)."""

    project_id: uuid.UUID
    training_register_from: date | None = Field(
        description="Read-only here; edited in PATCH /projects/{id}/hse-settings (Phase 1 §3.10)."
    )
    course_validity_months: dict[str, int] = Field(
        description="Code → months (shorten only; a value on a no-expiry course sets a cap)."
    )
    training_pass_mark_pct: int
    training_max_attempts_30d: int
    unverified_training_acceptance_hours: int
    training_verification_due_days: int
    session_close_deadline_days: int
    session_backdate_max_days: int
    session_day_max_net_hours: DecimalStr
    trainer_authorisation_max_months: int
    refresher_planning_days: int
    refresher_max_lapse_days: int
    matrix_line_max_due_days: int
    language_block_categories: list[CourseCategory]
    training_hook_transition_days: int
    training_hook_critical_transition_days: int
    training_hook_critical_codes: list[str]
    training_matrix_warning_pct: DecimalStr
    training_scan_retention_years: int
    alert_schedule_long_days: list[int]
    training_hooks_enabled: bool = Field(description="HK5-1 provider registered on the project.")
    updated_by: UserRef | None
    updated_at: datetime | None


class TrainingSettingsUpdate(StrictInput):
    """Capability 145. Only the "Allowed" ranges are accepted (422 VALIDATION_ERROR);
    `language_block_categories` and `training_hook_critical_codes` are add-only, and
    `course_validity_months` shorten-only (422 CATALOGUE_LOOSENING). A critical code added
    after critical_block_from blocks at once (as Phase 4)."""

    course_validity_months: dict[str, int] | None = None
    training_pass_mark_pct: int | None = Field(default=None, ge=50, le=100)
    training_max_attempts_30d: int | None = Field(default=None, ge=1, le=5)
    unverified_training_acceptance_hours: int | None = Field(default=None, ge=0, le=24)
    training_verification_due_days: int | None = Field(default=None, ge=1, le=14)
    session_close_deadline_days: int | None = Field(default=None, ge=1, le=7)
    session_backdate_max_days: int | None = Field(default=None, ge=0, le=14)
    session_day_max_net_hours: DecimalStr | None = Field(
        default=None, ge=Decimal("4.00"), le=Decimal("10.00"), max_digits=4, decimal_places=2
    )
    trainer_authorisation_max_months: int | None = Field(default=None, ge=6, le=24)
    refresher_planning_days: int | None = Field(default=None, ge=30, le=120)
    refresher_max_lapse_days: int | None = Field(default=None, ge=0, le=30)
    matrix_line_max_due_days: int | None = Field(default=None, ge=0, le=180)
    language_block_categories: list[CourseCategory] | None = None
    training_hook_transition_days: int | None = Field(default=None, ge=0, le=30)
    training_hook_critical_transition_days: int | None = Field(default=None, ge=0, le=7)
    training_hook_critical_codes: list[str] | None = None
    training_matrix_warning_pct: DecimalStr | None = Field(
        default=None, ge=Decimal("80.0"), le=Decimal("100.0"), max_digits=4, decimal_places=1
    )
    training_scan_retention_years: int | None = Field(default=None, ge=1, le=10)


class TrainingHooksEnableRequest(StrictInput):
    """HK5-1 (capability 145): register the training_course provider on the project. Needs
    training_register_from set and ≤ today (422 TRAINING_REGISTER_NOT_LIVE); already
    registered → 409 INVALID_TRANSITION. Dates per §6.5 from the training_hook_* settings;
    read the readiness report first (GET /projects/{id}/hook-readiness?kind=training_course).
    Early switch and the one deferral use POST /projects/{id}/hook-policy/training_course/…"""

    registered_on: date | None = Field(default=None, description="Default today (local).")


# ---- training hours report (§8.4, TH-6, TH-7) --------------------------------------------------


class TrainingHoursRow(ApiModel):
    month: str = Field(examples=["2026-09"])
    engagement: EngagementRef | None = Field(description="Null on the project total row.")
    source: TrainingHoursSource = Field(description="Source used for K-37 in the month.")
    register_days: int
    register_hours: DecimalStr = Field(description="TH-1…TH-3 (contractor_worker only).")
    daily_return_hours: DecimalStr = Field(description="All days of the month.")
    daily_return_hours_register_days: DecimalStr
    k37_numerator: DecimalStr = Field(description="§6.4 per-day single source.")
    staff_hours: DecimalStr = Field(description="client_pmc_staff (not in K-37).")
    voided_hours: DecimalStr = Field(description="TH-9 (kept in K-86 history).")
    reconciliation_pct: DecimalStr | None = Field(description="TH-7; null when no basis.")
    reconciliation_note: bool = Field(description="reconciliation_pct > 5.00.")
    sessions_not_closed: int
    by_category: dict[CourseCategory, DecimalStr] = Field(default_factory=dict)


class TrainingHoursReport(ApiModel):
    project_id: uuid.UUID
    date_from: date
    date_to: date
    training_register_from: date | None
    rows: list[TrainingHoursRow]
