"""Work-area access permits and operational suspension events (spec 2-access-permits §3.16,
§3.17, §4.8, §5.8)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.access_enums import OpsEventType, WapBlocker, WapStatus
from app.core.errors import error_responses, not_implemented
from app.schemas.waps import (
    CrewInput,
    OpsEventCreate,
    OpsEventEnd,
    OpsEventPage,
    OpsEventRead,
    OpsEventUpdate,
    WapBoardResponse,
    WapCreate,
    WapPage,
    WapPrintRead,
    WapRead,
    WapRevisionCreate,
    WapTransitionRequest,
    WapUpdate,
    WapVehicleInput,
)

router = APIRouter(tags=["work-area-permits"])


@router.get(
    "/projects/{project_id}/waps",
    response_model=WapPage,
    summary="WAP register (capability 73; crew names only with capability 46, WA-19)",
    responses=error_responses(401, 403, 404, 422),
)
def list_waps(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[WapStatus] | None, Query(alias="status")] = None,
    site_id: uuid.UUID | None = None,
    zone_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    active_on: date | None = None,
    blocked: Annotated[
        bool | None, Query(description="Action panel: Approved, inside validity, not Active.")
    ] = None,
    blocker: WapBlocker | None = None,
    worker_id: Annotated[uuid.UUID | None, Query(description="WAPs listing this worker.")] = None,
    vehicle_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> WapPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/waps",
    response_model=WapRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a WAP (capability 65) → draft",
    responses=error_responses(401, 403, 404, 422),
)
def create_wap(project_id: uuid.UUID, body: WapCreate, user: CurrentUser, db: DB) -> WapRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/wap-board",
    response_model=WapBoardResponse,
    summary="Today's WAP board per zone (crew counts, windows, NOTAM, clearance)",
    responses=error_responses(401, 403, 404, 422),
)
def get_wap_board(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    on: Annotated[date | None, Query(description="Local date; default today.")] = None,
    site_id: uuid.UUID | None = None,
) -> WapBoardResponse:
    raise not_implemented()


@router.get(
    "/waps/{wap_id}",
    response_model=WapRead,
    summary="Get a WAP with live blockers (WA-13)",
    responses=error_responses(401, 403, 404),
)
def get_wap(wap_id: uuid.UUID, user: CurrentUser, db: DB) -> WapRead:
    raise not_implemented()


@router.patch(
    "/waps/{wap_id}",
    response_model=WapRead,
    summary="Edit a draft WAP (capability 65)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_wap(wap_id: uuid.UUID, body: WapUpdate, user: CurrentUser, db: DB) -> WapRead:
    raise not_implemented()


@router.post(
    "/waps/{wap_id}/transitions",
    response_model=WapRead,
    summary="Move a WAP through §4.8 (submit, return, approve, reject, suspend, resume, close, "
    "cancel)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_wap(
    wap_id: uuid.UUID, body: WapTransitionRequest, user: CurrentUser, db: DB
) -> WapRead:
    raise not_implemented()


@router.post(
    "/waps/{wap_id}/revisions",
    response_model=WapRead,
    status_code=status.HTTP_201_CREATED,
    summary="Amend zones/dates/windows/links of an Approved/Active WAP → revision (WA-14)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_wap_revision(
    wap_id: uuid.UUID, body: WapRevisionCreate, user: CurrentUser, db: DB
) -> WapRead:
    raise not_implemented()


@router.post(
    "/waps/{wap_id}/crew",
    response_model=WapRead,
    summary="Add a crew member (capability 65; effective once evaluated, WA-14)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def add_wap_crew(wap_id: uuid.UUID, body: CrewInput, user: CurrentUser, db: DB) -> WapRead:
    raise not_implemented()


@router.delete(
    "/waps/{wap_id}/crew/{worker_id}",
    response_model=WapRead,
    summary="Remove a crew member (capability 65; history kept as status removed)",
    responses=error_responses(401, 403, 404, 409),
)
def remove_wap_crew(wap_id: uuid.UUID, worker_id: uuid.UUID, user: CurrentUser, db: DB) -> WapRead:
    raise not_implemented()


@router.post(
    "/waps/{wap_id}/vehicles",
    response_model=WapRead,
    summary="Add a vehicle (capability 65)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def add_wap_vehicle(wap_id: uuid.UUID, body: WapVehicleInput, user: CurrentUser, db: DB) -> WapRead:
    raise not_implemented()


@router.delete(
    "/waps/{wap_id}/vehicles/{vehicle_id}",
    response_model=WapRead,
    summary="Remove a vehicle (capability 65)",
    responses=error_responses(401, 403, 404, 409),
)
def remove_wap_vehicle(
    wap_id: uuid.UUID, vehicle_id: uuid.UUID, user: CurrentUser, db: DB
) -> WapRead:
    raise not_implemented()


@router.get(
    "/waps/{wap_id}/print",
    response_model=WapPrintRead,
    summary="WAP print with QR (crew names and worker_no only, WA-18)",
    responses=error_responses(401, 403, 404, 409),
)
def get_wap_print(wap_id: uuid.UUID, user: CurrentUser, db: DB) -> WapPrintRead:
    raise not_implemented()


# ---- operational suspension events --------------------------------------------------------------


@router.get(
    "/projects/{project_id}/ops-events",
    response_model=OpsEventPage,
    summary="Operational suspension log (capability 73)",
    responses=error_responses(401, 403, 404, 422),
)
def list_ops_events(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    active: bool | None = None,
    type_: Annotated[list[OpsEventType] | None, Query(alias="type")] = None,
    site_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> OpsEventPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/ops-events",
    response_model=OpsEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Declare an operational suspension (capability 67; WA-15 suspends WAPs)",
    responses=error_responses(401, 403, 404, 422),
)
def create_ops_event(
    project_id: uuid.UUID, body: OpsEventCreate, user: CurrentUser, db: DB
) -> OpsEventRead:
    raise not_implemented()


@router.get(
    "/ops-events/{event_id}",
    response_model=OpsEventRead,
    summary="Get an operational suspension event",
    responses=error_responses(401, 403, 404),
)
def get_ops_event(event_id: uuid.UUID, user: CurrentUser, db: DB) -> OpsEventRead:
    raise not_implemented()


@router.patch(
    "/ops-events/{event_id}",
    response_model=OpsEventRead,
    summary="Add zones to an active event (capability 67; defaults cannot be removed)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_ops_event(
    event_id: uuid.UUID, body: OpsEventUpdate, user: CurrentUser, db: DB
) -> OpsEventRead:
    raise not_implemented()


@router.post(
    "/ops-events/{event_id}/end",
    response_model=OpsEventRead,
    summary="End the event (capability 67; WAPs stay suspended until resumed)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def end_ops_event(
    event_id: uuid.UUID, body: OpsEventEnd, user: CurrentUser, db: DB
) -> OpsEventRead:
    raise not_implemented()
