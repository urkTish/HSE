"""Q2 routes: competence requirements, the competence matrix and a single check (spec 8-quality
§C.5)."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser
from app.core.errors import error_responses
from app.schemas.quality.q2 import (
    QCompetenceCheckRead,
    QCompetenceMatrixRead,
    QCompetenceReqCreate,
    QCompetenceReqRead,
    QCompetenceReqUpdate,
)
from app.services.quality.q2 import competence

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/quality/competence/requirements",
    response_model=list[QCompetenceReqRead],
    summary="Competence requirements (org-wide)",
    responses=E,
)
def q_list_competence(user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return competence.list_reqs(db, user)


@router.post(
    "/quality/competence/requirements",
    response_model=QCompetenceReqRead,
    status_code=status.HTTP_201_CREATED,
    summary="New requirement (263: QA/QC Manager, Quality Engineer)",
    responses=E,
)
def q_create_competence(body: QCompetenceReqCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return competence.create(db, user, body.model_dump())


@router.patch(
    "/quality/competence/requirements/{req_id}",
    response_model=QCompetenceReqRead,
    summary="Edit a requirement",
    responses=E,
)
def q_update_competence(
    req_id: uuid.UUID, body: QCompetenceReqUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return competence.update(db, user, req_id, body.model_dump(exclude_unset=True))


@router.get(
    "/projects/{project_id}/quality/competence/matrix",
    response_model=QCompetenceMatrixRead,
    summary="People × requirements (Q-CPT-03)",
    responses=E,
)
def q_competence_matrix(
    project_id: uuid.UUID, user: CurrentUser, db: DB, on: date | None = None
) -> dict[str, Any]:
    return competence.matrix(db, user, project_id, on)


@router.get(
    "/projects/{project_id}/quality/competence/check",
    response_model=QCompetenceCheckRead,
    summary="Check one person against one requirement (Q-CPT-01)",
    responses=E,
)
def q_competence_check(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    code: str,
    user: CurrentUser,
    db: DB,
    on: date | None = None,
) -> dict[str, Any]:
    return competence.check_api(db, user, project_id, user_id, code, on)
