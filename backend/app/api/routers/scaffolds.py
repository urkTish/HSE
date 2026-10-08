"""Scaffold register, tags, inspections, re-inspection requests and the tag board (spec
4-third-party-cert §3.8, §4.6, §6.4, SF-1…SF-7)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.cert_enums import ScaffoldStatus, ScaffoldTagStatus, ScaffoldType
from app.core.errors import error_responses, not_implemented
from app.schemas.equipment import EquipmentStickerRead, StickerReissueRequest
from app.schemas.scaffolds import (
    ScaffoldBoard,
    ScaffoldCreate,
    ScaffoldInspectionCreate,
    ScaffoldInspectionList,
    ScaffoldInspectionRead,
    ScaffoldPage,
    ScaffoldRead,
    ScaffoldReinspectionRequest,
    ScaffoldReinspectionResult,
    ScaffoldTransitionRequest,
    ScaffoldUpdate,
)

router = APIRouter(tags=["scaffolds"])


@router.get(
    "/projects/{project_id}/scaffolds",
    response_model=ScaffoldPage,
    summary="Scaffold register (capability 105)",
    responses=error_responses(401, 403, 404, 422),
)
def list_scaffolds(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[str | None, Query(max_length=100, description="Tag, location.")] = None,
    status_: Annotated[list[ScaffoldStatus] | None, Query(alias="status")] = None,
    tag_status: Annotated[list[ScaffoldTagStatus] | None, Query()] = None,
    scaffold_type: Annotated[list[ScaffoldType] | None, Query()] = None,
    site_id: uuid.UUID | None = None,
    zone_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    inspection_due_by: date | None = None,
) -> ScaffoldPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/scaffolds",
    response_model=ScaffoldRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a scaffold (capability 106) → Under Erection, red tag",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_scaffold(
    project_id: uuid.UUID, body: ScaffoldCreate, user: CurrentUser, db: DB
) -> ScaffoldRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/scaffold-board",
    response_model=ScaffoldBoard,
    summary="Scaffold tag board per zone (§8.4)",
    responses=error_responses(401, 403, 404, 422),
)
def get_scaffold_board(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    site_id: uuid.UUID | None = None,
    as_of: date | None = None,
) -> ScaffoldBoard:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/scaffold-reinspection-requests",
    response_model=ScaffoldReinspectionResult,
    summary="Require re-inspection of every In Use scaffold of a site / zone (SF-5; 112)",
    responses=error_responses(401, 403, 404, 422),
)
def request_scaffold_reinspection(
    project_id: uuid.UUID, body: ScaffoldReinspectionRequest, user: CurrentUser, db: DB
) -> ScaffoldReinspectionResult:
    raise not_implemented()


@router.get(
    "/scaffolds/{scaffold_id}",
    response_model=ScaffoldRead,
    summary="Scaffold detail with the current tag and crew certification (SF-3)",
    responses=error_responses(401, 403, 404),
)
def get_scaffold(scaffold_id: uuid.UUID, user: CurrentUser, db: DB) -> ScaffoldRead:
    raise not_implemented()


@router.patch(
    "/scaffolds/{scaffold_id}",
    response_model=ScaffoldRead,
    summary="Edit a scaffold (capability 106; not while In Use with a green / yellow tag "
    "for structural fields)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_scaffold(
    scaffold_id: uuid.UUID, body: ScaffoldUpdate, user: CurrentUser, db: DB
) -> ScaffoldRead:
    raise not_implemented()


@router.post(
    "/scaffolds/{scaffold_id}/transitions",
    response_model=ScaffoldRead,
    summary="Start alteration / dismantle (§4.6; capability 106)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_scaffold(
    scaffold_id: uuid.UUID, body: ScaffoldTransitionRequest, user: CurrentUser, db: DB
) -> ScaffoldRead:
    raise not_implemented()


@router.get(
    "/scaffolds/{scaffold_id}/inspections",
    response_model=ScaffoldInspectionList,
    summary="Scaffold inspections (newest first)",
    responses=error_responses(401, 403, 404),
)
def list_scaffold_inspections(
    scaffold_id: uuid.UUID, user: CurrentUser, db: DB
) -> ScaffoldInspectionList:
    raise not_implemented()


@router.post(
    "/scaffolds/{scaffold_id}/inspections",
    response_model=ScaffoldInspectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a scaffold inspection and tag (capability 113; SF-2…SF-4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_scaffold_inspection(
    scaffold_id: uuid.UUID, body: ScaffoldInspectionCreate, user: CurrentUser, db: DB
) -> ScaffoldInspectionRead:
    raise not_implemented()


@router.get(
    "/scaffolds/{scaffold_id}/sticker",
    response_model=EquipmentStickerRead,
    summary="Scaffold EQ sticker payload and printed ref",
    responses=error_responses(401, 403, 404, 409),
)
def get_scaffold_sticker(scaffold_id: uuid.UUID, user: CurrentUser, db: DB) -> EquipmentStickerRead:
    raise not_implemented()


@router.post(
    "/scaffolds/{scaffold_id}/sticker/reissue",
    response_model=EquipmentStickerRead,
    summary="Rotate the scaffold sticker token (capability 106)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def reissue_scaffold_sticker(
    scaffold_id: uuid.UUID, body: StickerReissueRequest, user: CurrentUser, db: DB
) -> EquipmentStickerRead:
    raise not_implemented()
