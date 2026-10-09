"""Emergency equipment (spec 6c-emergency-drills §3.8, §3.9, §4.4, EA-1…EA-7): the asset register
with EA stickers, readiness (§6.5), periodic checks by sticker scan or manual choice, tag-out and
retirement."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.emergency_enums import AssetStatus, AssetType, NotReadyReason
from app.core.errors import error_responses
from app.schemas.emergency import (
    AssetCreate,
    AssetPage,
    AssetRead,
    AssetTransition,
    AssetUpdate,
    CheckCreate,
    CheckPage,
    CheckRead,
    VoidInput,
)
from app.services.emergency import assets

router = APIRouter(tags=["emergency-assets"])


@router.get(
    "/projects/{project_id}/emergency-assets",
    response_model=AssetPage,
    summary="Emergency asset register with readiness (178)",
    responses=error_responses(401, 403, 404),
)
def list_emergency_assets(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    site_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    asset_type: Annotated[list[AssetType] | None, Query()] = None,
    status_: Annotated[AssetStatus | None, Query(alias="status")] = None,
    not_ready_reason: NotReadyReason | None = None,
    ready: bool | None = None,
) -> AssetPage:
    return assets.list_assets(
        db, user, project_id, site_id, zone_id, asset_type, status_, not_ready_reason, ready,
        pg.page, pg.page_size,
    )  # fmt: skip


@router.post(
    "/projects/{project_id}/emergency-assets",
    response_model=AssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an asset with its EA sticker (182; EA-1)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_emergency_asset(
    project_id: uuid.UUID, body: AssetCreate, user: CurrentUser, db: DB
) -> AssetRead:
    return assets.create_asset(db, user, project_id, body)


@router.get(
    "/emergency-assets/{asset_id}",
    response_model=AssetRead,
    summary="One asset with readiness",
    responses=error_responses(401, 403, 404),
)
def get_emergency_asset(asset_id: uuid.UUID, user: CurrentUser, db: DB) -> AssetRead:
    return assets.read_asset(db, user, asset_id)


@router.patch(
    "/emergency-assets/{asset_id}",
    response_model=AssetRead,
    summary="Edit location, service record or expiries (182)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_emergency_asset(
    asset_id: uuid.UUID, body: AssetUpdate, user: CurrentUser, db: DB
) -> AssetRead:
    return assets.update_asset(db, user, asset_id, body)


@router.post(
    "/emergency-assets/{asset_id}/transitions",
    response_model=AssetRead,
    summary="Tag out (183) or retire (182) an asset (§4.4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_emergency_asset(
    asset_id: uuid.UUID, body: AssetTransition, user: CurrentUser, db: DB
) -> AssetRead:
    return assets.transition_asset(db, user, asset_id, body)


@router.get(
    "/projects/{project_id}/emergency-asset-checks",
    response_model=CheckPage,
    summary="Asset checks, newest first (178)",
    responses=error_responses(401, 403, 404),
)
def list_emergency_asset_checks(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    asset_id: uuid.UUID | None = None,
) -> CheckPage:
    return assets.list_checks(db, user, project_id, asset_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/emergency-asset-checks",
    response_model=CheckRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a check by sticker scan or manual choice (183; EA-2…EA-4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_emergency_asset_check(
    project_id: uuid.UUID, body: CheckCreate, user: CurrentUser, db: DB
) -> CheckRead:
    return assets.create_check(db, user, project_id, body)


@router.post(
    "/emergency-asset-checks/{check_id}/void",
    response_model=CheckRead,
    summary="Void a check (190, reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_emergency_asset_check(
    check_id: uuid.UUID, body: VoidInput, user: CurrentUser, db: DB
) -> CheckRead:
    return assets.void_check(db, user, check_id, body)
