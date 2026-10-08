"""Job safety analysis: templates, permit instances, residual risk acceptance and
revisions (spec 3-ptw §3.9, §4.3, §5.3, §6.1)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses, not_implemented
from app.core.ptw_enums import JsaStatus, PermitType
from app.schemas.jsa import (
    JsaInstanceCreate,
    JsaListItem,
    JsaPage,
    JsaRead,
    JsaTemplateCreate,
    JsaTransition,
    JsaUpdate,
    ResidualAcceptanceInput,
)

router = APIRouter(tags=["jsa"])


@router.get(
    "/projects/{project_id}/jsa-templates",
    response_model=JsaPage,
    summary="JSA template library (capability 82)",
    responses=error_responses(401, 403, 404, 422),
)
def list_jsa_templates(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    work_type: Annotated[list[PermitType] | None, Query()] = None,
    status_: Annotated[list[JsaStatus] | None, Query(alias="status")] = None,
    engagement_id: uuid.UUID | None = None,
    review_due: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> JsaPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/jsa-templates",
    response_model=JsaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a JSA template (capability 96)",
    responses=error_responses(401, 403, 404, 422),
)
def create_jsa_template(
    project_id: uuid.UUID,
    body: JsaTemplateCreate,
    user: CurrentUser,
    db: DB,
) -> JsaRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/jsa",
    response_model=JsaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create the permit's JSA (blank or from a template; one per permit → 409)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_permit_jsa(
    permit_id: uuid.UUID,
    body: JsaInstanceCreate,
    user: CurrentUser,
    db: DB,
) -> JsaRead:
    raise not_implemented()


@router.get(
    "/jsas/{jsa_id}",
    response_model=JsaRead,
    summary="Get a JSA (template or instance)",
    responses=error_responses(401, 403, 404),
)
def get_jsa(jsa_id: uuid.UUID, user: CurrentUser, db: DB) -> JsaRead:
    raise not_implemented()


@router.patch(
    "/jsas/{jsa_id}",
    response_model=JsaRead,
    summary="Edit a draft JSA (steps, hazards, controls; risk recomputed)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_jsa(jsa_id: uuid.UUID, body: JsaUpdate, user: CurrentUser, db: DB) -> JsaRead:
    raise not_implemented()


@router.post(
    "/jsas/{jsa_id}/transitions",
    response_model=JsaRead,
    summary="Submit / approve / return a JSA (§4.3)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_jsa(jsa_id: uuid.UUID, body: JsaTransition, user: CurrentUser, db: DB) -> JsaRead:
    raise not_implemented()


@router.post(
    "/jsas/{jsa_id}/residual-acceptances",
    response_model=JsaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Accept residual risk by band (JS-7; signed)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def accept_jsa_residual_risk(
    jsa_id: uuid.UUID,
    body: ResidualAcceptanceInput,
    user: CurrentUser,
    db: DB,
) -> JsaRead:
    raise not_implemented()


@router.post(
    "/jsas/{jsa_id}/revisions",
    response_model=JsaRead,
    status_code=status.HTTP_201_CREATED,
    summary="New draft revision of an approved / review-due JSA (old one superseded on approval)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def revise_jsa(jsa_id: uuid.UUID, user: CurrentUser, db: DB) -> JsaRead:
    raise not_implemented()


@router.get(
    "/jsas/{jsa_id}/revisions",
    response_model=list[JsaListItem],
    summary="Revision history of a JSA",
    responses=error_responses(401, 403, 404),
)
def list_jsa_revisions(jsa_id: uuid.UUID, user: CurrentUser, db: DB) -> list[JsaListItem]:
    raise not_implemented()
