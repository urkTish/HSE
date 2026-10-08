"""Trainer authorisations (spec 5-training §3.3, §4.2, TA-1…TA-6)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.train_enums import TrainerAuthorisationStatus, TrainerRole
from app.schemas.trainer_authorisations import (
    TrainerAuthorisationCreate,
    TrainerAuthorisationPage,
    TrainerAuthorisationRead,
    TrainerAuthorisationTransition,
    TrainerAuthorisationUpdate,
)
from app.schemas.training_common import COURSE_CODE
from app.services.train import trainers

router = APIRouter(tags=["trainer-authorisations"])


@router.get(
    "/projects/{project_id}/trainer-authorisations",
    response_model=TrainerAuthorisationPage,
    summary="Trainer authorisation register (capability 136 on the project; 131 to edit)",
    responses=error_responses(401, 403, 404, 422),
)
def list_trainer_authorisations(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[TrainerAuthorisationStatus] | None, Query(alias="status")] = None,
    course_code: Annotated[str | None, Query(pattern=COURSE_CODE)] = None,
    role: TrainerRole | None = None,
    provider_id: uuid.UUID | None = None,
    expiring_days: Annotated[int | None, Query(ge=0, le=365)] = None,
) -> TrainerAuthorisationPage:
    return trainers.list_authorisations(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        status_,
        course_code,
        role,
        provider_id,
        expiring_days,
    )


@router.post(
    "/projects/{project_id}/trainer-authorisations",
    response_model=TrainerAuthorisationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Authorise a trainer / assessor (capability 131; authoriser ≠ trainer) → Active",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_trainer_authorisation(
    project_id: uuid.UUID, body: TrainerAuthorisationCreate, user: CurrentUser, db: DB
) -> TrainerAuthorisationRead:
    return trainers.create_authorisation(db, user, project_id, body)


@router.get(
    "/trainer-authorisations/{authorisation_id}",
    response_model=TrainerAuthorisationRead,
    summary="Trainer authorisation detail",
    responses=error_responses(401, 403, 404),
)
def get_trainer_authorisation(
    authorisation_id: uuid.UUID, user: CurrentUser, db: DB
) -> TrainerAuthorisationRead:
    return trainers.get_authorisation(db, user, authorisation_id)


@router.patch(
    "/trainer-authorisations/{authorisation_id}",
    response_model=TrainerAuthorisationRead,
    summary="Edit an Active authorisation (capability 131)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_trainer_authorisation(
    authorisation_id: uuid.UUID, body: TrainerAuthorisationUpdate, user: CurrentUser, db: DB
) -> TrainerAuthorisationRead:
    return trainers.update_authorisation(db, user, authorisation_id, body)


@router.post(
    "/trainer-authorisations/{authorisation_id}/transitions",
    response_model=TrainerAuthorisationRead,
    summary="Suspend / reinstate / withdraw (capability 131, §4.2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_trainer_authorisation(
    authorisation_id: uuid.UUID, body: TrainerAuthorisationTransition, user: CurrentUser, db: DB
) -> TrainerAuthorisationRead:
    return trainers.transition(db, user, authorisation_id, body)
