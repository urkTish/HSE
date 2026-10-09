"""Environmental monitoring: instruments with `env_monitor` devices, station ingest, points and
limits, readings, background declarations and exceedances (spec 6e-environmental §3.7–§3.12, MON,
LIM, EXD, AIR-1)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import DB, CurrentUser, PageParams, bearer_scheme
from app.core.env_enums import ExceedanceStatus, Parameter
from app.core.errors import error_responses
from app.schemas.env import (
    BackgroundCreate,
    BackgroundPage,
    BackgroundRead,
    EnvDeviceCreate,
    EnvDeviceRead,
    EnvInstrumentCreate,
    EnvInstrumentPage,
    EnvInstrumentRead,
    EnvInstrumentTransition,
    EnvPointCreate,
    EnvPointPage,
    EnvPointRead,
    EnvPointUpdate,
    EnvReadingCreate,
    EnvReadingPage,
    EnvReadingRead,
    EnvStationSessionInput,
    EnvStationSessionRead,
    EnvVoid,
    ExceedancePage,
    ExceedanceRead,
    ExceedanceReview,
    InstrumentUpdate,
    StationPush,
    StationPushResult,
)
from app.services.env import exceedances, monitoring

router = APIRouter(tags=["env-monitoring"])


@router.get(
    "/projects/{project_id}/env-instruments",
    response_model=EnvInstrumentPage,
    summary="Environmental instruments (202)",
    responses=error_responses(401, 403, 404),
)
def list_env_instruments(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> EnvInstrumentPage:
    return monitoring.list_instruments(db, user, project_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/env-instruments",
    response_model=EnvInstrumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an instrument (208; MON-1)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_env_instrument(
    project_id: uuid.UUID, body: EnvInstrumentCreate, user: CurrentUser, db: DB
) -> EnvInstrumentRead:
    return monitoring.create_instrument(db, user, project_id, body)


@router.patch(
    "/env-instruments/{instrument_id}",
    response_model=EnvInstrumentRead,
    summary="Edit an instrument (208; new calibration)",
    responses=error_responses(401, 403, 404, 422),
)
def update_env_instrument(
    instrument_id: uuid.UUID, body: InstrumentUpdate, user: CurrentUser, db: DB
) -> EnvInstrumentRead:
    return monitoring.update_instrument(db, user, instrument_id, body)


@router.post(
    "/env-instruments/{instrument_id}/transitions",
    response_model=EnvInstrumentRead,
    summary="Activate, quarantine or retire an instrument (208; §4.4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_env_instrument(
    instrument_id: uuid.UUID, body: EnvInstrumentTransition, user: CurrentUser, db: DB
) -> EnvInstrumentRead:
    return monitoring.transition_instrument(db, user, instrument_id, body)


@router.post(
    "/env-instruments/{instrument_id}/devices",
    response_model=EnvDeviceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an env_monitor device for a station instrument (208; token returned once)",
    responses=error_responses(401, 403, 404, 422),
)
def register_env_device(
    instrument_id: uuid.UUID, body: EnvDeviceCreate, user: CurrentUser, db: DB
) -> EnvDeviceRead:
    return monitoring.register_device(db, user, instrument_id, body)


@router.post(
    "/env-instruments/{instrument_id}/devices/{device_pk}/revoke",
    response_model=EnvDeviceRead,
    summary="Revoke an env_monitor device (208; its sessions end)",
    responses=error_responses(401, 403, 404, 409),
)
def revoke_env_device(
    instrument_id: uuid.UUID, device_pk: uuid.UUID, user: CurrentUser, db: DB
) -> EnvDeviceRead:
    return monitoring.revoke_device(db, user, instrument_id, device_pk)


@router.post(
    "/env/station-session",
    response_model=EnvStationSessionRead,
    summary="Start an env_monitor session with the device token (no user login)",
    responses=error_responses(401, 422),
)
def start_env_station_session(body: EnvStationSessionInput, db: DB) -> EnvStationSessionRead:
    return monitoring.station_session(db, body)


@router.post(
    "/env/station-readings",
    response_model=StationPushResult,
    summary="Station 15-min ingest (env_monitor session only; idempotent, MON-2)",
    responses=error_responses(401, 403, 422),
)
def ingest_env_station_readings(
    body: StationPush,
    db: DB,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
) -> StationPushResult:
    return monitoring.ingest(db, bearer.credentials if bearer else None, body)


@router.get(
    "/projects/{project_id}/env-points",
    response_model=EnvPointPage,
    summary="Monitoring points with requirements and effective limits (202)",
    responses=error_responses(401, 403, 404),
)
def list_env_points(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> EnvPointPage:
    return monitoring.list_points(db, user, project_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/env-points",
    response_model=EnvPointRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a monitoring point (208; LIM-1 prefill, LIM-2 tighten only)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_env_point(
    project_id: uuid.UUID, body: EnvPointCreate, user: CurrentUser, db: DB
) -> EnvPointRead:
    return monitoring.create_point(db, user, project_id, body)


@router.get(
    "/env-points/{point_id}",
    response_model=EnvPointRead,
    summary="One monitoring point",
    responses=error_responses(401, 403, 404),
)
def get_env_point(point_id: uuid.UUID, user: CurrentUser, db: DB) -> EnvPointRead:
    return monitoring.read_point(db, user, point_id)


@router.patch(
    "/env-points/{point_id}",
    response_model=EnvPointRead,
    summary="Edit a point or its limits (208; 422 LIMIT_LOOSENING; audited)",
    responses=error_responses(401, 403, 404, 422),
)
def update_env_point(
    point_id: uuid.UUID, body: EnvPointUpdate, user: CurrentUser, db: DB
) -> EnvPointRead:
    return monitoring.update_point(db, user, point_id, body)


@router.get(
    "/projects/{project_id}/env-readings",
    response_model=EnvReadingPage,
    summary="Readings register (202)",
    responses=error_responses(401, 403, 404),
)
def list_env_readings(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    point_id: uuid.UUID | None = None,
    parameter: Parameter | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> EnvReadingPage:
    return monitoring.list_readings(
        db, user, project_id, point_id, parameter, date_from, date_to, pg.page, pg.page_size
    )


@router.post(
    "/projects/{project_id}/env-readings",
    response_model=EnvReadingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a manual, visual or lab reading (209; MON-3, EXD-1)",
    description="422 INSTRUMENT_CALIBRATION_EXPIRED, FIELD_CALIBRATION_REQUIRED, "
    "BACKDATED_READING, VALUE_OUT_OF_RANGE, PROVIDER_NOT_APPROVED. Warning PERMIT_NOT_VALID.",
    responses=error_responses(401, 403, 404, 422),
)
def create_env_reading(
    project_id: uuid.UUID, body: EnvReadingCreate, user: CurrentUser, db: DB
) -> EnvReadingRead:
    return monitoring.create_reading(db, user, project_id, body)


@router.get(
    "/env-readings/{reading_id}",
    response_model=EnvReadingRead,
    summary="One reading",
    responses=error_responses(401, 403, 404),
)
def get_env_reading(reading_id: uuid.UUID, user: CurrentUser, db: DB) -> EnvReadingRead:
    return monitoring.read_reading(db, user, reading_id)


@router.post(
    "/env-readings/{reading_id}/void",
    response_model=EnvReadingRead,
    summary="Void a reading (214, reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_env_reading(
    reading_id: uuid.UUID, body: EnvVoid, user: CurrentUser, db: DB
) -> EnvReadingRead:
    return monitoring.void_reading(db, user, reading_id, body)


@router.get(
    "/projects/{project_id}/background-declarations",
    response_model=BackgroundPage,
    summary="Background dust declarations (202)",
    responses=error_responses(401, 403, 404),
)
def list_background_declarations(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> BackgroundPage:
    return monitoring.list_backgrounds(db, user, project_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/background-declarations",
    response_model=BackgroundRead,
    status_code=status.HTTP_201_CREATED,
    summary="Declare a background dust event (208; EXD-3)",
    responses=error_responses(401, 403, 404, 422),
)
def create_background_declaration(
    project_id: uuid.UUID, body: BackgroundCreate, user: CurrentUser, db: DB
) -> BackgroundRead:
    return monitoring.create_background(db, user, project_id, body)


@router.get(
    "/projects/{project_id}/env-exceedances",
    response_model=ExceedancePage,
    summary="Exceedances register (202)",
    responses=error_responses(401, 403, 404),
)
def list_env_exceedances(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[ExceedanceStatus] | None, Query(alias="status")] = None,
    point_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ExceedancePage:
    return exceedances.list_exceedances(
        db, user, project_id, status_, point_id, date_from, date_to, pg.page, pg.page_size
    )


@router.get(
    "/env-exceedances/{exceedance_id}",
    response_model=ExceedanceRead,
    summary="One exceedance",
    responses=error_responses(401, 403, 404),
)
def get_env_exceedance(exceedance_id: uuid.UUID, user: CurrentUser, db: DB) -> ExceedanceRead:
    return exceedances.read_exceedance(db, user, exceedance_id)


@router.post(
    "/env-exceedances/{exceedance_id}/review",
    response_model=ExceedanceRead,
    summary="Review an exceedance (210; EXD-5, 422 ENGAGEMENT_REQUIRED); also reclassifies",
    responses=error_responses(401, 403, 404, 409, 422),
)
def review_env_exceedance(
    exceedance_id: uuid.UUID, body: ExceedanceReview, user: CurrentUser, db: DB
) -> ExceedanceRead:
    return exceedances.review(db, user, exceedance_id, body)


@router.post(
    "/env-exceedances/{exceedance_id}/void",
    response_model=ExceedanceRead,
    summary="Void an exceedance (214, reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_env_exceedance(
    exceedance_id: uuid.UUID, body: EnvVoid, user: CurrentUser, db: DB
) -> ExceedanceRead:
    return exceedances.void(db, user, exceedance_id, body)
