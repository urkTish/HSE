"""Waste streams, storage areas and consignments (spec 6e-environmental §3.4–§3.6, §4.3, WST,
CON, AIR-2, AIR-3)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.env_enums import ConsignmentStatus
from app.core.errors import error_responses
from app.schemas.env import (
    AreaCreate,
    AreaPage,
    AreaRead,
    AreaUpdate,
    ConsignmentCreate,
    ConsignmentPage,
    ConsignmentRead,
    ConsignmentTransition,
    ConsignmentUpdate,
    ReceiptInput,
    StreamList,
    StreamRead,
    StreamUpsert,
)
from app.services.env import waste

router = APIRouter(tags=["env-waste"])


@router.get(
    "/projects/{project_id}/waste-streams",
    response_model=StreamList,
    summary="Waste streams of the project (list WS with the project's route and density)",
    responses=error_responses(401, 403, 404),
)
def list_waste_streams(project_id: uuid.UUID, user: CurrentUser, db: DB) -> StreamList:
    return waste.list_streams(db, user, project_id)


@router.put(
    "/projects/{project_id}/waste-streams/{stream_code}",
    response_model=StreamRead,
    summary="Activate or edit a waste stream (205, WST-1; audited)",
    responses=error_responses(401, 403, 404, 422),
)
def upsert_waste_stream(
    project_id: uuid.UUID, stream_code: str, body: StreamUpsert, user: CurrentUser, db: DB
) -> StreamRead:
    return waste.upsert_stream(db, user, project_id, stream_code, body)


@router.get(
    "/projects/{project_id}/waste-storage-areas",
    response_model=AreaPage,
    summary="Waste storage areas (202)",
    responses=error_responses(401, 403, 404),
)
def list_waste_areas(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    site_id: uuid.UUID | None = None,
) -> AreaPage:
    return waste.list_areas(db, user, project_id, site_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/waste-storage-areas",
    response_model=AreaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a storage area (205; WST-2, AIR-2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_waste_area(
    project_id: uuid.UUID, body: AreaCreate, user: CurrentUser, db: DB
) -> AreaRead:
    return waste.create_area(db, user, project_id, body)


@router.get(
    "/waste-storage-areas/{area_id}",
    response_model=AreaRead,
    summary="One storage area with its hazardous deadlines, WSA / ENV answers and consignments",
    responses=error_responses(401, 403, 404),
)
def get_waste_area(area_id: uuid.UUID, user: CurrentUser, db: DB) -> AreaRead:
    return waste.read_area(db, user, area_id)


@router.patch(
    "/waste-storage-areas/{area_id}",
    response_model=AreaRead,
    summary="Edit a storage area (205; accumulation start dates, WST-5)",
    responses=error_responses(401, 403, 404, 422),
)
def update_waste_area(area_id: uuid.UUID, body: AreaUpdate, user: CurrentUser, db: DB) -> AreaRead:
    return waste.update_area(db, user, area_id, body)


@router.get(
    "/projects/{project_id}/waste-consignments",
    response_model=ConsignmentPage,
    summary="Consignment register (202; driver and plate per P6e-3)",
    responses=error_responses(401, 403, 404),
)
def list_waste_consignments(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[ConsignmentStatus] | None, Query(alias="status")] = None,
    stream_code: str | None = None,
    provider_id: uuid.UUID | None = None,
    overdue: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ConsignmentPage:
    return waste.list_consignments(
        db, user, project_id, status_, stream_code, provider_id, overdue, date_from, date_to,
        pg.page, pg.page_size,
    )  # fmt: skip


@router.post(
    "/projects/{project_id}/waste-consignments",
    response_model=ConsignmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Dispatch a consignment (206; CON-1…CON-5, licence check without override)",
    description="422 PRODUCER_REGISTRATION_INVALID, PROVIDER_LICENCE_INVALID, "
    "LICENCE_SCOPE_MISMATCH, PROVIDER_NOT_APPROVED, MANIFEST_REF_REQUIRED, STREAM_NOT_ACCEPTED. "
    "Warning AVP_NOT_FOUND (AIR-3).",
    responses=error_responses(401, 403, 404, 422),
)
def create_waste_consignment(
    project_id: uuid.UUID, body: ConsignmentCreate, user: CurrentUser, db: DB
) -> ConsignmentRead:
    return waste.create_consignment(db, user, project_id, body)


@router.get(
    "/waste-consignments/{consignment_id}",
    response_model=ConsignmentRead,
    summary="One consignment",
    responses=error_responses(401, 403, 404),
)
def get_waste_consignment(consignment_id: uuid.UUID, user: CurrentUser, db: DB) -> ConsignmentRead:
    return waste.read_consignment(db, user, consignment_id)


@router.patch(
    "/waste-consignments/{consignment_id}",
    response_model=ConsignmentRead,
    summary="Edit a consignment until Closed (206; 409 CONSIGNMENT_CLOSED)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_waste_consignment(
    consignment_id: uuid.UUID, body: ConsignmentUpdate, user: CurrentUser, db: DB
) -> ConsignmentRead:
    return waste.update_consignment(db, user, consignment_id, body)


@router.post(
    "/waste-consignments/{consignment_id}/receipt",
    response_model=ConsignmentRead,
    summary="Record the weighbridge receipt (206 / 207; CON-6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_consignment_receipt(
    consignment_id: uuid.UUID, body: ReceiptInput, user: CurrentUser, db: DB
) -> ConsignmentRead:
    return waste.record_receipt(db, user, consignment_id, body)


@router.post(
    "/waste-consignments/{consignment_id}/transitions",
    response_model=ConsignmentRead,
    summary="Close (207, CON-7), reject (207, CON-8) or void (214) a consignment",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_waste_consignment(
    consignment_id: uuid.UUID, body: ConsignmentTransition, user: CurrentUser, db: DB
) -> ConsignmentRead:
    return waste.transition_consignment(db, user, consignment_id, body)
