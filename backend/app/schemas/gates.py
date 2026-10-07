"""Gates, gate devices, QR gate checks, escort/driver pairing and the gate log
(spec 2-access-permits §3.19, §3.20, §5.10, GC-1…GC-16)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import (
    AreaCategory,
    CardColour,
    GateCallerKind,
    GateDirection,
    GateReasonCode,
    GateReasonSeverity,
    GateResult,
    GateStatus,
    GateSubjectKind,
    GateType,
    PairingState,
    PairingWaitingFor,
    QrKind,
    WapBlocker,
    WapStatus,
)
from app.core.hse_enums import Trade
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import SiteRef, UserRef, ZoneRef

# ---- gates and devices --------------------------------------------------------------------------


class GateCreate(StrictInput):
    """Capability 75."""

    gate_code: str = Field(min_length=1, max_length=12, examples=["G-AAP3"])
    name_en: str = Field(min_length=1, max_length=120)
    name_ar: str = Field(min_length=1, max_length=120)
    site_id: uuid.UUID
    protected_zone_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Zones of that site; empty = whole site (site gate)."
    )
    gate_type: GateType


class GateUpdate(PatchInput):
    non_nullable = frozenset({"name_en", "name_ar", "protected_zone_ids", "gate_type", "status"})

    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    name_ar: str | None = Field(default=None, min_length=1, max_length=120)
    protected_zone_ids: list[uuid.UUID] | None = None
    gate_type: GateType | None = None
    status: GateStatus | None = None


class GateRef(ApiModel):
    id: uuid.UUID
    gate_code: str
    name_en: str
    name_ar: str
    gate_type: GateType


class GateDeviceRead(ApiModel):
    id: uuid.UUID
    device_id: str = Field(examples=["GATE-TAB-07"])
    label: str
    registered_at: datetime
    registered_by: UserRef | None
    last_seen_at: datetime | None
    revoked_at: datetime | None


class GateRead(Timestamps):
    id: uuid.UUID
    project_id: uuid.UUID
    gate_code: str
    name_en: str
    name_ar: str
    site: SiteRef
    protected_zones: list[ZoneRef]
    gate_type: GateType
    status: GateStatus
    devices: list[GateDeviceRead]


class GateList(ApiModel):
    items: list[GateRead]


class GateDeviceCreate(StrictInput):
    device_id: str = Field(min_length=1, max_length=40, examples=["GATE-TAB-07"])
    label: str = Field(min_length=1, max_length=80)


class GateDeviceRegistered(ApiModel):
    """The device token is shown once; enter it on the tablet (POST /gate-device/login).
    Revoking the device ends its sessions; register again to rotate."""

    device: GateDeviceRead
    device_token: str = Field(description="Opaque secret, shown only in this response.")


class GateDeviceLogin(StrictInput):
    device_token: str = Field(min_length=20, max_length=200)


class GateDeviceSession(ApiModel):
    """GC-1: a device session can call only the gate-check endpoints (others → 403
    GATE_DEVICE_FORBIDDEN); it expires after 12 h idle and is revoked with the device. Send
    the token as `Authorization: Bearer` (also set as the httpOnly cookie `hse_gate_session`)."""

    access_token: str
    token_type: str = "bearer"
    gate: GateRead
    device: GateDeviceRead
    idle_timeout_minutes: int = Field(examples=[720])


class GateCallerContext(ApiModel):
    """GET /gate-checks/context: what the scanner screen needs (gates the caller may use)."""

    caller_kind: GateCallerKind
    gates: list[GateRead]
    escort_pairing_seconds: int
    clear_after_seconds: int = Field(description="GC-7: the result screen clears after 30 s.")


# ---- gate check ---------------------------------------------------------------------------------


class GateCheckRequest(StrictInput):
    """GC-2. Send `payload` (QR text) or `printed_ref` (manual fallback, e.g.
    "WKR-000002 / ANIA-EXP", "AVP-S-0118", "WAP-ANIA-EXP-2026-0031"); a vehicle without an AVP
    has no sticker, so type its vehicle_no ("VEH-0004": PENDING_ESCORT_VEHICLE, VP-8). `zone_id` defaults to the
    gate's single protected zone; required when the gate protects several; omitted for a site
    gate. `pairing_id` continues an escort / driver / escort-vehicle pairing started on the
    same device (GC-8, GC-9)."""

    gate_id: uuid.UUID
    payload: str | None = Field(
        default=None, max_length=200, examples=["HSE2:AC:q8Xb2mJf0Q9nZr4tYc1wKA"]
    )
    printed_ref: str | None = Field(default=None, max_length=60)
    direction: GateDirection = GateDirection.in_
    zone_id: uuid.UUID | None = None
    pairing_id: uuid.UUID | None = None


class GateReason(ApiModel):
    code: GateReasonCode
    severity: GateReasonSeverity
    message_en: str
    message_ar: str


class GateCredentialLine(ApiModel):
    """One line on the result screen (GC-7)."""

    kind: str = Field(examples=["induction", "airport_pass", "adp", "wap", "avp"])
    label_en: str = Field(examples=["AIR induction", "PERM pass", "WAP-ANIA-EXP-2026-0031"])
    label_ar: str
    valid_until: date | None
    ok: bool
    card_colour: CardColour | None = None
    area_codes: list[str] | None = None
    adp_category: AreaCategory | None = None
    window_today: str | None = Field(default=None, examples=["23:00-05:00"])


class GatePersonCard(ApiModel):
    """GC-7: never the ID number, nationality, background status or offence history. The photo
    URL is signed and short-lived; devices must not cache it."""

    worker_no: str
    full_name_en: str
    full_name_ar: str
    photo_url: str | None
    employer_short_code: str | None
    trade: Trade | None
    escort_required: bool
    credentials: list[GateCredentialLine]


class GateVehicleCard(ApiModel):
    vehicle_no: str
    fleet_no: str
    category: str
    plate_display: str | None = Field(
        description="Arabic letters + LTR digits, e.g. 'ح ط ر 9012'; null without plate."
    )
    max_working_height_m_agl: str
    credentials: list[GateCredentialLine]


class GateWapCrewLine(ApiModel):
    worker_no: str
    full_name_en: str
    full_name_ar: str
    crew_role: str
    eligible_now: bool
    reasons: list[GateReasonCode]


class GateWapCard(ApiModel):
    """GC-10: WAP QR at a zone entry; logs `wap_view`, records no individual's entry."""

    wap_no: str
    status: WapStatus
    in_window_now: bool
    window_today: str | None
    blockers: list[WapBlocker]
    crew: list[GateWapCrewLine]
    vehicles: list[str] = Field(description="vehicle_no list.")


