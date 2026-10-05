"""FastAPI application factory."""

from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routers import (
    audit,
    auth,
    contractors,
    exports,
    health,
    notifications,
    projects,
    sites,
    users,
)
from app.core.config import API_PREFIX, CONTRACT_VERSION
from app.core.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    validation_exception_handler,
)

DESCRIPTION = """
HSE platform API — Phase 0 Foundation (spec `docs/specs/0-foundation.md` v1.0).

* Auth: `POST /api/v1/auth/login` sets the httpOnly SameSite=Lax cookie `hse_session` (JWT) and
  returns `{access_token, user}`. Send the cookie or `Authorization: Bearer <token>`.
* Errors: `{"detail": {"code", "message", "message_ar", "errors"}}`; 401 unauthenticated,
  403 forbidden, 404 not found / out of scope, 409 conflict / invalid transition, 422 validation.
* Lists: `?page=1&page_size=50` → `{items, total, page, page_size}`.
* Timestamps are UTC; display and day boundaries use the project timezone (Asia/Riyadh).
"""


def _operation_id(route: APIRoute) -> str:
    return route.name


def _install_openapi(app: FastAPI) -> None:
    """Use the project error envelope for every 422 (instead of FastAPI's default schema)."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        ref = "#/components/schemas/ErrorResponse"
        for ops in schema.get("paths", {}).values():
            for op in ops.values():
                resp = op.get("responses", {}).get("422")
                if resp is not None:
                    resp["description"] = "Validation error (field errors in detail.errors)."
                    resp["content"] = {"application/json": {"schema": {"$ref": ref}}}
        comps = schema.get("components", {}).get("schemas", {})
        comps.pop("HTTPValidationError", None)
        comps.pop("ValidationError", None)
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def create_app() -> FastAPI:
    app = FastAPI(
        title="HSE Platform API",
        version=CONTRACT_VERSION,
        description=DESCRIPTION,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    for module in (
        health,
        auth,
        projects,
        sites,
        contractors,
        users,
        audit,
        exports,
        notifications,
    ):
        app.include_router(module.router, prefix=API_PREFIX)
    app.include_router(auth.public_router, prefix=API_PREFIX)
    _install_openapi(app)
    return app


app = create_app()
