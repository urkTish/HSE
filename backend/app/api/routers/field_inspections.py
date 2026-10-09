"""Field execution (spec 6d-field-assurance §3.4–§3.6, §3.9, EXE-1…EXE-9, FND-1…FND-9): checklist
submissions (idempotent, offline tolerant), responses, the findings and stop-work registers, voids,
the offline pack, the field band and the 6d action panel."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.field_enums import FindingSeverity, StopOrderStatus
from app.schemas.field import (
    FieldActionPanel,
    FieldBand,
    FieldFindingPage,
    FieldVoid,
    InspectionVoid,
    OfflinePack,
    ResponseRead,
    StopWorkPage,
    StopWorkRead,
    StopWorkRelease,
    SubmissionCreate,
)
from app.schemas.inspections import InspectionRead
from app.services.field import board, execution, stopwork

router = APIRouter(tags=["field-inspections"])


@router.post(
    "/projects/{project_id}/checklist-submissions",
    response_model=ResponseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a checklist inspection (33; EXE-1…EXE-7, FND-1…FND-7)",
    description="Idempotent on client_uuid: a repeat returns the stored response (200 semantics, "
    "no second CA, alert or stop-work order). completed_at older than offline_submit_max_hours → "
    "422 OFFLINE_SUBMIT_TOO_LATE; later than received + 5 min → 422 CLOCK_SKEW.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def submit_checklist(
    project_id: uuid.UUID, body: SubmissionCreate, user: CurrentUser, db: DB
) -> ResponseRead:
    return execution.submit(db, user, project_id, body)


@router.get(
    "/checklist-responses/{response_id}",
    response_model=ResponseRead,
    summary="One checklist response with answers, findings and score (200)",
    responses=error_responses(401, 403, 404),
)
def get_checklist_response(response_id: uuid.UUID, user: CurrentUser, db: DB) -> ResponseRead:
    return execution.read_response(db, user, response_id)


@router.post(
    "/inspections/{inspection_id}/void",
    response_model=InspectionRead,
    summary="Void a Completed inspection (201; EXE-9)",
    description="The response and findings leave every KPI; CAs and stop-work orders stay; a "
    "planned instance returns to Planned or Missed by its dates.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_inspection(
    inspection_id: uuid.UUID, body: InspectionVoid, user: CurrentUser, db: DB
) -> InspectionRead:
    return execution.void_inspection(db, user, inspection_id, body)


@router.get(
    "/projects/{project_id}/field-findings",
    response_model=FieldFindingPage,
    summary="Findings register (200; repeat flag, CA status)",
    responses=error_responses(401, 403, 404),
)
def list_field_findings(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    site_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
    severity: Annotated[list[FindingSeverity] | None, Query()] = None,
    item_code: str | None = None,
    repeat: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> FieldFindingPage:
    return execution.list_findings(
        db, user, project_id, site_id, engagement_id, severity, item_code, repeat, date_from,
        date_to, pg.page, pg.page_size,
    )  # fmt: skip


@router.get(
    "/projects/{project_id}/field-offline-pack",
    response_model=OfflinePack,
    summary="Offline pack for the phone (EXE-6; no ID numbers, no card tokens)",
    responses=error_responses(401, 403, 404),
)
def get_field_offline_pack(project_id: uuid.UUID, user: CurrentUser, db: DB) -> OfflinePack:
    return execution.offline_pack(db, user, project_id)


# ---- stop-work orders ----------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/stop-work-orders",
    response_model=StopWorkPage,
    summary="Stop-work register (200)",
    responses=error_responses(401, 403, 404),
)
def list_stop_work_orders(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[StopOrderStatus] | None, Query(alias="status")] = None,
    site_id: uuid.UUID | None = None,
) -> StopWorkPage:
    return stopwork.list_orders(db, user, project_id, status_, site_id, pg.page, pg.page_size)


@router.get(
    "/stop-work-orders/{order_id}",
    response_model=StopWorkRead,
    summary="One stop-work order",
    responses=error_responses(401, 403, 404),
)
def get_stop_work_order(order_id: uuid.UUID, user: CurrentUser, db: DB) -> StopWorkRead:
    return stopwork.read_order(db, user, order_id)


@router.post(
    "/stop-work-orders/{order_id}/release",
    response_model=StopWorkRead,
    summary="Release a stop-work order (196; FND-8)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def release_stop_work_order(
    order_id: uuid.UUID, body: StopWorkRelease, user: CurrentUser, db: DB
) -> StopWorkRead:
    return stopwork.release_order(db, user, order_id, body)


@router.post(
    "/stop-work-orders/{order_id}/void",
    response_model=StopWorkRead,
    summary="Void a stop-work order raised in error (201)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_stop_work_order(
    order_id: uuid.UUID, body: FieldVoid, user: CurrentUser, db: DB
) -> StopWorkRead:
    return stopwork.void_order(db, user, order_id, body)


# ---- board ---------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/field-action-panel",
    response_model=FieldActionPanel,
    summary="6d action-panel items (§8.2)",
    responses=error_responses(401, 403, 404),
)
def get_field_action_panel(project_id: uuid.UUID, user: CurrentUser, db: DB) -> FieldActionPanel:
    return board.action_panel(db, user, project_id)


@router.get(
    "/projects/{project_id}/field-band",
    response_model=FieldBand,
    summary="Field band (§8.1 item 2, live)",
    responses=error_responses(401, 403, 404),
)
def get_field_band(project_id: uuid.UUID, user: CurrentUser, db: DB) -> FieldBand:
    return board.band(db, user, project_id)