class GatePairing(ApiModel):
    pairing_id: uuid.UUID
    waiting_for: PairingWaitingFor
    state: PairingState
    expires_at: datetime = Field(description="Start + escort_pairing_seconds.")
    started_check_id: uuid.UUID


class GatePairedResult(ApiModel):
    """Final result of another subject of the same pairing (e.g. the escorted person when the
    escort is scanned). Both are GRANTED or both DENIED (GC-8)."""

    check_id: uuid.UUID
    subject_kind: GateSubjectKind
    display_ref: str = Field(examples=["WKR-000004", "VEH-0004"])
    result: GateResult
    reasons: list[GateReason]


class GateCheckResponse(ApiModel):
    """GC-5/GC-6: any DENY reason → DENIED; else any WARN → GRANTED_WITH_WARNING. A subject
    outside a Contractor HSE Rep's scope returns DENIED with only OUT_OF_SCOPE and no card
    (GC-13). `out` direction never denies (EXIT_RECORDED; `late_exit` after the WAP window +
    wap_exit_grace_minutes)."""

    check_id: uuid.UUID = Field(description="Gate-log row id (use for admitted-despite-denial).")
    occurred_at: datetime
    gate: GateRef
    zone: ZoneRef | None = Field(description="Target zone; null at a site gate.")
    direction: GateDirection
    qr_kind: QrKind | None
    subject_kind: GateSubjectKind
    result: GateResult
    reasons: list[GateReason]
    person: GatePersonCard | None = None
    vehicle: GateVehicleCard | None = None
    wap: GateWapCard | None = None
    pairing: GatePairing | None = None
    paired_results: list[GatePairedResult] = Field(default_factory=list)
    late_exit: bool = False
    clear_after_seconds: int = 30


class PairingRead(ApiModel):
    """Poll while PENDING_*: on timeout the started subject is DENIED (ESCORT_REQUIRED for an
    escort pairing) and the final result is listed in `results`."""

    pairing: GatePairing
    results: list[GatePairedResult]


class AdmittedDespiteDenialRequest(StrictInput):
    """GC-14: no override exists; the guard records that a DENIED subject was admitted. Alerts
    the HSE Officer and HSE Manager immediately; counts in K-53b."""

    reason: str = Field(min_length=10, max_length=500)


# ---- gate log -----------------------------------------------------------------------------------


class GateLogEntry(ApiModel):
    """GC-12 immutable row (capability 76). Names only with capability 46."""

    id: uuid.UUID
    occurred_at: datetime
    gate_id: uuid.UUID
    gate_code: str
    device_id: str | None
    user: UserRef | None
    direction: GateDirection
    subject_kind: GateSubjectKind
    subject_ref: str | None = Field(examples=["WKR-000006", "VEH-0004", "WAP-ANIA-EXP-2026-0031"])
    subject_name_en: str | None
    subject_name_ar: str | None
    zone: ZoneRef | None
    result: GateResult
    reason_codes: list[GateReasonCode]
    pairing_id: uuid.UUID | None
    late_exit: bool
    admitted_despite_denial: bool
    admitted_reason: str | None
    admitted_by: UserRef | None


class GateLogPage(Page[GateLogEntry]):
    pass
