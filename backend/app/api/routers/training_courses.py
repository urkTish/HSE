"""Course catalogue, training providers and accreditations (spec 5-training §3.1, §3.2, §4.1,
CC-1…CC-7, PV-1…PV-8)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.train_enums import (
    AccreditationBodyCode,
    CourseCategory,
    TrainingProviderKind,
    TrainingProviderStatus,
)
from app.schemas.training_common import COURSE_CODE
from app.schemas.training_courses import (
    CourseCreate,
    CourseList,
    CourseRead,
    CourseUpdate,
    ProviderAcceptability,
    ProviderAccreditationCreate,
    ProviderAccreditationRead,
    ProviderAccreditationUpdate,
    ProviderCreate,
    ProviderImpact,
    ProviderPage,
    ProviderRead,
    ProviderTransitionRequest,
    ProviderUpdate,
    RegisterCheckInput,
)
from app.services.train import courses, providers

router = APIRouter(tags=["training-catalogue"])

CourseCode = Annotated[str, Query(pattern=COURSE_CODE)]


# ---- course catalogue -----------------------------------------------------------------------


@router.get(
    "/training-courses",
    response_model=CourseList,
    summary="Course catalogue (org-wide; capability 125). With project_id: effective validity, "
    "pass mark and critical flag on that project",
    responses=error_responses(401, 403, 404, 422),
)
def list_training_courses(
    user: CurrentUser,
    db: DB,
    category: Annotated[list[CourseCategory] | None, Query()] = None,
    active: bool | None = None,
    hook_code: bool | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Code or name.")] = None,
    project_id: uuid.UUID | None = None,
) -> CourseList:
    return courses.list_courses(db, user, category, active, hook_code, q, project_id)


@router.post(
    "/training-courses",
    response_model=CourseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a course (capability 126, HSE Manager; code ∉ Phase 4 PCT — 409 "
    "CODE_IN_OTHER_CATALOGUE)",
    responses=error_responses(401, 403, 409, 422),
)
def create_training_course(body: CourseCreate, user: CurrentUser, db: DB) -> CourseRead:
    return courses.create_course(db, user, body)


@router.get(
    "/training-courses/{code}",
    response_model=CourseRead,
    summary="Course detail",
    responses=error_responses(401, 403, 404),
)
def get_training_course(
    code: str, user: CurrentUser, db: DB, project_id: uuid.UUID | None = None
) -> CourseRead:
    return courses.get_course(db, user, code, project_id)


@router.patch(
    "/training-courses/{code}",
    response_model=CourseRead,
    summary="Edit a course (capability 126; tighten only — 422 CATALOGUE_LOOSENING, CC-2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_training_course(code: str, body: CourseUpdate, user: CurrentUser, db: DB) -> CourseRead:
    return courses.update_course(db, user, code, body)


@router.delete(
    "/training-courses/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete an unused course (capability 126); in use → 409 COURSE_IN_USE (make it "
    "inactive instead, CC-1)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_training_course(code: str, user: CurrentUser, db: DB) -> Response:
    courses.delete_course(db, user, code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- providers ------------------------------------------------------------------------------


@router.get(
    "/training-providers",
    response_model=ProviderPage,
    summary="Training provider register (org-wide; capability 125). Contractor roles see "
    "accepted / not accepted only (P5-4)",
    responses=error_responses(401, 403, 422),
)
def list_training_providers(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[str | None, Query(max_length=100, description="Code or name.")] = None,
    status_: Annotated[list[TrainingProviderStatus] | None, Query(alias="status")] = None,
    kind: Annotated[list[TrainingProviderKind] | None, Query()] = None,
    course_code: Annotated[str | None, Query(pattern=COURSE_CODE)] = None,
    accreditation_body: Annotated[list[AccreditationBodyCode] | None, Query()] = None,
    accreditation_expiring_days: Annotated[int | None, Query(ge=0, le=365)] = None,
) -> ProviderPage:
    return providers.list_providers(
        db,
        user,
        pg.page,
        pg.page_size,
        q,
        status_,
        kind,
        course_code,
        accreditation_body,
        accreditation_expiring_days,
    )


@router.post(
    "/training-providers",
    response_model=ProviderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a training provider (capability 127) → Draft",
    responses=error_responses(401, 403, 409, 422),
)
def create_training_provider(body: ProviderCreate, user: CurrentUser, db: DB) -> ProviderRead:
    return providers.create_provider(db, user, body)


@router.get(
    "/training-providers/{provider_id}",
    response_model=ProviderRead,
    summary="Training provider with accreditations",
    responses=error_responses(401, 403, 404),
)
def get_training_provider(provider_id: uuid.UUID, user: CurrentUser, db: DB) -> ProviderRead:
    return providers.get_provider(db, user, provider_id)


@router.patch(
    "/training-providers/{provider_id}",
    response_model=ProviderRead,
    summary="Edit a training provider (capability 127; provider_code and kind immutable)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_training_provider(
    provider_id: uuid.UUID, body: ProviderUpdate, user: CurrentUser, db: DB
) -> ProviderRead:
    return providers.update_provider(db, user, provider_id, body)


@router.post(
    "/training-providers/{provider_id}/transitions",
    response_model=ProviderRead,
    summary="Provider status transition (§4.1; submit: 127; approve / return / suspend / "
    "reinstate / blacklist / lift: 128)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_training_provider(
    provider_id: uuid.UUID, body: ProviderTransitionRequest, user: CurrentUser, db: DB
) -> ProviderRead:
    return providers.transition(db, user, provider_id, body)


@router.get(
    "/training-providers/{provider_id}/affected",
    response_model=ProviderImpact,
    summary="Holders and sessions affected by a suspension / blacklist (PV-5, PV-6)",
    responses=error_responses(401, 403, 404),
)
def get_training_provider_impact(
    provider_id: uuid.UUID, user: CurrentUser, db: DB
) -> ProviderImpact:
    return providers.impact(db, user, provider_id)


@router.get(
    "/training-providers/{provider_id}/acceptability",
    response_model=ProviderAcceptability,
    summary="PV-3 check: is the provider acceptable for a course on given dates (and, for "
    "contractor_internal, for these workers)?",
    responses=error_responses(401, 403, 404, 422),
)
def get_training_provider_acceptability(
    provider_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    course_code: CourseCode,
    on_date: Annotated[list[date], Query(min_length=1, max_length=15)],
    project_id: uuid.UUID | None = None,
    worker_id: Annotated[list[uuid.UUID] | None, Query(max_length=60)] = None,
) -> ProviderAcceptability:
    return providers.acceptability(
        db, user, provider_id, course_code, on_date, project_id, worker_id
    )


@router.post(
    "/training-providers/{provider_id}/accreditations",
    response_model=ProviderAccreditationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an accreditation (capability 127)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_training_provider_accreditation(
    provider_id: uuid.UUID, body: ProviderAccreditationCreate, user: CurrentUser, db: DB
) -> ProviderAccreditationRead:
    return providers.create_accreditation(db, user, provider_id, body)


@router.patch(
    "/training-provider-accreditations/{accreditation_id}",
    response_model=ProviderAccreditationRead,
    summary="Edit an accreditation (capability 127; clears register_checked_at when the body, "
    "number, scope or dates change)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_training_provider_accreditation(
    accreditation_id: uuid.UUID, body: ProviderAccreditationUpdate, user: CurrentUser, db: DB
) -> ProviderAccreditationRead:
    return providers.update_accreditation(db, user, accreditation_id, body)


@router.post(
    "/training-provider-accreditations/{accreditation_id}/register-check",
    response_model=ProviderAccreditationRead,
    summary="Record the public-register check (PV-2; capability 127)",
    responses=error_responses(401, 403, 404, 422),
)
def register_check_training_accreditation(
    accreditation_id: uuid.UUID, body: RegisterCheckInput, user: CurrentUser, db: DB
) -> ProviderAccreditationRead:
    return providers.register_check(db, user, accreditation_id, body)
