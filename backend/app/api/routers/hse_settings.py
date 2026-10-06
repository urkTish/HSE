"""Phase 1 project settings, AI transfer approval and reference lists (spec 1-dashboard §3.10,
§3.11, AI-14)."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser
from app.core.errors import error_responses, not_implemented
from app.core.hse_enums import ReferenceList
from app.schemas.hse_settings import (
    AiTransferApprovalCreate,
    HseSettingsRead,
    HseSettingsUpdate,
    ReferenceItemRead,
    ReferenceItemUpdate,
    ReferenceListsRead,
)

router = APIRouter(tags=["hse settings"])


@router.get(
    "/projects/{project_id}/hse-settings",
    response_model=HseSettingsRead,
    summary="Phase 1 settings and KPI targets of a project",
    responses=error_responses(401, 403, 404),
)
def get_hse_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> HseSettingsRead:
    raise not_implemented()


@router.patch(
    "/projects/{project_id}/hse-settings",
    response_model=HseSettingsRead,
    summary="Update Phase 1 settings / targets / ai_enabled (HSE Manager, capability 44)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_hse_settings(
    project_id: uuid.UUID, body: HseSettingsUpdate, user: CurrentUser, db: DB
) -> HseSettingsRead:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/ai-transfer-approval",
    response_model=HseSettingsRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record the client's approval of AI data transfer (HSE Manager, AI-14)",
    responses=error_responses(401, 403, 404, 422),
)
def record_ai_transfer_approval(
    project_id: uuid.UUID, body: AiTransferApprovalCreate, user: CurrentUser, db: DB
) -> HseSettingsRead:
    raise not_implemented()


@router.delete(
    "/projects/{project_id}/ai-transfer-approval",
    response_model=HseSettingsRead,
    summary="Withdraw the AI transfer approval (disables AI on the project)",
    responses=error_responses(401, 403, 404),
)
def withdraw_ai_transfer_approval(
    project_id: uuid.UUID, user: CurrentUser, db: DB
) -> HseSettingsRead:
    raise not_implemented()


@router.get(
    "/reference-lists",
    response_model=ReferenceListsRead,
    summary="All §3.11 reference lists with current EN/AR labels",
    responses=error_responses(401, 403),
)
def list_reference_lists(user: CurrentUser, db: DB) -> ReferenceListsRead:
    raise not_implemented()


@router.patch(
    "/reference-lists/{list_name}/{code}",
    response_model=ReferenceItemRead,
    summary="Edit a reference-list label (HSE Manager; codes immutable)",
    responses=error_responses(401, 403, 404, 422),
)
def update_reference_item(
    list_name: ReferenceList, code: str, body: ReferenceItemUpdate, user: CurrentUser, db: DB
) -> ReferenceItemRead:
    raise not_implemented()
