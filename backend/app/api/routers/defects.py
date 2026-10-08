"""Equipment and scaffold defects (spec 4-third-party-cert §3.11, §4.5, §6.3, DF-1…DF-10)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.cert_enums import DefectCategory, DefectSource, DefectStatus, EquipmentCertCategory
from app.core.errors import error_responses
from app.schemas.defects import (
    DefectCancelInput,
    DefectCloseInput,
    DefectCreate,
    DefectDestroyInput,
    DefectPage,
    DefectRead,
    DefectReopenInput,
    IncidentDefectPrompt,
    RectificationInput,
)
from app.services.cert import defects as svc

router = APIRouter(tags=["defects"])


@router.get(
    "/projects/{project_id}/defects",
    response_model=DefectPage,
    summary="Defect register by category and age (capability 105)",
    responses=error_responses(401, 403, 404, 422),
)
def list_defects(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[DefectStatus] | None, Query(alias="status")] = None,
    category: Annotated[list[DefectCategory] | None, Query()] = None,
    source: Annotated[list[DefectSource] | None, Query()] = None,
    equipment_category: Annotated[list[EquipmentCertCategory] | None, Query()] = None,
    equipment_id: uuid.UUID | None = None,
    scaffold_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    overdue: bool | None = None,
    due_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
) -> DefectPage:
    return svc.list_defects(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        status_,
        category,
        source,
        equipment_category,
        equipment_id,
        scaffold_id,
        engagement_id,
        include_subcontractors,
        overdue,
        due_within_days,
    )


@router.post(
    "/projects/{project_id}/defects",
    response_model=DefectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Raise a defect (capability 110; A → Out of Service at once, DF-3)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_defect(
    project_id: uuid.UUID, body: DefectCreate, user: CurrentUser, db: DB
) -> DefectRead:
    return svc.create(db, user, project_id, body)


@router.get(
    "/defects/{defect_id}",
    response_model=DefectRead,
    summary="Defect detail",
    responses=error_responses(401, 403, 404),
)
def get_defect(defect_id: uuid.UUID, user: CurrentUser, db: DB) -> DefectRead:
    return svc.read(db, user, defect_id)


@router.post(
    "/defects/{defect_id}/rectification",
    response_model=DefectRead,
    summary="Record rectification → Rectified (DF-5; capability 111)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def rectify_defect(
    defect_id: uuid.UUID, body: RectificationInput, user: CurrentUser, db: DB
) -> DefectRead:
    return svc.rectify(db, user, defect_id, body)


@router.post(
    "/defects/{defect_id}/close",
    response_model=DefectRead,
    summary="Close a rectified defect (DF-6; capability 112; SoD)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def close_defect(
    defect_id: uuid.UUID, body: DefectCloseInput, user: CurrentUser, db: DB
) -> DefectRead:
    return svc.close(db, user, defect_id, body)


@router.post(
    "/defects/{defect_id}/reopen",
    response_model=DefectRead,
    summary="Rectified → Open: verification failed (capability 112)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def reopen_defect(
    defect_id: uuid.UUID, body: DefectReopenInput, user: CurrentUser, db: DB
) -> DefectRead:
    return svc.reopen(db, user, defect_id, body)


@router.post(
    "/defects/{defect_id}/destroy",
    response_model=DefectRead,
    summary="Close as destroyed / returned to manufacturer; item Retired (DF-7; 112)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def destroy_defect_item(
    defect_id: uuid.UUID, body: DefectDestroyInput, user: CurrentUser, db: DB
) -> DefectRead:
    return svc.destroy(db, user, defect_id, body)


@router.post(
    "/defects/{defect_id}/cancel",
    response_model=DefectRead,
    summary="Cancel a defect raised in error (capability 112; not TPI-raised)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def cancel_defect(
    defect_id: uuid.UUID, body: DefectCancelInput, user: CurrentUser, db: DB
) -> DefectRead:
    return svc.cancel(db, user, defect_id, body)


@router.get(
    "/incidents/{incident_id}/defect-prompt",
    response_model=IncidentDefectPrompt,
    summary="Whether the incident should be linked to a defect, and its linked defects (DF-9)",
    responses=error_responses(401, 403, 404),
)
def get_incident_defect_prompt(
    incident_id: uuid.UUID, user: CurrentUser, db: DB
) -> IncidentDefectPrompt:
    return svc.incident_prompt(db, user, incident_id)
