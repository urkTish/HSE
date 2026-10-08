"""PTW appointments — functional authorisations per project (spec 3-ptw §3.4, §4.7, PR-1…PR-10)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.ptw_enums import (
    AppointmentDiscipline,
    AppointmentFunction,
    AppointmentStatus,
    PermitType,
)
from app.schemas.access_common import WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, SiteRef, UserRef, ZoneRef
from app.schemas.ptw_common import PermitRef


class AppointmentCreate(StrictInput):
    """Capability 100; `issuer` appointments by the HSE Manager only (403
    ISSUER_APPOINTMENT_MANAGER_ONLY, AC2). Exactly one holder: issuer, area_authority and
    isolation_authority need a user; gas_tester and authorised_person a worker or a user.
    valid_to ≤ valid_from + appointment_max_months (PR-7). Hook requirements (PTW-ISSUER,
    LOTO-AUTHORITY) are evaluated at creation (warn → HOOK_NOT_AVAILABLE warning)."""

    function: AppointmentFunction
    discipline: AppointmentDiscipline | None = Field(
        default=None, description="Required for isolation_authority and authorised_person."
    )
    holder_user_id: uuid.UUID | None = None
    holder_worker_id: uuid.UUID | None = None
    permit_types: list[PermitType] = Field(min_length=1)
    site_ids: list[uuid.UUID] = Field(min_length=1)
    zone_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Empty = all zones of the sites."
    )
    basis: str = Field(
        min_length=1,
        max_length=300,
        description="Course, assessment or certificate refs. Do not enter ID numbers.",
    )
    valid_from: date
    valid_to: date


class AppointmentUpdate(PatchInput):
    """Capability 100 (issuer appointments: HSE Manager). Changes are re-evaluated on every
    non-terminal permit where the holder acts (PR-8)."""

    non_nullable = frozenset({"permit_types", "site_ids", "zone_ids", "basis", "valid_to"})

    permit_types: list[PermitType] | None = Field(default=None, min_length=1)
    site_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    zone_ids: list[uuid.UUID] | None = None
    basis: str | None = Field(default=None, min_length=1, max_length=300)
    valid_to: date | None = None


class AppointmentTransition(StrictInput):
    """§4.7: active ⇄ suspended, active/suspended → revoked (terminal). Expired is set by the
    daily job. Reason required for suspend / revoke."""

    to_status: AppointmentStatus
    reason: str | None = Field(default=None, min_length=10, max_length=500)


class AppointmentRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    appointment_no: str = Field(examples=["APT-ANIA-EXP-0011"])
    function: AppointmentFunction
    discipline: AppointmentDiscipline | None
    holder_user: UserRef | None
    holder_worker: WorkerRef | None = Field(description="Names only with capability 46 (PT-19).")
    permit_types: list[PermitType]
    sites: list[SiteRef]
    zones: list[ZoneRef] = Field(description="Empty = all zones of the sites.")
    basis: str
    valid_from: date
    valid_to: date
    days_left: int = Field(description="valid_to − today (negative = past).")
    status: AppointmentStatus
    status_reason: str | None
    appointed_by: UserRef
    live_permits: list[PermitRef] = Field(
        description="Non-terminal permits where the holder acts under this appointment."
    )
    warnings: list[ApiWarning] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


AppointmentPage = Page[AppointmentRead]
