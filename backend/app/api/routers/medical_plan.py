"""Requirement plan, worker health profiles, per-deployment requirements and the fitness gap
register (spec 6a-occupational-health §3.4, §3.5, §6.3, MR, WP)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.schemas.medical import (
    FitnessGapPage,
    FitnessRequirementList,
    HealthProfileRead,
    HealthProfileUpdate,
    MedicalExemptionRequest,
    MedicalPlanLineCreate,
    MedicalPlanLineRead,
    MedicalPlanLineRemove,
    MedicalPlanLineUpdate,
    MedicalPlanLineVersions,
    MedicalPlanRead,
)
from app.services.med import plan

router = APIRouter(tags=["medical-plan"])


@router.get(
    "/projects/{project_id}/medical-plan",
    response_model=MedicalPlanRead,
    summary="Requirement plan at as_of: manual, hook-derived (H) and enforcement-only (E) lines "
    "with counted / met / gap figures (capability 146)",
    responses=error_responses(401, 403, 404),
)
def get_medical_plan(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    as_of: date | None = None,
    with_counts: bool = False,
) -> MedicalPlanRead:
    return plan.read_plan(db, user, project_id, as_of, with_counts)


@router.post(
    "/projects/{project_id}/medical-plan/lines",
    response_model=MedicalPlanLineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a manual plan line from today (capability 150; DUE_DAYS_NOT_ALLOWED for hook "
    "codes)",
    responses=error_responses(401, 403, 404, 422),
)
def create_medical_plan_line(
    project_id: uuid.UUID, body: MedicalPlanLineCreate, user: CurrentUser, db: DB
) -> MedicalPlanLineRead:
    return plan.create_line(db, user, project_id, body)


@router.patch(
    "/medical-plan-lines/{line_id}",
    response_model=MedicalPlanLineRead,
    summary="Change a manual line → new version from today (derived lines: 422 "
    "LINE_DERIVED_FROM_HOOK; loosening: HSE Manager + reason, else PLAN_LOOSENING)",
    responses=error_responses(401, 403, 404, 422),
)
def update_medical_plan_line(
    line_id: uuid.UUID, body: MedicalPlanLineUpdate, user: CurrentUser, db: DB
) -> MedicalPlanLineRead:
    return plan.update_line(db, user, line_id, body)


@router.post(
    "/medical-plan-lines/{line_id}/remove",
    response_model=MedicalPlanLineRead,
    summary="Remove a manual line (HSE Manager, reason ≥ 20 chars: effective_to = yesterday; "
    "others 422 PLAN_LOOSENING, MR-5)",
    responses=error_responses(401, 403, 404, 422),
)
def remove_medical_plan_line(
    line_id: uuid.UUID, body: MedicalPlanLineRemove, user: CurrentUser, db: DB
) -> MedicalPlanLineRead:
    return plan.remove_line(db, user, line_id, body)


@router.get(
    "/medical-plan-lines/{line_id}/versions",
    response_model=MedicalPlanLineVersions,
    summary="Every version of a plan line (MR-1)",
    responses=error_responses(401, 403, 404),
)
def get_medical_plan_line_versions(
    line_id: uuid.UUID, user: CurrentUser, db: DB
) -> MedicalPlanLineVersions:
    return plan.versions(db, user, line_id)


@router.post(
    "/projects/{project_id}/medical-exemptions",
    status_code=status.HTTP_201_CREATED,
    summary="Always 422 EXEMPTION_NOT_ALLOWED: there are no medical exemptions (MR-6)",
    responses=error_responses(401, 403, 404, 422),
)
def create_medical_exemption(
    project_id: uuid.UUID, body: MedicalExemptionRequest, user: CurrentUser, db: DB
) -> None:
    plan.exemption(db, user, project_id)


@router.get(
    "/deployments/{deployment_id}/health-profile",
    response_model=HealthProfileRead,
    summary="Worker health profile: exposure groups with history (capability 155 or 151)",
    responses=error_responses(401, 403, 404),
)
def get_health_profile(deployment_id: uuid.UUID, user: CurrentUser, db: DB) -> HealthProfileRead:
    return plan.get_profile(db, user, deployment_id)


@router.patch(
    "/deployments/{deployment_id}/health-profile",
    response_model=HealthProfileRead,
    summary="Edit exposure groups from today (capability 151; WP-1, WP-2)",
    responses=error_responses(401, 403, 404, 422),
)
def update_health_profile(
    deployment_id: uuid.UUID, body: HealthProfileUpdate, user: CurrentUser, db: DB
) -> HealthProfileRead:
    return plan.update_profile(db, user, deployment_id, body)


@router.get(
    "/deployments/{deployment_id}/fitness-requirements",
    response_model=FitnessRequirementList,
    response_model_exclude_unset=True,
    summary="Per-deployment fitness requirements at as_of (§6.3; tiered, capability 155)",
    responses=error_responses(401, 403, 404),
)
def get_fitness_requirements(
    deployment_id: uuid.UUID, user: CurrentUser, db: DB, as_of: date | None = None
) -> FitnessRequirementList:
    return plan.requirements(db, user, deployment_id, as_of)


@router.get(
    "/projects/{project_id}/fitness-gaps",
    response_model=FitnessGapPage,
    response_model_exclude_unset=True,
    summary="Fitness gap register at as_of (counted requirements in gap; capability 155, C "
    "scope; reasons tier 3 only; names only with capability 46)",
    responses=error_responses(401, 403, 404, 422),
)
def list_fitness_gaps(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    as_of: date | None = None,
    code: Annotated[list[str] | None, Query()] = None,
    engagement_id: uuid.UUID | None = None,
    hook_codes_only: bool = False,
) -> FitnessGapPage:
    return plan.gaps(
        db, user, project_id, pg.page, pg.page_size, as_of, code, engagement_id, hook_codes_only
    )
