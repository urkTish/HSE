"""Phase 2 project settings (spec 2-access-permits §3.22; HSE Manager only, capability 80,
audited) and the hook-requirement maps of HK-2."""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.access_enums import (
    AreaCategory,
    CrewRole,
    HookKind,
    HookPolicy,
    SuspendedContractorGateMode,
    VehicleCategory,
)
from app.schemas.access_common import HookRequirement, HookRequirementRead
from app.schemas.common import ApiModel, PatchInput
from app.schemas.hse_common import DecimalStr, UserRef
from app.schemas.inductions import HookProviderInfo


class AccessSettingsRead(ApiModel):
    """Every key of §3.22 (except induction_register_from, which is a Phase 1 setting on
    /projects/{id}/hse-settings, 1-dashboard v1.1)."""

    project_id: uuid.UUID
    induction_pass_mark_pct: int
    induction_retest_wait_hours: int
    induction_max_attempts_30d: int
    reinduction_absence_days: int | None
    reinduction_grace_days: int
    id_expiry_blocks_access: bool
    pass_max_validity_months: int
    temp_escorted_pass_max_days: int
    visitor_pass_max_days: int
    bg_recheck_months: int
    application_stale_days: int
    id_copy_retention_days: int
    pass_return_days: int
    lost_report_hours: int
    escort_ratio_max_apron: int
    escort_ratio_max_manoeuvring: int
    escort_ratio_max_other: int
    vehicle_escort_ratio_max_apron: int
    vehicle_escort_ratio_max_manoeuvring: int
    escort_pairing_seconds: int
    adp_validity_months: int
    adp_theory_pass_pct: int
    adp_points_threshold: int
    adp_points_window_days: int
    adp_suspension_days: int
    adp_revoke_after_suspensions: int
    adp_revoke_after_suspensions_window_days: int
    avp_validity_months: int
    wap_max_days: int
    wap_exit_grace_minutes: int
    notam_request_lead_days: int
    airac_lead_days: int
    obstacle_clearance_lead_days: int
    obstacle_height_threshold_m: DecimalStr
    ols_buffer_m: DecimalStr
    raised_suspension_max_hours: int
    suspended_contractor_gate: SuspendedContractorGateMode
    hook_policy: dict[HookKind, HookPolicy]
    hook_providers: list[HookProviderInfo]
    alert_schedule_long_days: list[int]
    alert_schedule_short_hours: list[int]
    gate_log_retention_months: int
    worker_retention_years: int
    induction_coverage_warning_pct: int
    hook_requirements_by_adp_category: dict[AreaCategory, list[HookRequirementRead]] = Field(
        description="HK-2, e.g. manoeuvring → training_course AIRSIDE-DRV."
    )
    hook_requirements_by_vehicle_category: dict[VehicleCategory, list[HookRequirementRead]] = Field(
        description="HK-2, e.g. mobile_crane → equipment_certificate CRANE-TPI."
    )
    hook_requirements_by_crew_role: dict[CrewRole, list[HookRequirementRead]] = Field(
        description="HK-2, e.g. banksman → personnel_certificate BANKSMAN."
    )
    updated_at: datetime | None
    updated_by: UserRef | None


