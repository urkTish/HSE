"""SIMOPS conflict check, conflicts and coordination records (spec 3-ptw §3.12, §4.8, §5.6,
§6.4, §6.5)."""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.ptw_enums import (
    CoordinationSignerRole,
    CoordinationStatus,
    DistanceBasis,
    PermitType,
    SimopsCheckTrigger,
    SimopsConflictStatus,
    SimopsResult,
)
from app.schemas.common import ApiModel, Page, StrictInput
from app.schemas.hse_common import DecimalStr, UserRef
from app.schemas.ptw_common import CoSignature, GridM, PermitRef, PermitWindow

# ---- check --------------------------------------------------------------------------------------


class SimopsMatch(ApiModel):
    """One rule match between the checked permit (A or B side) and another permit."""

    rule_code: str = Field(examples=["SM-R05b"])
    result: SimopsResult
    other_permit: PermitRef
    checked_is_a: bool = Field(description="True when the checked permit is rule side A.")
    distance_m: DecimalStr | None = Field(description="1 dp display; compared unrounded (§6.4).")
    distance_basis: DistanceBasis
    vertical_note: str | None = Field(default=None, examples=["A above B (152.00 ≥ 148.00 + 2.0)"])
    overlap_from: datetime
    overlap_to: datetime
    required_controls_en: str | None
    required_controls_ar: str | None
    conflict_id: uuid.UUID | None = Field(description="Stored conflict (null in a preview).")
    conflict_status: SimopsConflictStatus | None
    coordinated: bool


class SimopsCheckResult(ApiModel):
    """SM-1…SM-8. `prohibited` blocks Approve and Issue (SIMOPS_PROHIBITED); `conditional`
    blocks Issue until a coordination record is signed (SIMOPS_COORDINATION_REQUIRED)."""

    trigger: SimopsCheckTrigger
    checked_at: datetime
    permit: PermitRef | None = Field(description="Null for a preview of unsaved data.")
    matches: list[SimopsMatch]
    prohibited: int
    conditional: int
    resolved_by_change: list[str] = Field(
        description="Conflict numbers that no longer match after this check."
    )


class SimopsPreviewRequest(StrictInput):
    """Preview for the permit form (nothing stored). Same inputs as the permit fields that the
    check uses."""

    permit_id: uuid.UUID | None = Field(
        default=None, description="Exclude this permit (editing an existing one)."
    )
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)
    engagement_id: uuid.UUID
    work_types: list[PermitType] = Field(min_length=1)
    grid_x_m: GridM | None = None
    grid_y_m: GridM | None = None
    elevation_m: DecimalStr | None = Field(default=None, max_digits=7, decimal_places=2)
    valid_from_at: datetime
    valid_to_at: datetime
    windows: list[PermitWindow] = Field(min_length=1, max_length=3)
    flammables_in_use: bool = False
    combustion_engine_plant: bool = False
    hot_work_height_above_floor_m: DecimalStr | None = Field(
        default=None, max_digits=7, decimal_places=2
    )
    lifting_landing_grid_x_m: GridM | None = None
    lifting_landing_grid_y_m: GridM | None = None
    lifting_exclusion_radius_m: DecimalStr | None = Field(
        default=None, max_digits=7, decimal_places=1
    )
    lifting_appliance_grid_x_m: GridM | None = None
    lifting_appliance_grid_y_m: GridM | None = None
    lifting_slew_radius_m: DecimalStr | None = Field(default=None, max_digits=7, decimal_places=1)
    radiography_planned_barrier_m: DecimalStr | None = Field(
        default=None, max_digits=7, decimal_places=1
    )
    excavation_max_depth_m: DecimalStr | None = Field(default=None, max_digits=7, decimal_places=2)
    electrical_energized: bool = False


# ---- conflicts and coordination -----------------------------------------------------------------


class CoordinationSignature(ApiModel):
    role: CoordinationSignerRole
    user: UserRef
    signed_at: datetime | None


class CoordinationRead(ApiModel):
    """§3.12 coordination record (conditional conflicts only). Signed by the issuers of both
    permits (one signature when the same user) and the area authority of permit A's zone."""

    id: uuid.UUID
    conflict_id: uuid.UUID
    agreed_controls_en: str
    agreed_controls_ar: str | None
    signatures: list[CoordinationSignature]
    status: CoordinationStatus
    signed_at: datetime | None = Field(description="When the last required signature was made.")
    valid_until: datetime = Field(description="Earliest valid_to of the two permits.")
    created_by: UserRef
    created_at: datetime


class SimopsConflictRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    conflict_no: str = Field(examples=["SIM-RBT-52-2026-0021"])
    permit_a: PermitRef
    permit_b: PermitRef
    rule_code: str
    result: SimopsResult
    distance_m: DecimalStr | None
    distance_basis: DistanceBasis
    overlap_from: datetime | None
    overlap_to: datetime | None
    required_controls_en: str | None
    required_controls_ar: str | None
    status: SimopsConflictStatus
    detected_at: datetime
    resolved_at: datetime | None
    coordination: CoordinationRead | None
    required_signers: list[CoordinationSignature] = Field(
        description="Who must sign (issuer A, issuer B, area authority); signed_at null = open."
    )


SimopsConflictPage = Page[SimopsConflictRead]


class CoordinationCreate(StrictInput):
    """Capability 97, signed (PT-15). The caller's signature is recorded with the record;
    others sign via POST /simops-coordinations/{id}/sign or `cosigners` here."""

    agreed_controls_en: str = Field(min_length=30, max_length=1000)
    agreed_controls_ar: str | None = Field(default=None, max_length=1000)
    cosigners: list[CoSignature] = Field(default_factory=list, max_length=2)


class CoordinationSignInput(StrictInput):
    note: str | None = Field(default=None, max_length=300)
