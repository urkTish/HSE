"""Phase 1 project settings, KPI targets, AI transfer approval and reference lists (spec
1-dashboard §3.10, §3.11, AI-14)."""

import uuid
from datetime import date, datetime, time

from pydantic import Field

from app.core.hse_enums import CaPriority, KpiMetric, ReferenceList, TreatmentClass
from app.core.ptw_enums import AuditFindingSeverity, PermitType
from app.schemas.common import ApiModel, PatchInput, StrictInput
from app.schemas.hse_common import DecimalStr, UserRef

MMDD = r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"


class HeatSeason(ApiModel):
    start: str = Field(pattern=MMDD, examples=["06-01"])
    end: str = Field(pattern=MMDD, examples=["09-30"])


class AiTransferApprovalRead(ApiModel):
    """AI-14: client approval of sending de-identified aggregated data to the AI provider."""

    approved_on: date
    approver_name: str
    approver_organisation: str
    reference: str | None
    notes: str | None
    recorded_by: UserRef
    recorded_at: datetime


class AiTransferApprovalCreate(StrictInput):
    approved_on: date
    approver_name: str = Field(min_length=1, max_length=120)
    approver_organisation: str = Field(min_length=1, max_length=150)
    reference: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=500)


class HseSettingsRead(ApiModel):
    """§3.10 (HSE Manager only to edit; audited). Bases come from Phase 0 settings."""

    project_id: uuid.UUID
    lost_days_cap: int = Field(description="180 (OSHA) or 0 = no cap.")
    fatality_lost_days_charge: int = Field(description="0 or 6000 (ANSI Z16.1).")
    include_commuting_in_rates: bool
    include_non_contractor_cases_in_rates: bool
    max_hours_per_person_day: int
    warn_hours_per_person_day: int
    daily_return_deadline: time = Field(description="Local time on the next day.")
    completeness_threshold_pct: int
    inspection_grace_days: int
    ca_due_days: dict[CaPriority, int]
    ca_max_extensions: int
    new_starter_days: int
    heat_season: HeatSeason
    low_exposure_hours: int
    leading_warning_drop_pct: int
    leading_warning_rise_pct: int
    kpi_targets: dict[KpiMetric, DecimalStr] = Field(
        description="Targets per metric; no RAG colour until set."
    )
    month_lock_day: int
    injury_identity_retention_years: int
    induction_register_from: date | None = Field(
        default=None,
        description="v1.1: K-38 counts passed general_site induction records from this date "
        "(daily-return inductions before it; null = daily returns only).",
    )
    ai_enabled: bool = Field(description="Effective: requested AND approval recorded (AI-14).")
    ai_requested: bool = Field(description="The HSE Manager's switch.")
    ai_transfer_approval: AiTransferApprovalRead | None
    updated_at: datetime | None
    updated_by: UserRef | None


class HseSettingsUpdate(PatchInput):
    """Partial update (capability 44). `ai_enabled = true` without a recorded approval →
    409 AI_TRANSFER_APPROVAL_REQUIRED."""

    non_nullable = frozenset(
        {
            "lost_days_cap",
            "fatality_lost_days_charge",
            "include_commuting_in_rates",
            "include_non_contractor_cases_in_rates",
            "max_hours_per_person_day",
            "warn_hours_per_person_day",
            "daily_return_deadline",
            "completeness_threshold_pct",
            "inspection_grace_days",
            "ca_due_days",
            "ca_max_extensions",
            "new_starter_days",
            "heat_season",
            "low_exposure_hours",
            "leading_warning_drop_pct",
            "leading_warning_rise_pct",
            "kpi_targets",
            "month_lock_day",
            "injury_identity_retention_years",
            "ai_enabled",
        }
    )

    lost_days_cap: int | None = Field(default=None, description="180 or 0.")
    fatality_lost_days_charge: int | None = Field(default=None, description="0 or 6000.")
    include_commuting_in_rates: bool | None = None
    include_non_contractor_cases_in_rates: bool | None = None
    max_hours_per_person_day: int | None = Field(default=None, ge=12, le=24)
    warn_hours_per_person_day: int | None = Field(default=None, ge=8, le=16)
    daily_return_deadline: time | None = None
    completeness_threshold_pct: int | None = Field(default=None, ge=50, le=100)
    inspection_grace_days: int | None = Field(default=None, ge=0, le=7)
    ca_due_days: dict[CaPriority, int] | None = Field(
        default=None, description="Each 1-90; all four priorities."
    )
    ca_max_extensions: int | None = Field(default=None, ge=0, le=5)
    new_starter_days: int | None = Field(default=None, ge=7, le=90)
    heat_season: HeatSeason | None = None
    low_exposure_hours: int | None = Field(default=None, ge=0)
    leading_warning_drop_pct: int | None = Field(default=None, ge=5, le=90)
    leading_warning_rise_pct: int | None = Field(default=None, ge=5, le=200)
    kpi_targets: dict[KpiMetric, DecimalStr] | None = None
    month_lock_day: int | None = Field(default=None, ge=1, le=28)
    injury_identity_retention_years: int | None = Field(default=None, ge=5, le=30)
    induction_register_from: date | None = Field(
        default=None, description="≥ project start; null switches K-38 back to daily returns."
    )
    ai_enabled: bool | None = None


class ReferenceItemRead(ApiModel):
    code: str
    label_en: str
    label_ar: str
    group: str | None = Field(
        default=None,
        description="treatment: first_aid | medical_treatment | diagnostic; root_cause: ICAM "
        "level AD/IT/TE/OF; severity: description key.",
    )
    treatment_class: TreatmentClass | None = None
    points: int | None = Field(default=None, description="airside_offence: ADP points.")
    immediate_suspension: bool | None = Field(
        default=None, description="airside_offence: suspends the ADP immediately (OFF-05/06)."
    )
    description_en: str | None = None
    description_ar: str | None = None
    permit_types: list[PermitType] | None = Field(
        default=None,
        description="PTW lists (checklists C/X, audit items A, hazards): types it applies to; "
        "null = all.",
    )
    default_severity: AuditFindingSeverity | None = Field(
        default=None, description="ptw_audit_item: default finding severity."
    )
    na_allowed: bool | None = Field(
        default=None, description="PTW checklists: n.a. may be answered."
    )
    routine: bool | None = Field(
        default=None, description="ptw_status_reason: routine (shift_end, midday_ban; SH-8)."
    )
    key_role: bool | None = Field(default=None, description="ptw_crew_role: key role (§3.6).")
    sort_order: int


class ReferenceListRead(ApiModel):
    name: ReferenceList
    items: list[ReferenceItemRead]


class ReferenceListsRead(ApiModel):
    lists: list[ReferenceListRead]


class ReferenceItemUpdate(PatchInput):
    """HSE Manager edits labels only; codes are immutable (§3.11)."""

    non_nullable = frozenset({"label_en", "label_ar"})

    label_en: str | None = Field(default=None, min_length=1, max_length=120)
    label_ar: str | None = Field(default=None, min_length=1, max_length=120)
    description_en: str | None = Field(default=None, max_length=300)
    description_ar: str | None = Field(default=None, max_length=300)
    points: int | None = Field(
        default=None, ge=0, le=24, description="airside_offence only (applies to new offences)."
    )
