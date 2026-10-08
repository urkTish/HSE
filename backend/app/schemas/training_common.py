"""Building blocks shared by the Phase 5 schemas (spec 5-training)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.core.cert_enums import HookReasonCode
from app.core.train_enums import (
    CourseCategory,
    SessionStatus,
    TrainingLimitingFactor,
    TrainingProviderKind,
    TrainingProviderStatus,
    TrainingRecordStatus,
)
from app.schemas.common import ApiModel
from app.schemas.hse_common import DecimalStr

COURSE_CODE = r"^[A-Z0-9-]{2,20}$"
"""Catalogue code (§3.1): immutable, org-wide, disjoint from Phase 4 list PCT (BD5-2)."""
PROVIDER_CODE = r"^[A-Z0-9-]{2,12}$"
TR_QR_PATTERN = r"^HSE2:TR:[A-Za-z0-9_-]{22}$"
"""QR kind TR (CK5-1): session-issued certificates only; never an access token (GC-3)."""

P5_HINT = (
    "P3/P5 hint: no ID numbers, medical details, scores of other people or personal mobiles "
    "(P5-10 ID scan applies)."
)
NOT_ACCEPTED_EN = "Training record not accepted"
NOT_ACCEPTED_AR = "السجل التدريبي غير مقبول"

Hours = Annotated[DecimalStr, Field(ge=Decimal(0), max_digits=6, decimal_places=2)]
"""Hours, 2 dp (decimal(6,2)); JSON string on output."""
ScorePct = Annotated[
    DecimalStr, Field(ge=Decimal(0), le=Decimal(100), max_digits=5, decimal_places=2)
]


class CourseRef(ApiModel):
    code: str = Field(examples=["CSE-ATTENDANT"])
    name_en: str
    name_ar: str
    category: CourseCategory


class TrainingProviderRef(ApiModel):
    """Contractor roles see `accepted_for_use` instead of status reasons (P5-4)."""

    id: uuid.UUID
    provider_code: str = Field(examples=["INT-HSE"])
    legal_name_en: str
    legal_name_ar: str
    kind: TrainingProviderKind
    status: TrainingProviderStatus | None = Field(
        default=None, description="Null for callers outside HSE roles."
    )
    accepted_for_use: bool


class TrainingSessionRef(ApiModel):
    id: uuid.UUID
    session_no: str = Field(examples=["TRS-ANIA-EXP-2026-00057"])
    course_code: str
    status: SessionStatus
    first_day: date
    last_day: date


class TrainingRecordRef(ApiModel):
    id: uuid.UUID
    record_no: str = Field(examples=["TRR-000812"])
    course_code: str
    status: TrainingRecordStatus
    valid_until: date | None


class TrainingValidity(ApiModel):
    """§6.1 strictest-wins validity and the §6.6 in-force predicate at `as_of` on `project_id`
    (the project's `course_validity_months` override applies on read, TR-16)."""

    project_id: uuid.UUID | None = Field(
        description="Project whose override was applied; null = org default."
    )
    as_of: date
    valid_until: date | None = Field(description="Effective last valid day; null = no expiry.")
    stored_valid_until: date | None = Field(description="Org default (no project override).")
    limiting_factor: TrainingLimitingFactor
    course_end: date | None
    printed_expiry: date | None
    days_left: int | None
    in_force: bool
    not_in_force_reason: HookReasonCode | None = Field(
        description="TRAINING_PENDING_REVIEW, TRAINING_UNVERIFIED, TRAINING_EXPIRED, "
        "TRAINING_SUSPENDED, TRAINING_REVOKED, TRAINING_VERIFICATION_FAILED."
    )
    expiring: bool = Field(description="KPI / alerts: in force and valid_until ≤ as_of + 30.")
    expiring_hook: bool = Field(description="Hook: in force and valid_until ≤ as_of + 7.")
    unverified_window_until: datetime | None = Field(
        default=None,
        description="VR-1: in force before verification until this time (setting "
        "unverified_training_acceptance_hours, default 0 = never); never for critical codes.",
    )
