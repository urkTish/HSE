"""Airport pass categories, area codes, applications and issued passes
(spec 2-access-permits §3.6-§3.9, §4.4, §5.4). Airport projects only (AP-2)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.access_enums import (
    CustodyStatus,
    PassApplicationStatus,
    PassApplicationType,
    ValidityStatus,
)
from app.core.errors import error_responses
from app.schemas.airport_passes import (
    AirportPassPage,
    AirportPassRead,
    BackgroundCheckUpdate,
    PassApplicationCreate,
    PassApplicationPage,
    PassApplicationRead,
    PassApplicationTransitionRequest,
    PassApplicationUpdate,
    PassAreaCreate,
    PassAreaList,
    PassAreaRead,
    PassAreaUpdate,
    PassCategoryCreate,
    PassCategoryList,
    PassCategoryRead,
    PassCategoryUpdate,
    PassIssueRequest,
)
from app.services.access import passes as svc

router = APIRouter(tags=["airport-passes"])

# ---- AP-CAT / AP-AREA ---------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/airport-pass-categories",
    response_model=PassCategoryList,
    summary="Pass categories (AP-CAT) of an airport project",
    responses=error_responses(401, 403, 404, 422),
)
def list_pass_categories(project_id: uuid.UUID, user: CurrentUser, db: DB) -> PassCategoryList:
    return svc.list_categories(db, user, project_id)


@router.post(
    "/projects/{project_id}/airport-pass-categories",
    response_model=PassCategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a pass category (capability 80)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_pass_category(
    project_id: uuid.UUID, body: PassCategoryCreate, user: CurrentUser, db: DB
) -> PassCategoryRead:
    return svc.create_category(db, user, project_id, body)


@router.patch(
    "/airport-pass-categories/{category_id}",
    response_model=PassCategoryRead,
    summary="Edit a pass category (capability 80; code immutable)",
    responses=error_responses(401, 403, 404, 422),
)
def update_pass_category(
    category_id: uuid.UUID, body: PassCategoryUpdate, user: CurrentUser, db: DB
) -> PassCategoryRead:
    return svc.update_category(db, user, category_id, body)


@router.get(
    "/projects/{project_id}/airport-pass-areas",
    response_model=PassAreaList,
    summary="Pass area codes (AP-AREA) of an airport project",
    responses=error_responses(401, 403, 404, 422),
)
def list_pass_areas(project_id: uuid.UUID, user: CurrentUser, db: DB) -> PassAreaList:
    return svc.list_areas(db, user, project_id)


@router.post(
    "/projects/{project_id}/airport-pass-areas",
    response_model=PassAreaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a pass area code (capability 80)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_pass_area(
    project_id: uuid.UUID, body: PassAreaCreate, user: CurrentUser, db: DB
) -> PassAreaRead:
    return svc.create_area(db, user, project_id, body)


@router.patch(
    "/airport-pass-areas/{area_id}",
    response_model=PassAreaRead,
    summary="Edit a pass area code (capability 80; code immutable)",
    responses=error_responses(401, 403, 404, 422),
)
def update_pass_area(
    area_id: uuid.UUID, body: PassAreaUpdate, user: CurrentUser, db: DB
) -> PassAreaRead:
    return svc.update_area(db, user, area_id, body)


# ---- applications -------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/pass-applications",
    response_model=PassApplicationPage,
    response_model_exclude_unset=True,
    summary="Pass application tracker (status ageing)",
    description="background_check / outcome_note keys only with capability 56 (AP-13).",
    responses=error_responses(401, 403, 404, 422),
)
def list_pass_applications(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[PassApplicationStatus] | None, Query(alias="status")] = None,
    application_type: PassApplicationType | None = None,
    worker_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    stale: Annotated[bool | None, Query(description="Action panel: lodged > stale days.")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> PassApplicationPage:
    return svc.list_applications(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        status_,
        application_type,
        worker_id,
        engagement_id,
        include_subcontractors,
        stale,
        q,
    )


@router.post(
    "/projects/{project_id}/pass-applications",
    response_model=PassApplicationRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pass application (capability 53) → draft",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_pass_application(
    project_id: uuid.UUID, body: PassApplicationCreate, user: CurrentUser, db: DB
) -> PassApplicationRead:
    return svc.create_application(db, user, project_id, body)


@router.get(
    "/pass-applications/{application_id}",
    response_model=PassApplicationRead,
    response_model_exclude_unset=True,
    summary="Get a pass application (background status audited for capability 56)",
    responses=error_responses(401, 403, 404),
)
def get_pass_application(
    application_id: uuid.UUID, user: CurrentUser, db: DB
) -> PassApplicationRead:
    return svc.read_application(db, user, application_id)


@router.patch(
    "/pass-applications/{application_id}",
    response_model=PassApplicationRead,
    response_model_exclude_unset=True,
    summary="Edit a draft application (capability 53)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_pass_application(
    application_id: uuid.UUID, body: PassApplicationUpdate, user: CurrentUser, db: DB
) -> PassApplicationRead:
    return svc.update_application(db, user, application_id, body)


@router.post(
    "/pass-applications/{application_id}/transitions",
    response_model=PassApplicationRead,
    response_model_exclude_unset=True,
    summary="Move an application through §4.4 (submit, return, endorse, lodge, decide, …)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_pass_application(
    application_id: uuid.UUID,
    body: PassApplicationTransitionRequest,
    user: CurrentUser,
    db: DB,
) -> PassApplicationRead:
    return svc.transition(db, user, application_id, body)


@router.put(
    "/pass-applications/{application_id}/background-check",
    response_model=PassApplicationRead,
    response_model_exclude_unset=True,
    summary="Record the background-check status and date (capabilities 55 + 56)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def put_background_check(
    application_id: uuid.UUID, body: BackgroundCheckUpdate, user: CurrentUser, db: DB
) -> PassApplicationRead:
    return svc.put_background(db, user, application_id, body)


@router.post(
    "/pass-applications/{application_id}/issue",
    response_model=AirportPassRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
    summary="Record the issued pass: approved → issued (capability 55; AP-9, AP-11)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def issue_airport_pass(
    application_id: uuid.UUID, body: PassIssueRequest, user: CurrentUser, db: DB
) -> AirportPassRead:
    return svc.issue(db, user, application_id, body)


# ---- passes -------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/airport-passes",
    response_model=AirportPassPage,
    response_model_exclude_unset=True,
    summary="Airport pass register with effective validity and limiting factor",
    responses=error_responses(401, 403, 404, 422),
)
def list_airport_passes(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    validity_status: Annotated[list[ValidityStatus] | None, Query()] = None,
    custody_status: Annotated[list[CustodyStatus] | None, Query()] = None,
    return_overdue: bool | None = None,
    pass_category: Annotated[list[str] | None, Query()] = None,
    area_code: Annotated[list[str] | None, Query()] = None,
    worker_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    expiring_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> AirportPassPage:
    return svc.list_passes(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        validity_status,
        custody_status,
        return_overdue,
        pass_category,
        area_code,
        worker_id,
        engagement_id,
        include_subcontractors,
        expiring_within_days,
        q,
    )


@router.get(
    "/airport-passes/{pass_id}",
    response_model=AirportPassRead,
    response_model_exclude_unset=True,
    summary="Get an airport pass",
    responses=error_responses(401, 403, 404),
)
def get_airport_pass(pass_id: uuid.UUID, user: CurrentUser, db: DB) -> AirportPassRead:
    return svc.get_pass(db, user, pass_id)
