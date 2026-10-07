"""Stable error codes and the API error envelope.

Every error response body is ``{"detail": {"code": ..., "message": ..., "message_ar": ...}}``
(see docs/CONVENTIONS.md). The frontend maps ``code`` to EN/AR text (spec §5.7 rule 48).
"""

from enum import StrEnum
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(StrEnum):
    """Machine-readable error codes. Stable: the frontend translates these."""

    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    PRIVACY_ACK_REQUIRED = "PRIVACY_ACK_REQUIRED"
    PRIVACY_NOTICE_VERSION_MISMATCH = "PRIVACY_NOTICE_VERSION_MISMATCH"
    INVITE_INVALID = "INVITE_INVALID"
    INVITE_EXPIRED = "INVITE_EXPIRED"
    RESET_TOKEN_INVALID = "RESET_TOKEN_INVALID"
    WEAK_PASSWORD = "WEAK_PASSWORD"
    CURRENT_PASSWORD_INCORRECT = "CURRENT_PASSWORD_INCORRECT"
    FORBIDDEN = "FORBIDDEN"
    READ_ONLY_ROLE = "READ_ONLY_ROLE"
    CONTRACTOR_SUSPENDED = "CONTRACTOR_SUSPENDED"
    SELF_MODIFICATION_FORBIDDEN = "SELF_MODIFICATION_FORBIDDEN"
    ROLE_NOT_ASSIGNABLE = "ROLE_NOT_ASSIGNABLE"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DUPLICATE_VALUE = "DUPLICATE_VALUE"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    TRANSITION_CONDITION_NOT_MET = "TRANSITION_CONDITION_NOT_MET"
    PROJECT_CLOSED = "PROJECT_CLOSED"
    SITE_INACTIVE = "SITE_INACTIVE"
    ZONE_ARCHIVED = "ZONE_ARCHIVED"
    CONTRACTOR_NOT_APPROVED = "CONTRACTOR_NOT_APPROVED"
    LAST_HSE_MANAGER = "LAST_HSE_MANAGER"
    SOD_CONFLICT = "SOD_CONFLICT"
    # ---- Phase 1 (1-dashboard) ----
    DUPLICATE_RETURN = "DUPLICATE_RETURN"  # W-1 / AC2
    PERIOD_LOCKED = "PERIOD_LOCKED"  # W-10: row/case in a Locked month
    VERIFIER_IS_CREATOR = "VERIFIER_IS_CREATOR"  # §4.1 verifier ≠ creator
    OUTSIDE_MOBILISATION = "OUTSIDE_MOBILISATION"  # E05 for manual entry
    IMPORT_FILE_INVALID = "IMPORT_FILE_INVALID"  # E14 whole file, size/row limits, type
    IMPORT_HAS_ERRORS = "IMPORT_HAS_ERRORS"  # W-5 commit with rows_error > 0
    IMPORT_EXPIRED = "IMPORT_EXPIRED"  # W-5 / AC5 dry-run older than 60 min
    IMPORT_NOT_VALIDATED = "IMPORT_NOT_VALIDATED"  # batch already committed/discarded
    NEAR_MISS_EXCLUSIVE = "NEAR_MISS_EXCLUSIVE"  # I-3 / AC19
    INJURY_CASE_REQUIRED = "INJURY_CASE_REQUIRED"  # I-2 / AC20
    INVESTIGATION_LEVEL_TOO_LOW = "INVESTIGATION_LEVEL_TOO_LOW"  # I-14 / AC23
    INVESTIGATION_INCOMPLETE = "INVESTIGATION_INCOMPLETE"  # §3.5 / I-16 at submit
    INVESTIGATION_LEAD_NOT_ALLOWED = "INVESTIGATION_LEAD_NOT_ALLOWED"  # §3.5 / I-15
    INVESTIGATION_TEAM_INCOMPLETE = "INVESTIGATION_TEAM_INCOMPLETE"  # I-15 L3 team
    APPROVER_IS_LEAD = "APPROVER_IS_LEAD"  # §3.5 approver ≠ lead investigator
    CASES_NOT_CONFIRMED = "CASES_NOT_CONFIRMED"  # §4.2 Pending Review → Actions Pending
    HIGHER_CONTROL_REQUIRED = "HIGHER_CONTROL_REQUIRED"  # I-17 / AC24
    JUSTIFICATION_REQUIRED = "JUSTIFICATION_REQUIRED"  # I-6 category override
    POSSIBLE_ID_NUMBER = "POSSIBLE_ID_NUMBER"  # P1-8 warning code (never an error status)
    SAFE_OBSERVATION_IMMUTABLE = "SAFE_OBSERVATION_IMMUTABLE"  # O-3
    FINDING_CA_REQUIRED = "FINDING_CA_REQUIRED"  # N-4
    VERIFIER_IS_OWNER = "VERIFIER_IS_OWNER"  # CA-5 / AC40
    VERIFIER_ROLE_NOT_ALLOWED = "VERIFIER_ROLE_NOT_ALLOWED"  # CA-5 role per priority
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"  # CA-4 / AC42
    EXTENSION_LIMIT_REACHED = "EXTENSION_LIMIT_REACHED"  # CA-3 / AC41
    DUE_DATE_TOO_LATE = "DUE_DATE_TOO_LATE"  # CA-2
    RESTRICTED_DIMENSION = "RESTRICTED_DIMENSION"  # D-7 / AI-6 nationality, age band
    MIXED_PROJECT_SCOPE = "MIXED_PROJECT_SCOPE"  # all-projects requested by non-manager
    EXPORT_PURPOSE_REQUIRED = "EXPORT_PURPOSE_REQUIRED"  # P1-6
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_TYPE_NOT_ALLOWED = "FILE_TYPE_NOT_ALLOWED"
    SIGNED_URL_INVALID = "SIGNED_URL_INVALID"  # P1-3 expired or tampered link
    AI_DISABLED = "AI_DISABLED"  # AI-14 / AC73 (ai_enabled false or no transfer approval)
    AI_TRANSFER_APPROVAL_REQUIRED = "AI_TRANSFER_APPROVAL_REQUIRED"  # AI-14 enabling AI
    AI_UNAVAILABLE = "AI_UNAVAILABLE"  # AI-18: no API key / provider down / timeout
    AI_RATE_LIMITED = "AI_RATE_LIMITED"  # AI-17 per-user / per-project limits
    # ---- Phase 2 (2-access-permits) ----
    GATE_DEVICE_FORBIDDEN = "GATE_DEVICE_FORBIDDEN"  # GC-1 device session outside gate checks
    GATE_DEVICE_REVOKED = "GATE_DEVICE_REVOKED"  # GC-1 revoked / unknown device token
    GATE_RATE_LIMITED = "GATE_RATE_LIMITED"  # GC-3 120 checks/min per device or user
    PAIRING_NOT_FOUND = "PAIRING_NOT_FOUND"  # GC-8 pairing id unknown / other device
    WORKER_EXISTS = "WORKER_EXISTS"  # WK-2 (meta.worker_no, meta.worker_id)
    WORKER_EXISTS_OUT_OF_SCOPE = "WORKER_EXISTS_OUT_OF_SCOPE"  # WK-2 (no identifying data)
    ADULT_ATTESTATION_REQUIRED = "ADULT_ATTESTATION_REQUIRED"  # WK-6
    DEPLOYMENT_EXISTS = "DEPLOYMENT_EXISTS"  # WK-10
    WORKER_BANNED = "WORKER_BANNED"  # WK-12
    PHOTO_REQUIRED = "PHOTO_REQUIRED"  # §3.1 photo for airside/pass, AP-5
    DELIVERER_NOT_ALLOWED = "DELIVERER_NOT_ALLOWED"  # IN-3 / IN-12 / AC13
    INDUCTION_PREREQUISITE = "INDUCTION_PREREQUISITE"  # IN-4
    INDUCTION_ATTEMPTS_EXCEEDED = "INDUCTION_ATTEMPTS_EXCEEDED"  # IN-5
    INDUCTION_TOO_SHORT = "INDUCTION_TOO_SHORT"  # IN-7
    INDUCTION_EDIT_LOCKED = "INDUCTION_EDIT_LOCKED"  # IN-11 edits after 24 h
    PROFILE_LOOSENING = "PROFILE_LOOSENING"  # ZP-2
    HOOK_PROVIDER_MISSING = "HOOK_PROVIDER_MISSING"  # HK-4
    NOT_AIRPORT_PROJECT = "NOT_AIRPORT_PROJECT"  # AP-2
    APPLICATION_OPEN = "APPLICATION_OPEN"  # AP-3
    ID_EXPIRES_SOON = "ID_EXPIRES_SOON"  # AP-5
    ID_EXPIRED = "ID_EXPIRED"  # WK-7 on writes that need a valid ID
    VALIDITY_EXCEEDS_LIMIT = "VALIDITY_EXCEEDS_LIMIT"  # AP-6 (meta.limiting_factor, meta.max)
    BACKGROUND_NOT_CLEARED = "BACKGROUND_NOT_CLEARED"  # AP-4
    ENDORSER_NOT_ALLOWED = "ENDORSER_NOT_ALLOWED"  # AP-8
    PREREQUISITES_NOT_MET = "PREREQUISITES_NOT_MET"  # AP-7 endorse (meta.requirements)
    AREA_NOT_REQUESTED = "AREA_NOT_REQUESTED"  # AP-9 issued areas ⊆ requested
    ADP_PASS_REQUIRED = "ADP_PASS_REQUIRED"  # DP-3
    ADP_EXISTS = "ADP_EXISTS"  # DP-2
    LICENCE_NOT_VALID = "LICENCE_NOT_VALID"  # DP-4
    RTF_REQUIRED = "RTF_REQUIRED"  # DP-5
    TESTS_NOT_VALID = "TESTS_NOT_VALID"  # DP-6
    SUSPENSION_PERIOD_RUNNING = "SUSPENSION_PERIOD_RUNNING"  # DP-8
    AVP_PRECONDITION = "AVP_PRECONDITION"  # VP-3 / VP-4
    AVP_EXISTS = "AVP_EXISTS"  # VP-2
    LATE_JUSTIFICATION_REQUIRED = "LATE_JUSTIFICATION_REQUIRED"  # NT-2 / OB-5 short lead
    OB_CONDITIONS_REQUIRED = "OB_CONDITIONS_REQUIRED"  # OB-4
    CLEARANCE_NOT_LINKABLE = "CLEARANCE_NOT_LINKABLE"  # OB-8 rejected clearance on a WAP
    WAP_DURATION_EXCEEDED = "WAP_DURATION_EXCEEDED"  # WA-5 wap_max_days
    WSP_REQUIRED = "WSP_REQUIRED"  # WA-6
    WAP_BLOCKED = "WAP_BLOCKED"  # WA-13 resume with blockers (meta.blockers)
    CREW_INVALID = "CREW_INVALID"  # WA-2 crew / supervisor composition
    FOD_HANDBACK_REQUIRED = "FOD_HANDBACK_REQUIRED"  # WA-17
    OPS_ZONES_LOCKED = "OPS_ZONES_LOCKED"  # WA-16 default zones cannot be removed
    SYSTEM_SUSPENSION = "SYSTEM_SUSPENSION"  # LC-6 dependency suspensions lift automatically
    CREDENTIAL_TERMINAL = "CREDENTIAL_TERMINAL"  # LC-5 revoked/expired/lost
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class FieldError(BaseModel):
    """One field-level problem (used with VALIDATION_ERROR and DUPLICATE_VALUE)."""

    loc: list[str | int] = Field(description='Path to the field, e.g. ["body", "zone_type"].')
    msg: str = Field(description="English description of the problem.")
    msg_ar: str | None = Field(
        default=None,
        description="Arabic description of the problem (always sent by the server; a generic "
        "text per `type` when no specific translation exists).",
    )
    type: str = Field(description="Machine-readable error type, e.g. 'missing', 'value_error'.")


