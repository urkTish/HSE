"""Building blocks shared by the Phase 3 PTW schemas (spec 3-ptw)."""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.core.hse_enums import Weekday
from app.core.ptw_enums import (
    AppointmentDiscipline,
    AppointmentFunction,
    AppointmentStatus,
    DetectorStatus,
    PermitBlocker,
    PermitStatus,
    PermitType,
    PermitWarningCode,
    SignaturePurpose,
)
from app.schemas.common import ApiModel, StrictInput
from app.schemas.hse_common import DecimalStr, UserRef

GridM = Annotated[DecimalStr, Field(max_digits=8, decimal_places=1)]
"""Site setting-out grid coordinate in metres (1 dp)."""
Dec1 = Annotated[DecimalStr, Field(ge=Decimal(0), max_digits=7, decimal_places=1)]
"""Non-negative decimal, 1 dp (distances, radii, speeds)."""
Dec2 = Annotated[DecimalStr, Field(ge=Decimal(0), max_digits=7, decimal_places=2)]
"""Non-negative decimal, 2 dp (heights, depths, lengths)."""
Dec3 = Annotated[DecimalStr, Field(ge=Decimal(0), max_digits=8, decimal_places=3)]
"""Non-negative decimal, 3 dp (tonnes)."""

PERMIT_NO_DOC = "`PTW-<project>-<yyyy>-<nnnn>`; display adds the type letters (`· LF`)."
PT_QR_PATTERN = r"^HSE2:PT:[A-Za-z0-9_-]{22}$"

SIGNING_DOC = (
    "Signing transition (PT-15): the caller must have authenticated (login or "
    "POST /auth/reauth) within `step_up_reauth_minutes` (default 15), else 401 "
    "REAUTH_REQUIRED (meta.reauth_minutes). Re-authenticate and retry the same request."
)
BLOCKED_DOC = (
    "Blocked → 422 with detail.code = the first blocker (list B order) and "
    "detail.meta.blockers = every blocker [{code, detail_en, detail_ar}]. There is no override "
    "(PT-17)."
)
WINDOW_DOC = (
    "Local times (Asia/Riyadh). end ≤ start crosses midnight and belongs to the start date: "
    "window on date d = [d + start, d′ + end), d′ = d + 1 if end ≤ start (§6.5, as Phase 2 "
    "WA-9). 06:00–06:00 is a 24 h window."
)


class PermitRef(ApiModel):
    id: uuid.UUID
    permit_no: str = Field(examples=["PTW-ANIA-EXP-2026-0413"], description=PERMIT_NO_DOC)
    display_no: str = Field(examples=["PTW-ANIA-EXP-2026-0413 · CS"])
    work_types: list[PermitType]
    primary_type: PermitType
    status: PermitStatus


class AppointmentRef(ApiModel):
    """Holder names only for callers with capability 46 (worker holders) — a user holder is
    always shown by name (users are not PDPL-restricted beyond Phase 0)."""

    id: uuid.UUID
    appointment_no: str = Field(examples=["APT-ANIA-EXP-0011"])
    function: AppointmentFunction
    discipline: AppointmentDiscipline | None
    holder_name_en: str | None
    holder_name_ar: str | None
    valid_to: date
    status: AppointmentStatus


class DetectorRef(ApiModel):
    id: uuid.UUID
    detector_no: str = Field(examples=["GD-ANIA-003"])
    status: DetectorStatus
    calibration_due_on: date


class CoSignature(StrictInput):
    """A second signer present at the same device (e.g. the receiver accepting the issue on
    the issuer's tablet). The server checks the password (failed attempts count toward the
    lockout) and records the signature in that user's name. Alternative: the second person
    signs on their own device beforehand (receiver acceptance endpoint)."""

    user_id: uuid.UUID
    password: str = Field(min_length=1, max_length=200)


class SignatureRead(ApiModel):
    """PT-15 signature record: {user, role/appointment, transition, timestamp, permit hash}."""

    id: uuid.UUID
    purpose: SignaturePurpose
    user: UserRef | None = Field(description="Null for a worker signatory (gas tester).")
    worker_label: str | None = Field(
        default=None,
        description="Worker signatory: 'Salem Al-Harthi (WKR-000018)' with capability 46, else "
        "'Worker'; 'Anonymised worker WKR-nnnnnn' after anonymisation (P3-5).",
    )
    role_label: str = Field(examples=["issuer", "permit_receiver", "area_authority"])
    appointment_no: str | None
    signed_at: datetime
    permit_hash: str = Field(description="SHA-256 of the permit content signed.")
    co_signed_on_device_of: UserRef | None = Field(
        default=None, description="Set when signed with a CoSignature on another user's session."
    )


class BlockerItem(ApiModel):
    code: PermitBlocker
    detail_en: str
    detail_ar: str
    ref: str | None = Field(
        default=None, description="Record causing it, e.g. SIM-RBT-52-2026-0021, WKR-000019."
    )
    issue_time: bool = Field(
        description="True for issue-time blockers (checked at Issue/Start/Revalidate/Resume "
        "only, PT-16); false = also blocks Approve."
    )


class WarningItem(ApiModel):
    """Amber, never blocking."""

    code: PermitWarningCode
    detail_en: str
    detail_ar: str
    ref: str | None = None


class PermitWindow(StrictInput):
    start_local: time = Field(examples=["07:00"])
    end_local: time = Field(examples=["19:00"])
    weekdays: list[Weekday] = Field(min_length=1, max_length=7, description="Sun..Sat.")


class PermitWindowRead(ApiModel):
    start_local: time
    end_local: time
    weekdays: list[Weekday]
    crosses_midnight: bool


class WindowInstance(ApiModel):
    """One concrete window instance (UTC), clipped to the permit validity."""

    start_at: datetime
    end_at: datetime


class GridPoint(ApiModel):
    x_m: GridM = Field(examples=["128.0"])
    y_m: GridM = Field(examples=["51.0"])
