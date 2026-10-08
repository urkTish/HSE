"""Gas detectors, bump tests and gas tests (spec 3-ptw §3.9, §3.10, §4.6, §5.4, §6.2, §6.3,
§6.10)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.ptw_enums import (
    BumpTestResult,
    DetectorStatus,
    GasFailCode,
    GasLimitProfile,
    GasReadingPoint,
    GasSensor,
    GasTestResult,
    GasTestType,
    LelReferenceGas,
    QuarantineReason,
)
from app.schemas.access_common import WorkerRef
from app.schemas.cert_common import TpiRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import DecimalStr, EngagementRef, UserRef
from app.schemas.ptw_common import AppointmentRef, DetectorRef, PermitRef
from app.schemas.ptw_config import GasLimitSet, OtherGasLimit

# ---- detectors ----------------------------------------------------------------------------------


class DetectorCreate(StrictInput):
    """Capability 91 → in_service when calibration_due_on ≥ today (§4.6). serial unique per
    project. o2 and lel are required for any CSE / hot-work test, h2s and co for CSE and
    excavation (checked per test, DETECTOR_SENSOR_MISSING)."""

    engagement_id: uuid.UUID
    make_model: str = Field(min_length=1, max_length=80)
    serial: str = Field(min_length=1, max_length=40)
    sensors: list[GasSensor] = Field(min_length=1)
    lel_reference_gas: LelReferenceGas | None = Field(default=None, description="Required if lel.")
    calibrated_on: date = Field(description="≤ today.")
    calibration_cert_ref: str = Field(min_length=1, max_length=40)
    certificate_due_on: date | None = Field(
        default=None, description="If entered: calibration_due_on = min(interval, this) (§6.10)."
    )
    calibration_body_id: uuid.UUID | None = Field(
        default=None,
        description="v1.1 (4-third-party-cert BL-7): TPI of kind calibration_lab; quarantined "
        "(calibration_body_blacklisted) when it is blacklisted in scope.",
    )


class DetectorUpdate(PatchInput):
    non_nullable = frozenset({"make_model", "sensors"})

    make_model: str | None = Field(default=None, min_length=1, max_length=80)
    sensors: list[GasSensor] | None = Field(default=None, min_length=1)
    lel_reference_gas: LelReferenceGas | None = None
    calibration_body_id: uuid.UUID | None = Field(default=None, description="v1.1 (BL-7).")


class CalibrationInput(StrictInput):
    """Records a calibration; a quarantined detector returns to in_service (a bump-fail
    quarantine also needs a passing bump test after the calibration)."""

    calibrated_on: date
    calibration_cert_ref: str = Field(min_length=1, max_length=40)
    certificate_due_on: date | None = None


class DetectorRetireInput(StrictInput):
    reason: str = Field(min_length=10, max_length=300)


class BumpTestCreate(StrictInput):
    """Capability 90. sensors_responded must equal the detector's sensors for a pass; a fail
    quarantines the detector."""

    tested_at: datetime = Field(description="≤ now.")
    result: BumpTestResult
    sensors_responded: list[GasSensor]
    tested_by_user_id: uuid.UUID | None = Field(default=None, description="Default: the caller.")
    tested_by_worker_id: uuid.UUID | None = None
    gas_cylinder_lot: str = Field(min_length=1, max_length=40)
    gas_cylinder_expiry: date


class BumpTestRead(ApiModel):
    id: uuid.UUID
    detector_id: uuid.UUID
    tested_at: datetime
    result: BumpTestResult
    sensors_responded: list[GasSensor]
    tested_by_user: UserRef | None
    tested_by_worker: WorkerRef | None
    gas_cylinder_lot: str
    gas_cylinder_expiry: date
    valid_for_date: date = Field(description="Local date it covers (tests after tested_at).")


class DetectorRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    detector_no: str = Field(examples=["GD-ANIA-003"])
    engagement: EngagementRef
    make_model: str
    serial: str
    sensors: list[GasSensor]
    lel_reference_gas: LelReferenceGas | None
    calibrated_on: date
    calibration_cert_ref: str
    certificate_due_on: date | None
    calibration_body: TpiRef | None = Field(default=None, description="v1.1 (BL-7).")
    calibration_due_on: date = Field(description="§6.10.")
    calibration_days_left: int
    status: DetectorStatus
    quarantine_reason: QuarantineReason | None
    quarantined_at: datetime | None
    last_bump_test: BumpTestRead | None
    bump_tested_today: bool
    live_permits: list[PermitRef] = Field(
        description="Live permits using it (continuous monitor or recent tests)."
    )
    created_at: datetime
    updated_at: datetime


DetectorPage = Page[DetectorRead]


class BumpTestList(ApiModel):
    items: list[BumpTestRead]


# ---- gas tests ----------------------------------------------------------------------------------


class OtherReading(StrictInput):
    gas: str = Field(min_length=1, max_length=40)
    value: DecimalStr = Field(ge=Decimal(0), max_digits=8, decimal_places=2)
    unit: str = Field(max_length=10)


class GasReadingInput(StrictInput):
    point: GasReadingPoint
    o2_pct: DecimalStr | None = Field(
        default=None, ge=Decimal(0), le=Decimal(30), max_digits=4, decimal_places=1
    )
    lel_pct: DecimalStr | None = Field(
        default=None, ge=Decimal(0), le=Decimal(100), max_digits=4, decimal_places=1
    )
    h2s_ppm: DecimalStr | None = Field(
        default=None, ge=Decimal(0), le=Decimal(500), max_digits=5, decimal_places=1
    )
    co_ppm: DecimalStr | None = Field(
        default=None, ge=Decimal(0), le=Decimal(2000), max_digits=6, decimal_places=1
    )
    other: list[OtherReading] = Field(default_factory=list)


class GasTestCreate(StrictInput):
    """Capability 90, as or for an appointed gas tester (GT-2). Accepted only when the detector
    is in service, calibrated (DETECTOR_CALIBRATION_OVERDUE), bump-tested today before
    tested_at (BUMP_TEST_MISSING) and has the required sensors (DETECTOR_SENSOR_MISSING);
    tested_at ≥ now − 60 min (BACKDATED_TEST). CSE pre_entry/pre_issue: ≥ 3 points top, middle,
    bottom (CSE_POINTS_REQUIRED). A tester without a user account signs on the recorder's
    device (`tester_signature_png_base64`, else 422 TESTER_SIGNATURE_REQUIRED). A failed test on
    an Active permit suspends it at once (gas_test_failed). Immutable after save (GT-8)."""

    test_type: GasTestType
    tested_at: datetime
    tester_appointment_id: uuid.UUID
    detector_id: uuid.UUID
    readings: list[GasReadingInput] = Field(min_length=1, max_length=10)
    internal_temp_c: DecimalStr | None = Field(
        default=None,
        ge=Decimal(-10),
        le=Decimal(70),
        max_digits=4,
        decimal_places=1,
        description="CSE: recorded at every test (GT-9, HT-6).",
    )
    tester_signature_png_base64: str | None = Field(default=None, max_length=400_000)
    note: str | None = Field(default=None, max_length=300)


class GasReadingRead(ApiModel):
    point: GasReadingPoint
    o2_pct: DecimalStr | None
    lel_pct: DecimalStr | None
    h2s_ppm: DecimalStr | None
    co_ppm: DecimalStr | None
    other: list[OtherReading]
    fail_codes: list[GasFailCode]


class AppliedLimits(ApiModel):
    """Strictest limits across the permit's types (§6.2)."""

    profiles: list[GasLimitProfile]
    limits: GasLimitSet
    other_toxics: list[OtherGasLimit]


