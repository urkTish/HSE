"""Spills, water use, dewatering discharge, complaints, the environment band and the 6e action
panel (spec 6e-environmental §3.13–§3.15, §4.6, §4.7, SPL, WAT, CPL, §8.1, §8.2)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.env_enums import ComplaintStatus, SpillStatus
from app.core.errors import error_responses
from app.schemas.env import (
    ComplaintCreate,
    ComplaintPage,
    ComplaintRead,
    ComplaintTransition,
    ComplaintUpdate,
    DischargeCreate,
    DischargePage,
    DischargeRead,
    EnvActionPanel,
    EnvBand,
    EnvVoid,
    NearbyReadings,
    SpillCreate,
    SpillPage,
    SpillRead,
    SpillTransition,
    WaterCreate,
    WaterPage,
    WaterRead,
    WaterUpdate,
)
from app.services.env import board, spills, water

router = APIRouter(tags=["env-events"])


@router.get(
    "/projects/{project_id}/spills",
    response_model=SpillPage,
    summary="Spill log (202)",
    responses=error_responses(401, 403, 404),
)
def list_spills(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[SpillStatus] | None, Query(alias="status")] = None,
    reportable: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> SpillPage:
    return spills.list_spills(
        db, user, project_id, status_, reportable, date_from, date_to, pg.page, pg.page_size
    )


@router.post(
    "/projects/{project_id}/spills",
    response_model=SpillRead,
    status_code=status.HTTP_201_CREATED,
    summary="Report a spill (211; SPL-1…SPL-5; idempotent on client_uuid)",
    description="A reportable spill links an existing environmental incident or creates one "
    "(422 INCIDENT_FIELDS_REQUIRED / INCIDENT_NOT_ENVIRONMENTAL).",
    responses=error_responses(401, 403, 404, 422),
)
def create_spill(project_id: uuid.UUID, body: SpillCreate, user: CurrentUser, db: DB) -> SpillRead:
    return spills.create_spill(db, user, project_id, body)


@router.get(
    "/spills/{spill_id}",
    response_model=SpillRead,
    summary="One spill",
    responses=error_responses(401, 403, 404),
)
def get_spill(spill_id: uuid.UUID, user: CurrentUser, db: DB) -> SpillRead:
    return spills.read_spill(db, user, spill_id)


@router.post(
    "/spills/{spill_id}/transitions",
    response_model=SpillRead,
    summary="Clean up (211), close (210; 422 CLEANUP_WASTE_UNTRACKED) or void (214) a spill",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_spill(
    spill_id: uuid.UUID, body: SpillTransition, user: CurrentUser, db: DB
) -> SpillRead:
    return spills.transition_spill(db, user, spill_id, body)


@router.get(
    "/projects/{project_id}/water-entries",
    response_model=WaterPage,
    summary="Monthly water use (202)",
    responses=error_responses(401, 403, 404),
)
def list_water_entries(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
) -> WaterPage:
    return water.list_water(db, user, project_id, month, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/water-entries",
    response_model=WaterRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record monthly water use (209; 422 DUPLICATE_WATER_ENTRY)",
    responses=error_responses(401, 403, 404, 422),
)
def create_water_entry(
    project_id: uuid.UUID, body: WaterCreate, user: CurrentUser, db: DB
) -> WaterRead:
    return water.create_water(db, user, project_id, body)


@router.patch(
    "/water-entries/{entry_id}",
    response_model=WaterRead,
    summary="Edit a water entry until the 10th of the next month (209)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_water_entry(
    entry_id: uuid.UUID, body: WaterUpdate, user: CurrentUser, db: DB
) -> WaterRead:
    return water.update_water(db, user, entry_id, body)


@router.post(
    "/water-entries/{entry_id}/void",
    response_model=WaterRead,
    summary="Void a water entry (214, reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_water_entry(entry_id: uuid.UUID, body: EnvVoid, user: CurrentUser, db: DB) -> WaterRead:
    return water.void_water(db, user, entry_id, body)


@router.get(
    "/projects/{project_id}/discharge-days",
    response_model=DischargePage,
    summary="Dewatering discharge days (202)",
    responses=error_responses(401, 403, 404),
)
def list_discharge_days(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> DischargePage:
    return water.list_discharge(db, user, project_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/discharge-days",
    response_model=DischargeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a discharge day (209; WAT-2, warning PERMIT_NOT_VALID)",
    responses=error_responses(401, 403, 404, 422),
)
def create_discharge_day(
    project_id: uuid.UUID, body: DischargeCreate, user: CurrentUser, db: DB
) -> DischargeRead:
    return water.create_discharge(db, user, project_id, body)


@router.get(
    "/projects/{project_id}/env-complaints",
    response_model=ComplaintPage,
    summary="Complaints log (202; complainant data per P6e-2)",
    responses=error_responses(401, 403, 404),
)
def list_env_complaints(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[ComplaintStatus] | None, Query(alias="status")] = None,
) -> ComplaintPage:
    return water.list_complaints(db, user, project_id, status_, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/env-complaints",
    response_model=ComplaintRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a complaint (212; CPL-1)",
    responses=error_responses(401, 403, 404, 422),
)
def create_env_complaint(
    project_id: uuid.UUID, body: ComplaintCreate, user: CurrentUser, db: DB
) -> ComplaintRead:
    return water.create_complaint(db, user, project_id, body)


@router.get(
    "/env-complaints/{complaint_id}",
    response_model=ComplaintRead,
    summary="One complaint",
    responses=error_responses(401, 403, 404),
)
def get_env_complaint(complaint_id: uuid.UUID, user: CurrentUser, db: DB) -> ComplaintRead:
    return water.read_complaint(db, user, complaint_id)


@router.patch(
    "/env-complaints/{complaint_id}",
    response_model=ComplaintRead,
    summary="Edit a complaint: investigation, links (212)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_env_complaint(
    complaint_id: uuid.UUID, body: ComplaintUpdate, user: CurrentUser, db: DB
) -> ComplaintRead:
    return water.update_complaint(db, user, complaint_id, body)


@router.post(
    "/env-complaints/{complaint_id}/transitions",
    response_model=ComplaintRead,
    summary="Respond, close (212) or void (214) a complaint",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_env_complaint(
    complaint_id: uuid.UUID, body: ComplaintTransition, user: CurrentUser, db: DB
) -> ComplaintRead:
    return water.transition_complaint(db, user, complaint_id, body)


@router.get(
    "/env-complaints/{complaint_id}/nearby-readings",
    response_model=NearbyReadings,
    summary="Readings on the complaint's site within ± 2 h (CPL-2, dust and noise)",
    responses=error_responses(401, 403, 404),
)
def get_complaint_nearby_readings(
    complaint_id: uuid.UUID, user: CurrentUser, db: DB
) -> NearbyReadings:
    return water.nearby_readings(db, user, complaint_id)


@router.get(
    "/projects/{project_id}/env-action-panel",
    response_model=EnvActionPanel,
    summary="6e action panel (§8.2; 202)",
    responses=error_responses(401, 403, 404),
)
def get_env_action_panel(project_id: uuid.UUID, user: CurrentUser, db: DB) -> EnvActionPanel:
    return board.action_panel(db, user, project_id)


@router.get(
    "/projects/{project_id}/env-band",
    response_model=EnvBand,
    summary="Environment band (§8.1 item 2; 202)",
    responses=error_responses(401, 403, 404),
)
def get_env_band(project_id: uuid.UUID, user: CurrentUser, db: DB) -> EnvBand:
    return board.band(db, user, project_id)
