"""Training matrix, training profiles, requirement status, exemptions, the gap register and the
refresher plan (spec 5-training §3.4, §3.5, §3.10, §3.11, §3.14, §6.2, §6.7, MX, GP)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.hse_enums import Trade
from app.core.train_enums import (
    ExemptionStatus,
    MatrixAppliesTo,
    MatrixLevel,
    MatrixLineSource,
    RefresherPlanState,
    RequirementState,
)
from app.schemas.training_common import COURSE_CODE
from app.schemas.training_matrix import (
    DeploymentRequirements,
    ExemptionCreate,
    ExemptionPage,
    ExemptionRead,
    ExemptionWithdraw,
    GapPage,
    GapSummary,
    MatrixLineCreate,
    MatrixLineRead,
    MatrixLineRemove,
    MatrixLineUpdate,
    MatrixLineVersions,
    MatrixRead,
    RefresherPlanPage,
    RetrainingNoteCreate,
    RetrainingNoteRead,
    TrainingProfileRead,
    TrainingProfileUpdate,
)
from app.services.train import gaps, matrix

router = APIRouter(tags=["training-matrix"])

AsOf = Annotated[date | None, Query(description="Default today (project timezone).")]


@router.get(
    "/projects/{project_id}/training-matrix",
    response_model=MatrixRead,
    summary="Project training matrix at as_of (capability 125): manual and hook-derived lines",
    responses=error_responses(401, 403, 404, 422),
)
def get_training_matrix(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    as_of: AsOf = None,
    applies_to_kind: Annotated[list[MatrixAppliesTo] | None, Query()] = None,
    level: MatrixLevel | None = None,
    source: MatrixLineSource | None = None,
    course_code: Annotated[str | None, Query(pattern=COURSE_CODE)] = None,
    include_counts: Annotated[
        bool, Query(description="Adds applicable_deployments per kpi_counted line.")
    ] = False,
) -> MatrixRead:
    return matrix.read_matrix(
        db, user, project_id, as_of, applies_to_kind, level, source, course_code, include_counts
    )


@router.post(
    "/projects/{project_id}/training-matrix/lines",
    response_model=MatrixLineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a manual matrix line effective today (capability 129, MX-7)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_training_matrix_line(
    project_id: uuid.UUID, body: MatrixLineCreate, user: CurrentUser, db: DB
) -> MatrixLineRead:
    return matrix.create_line(db, user, project_id, body)


@router.patch(
    "/training-matrix-lines/{line_id}",
    response_model=MatrixLineRead,
    summary="Change a manual line → new version from today (capability 129; loosening HSE "
    "Manager only, MX-8)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_training_matrix_line(
    line_id: uuid.UUID, body: MatrixLineUpdate, user: CurrentUser, db: DB
) -> MatrixLineRead:
    return matrix.update_line(db, user, line_id, body)


@router.post(
    "/training-matrix-lines/{line_id}/remove",
    response_model=MatrixLineRead,
    summary="Remove a manual line (effective_to = yesterday; mandatory: HSE Manager + reason)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def remove_training_matrix_line(
    line_id: uuid.UUID, body: MatrixLineRemove, user: CurrentUser, db: DB
) -> MatrixLineRead:
    return matrix.remove_line(db, user, line_id, body)


@router.get(
    "/training-matrix-lines/{line_id}/versions",
    response_model=MatrixLineVersions,
    summary="Every version of a matrix line (MX-1)",
    responses=error_responses(401, 403, 404),
)
def get_training_matrix_line_versions(
    line_id: uuid.UUID, user: CurrentUser, db: DB
) -> MatrixLineVersions:
    return matrix.versions(db, user, line_id)


# ---- profiles and requirements --------------------------------------------------------------


@router.get(
    "/deployments/{deployment_id}/training-profile",
    response_model=TrainingProfileRead,
    summary="Worker training profile of a Phase 2 deployment (capability 136) with history",
    responses=error_responses(401, 403, 404),
)
def get_training_profile(
    deployment_id: uuid.UUID, user: CurrentUser, db: DB
) -> TrainingProfileRead:
    return matrix.get_profile(db, user, deployment_id)


@router.patch(
    "/deployments/{deployment_id}/training-profile",
    response_model=TrainingProfileRead,
    summary="Edit matrix roles / work zones from today (capability 130; C scope for Contractor "
    "HSE Reps, MX-9)",
    responses=error_responses(401, 403, 404, 422),
)
def update_training_profile(
    deployment_id: uuid.UUID, body: TrainingProfileUpdate, user: CurrentUser, db: DB
) -> TrainingProfileRead:
    return matrix.update_profile(db, user, deployment_id, body)


@router.get(
    "/deployments/{deployment_id}/training-requirements",
    response_model=DeploymentRequirements,
    summary="Requirement status of a deployment at as_of (§3.10, §6.2; capability 136)",
    responses=error_responses(401, 403, 404, 422),
)
def get_training_requirements(
    deployment_id: uuid.UUID, user: CurrentUser, db: DB, as_of: AsOf = None
) -> DeploymentRequirements:
    return gaps.get_requirements(db, user, deployment_id, as_of)


# ---- exemptions -----------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/training-exemptions",
    response_model=ExemptionPage,
    summary="Requirement exemptions (capability 136)",
    responses=error_responses(401, 403, 404, 422),
)
def list_training_exemptions(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[ExemptionStatus] | None, Query(alias="status")] = None,
    deployment_id: uuid.UUID | None = None,
) -> ExemptionPage:
    return matrix.list_exemptions(
        db, user, project_id, pg.page, pg.page_size, status_, deployment_id
    )


@router.post(
    "/projects/{project_id}/training-exemptions",
    response_model=ExemptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Grant an exemption (capability 129; never IND-GENERAL or hook codes — 422 "
    "EXEMPTION_NOT_ALLOWED)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_training_exemption(
    project_id: uuid.UUID, body: ExemptionCreate, user: CurrentUser, db: DB
) -> ExemptionRead:
    return matrix.create_exemption(db, user, project_id, body)


@router.post(
    "/training-exemptions/{exemption_id}/withdraw",
    response_model=ExemptionRead,
    summary="Withdraw an exemption (capability 129)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def withdraw_training_exemption(
    exemption_id: uuid.UUID, body: ExemptionWithdraw, user: CurrentUser, db: DB
) -> ExemptionRead:
    return matrix.withdraw_exemption(db, user, exemption_id, body)


# ---- gap register and refresher plan --------------------------------------------------------


@router.get(
    "/projects/{project_id}/training-gaps",
    response_model=GapPage,
    summary="Gap register (GP-1; capability 136, C scope for contractor roles; Viewer/Client "
    "403 — use /summary)",
    responses=error_responses(401, 403, 404, 422),
)
def list_training_gaps(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    as_of: AsOf = None,
    state: Annotated[
        list[RequirementState] | None, Query(description="Default gap, due, expiring.")
    ] = None,
    engagement_id: uuid.UUID | None = None,
    include_subcontractors: bool = True,
    trade: Annotated[list[Trade] | None, Query()] = None,
    course_code: Annotated[list[str] | None, Query()] = None,
    hook_code: bool | None = None,
    on_live_work: Annotated[
        bool | None, Query(description="Only workers on non-terminal permits / Active WAPs.")
    ] = None,
    counted_only: bool = False,
) -> GapPage:
    return gaps.list_gaps(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        as_of,
        state,
        engagement_id,
        include_subcontractors,
        trade,
        course_code,
        hook_code,
        on_live_work,
        counted_only,
    )


@router.get(
    "/projects/{project_id}/training-gaps/summary",
    response_model=GapSummary,
    summary="Gap counts by course, contractor and trade (capability 143; aggregates, TK-5)",
    responses=error_responses(401, 403, 404, 422),
)
def get_training_gap_summary(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    as_of: AsOf = None,
    engagement_id: uuid.UUID | None = None,
    include_subcontractors: bool = True,
) -> GapSummary:
    return gaps.gap_summary(db, user, project_id, as_of, engagement_id, include_subcontractors)


@router.get(
    "/projects/{project_id}/refresher-plan",
    response_model=RefresherPlanPage,
    summary="Refresher plan (GP-3…GP-6; capability 143, names per capability 46)",
    responses=error_responses(401, 403, 404, 422),
)
def get_refresher_plan(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    as_of: AsOf = None,
    state: Annotated[list[RefresherPlanState] | None, Query()] = None,
    course_code: Annotated[list[str] | None, Query()] = None,
    engagement_id: uuid.UUID | None = None,
    due_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
) -> RefresherPlanPage:
    return gaps.refresher_plan(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        as_of,
        state,
        course_code,
        engagement_id,
        due_within_days,
    )


@router.post(
    "/workers/{worker_id}/training-retraining-notes",
    response_model=RetrainingNoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a re-training note releasing the attempts limit (AT-5; capability 138)",
    responses=error_responses(401, 403, 404, 422),
)
def create_training_retraining_note(
    worker_id: uuid.UUID, body: RetrainingNoteCreate, user: CurrentUser, db: DB
) -> RetrainingNoteRead:
    return gaps.create_note(db, user, worker_id, body)
