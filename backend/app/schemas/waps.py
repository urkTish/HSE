"""Work-area access permits (WAP) and operational suspension events
(spec 2-access-permits §3.16, §3.17, §4.8, §5.8, §6.7)."""

import uuid
from datetime import date, datetime, time

from pydantic import Field

from app.core.access_enums import (
    CredentialReason,
    CrewMemberStatus,
    CrewRole,
    FodCheckResult,
    GateReasonCode,
    OpsEventSource,
    OpsEventType,
    QrTokenStatus,
    WapBlocker,
    WapStatus,
)
from app.core.hse_enums import Weekday
from app.schemas.access_common import QR_PAYLOAD_DOC, VehicleRef, WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import ApiWarning, DecimalStr, EngagementRef, SiteRef, UserRef, ZoneRef

WINDOW_DOC = (
    "Local times (Asia/Riyadh). end ≤ start crosses midnight and belongs to the start date: "
    "window on date d = [d + start, d + 1 + end) (WA-9, §6.7)."
)


class WapWindow(StrictInput):
    start_local: time = Field(examples=["23:00"])
    end_local: time = Field(examples=["05:00"])
    weekdays: list[Weekday] = Field(min_length=1, max_length=7, description="Sun..Sat.")


class WapWindowRead(ApiModel):
    start_local: time
    end_local: time
    weekdays: list[Weekday]
    crosses_midnight: bool


class CrewInput(StrictInput):
    worker_id: uuid.UUID
    crew_role: CrewRole
    escort_worker_id: uuid.UUID | None = Field(
        default=None, description="Required for members holding an escorted pass (WA-11)."
    )


class WapVehicleInput(StrictInput):
    vehicle_id: uuid.UUID
    escort_vehicle_id: uuid.UUID | None = Field(
        default=None, description="Listed vehicle with an AVP for the zone (WA-12, VP-8)."
    )
    height_limited_to_m: DecimalStr | None = Field(
        default=None,
        max_digits=6,
        decimal_places=2,
        description="Only when a height limiter is fitted and locked; ≤ max working height.",
    )


class FodCheckInput(StrictInput):
    """WA-17: required to resume or close a WAP with fod_handback_required."""

    checked_by_worker_id: uuid.UUID | None = None
    checked_by_user_id: uuid.UUID | None = Field(
        default=None, description="One of worker / user; default the caller."
    )
    checked_at: datetime = Field(description="≤ now.")
    result: FodCheckResult


class WapFields(StrictInput):
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(min_length=1, description="All of one site (WA-2).")
    engagement_id: uuid.UUID
    supervisor_worker_id: uuid.UUID
    scope_en: str = Field(min_length=1, max_length=500)
    scope_ar: str = Field(min_length=1, max_length=500)
    works_safety_plan_ref: str | None = Field(
        default=None, max_length=40, description="Required iff any zone in_movement_area (WA-6)."
    )
    valid_from: date
    valid_to: date = Field(description="valid_to − valid_from + 1 ≤ wap_max_days (WA-5).")
    windows: list[WapWindow] = Field(min_length=1, max_length=3, description=WINDOW_DOC)
    crew: list[CrewInput] = Field(min_length=1)
    vehicles: list[WapVehicleInput] = Field(default_factory=list)
    operator_permit_ref: str | None = Field(default=None, max_length=40)
    linked_ntm_ids: list[uuid.UUID] = Field(default_factory=list)
    linked_obs_ids: list[uuid.UUID] = Field(default_factory=list)
    conditions_en: str | None = Field(default=None, max_length=1000)
    conditions_ar: str | None = Field(default=None, max_length=1000)


class WapCreate(WapFields):
    """Capability 65 → draft. Contractor suspended/blacklisted → 403 CONTRACTOR_SUSPENDED
    (WA-3)."""


