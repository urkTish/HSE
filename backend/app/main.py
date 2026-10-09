"""FastAPI application factory."""

import os
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routers import (
    access_settings,
    ai,
    airport_passes,
    airside_driving,
    airside_works,
    attachments,
    audit,
    auth,
    cert_checks,
    cert_config,
    cert_imports,
    contractors,
    corrective_actions,
    credentials,
    dashboard,
    defects,
    emergency_assets,
    emergency_config,
    emergency_drills,
    equipment,
    equipment_certificates,
    exports,
    field_audits,
    field_inspections,
    field_library,
    field_toolbox,
    fitness_assessments,
    fitness_holds,
    gas,
    gates,
    health,
    heat_config,
    heat_field,
    heat_readings,
    hse_settings,
    incidents,
    inductions,
    inspections,
    isolations,
    jsa,
    kpi,
    medical_catalogue,
    medical_config,
    medical_plan,
    meetings,
    notifications,
    observations,
    permits,
    personnel_certificates,
    projects,
    ptw_appointments,
    ptw_audits,
    ptw_config,
    scaffolds,
    simops,
    sites,
    tpis,
    trainer_authorisations,
    training_config,
    training_courses,
    training_imports,
    training_matrix,
    training_records,
    training_sessions,
    users,
    waps,
    workers,
    workforce,
)
from app.core.clock import pin_from_env
from app.core.config import API_PREFIX, CONTRACT_VERSION, get_settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.middleware import RequestContextMiddleware
from app.schemas.ai import AiStreamEvent

DESCRIPTION = """
HSE platform API — Phase 0 Foundation (spec `docs/specs/0-foundation.md` v1.2), Phase 1
Dashboard & core data with AI (spec `docs/specs/1-dashboard.md` v1.7), Phase 2 Site/Airport
access permits (spec `docs/specs/2-access-permits.md` v1.6), Phase 3 Permit to Work (spec
`docs/specs/3-ptw.md` v1.5), Phase 4 Third-party inspection & certification (spec
`docs/specs/4-third-party-cert.md` v1.3), Phase 5 Training certificates (spec
`docs/specs/5-training.md` v1.3), Phase 6a Occupational health & medical fitness (spec
`docs/specs/6a-occupational-health.md` v1.1), Phase 6b Heat stress management (spec
`docs/specs/6b-heat-stress.md` v1.1), Phase 6c Emergency preparedness & drills (spec
`docs/specs/6c-emergency-drills.md` v1.1) and Phase 6d Field assurance (spec
`docs/specs/6d-field-assurance.md` v1.0).

* Auth: `POST /api/v1/auth/login` sets the httpOnly SameSite=Lax cookie `hse_session` (JWT) and
  returns `{access_token, user}`. Send the cookie or `Authorization: Bearer <token>`.
* Errors: `{"detail": {"code", "message", "message_ar", "errors"}}`; 401 unauthenticated,
  403 forbidden, 404 not found / out of scope, 409 conflict / invalid transition, 422 validation.
* Lists: `?page=1&page_size=50` → `{items, total, page, page_size}`.
* Timestamps are UTC; display and day boundaries use the project timezone (Asia/Riyadh).
* Decimals (man-hours, rates, percentages) are JSON strings, already rounded half-up per spec
  K-R8; KPI payloads also carry the exact `display` text. The frontend never recomputes.
* KPI/dashboard endpoints share one filter set (`project_id`, `site_id`, `zone_id`,
  `zone_type`, `engagement_id`, `include_subcontractors`, `tier`, `period`, `anchor`,
  `start`, `end`, `as_of`, `compare`).
* `POST /ai/ask` streams Server-Sent Events (schema `AiStreamEvent`).
* Phase 2: ID numbers are masked everywhere (`2*******02`); the full value only from
  `POST /workers/{id}/id-number/unmask` (audited). QR payloads are `HSE2:<AC|VS|WP>:<token>`
  with no personal data. Gate checks (`/gate-checks/*`) accept a user session or a gate-device
  session (`POST /gate-device/login`); device sessions can call nothing else.
* Some errors carry `detail.meta` (e.g. WORKER_EXISTS → worker_no; VALIDITY_EXCEEDS_LIMIT →
  limiting_factor; WAP_BLOCKED → blockers).
* Phase 3: signing actions need a password entry within `step_up_reauth_minutes`
  (`POST /auth/reauth`), else 401 REAUTH_REQUIRED. Blocked permit transitions return 422 with
  `detail.code` = the first blocker and `detail.meta.blockers` = all of them (no override).
  Permit QR payloads are `HSE2:PT:<token>`. HSE Managers do not prepare, receive, review as
  area authority, issue, isolate or sign SIMOPS coordination unless they also hold that project
  role.
* Phase 4: equipment and scaffold stickers are `HSE2:EQ:<token>` (printed ref
  `<project>-<tag>`); gate checks accept them (subject `equipment_deployment`).
  `POST /certification-checks` is the platform sticker / certificate check. Personnel ID
  numbers typed for the PC-3 check are never stored or echoed; scans need a reason
  (`POST /personnel-certificates/{id}/scan-url`). Hook results carry `hard_stop`,
  `hook_reason_code` and `conditions`; the hook stage per project and kind (warn → transition →
  block) is `GET /projects/{id}/hook-policy`.
* Phase 5: course codes key the catalogue (`/training-courses/{code}`). Session-issued training
  certificates carry `HSE2:TR:<token>` — checked with `POST /certification-checks` (capability
  142), never an access token (gates answer TOKEN_UNKNOWN). Training hooks use the shared hook
  policy (kind `training_course`; enable with `POST /projects/{id}/training-hooks/enable`).
  Scores are visible per AT-7; scans need a reason (`POST /training-records/{id}/scan-url`).
* Phase 6a: fitness data is tiered (OH-2): tier 1 status (fit / not fit / due) for gate and
  crew roles, tier 2 functional (restrictions, dates) with capability 156, tier 3
  clinical-administrative (outcome details, hold reasons, verification) with capability 157.
  No diagnosis, test result or clinical note is ever stored (P6-1). Medical hooks use the shared
  hook policy (kind `medical_fitness`; enable with `POST /projects/{id}/medical-hooks/enable`);
  gate texts never say "medical". Site-clinic sign-off needs step-up re-auth.
"""

