"""Phase 2 project settings (spec 2-access-permits §3.22; capability 80)."""

import uuid

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.core.errors import error_responses, not_implemented
from app.schemas.access_settings import AccessSettingsRead, AccessSettingsUpdate

router = APIRouter(tags=["access-settings"])


@router.get(
    "/projects/{project_id}/access-settings",
    response_model=AccessSettingsRead,
    summary="Phase 2 settings, hook policy and hook-requirement maps of a project",
    responses=error_responses(401, 403, 404),
)
def get_access_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> AccessSettingsRead:
    raise not_implemented()


@router.patch(
    "/projects/{project_id}/access-settings",
    response_model=AccessSettingsRead,
    summary="Update Phase 2 settings (HSE Manager, capability 80; audited)",
    responses=error_responses(401, 403, 404, 422),
)
def update_access_settings(
    project_id: uuid.UUID, body: AccessSettingsUpdate, user: CurrentUser, db: DB
) -> AccessSettingsRead:
    raise not_implemented()