class WapUpdate(PatchInput):
    """Draft only. On Active/Approved WAPs use the crew/vehicle endpoints or a revision
    (WA-14)."""

    non_nullable = frozenset(
        {
            "zone_ids",
            "supervisor_worker_id",
            "scope_en",
            "scope_ar",
            "valid_from",
            "valid_to",
            "windows",
            "crew",
            "vehicles",
            "linked_ntm_ids",
            "linked_obs_ids",
        }
    )

    zone_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    supervisor_worker_id: uuid.UUID | None = None
    scope_en: str | None = Field(default=None, min_length=1, max_length=500)
    scope_ar: str | None = Field(default=None, min_length=1, max_length=500)
    works_safety_plan_ref: str | None = Field(default=None, max_length=40)
    valid_from: date | None = None
    valid_to: date | None = None
    windows: list[WapWindow] | None = Field(default=None, min_length=1, max_length=3)
    crew: list[CrewInput] | None = Field(default=None, min_length=1)
    vehicles: list[WapVehicleInput] | None = None
    operator_permit_ref: str | None = Field(default=None, max_length=40)
    linked_ntm_ids: list[uuid.UUID] | None = None
    linked_obs_ids: list[uuid.UUID] | None = None
    conditions_en: str | None = Field(default=None, max_length=1000)
    conditions_ar: str | None = Field(default=None, max_length=1000)


class WapRevisionCreate(StrictInput):
    """WA-14: changing zones, dates, windows or NOTAM/clearance links of an Approved/Active WAP
    creates a revision in Submitted; the current revision stays in force until the new one is
    Approved (then replaced) or Rejected. Returns the revision (201)."""

    zone_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    valid_from: date | None = None
    valid_to: date | None = None
    windows: list[WapWindow] | None = Field(default=None, min_length=1, max_length=3)
    linked_ntm_ids: list[uuid.UUID] | None = None
    linked_obs_ids: list[uuid.UUID] | None = None
    reason: str = Field(min_length=10, max_length=500)


class WapTransitionRequest(StrictInput):
    """§4.8 transitions (Approved → Active and Approved → Expired are system-only):

    * draft → submitted (65): crew ≥ 1 incl. a supervisor (CREW_INVALID); WA-5 dates
      (WAP_DURATION_EXCEEDED); WA-6 (WSP_REQUIRED); contractor not suspended; crew evaluated
    * submitted → draft (66): `reason` = return comment
    * submitted → approved (66): approver ≠ requester and not employed by the contractor or an
      ancestor (SOD_CONFLICT, WA-4); blockers allowed and recorded
    * submitted → rejected (66): `reason`
    * active → suspended (67): `reason_code`, `reason`
    * suspended → active (66, "resume"): blockers = [] (WAP_BLOCKED with meta.blockers);
      `fod_check` when fod_handback_required (FOD_HANDBACK_REQUIRED)
    * active/suspended → closed (68): `fod_check` when required
    * draft/submitted/approved → cancelled (68): `reason`
    """

    to_status: WapStatus
    reason: str | None = Field(default=None, max_length=500)
    reason_code: CredentialReason | None = None
    fod_check: FodCheckInput | None = None


class CrewMemberRead(ApiModel):
    worker: WorkerRef
    crew_role: CrewRole
    escort_worker_id: uuid.UUID | None
    status: CrewMemberStatus
    exclusion_reasons: list[GateReasonCode]
    escorted: bool = Field(description="Holds an escorted pass.")
    eligible_now: bool | None = Field(description="Last evaluation result.")
    evaluated_at: datetime | None


class WapVehicleRead(ApiModel):
    vehicle: VehicleRef
    escort_vehicle_id: uuid.UUID | None
    height_limited_to_m: DecimalStr | None
    avp_no: str | None
    status: CrewMemberStatus
    exclusion_reasons: list[GateReasonCode]


class WapBlockerRead(ApiModel):
    code: WapBlocker
    detail_en: str
    detail_ar: str
    ref: str | None = Field(examples=["NTM-ANIA-EXP-2026-0014"])


class FodCheckRead(ApiModel):
    checked_by_worker: WorkerRef | None
    checked_by_user: UserRef | None
    checked_at: datetime
    result: FodCheckResult


class WapWindowInstance(ApiModel):
    """A concrete window: local date it belongs to and its UTC bounds (§6.7)."""

    local_date: date
    start_utc: datetime
    end_utc: datetime


