"""Heat stress configuration and registers (spec 6b-heat-stress §3.1–§3.4, §3.7, §3.14, HS):
reference lists, settings, the regime table, instruments with weather-station devices,
monitoring points and rest stations."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.schemas.heat import (
    HeatReference,
    HeatSettingsRead,
    HeatSettingsUpdate,
    InstrumentCreate,
    InstrumentPage,
    InstrumentRead,
    InstrumentTransition,
    PointCreate,
    PointPage,
    PointRead,
    PointUpdate,
    RegimeTableRead,
    RegimeTableUpdate,
    RestStationCreate,
    RestStationPage,
    RestStationRead,
    RestStationUpdate,
    StationDeviceCreate,
    StationDeviceRead,
    StationDeviceRegistered,
)
from app.services.heat import config, registers

router = APIRouter(tags=["heat-config"])


@router.get(
    "/heat-reference",
    response_model=HeatReference,
    summary="6b reference lists WL, CL, RGM, APT, HW, BO, HC with EN/AR labels",
    responses=error_responses(401),
)
def get_heat_reference(user: CurrentUser) -> HeatReference:
    return config.reference()


@router.get(
    "/projects/{project_id}/heat-settings",
    response_model=HeatSettingsRead,
    summary="6b project settings (§3.14) with the Phase 3 ban dates (capability 166)",
    responses=error_responses(401, 403, 404),
)
def get_heat_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> HeatSettingsRead:
    return config.read_settings(db, user, project_id)


@router.patch(
    "/projects/{project_id}/heat-settings",
    response_model=HeatSettingsRead,
    summary="Edit 6b settings; set heat_ptw_enforcement_from (capability 175, HS-6, HS-7)",
    responses=error_responses(401, 403, 404, 422),
)
def update_heat_settings(
    project_id: uuid.UUID, body: HeatSettingsUpdate, user: CurrentUser, db: DB
) -> HeatSettingsRead:
    return config.update_settings(db, user, project_id, body)


@router.get(
    "/heat-regime-table",
    response_model=RegimeTableRead,
    summary="Org-wide work/rest regime table (§3.4)",
    responses=error_responses(401, 403),
)
def get_regime_table(user: CurrentUser, db: DB) -> RegimeTableRead:
    return config.read_regime_table(db, user)


@router.patch(
    "/heat-regime-table",
    response_model=RegimeTableRead,
    summary="Lower regime limits (capability 175; REGIME_LOOSENING, HS-5)",
    responses=error_responses(401, 403, 422),
)
def update_regime_table(body: RegimeTableUpdate, user: CurrentUser, db: DB) -> RegimeTableRead:
    return config.update_regime_table(db, user, body)


# ---- instruments and weather-station devices -----------------------------------------------------


@router.get(
    "/projects/{project_id}/heat-instruments",
    response_model=InstrumentPage,
    summary="Heat instruments (capability 166)",
    responses=error_responses(401, 403, 404),
)
def list_heat_instruments(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> InstrumentPage:
    return registers.list_instruments(db, user, project_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/heat-instruments",
    response_model=InstrumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register and activate an instrument (capability 168; HS-2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_heat_instrument(
    project_id: uuid.UUID, body: InstrumentCreate, user: CurrentUser, db: DB
) -> InstrumentRead:
    return registers.create_instrument(db, user, project_id, body)


@router.get(
    "/heat-instruments/{instrument_id}",
    response_model=InstrumentRead,
    summary="One instrument",
    responses=error_responses(401, 403, 404),
)
def get_heat_instrument(instrument_id: uuid.UUID, user: CurrentUser, db: DB) -> InstrumentRead:
    return registers.read_instrument(db, user, instrument_id)


@router.post(
    "/heat-instruments/{instrument_id}/transitions",
    response_model=InstrumentRead,
    summary="Activate / quarantine / retire an instrument (capability 168, §4.1)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_heat_instrument(
    instrument_id: uuid.UUID, body: InstrumentTransition, user: CurrentUser, db: DB
) -> InstrumentRead:
    return registers.transition_instrument(db, user, instrument_id, body)


@router.post(
    "/heat-instruments/{instrument_id}/devices",
    response_model=StationDeviceRegistered,
    status_code=status.HTTP_201_CREATED,
    summary="Register a weather-station device for a fixed station (capability 168, HS-4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def register_station_device(
    instrument_id: uuid.UUID, body: StationDeviceCreate, user: CurrentUser, db: DB
) -> StationDeviceRegistered:
    return registers.register_device(db, user, instrument_id, body)


@router.post(
    "/heat-instruments/{instrument_id}/devices/{device_pk}/revoke",
    response_model=StationDeviceRead,
    summary="Revoke a weather-station device (its sessions end; ingest answers 401)",
    responses=error_responses(401, 403, 404, 409),
)
def revoke_station_device(
    instrument_id: uuid.UUID, device_pk: uuid.UUID, user: CurrentUser, db: DB
) -> StationDeviceRead:
    return registers.revoke_device(db, user, instrument_id, device_pk)


# ---- monitoring points ---------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/monitoring-points",
    response_model=PointPage,
    summary="Monitoring points (capability 166)",
    responses=error_responses(401, 403, 404),
)
def list_monitoring_points(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> PointPage:
    return registers.list_points(db, user, project_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/monitoring-points",
    response_model=PointRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a monitoring point (capability 168; ZONE_ALREADY_COVERED, HS-3)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_monitoring_point(
    project_id: uuid.UUID, body: PointCreate, user: CurrentUser, db: DB
) -> PointRead:
    return registers.create_point(db, user, project_id, body)


@router.patch(
    "/monitoring-points/{point_id}",
    response_model=PointRead,
    summary="Edit a monitoring point (capability 168)",
    responses=error_responses(401, 403, 404, 422),
)
def update_monitoring_point(
    point_id: uuid.UUID, body: PointUpdate, user: CurrentUser, db: DB
) -> PointRead:
    return registers.update_point(db, user, point_id, body)


# ---- rest stations -------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/rest-stations",
    response_model=RestStationPage,
    summary="Rest stations (capability 166)",
    responses=error_responses(401, 403, 404),
)
def list_rest_stations(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> RestStationPage:
    return registers.list_stations(db, user, project_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/rest-stations",
    response_model=RestStationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a rest station (capability 168)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_rest_station(
    project_id: uuid.UUID, body: RestStationCreate, user: CurrentUser, db: DB
) -> RestStationRead:
    return registers.create_station(db, user, project_id, body)


@router.patch(
    "/rest-stations/{station_id}",
    response_model=RestStationRead,
    summary="Edit a rest station (capability 168)",
    responses=error_responses(401, 403, 404, 422),
)
def update_rest_station(
    station_id: uuid.UUID, body: RestStationUpdate, user: CurrentUser, db: DB
) -> RestStationRead:
    return registers.update_station(db, user, station_id, body)
