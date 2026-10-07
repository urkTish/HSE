"""Building blocks shared by the Phase 2 schemas (spec 2-access-permits)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.core.access_enums import (
    CredentialAction,
    CredentialKind,
    CredentialReason,
    CustodyStatus,
    HookKind,
    LimitingFactor,
    SuspensionState,
    ValidityStatus,
    VehicleCategory,
    WorkerStatus,
)
from app.schemas.common import ApiModel, StrictInput
from app.schemas.hse_common import DecimalStr, UserRef

Metres = Annotated[DecimalStr, Field(ge=Decimal(0), max_digits=7, decimal_places=2)]
"""Height/elevation in metres, 2 dp; JSON string on output."""

MASKED_ID_DOC = (
    "Masked per WK-4: Iqama/National ID first digit + 7 `*` + last 2 (`2*******02`); GCC "
    "ID/passport first 2 + `*` per hidden char + last 2 (`TE*****12`). The full value is only "
    "returned by POST /workers/{id}/id-number/unmask (capability 48, audited)."
)

QR_PAYLOAD_DOC = (
    "`HSE2:<AC|VS|WP>:<22-char base64url token>` — no name, ID or other personal data (§3.20). "
    "Encode as a QR code; print `printed_ref` beside it for manual fallback."
)


class WorkerRef(ApiModel):
    """A worker as shown in lists of other records. Names are present only for callers with
    capability 46 on the record's project (WA-19, KA-4); otherwise only worker_no."""

    id: uuid.UUID
    worker_no: str = Field(examples=["WKR-000002"])
    full_name_en: str | None = None
    full_name_ar: str | None = None
    status: WorkerStatus


class VehicleRef(ApiModel):
    id: uuid.UUID
    vehicle_no: str = Field(examples=["VEH-0002"])
    fleet_no: str = Field(examples=["GP-LV-07"])
    category: VehicleCategory


class HookRequirement(StrictInput):
    """HK-2: a requirement owned by a later phase (codes are free text until those modules
    publish their lists)."""

    kind: HookKind
    code: str = Field(min_length=1, max_length=40, examples=["AVSEC-AWR"])


class HookRequirementRead(ApiModel):
    kind: HookKind
    code: str


class CredentialSuspension(ApiModel):
    """An open suspension on a credential (LC-3, LC-6). A credential returns to active only
    when no open suspension remains."""

    state: SuspensionState
    reason_code: CredentialReason
    reason_text: str | None
    raised_by: UserRef | None = Field(description="Null = system.")
    raised_at: datetime
    expires_at: datetime | None = Field(
        description="Raised suspensions: lifts automatically at this time unless confirmed."
    )
    suspension_end: date | None = Field(
        default=None,
        description="DP-8 points suspensions: last day; reinstatement allowed from the next day.",
    )


class CredentialEventRead(ApiModel):
    """§3.18 log entry."""

    id: uuid.UUID
    credential_kind: CredentialKind
    credential_id: uuid.UUID
    action: CredentialAction
    reason_code: CredentialReason
    reason_text: str | None
    actor: UserRef | None = Field(description="Null = system job.")
    occurred_at: datetime
    expires_at: datetime | None


class ValidityBlock(ApiModel):
    """Validity summary carried by passes, ADPs and AVPs (§6.2, §4.5, §4.9)."""

    validity_status: ValidityStatus
    effective_valid_until: date | None = Field(description="Strictest-wins (§6.2).")
    limiting_factor: LimitingFactor | None
    days_left: int | None = Field(description="effective_valid_until − today; negative = past.")
    custody_status: CustodyStatus | None = Field(description="Null until issued.")
    return_due_on: date | None
    return_overdue: bool = Field(description="custody return_due and today > return_due_on.")
    returned_at: datetime | None
    received_by: UserRef | None
    lost_reported_at: datetime | None
    authority_notified_at: datetime | None
    open_suspensions: list[CredentialSuspension]


class NamedCode(ApiModel):
    code: str
    name_en: str
    name_ar: str