class WapRead(Timestamps):
    """Crew names (WorkerRef names) only for capability 46; others (e.g. Viewer/Client) get
    `crew: []` and only `crew_count` / `vehicle_count` (WA-19)."""

    id: uuid.UUID
    wap_no: str = Field(examples=["WAP-ANIA-EXP-2026-0031"])
    revision_no: int
    revision_of_id: uuid.UUID | None
    pending_revision_id: uuid.UUID | None
    project_id: uuid.UUID
    site: SiteRef
    zones: list[ZoneRef]
    engagement: EngagementRef
    requested_by: UserRef
    supervisor: WorkerRef | None
    scope_en: str
    scope_ar: str
    works_safety_plan_ref: str | None
    valid_from: date
    valid_to: date
    windows: list[WapWindowRead]
    current_window: WapWindowInstance | None = Field(description="Window in force now, if any.")
    next_window: WapWindowInstance | None
    crew_count: int
    vehicle_count: int
    crew: list[CrewMemberRead]
    vehicles: list[WapVehicleRead]
    operator_permit_ref: str | None
    linked_ntm_ids: list[uuid.UUID]
    linked_obs_ids: list[uuid.UUID]
    fod_handback_required: bool
    fod_check: FodCheckRead | None
    conditions_en: str | None
    conditions_ar: str | None
    approved_by: UserRef | None
    approved_at: datetime | None
    blockers: list[WapBlockerRead] = Field(description="WA-13, recomputed on every read.")
    suspension_reason: CredentialReason | None
    status: WapStatus
    warnings: list[ApiWarning] = Field(default_factory=list)


class WapPage(Page[WapRead]):
    pass


class WapPrintRead(ApiModel):
    """WA-18: crew names and worker_no only — never ID numbers."""

    wap_id: uuid.UUID
    wap_no: str
    qr_payload: str = Field(pattern=r"^HSE2:WP:[A-Za-z0-9_-]{22}$", description=QR_PAYLOAD_DOC)
    printed_ref: str = Field(examples=["WAP-ANIA-EXP-2026-0031"])
    token_status: QrTokenStatus
    wap: WapRead


class WapBoardZone(ApiModel):
    zone: ZoneRef
    waps: list[WapRead]
    ops_suspension_active: bool


class WapBoardResponse(ApiModel):
    """Today's WAP board per zone (§8.4)."""

    project_id: uuid.UUID
    date: date
    zones: list[WapBoardZone]


# ---- operational suspension events --------------------------------------------------------------


class OpsEventCreate(StrictInput):
    """Capability 67. lvp / dust_sandstorm default to every zone of the site with
    lvp_withdrawal_required (the declarer may add zones, not remove them, WA-16). Starting the
    event suspends every Active WAP in those zones (`ops_suspension`) within 60 s (WA-15)."""

    type: OpsEventType
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(default_factory=list)
    source: OpsEventSource
    source_ref: str = Field(min_length=1, max_length=40)
    started_at: datetime | None = Field(default=None, description="Default now.")
    notes: str | None = Field(default=None, max_length=500)


class OpsEventUpdate(PatchInput):
    """Add zones (never remove defaults → 422 OPS_ZONES_LOCKED)."""

    zone_ids: list[uuid.UUID] | None = None
    notes: str | None = Field(default=None, max_length=500)


class OpsEventEnd(StrictInput):
    """Ending does not resume WAPs (each is resumed by capability 66)."""

    ended_at: datetime | None = Field(default=None, description="Default now.")


class OpsEventRead(Timestamps):
    id: uuid.UUID
    ops_no: str = Field(examples=["OPS-ANIA-EXP-2026-0009"])
    project_id: uuid.UUID
    site: SiteRef
    type: OpsEventType
    zones: list[ZoneRef]
    default_zone_ids: list[uuid.UUID]
    source: OpsEventSource
    source_ref: str
    started_at: datetime
    ended_at: datetime | None
    active: bool
    declared_by: UserRef
    notes: str | None
    suspended_wap_ids: list[uuid.UUID]


class OpsEventPage(Page[OpsEventRead]):
    pass
