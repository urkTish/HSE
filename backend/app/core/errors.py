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
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class FieldError(BaseModel):
    """One field-level problem (used with VALIDATION_ERROR and DUPLICATE_VALUE)."""

    loc: list[str | int] = Field(description='Path to the field, e.g. ["body", "zone_type"].')
    msg: str = Field(description="English description of the problem.")
    type: str = Field(description="Machine-readable error type, e.g. 'missing', 'value_error'.")


class ErrorDetail(BaseModel):
    code: ErrorCode = Field(description="Stable machine code; map it to EN/AR UI text.")
    message: str = Field(description="English, human-readable message.")
    message_ar: str | None = Field(default=None, description="Arabic message, when available.")
    errors: list[FieldError] | None = Field(
        default=None, description="Field-level errors (422 validation, 409 duplicates)."
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
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.message_ar = message_ar
        self.errors = errors
        self.headers = headers

    def to_response(self) -> JSONResponse:
        body = ErrorResponse(
            detail=ErrorDetail(
                code=self.code,
                message=self.message,
                message_ar=self.message_ar,
                errors=self.errors,
            )
        )
        return JSONResponse(
            status_code=self.status_code,
            content=body.model_dump(mode="json", exclude_none=True),
            headers=self.headers,
        )


def field_error(field: str, msg: str, type_: str = "value_error") -> FieldError:
    return FieldError(loc=["body", field], msg=msg, type=type_)


def validation_error(field: str, msg: str, type_: str = "value_error") -> ApiError:
    return ApiError(422, ErrorCode.VALIDATION_ERROR, msg, errors=[field_error(field, msg, type_)])


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
        errors.append(FieldError(loc=loc, msg=str(err.get("msg", "")), type=str(err["type"])))
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
        422: "Validation error (field errors in detail.errors).",
        501: "Not implemented yet.",
    }
    return {c: {"model": ErrorResponse, "description": descriptions.get(c, "Error")} for c in codes}
