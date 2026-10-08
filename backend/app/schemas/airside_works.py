"""NOTAM works clearances and obstacle/crane clearances
(spec 2-access-permits §3.14, §3.15, §4.6, §4.7, §5.7, §6.4)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import (
    ClearanceReason,
    NotamStatus,
    NotamType,
    ObstacleCondition,
    ObstacleDecision,
    ObstacleEquipmentType,
    ObstacleStatus,
    OlsSurface,
    WorksImpact,
)
from app.schemas.access_common import Metres, VehicleRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import ApiWarning, DecimalStr, EngagementRef, UserRef, ZoneRef

NOTAM_NO = r"^[A-Z]\d{4}/\d{2}$"
UTC_DOC = "UTC (NT-3). Shown as NOTAM format YYMMDDHHMM UTC and local Asia/Riyadh."

# ---- NOTAM works clearance ----------------------------------------------------------------------


class NotamRequestCreate(StrictInput):
    """Capability 69 → draft; 422 NOT_AIRPORT_PROJECT. Zones must be airside with
    notam_required_for_works = true."""

    zone_ids: list[uuid.UUID] = Field(min_length=1)
    engagement_id: uuid.UUID | None = Field(default=None, description="Requesting contractor.")
    works_impact: list[WorksImpact] = Field(min_length=1)
    description_en: str = Field(min_length=1, max_length=1000)
    description_ar: str = Field(min_length=1, max_length=1000)
    requested_start_utc: datetime = Field(description=UTC_DOC)
    requested_end_utc: datetime = Field(description=UTC_DOC)
    schedule_text: str | None = Field(
        default=None, max_length=200, examples=["DAILY 2000-0200"], description="Item D."
    )


class NotamRequestUpdate(PatchInput):
    """Draft only."""

    non_nullable = frozenset(
        {
            "zone_ids",
            "works_impact",
            "description_en",
            "description_ar",
            "requested_start_utc",
            "requested_end_utc",
        }
    )

    zone_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    works_impact: list[WorksImpact] | None = Field(default=None, min_length=1)
    description_en: str | None = Field(default=None, min_length=1, max_length=1000)
    description_ar: str | None = Field(default=None, min_length=1, max_length=1000)
    requested_start_utc: datetime | None = None
    requested_end_utc: datetime | None = None
    schedule_text: str | None = Field(default=None, max_length=200)


class NotamTransitionRequest(StrictInput):
    """§4.6 transitions:

    * draft → submitted_to_ops (69): sets submitted_to_ops_at = now; NT-2 lead check — a
      shorter lead needs `late_justification` (else 422 LATE_JUSTIFICATION_REQUIRED) and sets
      late_request = true
    * submitted_to_ops → requested_from_ais (70)
    * requested_from_ais → issued (70): `notam_number` (unique per project), `notam_type`,
      `effective_from_utc`, `effective_to_utc`, optional `item_e_text`
    * submitted_to_ops / requested_from_ais → rejected (70): `reason`
    * issued → cancelled (70): `reason`; suspends linked Active WAPs (NT-5, WA-15)
    * issued → replaced: use POST /notam-requests/{id}/replace.
    """

    to_status: NotamStatus
    reason: str | None = Field(default=None, max_length=500)
    late_justification: str | None = Field(default=None, min_length=10, max_length=500)
    notam_number: str | None = Field(default=None, pattern=NOTAM_NO, examples=["A0999/26"])
    notam_type: NotamType | None = None
    effective_from_utc: datetime | None = None
    effective_to_utc: datetime | None = None
    item_e_text: str | None = Field(default=None, max_length=2000)


class NotamReplaceRequest(StrictInput):
    """issued → replaced (70): creates a new Issued record (notam_type R, replaces_ntm_id) that
    is auto-linked to the WAPs of the replaced record (NT-5). Returns the new record (201)."""

    notam_number: str = Field(pattern=NOTAM_NO)
    effective_from_utc: datetime
    effective_to_utc: datetime
    item_e_text: str | None = Field(default=None, max_length=2000)
    schedule_text: str | None = Field(default=None, max_length=200)


class NotamRequestRead(Timestamps):
    id: uuid.UUID
    ntm_no: str = Field(examples=["NTM-ANIA-EXP-2026-0012"])
    project_id: uuid.UUID
    zones: list[ZoneRef]
    engagement: EngagementRef | None
    works_impact: list[WorksImpact]
    description_en: str
    description_ar: str
    requested_start_utc: datetime
    requested_end_utc: datetime
    schedule_text: str | None
    required_lead_days: int = Field(description="notam_request_lead_days or airac_lead_days.")
    submitted_to_ops_at: datetime | None
    late_request: bool
    late_justification: str | None
    notam_number: str | None
    notam_type: NotamType | None
    effective_from_utc: datetime | None
    effective_to_utc: datetime | None
    effective_from_notam: str | None = Field(examples=["2610012000"], description="YYMMDDHHMM.")
    effective_to_notam: str | None
    item_e_text: str | None
    replaces_ntm_id: uuid.UUID | None
    replaced_by_ntm_id: uuid.UUID | None
    in_effect: bool = Field(description="Issued and effective_from ≤ now ≤ effective_to.")
    linked_wap_ids: list[uuid.UUID]
    requested_by: UserRef
    status: NotamStatus
    warnings: list[ApiWarning] = Field(default_factory=list)


class NotamRequestPage(Page[NotamRequestRead]):
    pass


# ---- obstacle / crane clearance -----------------------------------------------------------------


class ObstacleFields(StrictInput):
    zone_id: uuid.UUID | None = Field(default=None, description="Required on airport projects.")
    engagement_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = Field(
        default=None, description="One of vehicle_id / equipment_desc is required."
    )
    equipment_desc: str | None = Field(default=None, max_length=150)
    equipment_item_id: uuid.UUID | None = Field(
        default=None,
        description="v1.2 (4-third-party-cert CF-4): Phase 4 item whose height changes "
        "re-check this clearance (OB-6).",
    )
    equipment_type: ObstacleEquipmentType
    location_lat: DecimalStr = Field(max_digits=9, decimal_places=6)
    location_lng: DecimalStr = Field(max_digits=9, decimal_places=6)
    location_desc: str = Field(min_length=1, max_length=150)
    ground_elevation_m_amsl: Metres = Field(le=3000)
    max_height_m_agl: Metres = Field(
        description="Highest point in the planned configuration incl. load/rigging (OB-2); "
        "≥ the linked vehicle's max working height."
    )
    ols_surface: OlsSurface | None = Field(
        default=None, description="Required on airport projects."
    )
    ols_limit_m_amsl: Metres | None = Field(
        default=None, description="Default = zone.ols_height_limit_m_amsl."
    )
    ols_source_ref: str | None = Field(
        default=None, max_length=40, description="Required when the limit differs from the zone."
    )
    requested_from: date
    requested_to: date


class ObstacleCreate(ObstacleFields):
    """Capability 71 → draft (any project, OB-1). The server computes top elevation, margin,
    penetration and reasons (§6.4, OB-3)."""


class ObstacleUpdate(PatchInput):
    """Draft only."""

    zone_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = None
    equipment_desc: str | None = Field(default=None, max_length=150)
    equipment_item_id: uuid.UUID | None = None
    equipment_type: ObstacleEquipmentType | None = None
    location_lat: DecimalStr | None = Field(default=None, max_digits=9, decimal_places=6)
    location_lng: DecimalStr | None = Field(default=None, max_digits=9, decimal_places=6)
    location_desc: str | None = Field(default=None, min_length=1, max_length=150)
    ground_elevation_m_amsl: Metres | None = None
    max_height_m_agl: Metres | None = None
    ols_surface: OlsSurface | None = None
    ols_limit_m_amsl: Metres | None = None
    ols_source_ref: str | None = Field(default=None, max_length=40)
    requested_from: date | None = None
    requested_to: date | None = None


class ObstaclePreviewRequest(ObstacleFields):
    """Same body as create; nothing is saved."""

    project_id: uuid.UUID


class HeightFigures(ApiModel):
    """§6.4. Metres and feet (÷ 0.3048), 2 dp, half-up (OB-9)."""

    top_elevation_m_amsl: DecimalStr
    top_elevation_ft_amsl: DecimalStr
    ols_limit_m_amsl: DecimalStr | None
    margin_m: DecimalStr | None = Field(description="Negative = penetration.")
    margin_ft: DecimalStr | None
    penetration_m: DecimalStr
    penetration_ft: DecimalStr
    max_height_m_agl: DecimalStr
    max_height_ft_agl: DecimalStr
    zone_max_equipment_height_m_agl: DecimalStr | None
    clearance_reasons: list[ClearanceReason]
    clearance_required: bool


class ObstacleTransitionRequest(StrictInput):
    """§4.7 transitions:

    * draft → submitted (71): OB-5 lead check — shorter lead needs `late_justification`
      (LATE_JUSTIFICATION_REQUIRED), sets late_request; `authority_ref` optional
    * approved* → suspended (72): `reason`; suspended → approved* (72): `reason`
      (system suspensions under OB-7 lift automatically)
    * approved* → withdrawn (71 own / 72): `reason`
    * submitted → approved / approved_with_conditions / rejected: use POST …/decision.
    """

    to_status: ObstacleStatus
    reason: str | None = Field(default=None, max_length=500)
    late_justification: str | None = Field(default=None, min_length=10, max_length=500)
    authority_ref: str | None = Field(default=None, max_length=40)


class ObstacleDecisionRequest(StrictInput):
    """Capability 72. With `ols_penetration`, an approval must include conditions
    notam_required and obstruction_light and an authority_ref (422 OB_CONDITIONS_REQUIRED,
    OB-4). notam_required needs linked_ntm_ids (OB-7)."""

    decision: ObstacleDecision
    authority_ref: str | None = Field(default=None, max_length=40)
    approved_max_height_m_agl: Metres | None = Field(default=None, description="≤ requested.")
    approved_top_m_amsl: Metres | None = None
    conditions: list[ObstacleCondition] = Field(default_factory=list)
    conditions_text: str | None = Field(default=None, max_length=1000)
    valid_from: date | None = Field(default=None, description="Within the requested window.")
    valid_to: date | None = None
    linked_ntm_ids: list[uuid.UUID] = Field(default_factory=list)


class ObstacleRead(Timestamps):
    id: uuid.UUID
    obs_no: str = Field(examples=["OBS-ANIA-EXP-2026-0004"])
    project_id: uuid.UUID
    zone: ZoneRef | None
    engagement: EngagementRef | None
    vehicle: VehicleRef | None
    equipment_desc: str | None
    equipment_item_id: uuid.UUID | None = Field(default=None, description="v1.2 (CF-4).")
    equipment_type: ObstacleEquipmentType
    location_lat: DecimalStr
    location_lng: DecimalStr
    location_desc: str
    ground_elevation_m_amsl: DecimalStr
    ols_surface: OlsSurface | None
    ols_source_ref: str | None
    heights: HeightFigures
    requested_from: date
    requested_to: date
    submitted_at: datetime | None
    late_request: bool
    late_justification: str | None
    authority_ref: str | None
    decision: ObstacleDecision | None
    approved_max_height_m_agl: DecimalStr | None
    approved_max_height_ft_agl: DecimalStr | None
    approved_top_m_amsl: DecimalStr | None
    conditions: list[ObstacleCondition]
    conditions_text: str | None
    valid_from: date | None
    valid_to: date | None
    linked_ntm_ids: list[uuid.UUID]
    active_today: bool = Field(description="Approved* and valid today.")
    system_suspended: bool = Field(description="OB-7 suspension (lifts automatically).")
    requested_by: UserRef
    status: ObstacleStatus
    warnings: list[ApiWarning] = Field(default_factory=list)


class ObstaclePage(Page[ObstacleRead]):
    pass