# Schemas used only in non-JSON responses (SSE) and therefore not reachable from any route.
EXTRA_SCHEMAS: tuple[type[BaseModel], ...] = (AiStreamEvent,)


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
        comps = schema.setdefault("components", {}).setdefault("schemas", {})
        _, extra = models_json_schema(
            [(m, "serialization") for m in EXTRA_SCHEMAS],
            ref_template="#/components/schemas/{model}",
        )
        for name, definition in extra.get("$defs", {}).items():
            comps.setdefault(name, definition)
        comps.pop("HTTPValidationError", None)
        comps.pop("ValidationError", None)
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def create_app() -> FastAPI:
    pin_from_env(
        os.environ.get("HSE_CLOCK_AT"), os.environ.get("HSE_CLOCK_MODE"), get_settings().environment
    )
    app = FastAPI(
        title="HSE Platform API",
        version=CONTRACT_VERSION,
        description=DESCRIPTION,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )
    app.add_middleware(RequestContextMiddleware, trust_proxy=get_settings().trust_proxy_headers)
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
        hse_settings,
        workforce,
        incidents,
        observations,
        inspections,
        corrective_actions,
        meetings,
        attachments,
        kpi,
        dashboard,
        ai,
        # Phase 2
        workers,
        inductions,
        airport_passes,
        airside_driving,
        airside_works,
        waps,
        credentials,
        gates,
        access_settings,
        # Phase 3
        ptw_config,
        ptw_appointments,
        permits,
        jsa,
        gas,
        isolations,
        simops,
        ptw_audits,
        # Phase 4
        cert_config,
        tpis,
        equipment,
        equipment_certificates,
        scaffolds,
        personnel_certificates,
        defects,
        cert_imports,
        cert_checks,
        # Phase 5
        training_config,
        training_courses,
        trainer_authorisations,
        training_matrix,
        training_sessions,
        training_records,
        training_imports,
        # Phase 6a
        medical_config,
        medical_catalogue,
        medical_plan,
        fitness_assessments,
        fitness_holds,
        # Phase 6b
        heat_config,
        heat_readings,
        heat_field,
        # Phase 6c
        emergency_config,
        emergency_assets,
        emergency_drills,
        # Phase 6d
        field_library,
        field_inspections,
        field_audits,
        field_toolbox,
    ):
        app.include_router(module.router, prefix=API_PREFIX)
    app.include_router(auth.public_router, prefix=API_PREFIX)
    _install_openapi(app)
    return app


app = create_app()