class ErrorDetail(BaseModel):
    code: ErrorCode = Field(description="Stable machine code; map it to EN/AR UI text.")
    message: str = Field(description="English, human-readable message.")
    message_ar: str | None = Field(default=None, description="Arabic message, when available.")
    errors: list[FieldError] | None = Field(
        default=None, description="Field-level errors (422 validation, 409 duplicates)."
    )
    meta: dict[str, Any] | None = Field(
        default=None,
        description="Machine-readable context for some codes, e.g. WORKER_EXISTS → "
        "{worker_id, worker_no}; VALIDITY_EXCEEDS_LIMIT → {limiting_factor, max_date}; "
        "WAP_BLOCKED → {blockers}; PREREQUISITES_NOT_MET → {requirements}.",
    )


class ErrorResponse(BaseModel):
    """Envelope for every 4xx/5xx response."""

    detail: ErrorDetail


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        message_ar: str | None = None,
        errors: list[FieldError] | None = None,
        headers: dict[str, str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        for e in errors or []:
            if e.msg_ar is None:
                same = len(errors or []) == 1 and e.msg == message and message_ar
                e.msg_ar = message_ar if same else arabic_for(e.type)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.message_ar = message_ar
        self.errors = errors
        self.headers = headers
        self.meta = meta

    def to_response(self) -> JSONResponse:
        body = ErrorResponse(
            detail=ErrorDetail(
                code=self.code,
                message=self.message,
                message_ar=self.message_ar,
                errors=self.errors,
                meta=self.meta,
            )
        )
        return JSONResponse(
            status_code=self.status_code,
            content=body.model_dump(mode="json", exclude_none=True),
            headers=self.headers,
        )


# Arabic fallbacks per error type (Pydantic types and our own codes).
AR_BY_TYPE: dict[str, str] = {
    "missing": "هذا الحقل مطلوب.",
    "string_too_short": "النص أقصر من المسموح.",
    "string_too_long": "النص أطول من المسموح.",
    "string_pattern_mismatch": "الصيغة غير صحيحة.",
    "string_type": "يجب أن تكون القيمة نصًا.",
    "int_parsing": "يجب أن تكون القيمة رقمًا صحيحًا.",
    "int_type": "يجب أن تكون القيمة رقمًا صحيحًا.",
    "decimal_parsing": "يجب أن تكون القيمة رقمًا.",
    "decimal_type": "يجب أن تكون القيمة رقمًا.",
    "decimal_max_digits": "عدد الأرقام أكبر من المسموح.",
    "decimal_max_places": "عدد المنازل العشرية أكبر من المسموح.",
    "float_parsing": "يجب أن تكون القيمة رقمًا.",
    "greater_than": "القيمة أصغر من المسموح.",
    "greater_than_equal": "القيمة أصغر من المسموح.",
    "less_than": "القيمة أكبر من المسموح.",
    "less_than_equal": "القيمة أكبر من المسموح.",
    "too_short": "عدد العناصر أقل من المسموح.",
    "too_long": "عدد العناصر أكبر من المسموح.",
    "enum": "القيمة ليست من الخيارات المسموحة.",
    "literal_error": "القيمة ليست من الخيارات المسموحة.",
    "bool_parsing": "يجب أن تكون القيمة نعم أو لا.",
    "date_parsing": "صيغة التاريخ غير صحيحة.",
    "date_from_datetime_parsing": "صيغة التاريخ غير صحيحة.",
    "datetime_parsing": "صيغة التاريخ والوقت غير صحيحة.",
    "datetime_from_date_parsing": "صيغة التاريخ والوقت غير صحيحة.",
    "time_parsing": "صيغة الوقت غير صحيحة.",
    "uuid_parsing": "المعرّف غير صالح.",
    "uuid_type": "المعرّف غير صالح.",
    "extra_forbidden": "هذا الحقل غير مسموح.",
    "list_type": "يجب أن تكون القيمة قائمة.",
    "dict_type": "يجب أن تكون القيمة كائنًا.",
    "model_type": "يجب أن تكون القيمة كائنًا.",
    "json_invalid": "صيغة JSON غير صحيحة.",
    "value_error": "القيمة غير صالحة.",
    "duplicate": "هذه القيمة مستخدمة من قبل.",
    "not_null": "لا يمكن حذف قيمة هذا الحقل.",
    "weak_password": "كلمة المرور لا تستوفي متطلبات الأمان.",
}
AR_GENERIC = "القيمة غير صالحة."


def arabic_for(type_: str) -> str:
    return AR_BY_TYPE.get(type_, AR_GENERIC)


def field_error(
    field: str, msg: str, type_: str = "value_error", msg_ar: str | None = None
) -> FieldError:
    return FieldError(loc=["body", field], msg=msg, msg_ar=msg_ar, type=type_)


def validation_error(
    field: str, msg: str, type_: str = "value_error", msg_ar: str | None = None
) -> ApiError:
    ar = msg_ar or arabic_for(type_)
    return ApiError(
        422, ErrorCode.VALIDATION_ERROR, msg, ar, errors=[field_error(field, msg, type_, ar)]
    )


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, ErrorCode.NOT_FOUND, f"{what} not found.", "العنصر غير موجود.")