class GasEvaluation(ApiModel):
    """Server-side result; the frontend never evaluates readings itself."""

    result: GasTestResult
    fail_codes: list[GasFailCode]
    worst: GasReadingRead = Field(description="Worst value per gas across the points.")
    applicable_limits: AppliedLimits
    errors: list[str] = Field(
        description="Codes the save would reject with (e.g. CSE_POINTS_REQUIRED, "
        "BUMP_TEST_MISSING)."
    )


class GasTestPreview(StrictInput):
    """Evaluate readings against the permit's limits without saving."""

    test_type: GasTestType
    tested_at: datetime | None = None
    detector_id: uuid.UUID | None = None
    readings: list[GasReadingInput] = Field(min_length=1, max_length=10)


class GasTestRead(ApiModel):
    id: uuid.UUID
    test_no: str = Field(examples=["GT-PTW-ANIA-EXP-2026-0413-03"])
    permit: PermitRef
    shift_no: int | None
    test_type: GasTestType
    tested_at: datetime
    tester: AppointmentRef
    recorded_by: UserRef
    tester_signature_attachment_id: uuid.UUID | None = Field(
        description="Signed URL (≤ 5 min) via /attachments only with capability 46 (AC98)."
    )
    detector: DetectorRef
    readings: list[GasReadingRead]
    internal_temp_c: DecimalStr | None
    applicable_limits: AppliedLimits
    result: GasTestResult
    fail_codes: list[GasFailCode]
    valid_for_start_until: datetime = Field(description="tested_at + gas_pre_start_validity.")
    next_due_at: datetime | None = Field(description="§6.3 (passing tests).")
    superseded: bool
    superseded_reason: str | None
    note: str | None
    created_at: datetime


class GasTestSupersede(StrictInput):
    """GT-8: corrections are new tests; the wrong one stays, flagged superseded."""

    reason: str = Field(min_length=10, max_length=300)


class GasTestList(ApiModel):
    items: list[GasTestRead]


GasTestPage = Page[GasTestRead]