class AccessSettingsUpdate(PatchInput):
    """Partial update (capability 80, audited). Ranges per §3.22. Switching a hook kind to
    `block` without a registered provider → 422 HOOK_PROVIDER_MISSING (HK-4)."""

    non_nullable = frozenset(
        {
            "induction_pass_mark_pct",
            "induction_retest_wait_hours",
            "induction_max_attempts_30d",
            "reinduction_grace_days",
            "id_expiry_blocks_access",
            "pass_max_validity_months",
            "temp_escorted_pass_max_days",
            "visitor_pass_max_days",
            "bg_recheck_months",
            "application_stale_days",
            "id_copy_retention_days",
            "pass_return_days",
            "lost_report_hours",
            "escort_ratio_max_apron",
            "escort_ratio_max_manoeuvring",
            "escort_ratio_max_other",
            "vehicle_escort_ratio_max_apron",
            "vehicle_escort_ratio_max_manoeuvring",
            "escort_pairing_seconds",
            "adp_validity_months",
            "adp_theory_pass_pct",
            "adp_points_threshold",
            "adp_points_window_days",
            "adp_suspension_days",
            "adp_revoke_after_suspensions",
            "adp_revoke_after_suspensions_window_days",
            "avp_validity_months",
            "wap_max_days",
            "wap_exit_grace_minutes",
            "notam_request_lead_days",
            "airac_lead_days",
            "obstacle_clearance_lead_days",
            "obstacle_height_threshold_m",
            "ols_buffer_m",
            "raised_suspension_max_hours",
            "suspended_contractor_gate",
            "hook_policy",
            "alert_schedule_long_days",
            "alert_schedule_short_hours",
            "gate_log_retention_months",
            "worker_retention_years",
            "induction_coverage_warning_pct",
            "hook_requirements_by_adp_category",
            "hook_requirements_by_vehicle_category",
            "hook_requirements_by_crew_role",
        }
    )

    induction_pass_mark_pct: int | None = Field(default=None, ge=50, le=100)
    induction_retest_wait_hours: int | None = Field(default=None, ge=0, le=72)
    induction_max_attempts_30d: int | None = Field(default=None, ge=1, le=5)
    reinduction_absence_days: int | None = Field(
        default=None, ge=30, le=365, description="null = off."
    )
    reinduction_grace_days: int | None = Field(default=None, ge=0, le=90)
    id_expiry_blocks_access: bool | None = None
    pass_max_validity_months: int | None = Field(default=None, ge=1, le=36)
    temp_escorted_pass_max_days: int | None = Field(default=None, ge=1, le=90)
    visitor_pass_max_days: int | None = Field(default=None, ge=1, le=7)
    bg_recheck_months: int | None = Field(default=None, ge=12, le=60)
    application_stale_days: int | None = Field(default=None, ge=7, le=90)
    id_copy_retention_days: int | None = Field(default=None, ge=0, le=180)
    pass_return_days: int | None = Field(default=None, ge=1, le=14)
    lost_report_hours: int | None = Field(default=None, ge=1, le=72)
    escort_ratio_max_apron: int | None = Field(default=None, ge=1, le=10)
    escort_ratio_max_manoeuvring: int | None = Field(default=None, ge=1, le=10)
    escort_ratio_max_other: int | None = Field(default=None, ge=1, le=10)
    vehicle_escort_ratio_max_apron: int | None = Field(default=None, ge=1, le=5)
    vehicle_escort_ratio_max_manoeuvring: int | None = Field(default=None, ge=1, le=5)
    escort_pairing_seconds: int | None = Field(default=None, ge=30, le=600)
    adp_validity_months: int | None = Field(default=None, ge=6, le=36)
    adp_theory_pass_pct: int | None = Field(default=None, ge=50, le=100)
    adp_points_threshold: int | None = Field(default=None, ge=3, le=24)
    adp_points_window_days: int | None = Field(default=None, ge=90, le=730)
    adp_suspension_days: int | None = Field(default=None, ge=7, le=180)
    adp_revoke_after_suspensions: int | None = Field(default=None, ge=1, le=5)
    adp_revoke_after_suspensions_window_days: int | None = Field(default=None, ge=365, le=1095)
    avp_validity_months: int | None = Field(default=None, ge=1, le=24)
    wap_max_days: int | None = Field(default=None, ge=1, le=90)
    wap_exit_grace_minutes: int | None = Field(default=None, ge=0, le=60)
    notam_request_lead_days: int | None = Field(default=None, ge=1, le=30)
    airac_lead_days: int | None = Field(default=None, ge=28, le=84)
    obstacle_clearance_lead_days: int | None = Field(default=None, ge=3, le=90)
    obstacle_height_threshold_m: DecimalStr | None = Field(
        default=None, ge=10, le=150, max_digits=5, decimal_places=2
    )
    ols_buffer_m: DecimalStr | None = Field(
        default=None, ge=0, le=30, max_digits=4, decimal_places=2
    )
    raised_suspension_max_hours: int | None = Field(default=None, ge=4, le=168)
    suspended_contractor_gate: SuspendedContractorGateMode | None = None
    hook_policy: dict[HookKind, HookPolicy] | None = None
    alert_schedule_long_days: list[int] | None = Field(default=None, min_length=1, max_length=6)
    alert_schedule_short_hours: list[int] | None = Field(default=None, min_length=1, max_length=6)
    gate_log_retention_months: int | None = Field(default=None, ge=3, le=60)
    worker_retention_years: int | None = Field(default=None, ge=1, le=15)
    induction_coverage_warning_pct: int | None = Field(default=None, ge=80, le=100)
    hook_requirements_by_adp_category: dict[AreaCategory, list[HookRequirement]] | None = None
    hook_requirements_by_vehicle_category: dict[VehicleCategory, list[HookRequirement]] | None = (
        None
    )
    hook_requirements_by_crew_role: dict[CrewRole, list[HookRequirement]] | None = None
