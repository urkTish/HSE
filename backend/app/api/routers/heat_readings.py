"""WBGT readings, weather-station ingest, imports and the live heat board (spec 6b-heat-stress
§3.3, §3.5, WB, WR, §8.1 item 2)."""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, File, Query, Security, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import DB, CurrentUser, PageParams, bearer_scheme
from app.core.errors import error_responses
from app.core.heat_enums import RecordStatus
from app.schemas.heat import (
    AcclimatisationStatusRead,
    HeatBoard,
    HeatDutyList,
    ReadingCreate,
    ReadingImportResult,
    ReadingPage,
    ReadingRead,
    StationReadingCreate,
    StationSessionInput,
    StationSessionRead,
    VoidInput,
    ZoneHeatState,
)
from app.services.heat import board, readings

router = APIRouter(tags=["heat-readings"])


@router.get(
    "/projects/{project_id}/wbgt-readings",
    response_model=ReadingPage,
    summary="WBGT readings with regime cells (capability 166)",
    responses=error_responses(401, 403, 404),
)
def list_wbgt_readings(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    point_id: uuid.UUID | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    status_: Annotated[RecordStatus | None, Query(alias="status")] = None,
) -> ReadingPage:
    return readings.list_readings(
        db, user, project_id, pg.page, pg.page_size, point_id, from_at, to_at, status_
    )


@router.post(
    "/projects/{project_id}/wbgt-readings",
    response_model=ReadingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a manual WBGT reading (capability 167; WB-1…WB-4)",
    responses=error_responses(401, 403, 404, 422),
)
def create_wbgt_reading(
    project_id: uuid.UUID, body: ReadingCreate, user: CurrentUser, db: DB
) -> ReadingRead:
    return readings.create_manual(db, user, project_id, body)


@router.post(
    "/wbgt-readings/{reading_id}/void",
    response_model=ReadingRead,
    summary="Void a reading (capability 177; reason ≥ 20 chars; state recomputed, WB-5)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_wbgt_reading(
    reading_id: uuid.UUID, body: VoidInput, user: CurrentUser, db: DB
) -> ReadingRead:
    return readings.void(db, user, reading_id, body)


@router.post(
    "/projects/{project_id}/wbgt-imports",
    response_model=ReadingImportResult,
    summary="Import readings (template wbgt_readings, .csv ≤ 5 MB; capability 168; WB-4)",
    responses=error_responses(401, 403, 404, 422),
)
def import_wbgt_readings(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    file: Annotated[UploadFile, File(description="CSV in the wbgt_readings template.")],
    dry_run: bool = True,
) -> ReadingImportResult:
    return readings.import_csv(db, user, project_id, file, dry_run)


@router.post(
    "/heat/station-session",
    response_model=StationSessionRead,
    summary="Start a weather-station session with the device token (no user login, HS-4)",
    responses=error_responses(401, 422),
)
def start_station_session(body: StationSessionInput, db: DB) -> StationSessionRead:
    return readings.station_session(db, body)


@router.post(
    "/heat/station-readings",
    response_model=ReadingRead,
    summary="Weather-station reading ingest (device session only; idempotent per measured_at)",
    responses=error_responses(401, 403, 422),
)
def ingest_station_reading(
    body: StationReadingCreate,
    db: DB,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
) -> ReadingRead:
    return readings.ingest(db, bearer.credentials if bearer else None, body)


@router.get(
    "/projects/{project_id}/heat-board",
    response_model=HeatBoard,
    summary="Live heat band: zone WBGT, state, regimes, ban, exemptions (capability 166)",
    responses=error_responses(401, 403, 404),
)
def get_heat_board(
    project_id: uuid.UUID, user: CurrentUser, db: DB, at: datetime | None = None
) -> HeatBoard:
    return board.board(db, user, project_id, at)


@router.get(
    "/zones/{zone_id}/heat-state",
    response_model=ZoneHeatState,
    summary="The zone regime in force at a time (§6.3; default now)",
    responses=error_responses(401, 403, 404),
)
def get_zone_heat_state(
    zone_id: uuid.UUID, user: CurrentUser, db: DB, at: datetime | None = None
) -> ZoneHeatState:
    return board.zone_state(db, user, zone_id, at)


@router.get(
    "/projects/{project_id}/heat-duty-list",
    response_model=HeatDutyList,
    summary="Heat duty list per engagement and day (capability 166, §8.4)",
    responses=error_responses(401, 403, 404),
)
def get_heat_duty_list(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    day: date | None = None,
    engagement_id: uuid.UUID | None = None,
) -> HeatDutyList:
    return board.duty_list(db, user, project_id, day, engagement_id)


@router.get(
    "/workers/{worker_id}/acclimatisation-status",
    response_model=AcclimatisationStatusRead,
    summary="A worker's acclimatisation status on a day (§6.4; capability 166)",
    responses=error_responses(401, 403, 404),
)
def get_acclimatisation_status(
    worker_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    project_id: uuid.UUID,
    day: date | None = None,
) -> AcclimatisationStatusRead:
    return board.acclimatisation_status(db, user, project_id, worker_id, day)
