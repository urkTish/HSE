"""Projects and project settings (spec §3.1, §3.9, §4.1, §5.5)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.enums import ProjectStatus, ProjectType
from app.core.errors import error_responses
from app.schemas.projects import (
    ProjectCreate,
    ProjectPage,
    ProjectRead,
    ProjectSettingsRead,
    ProjectSettingsUpdate,
    ProjectTransitionRequest,
    ProjectUpdate,
)
from app.services import projects as svc
from app.services.common import paginate

router = APIRouter(prefix="/projects", tags=["projects"])

ProjectSort = Literal["code", "-code", "name", "-name", "start_date", "-start_date"]


@router.get(
    "",
    response_model=ProjectPage,
    summary="List projects visible to the caller",
    responses=error_responses(401, 403, 422),
)
def list_projects(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[ProjectStatus] | None, Query(alias="status")] = None,
    project_type: ProjectType | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Code/name search.")] = None,
    sort: ProjectSort = "code",
) -> ProjectPage:
    stmt = svc.list_query(user, status_, project_type, q, sort, user.user.preferred_language)
    items, total = paginate(db, stmt, pg.page, pg.page_size)
    return ProjectPage(
        items=[svc.to_read(x) for x in items], total=total, page=pg.page, page_size=pg.page_size
    )


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project (HSE Manager); starts in planning with default settings",
    responses=error_responses(401, 403, 409, 422),
)
def create_project(body: ProjectCreate, user: CurrentUser, db: DB) -> ProjectRead:
    return svc.to_read(svc.create(db, user, body))


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project",
    responses=error_responses(401, 403, 404),
)
def get_project(project_id: uuid.UUID, user: CurrentUser, db: DB) -> ProjectRead:
    return svc.to_read(svc.get_visible(db, user, project_id))


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update a project (HSE Manager)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, user: CurrentUser, db: DB
) -> ProjectRead:
    return svc.to_read(svc.update(db, user, project_id, body))


@router.post(
    "/{project_id}/transitions",
    response_model=ProjectRead,
    summary="Change project status (HSE Manager)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_project(
    project_id: uuid.UUID, body: ProjectTransitionRequest, user: CurrentUser, db: DB
) -> ProjectRead:
    return svc.to_read(svc.transition(db, user, project_id, body))


@router.get(
    "/{project_id}/settings",
    response_model=ProjectSettingsRead,
    summary="Get project settings",
    responses=error_responses(401, 403, 404),
)
def get_project_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> ProjectSettingsRead:
    return svc.settings_read(svc.get_settings_for(db, user, project_id))


@router.patch(
    "/{project_id}/settings",
    response_model=ProjectSettingsRead,
    summary="Update project settings (HSE Manager); audited as settings_changed",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_project_settings(
    project_id: uuid.UUID, body: ProjectSettingsUpdate, user: CurrentUser, db: DB
) -> ProjectSettingsRead:
    return svc.settings_read(svc.update_settings(db, user, project_id, body))