def forbidden(message: str = "You do not have permission for this action.") -> ApiError:
    return ApiError(403, ErrorCode.FORBIDDEN, message, "ليس لديك صلاحية لتنفيذ هذا الإجراء.")


def not_implemented() -> ApiError:
    return ApiError(501, ErrorCode.NOT_IMPLEMENTED, "Not implemented yet.")


async def api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):  # pragma: no cover
        raise exc
    return exc.to_response()


async def validation_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        raise exc
    errors: list[FieldError] = []
    for err in exc.errors():
        loc: list[Any] = [x if isinstance(x, str | int) else str(x) for x in err.get("loc", [])]
        t = str(err["type"])
        errors.append(
            FieldError(loc=loc, msg=str(err.get("msg", "")), msg_ar=arabic_for(t), type=t)
        )
    return ApiError(
        422,
        ErrorCode.VALIDATION_ERROR,
        "Request validation failed.",
        "فشل التحقق من صحة الطلب.",
        errors=errors,
    ).to_response()


_STATUS_CODES: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.NOT_FOUND,
}


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover
        raise exc
    code = _STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return ApiError(exc.status_code, code, str(exc.detail)).to_response()


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses=` helper: documents the error envelope for the given statuses."""
    descriptions = {
        401: "Not authenticated, session expired, or login rejected.",
        403: "Missing capability, read-only role, contractor suspended, or privacy notice not "
        "acknowledged (PRIVACY_ACK_REQUIRED).",
        404: "Not found or outside the caller's project/contractor scope.",
        409: "Invalid state transition, closed project, duplicate value or business-rule conflict.",
        410: "Token expired.",
        429: "Rate limit reached (AI_RATE_LIMITED); see Retry-After.",
        503: "Dependency unavailable (AI_UNAVAILABLE).",
        422: "Validation error (field errors in detail.errors).",
        501: "Not implemented yet.",
    }
    return {c: {"model": ErrorResponse, "description": descriptions.get(c, "Error")} for c in codes}
