"""Fitness code catalogue, medical providers (clinics) and examiner registrations (spec
6a-occupational-health §3.1–§3.3, §4.1, §4.2, MC, MP, EX)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.med_enums import ExaminerStatus, MedicalProviderKind, MedicalProviderStatus
from app.schemas.access_common import WorkerRef
from app.schemas.medical import (
    ExaminerCreate,
    ExaminerPage,
    ExaminerRead,
    ExaminerTransition,
    ExaminerUpdate,
    FitnessCodeCreate,
    FitnessCodeList,
    FitnessCodeRead,
    FitnessCodeUpdate,
    FitnessReference,
    MedicalProviderCreate,
    MedicalProviderPage,
    MedicalProviderRead,
    MedicalProviderTransition,
    MedicalProviderUpdate,
)
from app.services.med import catalogue, providers

router = APIRouter(tags=["medical-catalogue"])


@router.get(
    "/fitness-reference",
    response_model=FitnessReference,
    summary="§3.10 reference lists with EN/AR labels (restrictions with negates / review, "
    "exposure groups, outcomes, assessment types, hints)",
    responses=error_responses(401),
)
def get_fitness_reference(user: CurrentUser, db: DB) -> FitnessReference:
    return catalogue.reference(db, user)


@router.get(
    "/fitness-codes",
    response_model=FitnessCodeList,
    summary="Fitness code catalogue (capability 146; org-wide)",
    responses=error_responses(401, 403),
)
def list_fitness_codes(
    user: CurrentUser,
    db: DB,
    project_id: Annotated[
        uuid.UUID | None, Query(description="Adds the project's effective validity (MC-5).")
    ] = None,
    include_inactive: bool = True,
) -> FitnessCodeList:
    return catalogue.list_codes(db, user, project_id, include_inactive)


@router.post(
    "/fitness-codes",
    response_model=FitnessCodeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a fitness code (capability 147; CODE_IN_OTHER_CATALOGUE, MC-2; MC-4)",
    responses=error_responses(401, 403, 409, 422),
)
def create_fitness_code(body: FitnessCodeCreate, user: CurrentUser, db: DB) -> FitnessCodeRead:
    return catalogue.create_code(db, user, body)


@router.get(
    "/fitness-codes/{code}",
    response_model=FitnessCodeRead,
    summary="One fitness code",
    responses=error_responses(401, 403, 404),
)
def get_fitness_code(
    code: str, user: CurrentUser, db: DB, project_id: uuid.UUID | None = None
) -> FitnessCodeRead:
    return catalogue.get_code(db, user, code, project_id)


@router.patch(
    "/fitness-codes/{code}",
    response_model=FitnessCodeRead,
    summary="Edit a fitness code — tighten only (MC-3: 422 CATALOGUE_LOOSENING); a shorter "
    "validity recomputes every line and alerts workers now expiring ≤ 30 days",
    responses=error_responses(401, 403, 404, 422),
)
def update_fitness_code(
    code: str, body: FitnessCodeUpdate, user: CurrentUser, db: DB
) -> FitnessCodeRead:
    return catalogue.update_code(db, user, code, body)


@router.delete(
    "/fitness-codes/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an unused fitness code (in use → 409 FITNESS_CODE_IN_USE: make inactive)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_fitness_code(code: str, user: CurrentUser, db: DB) -> Response:
    catalogue.delete_code(db, user, code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- providers -----------------------------------------------------------------------------------


@router.get(
    "/medical-providers",
    response_model=MedicalProviderPage,
    summary="Medical provider register (capability 146; org-wide)",
    responses=error_responses(401, 403, 422),
)
def list_medical_providers(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[str | None, Query(max_length=100)] = None,
    kind: Annotated[list[MedicalProviderKind] | None, Query()] = None,
    status_: Annotated[list[MedicalProviderStatus] | None, Query(alias="status")] = None,
    project_id: uuid.UUID | None = None,
) -> MedicalProviderPage:
    return providers.list_providers(db, user, pg.page, pg.page_size, q, kind, status_, project_id)


@router.post(
    "/medical-providers",
    response_model=MedicalProviderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a medical provider → Draft (capability 148)",
    responses=error_responses(401, 403, 409, 422),
)
def create_medical_provider(
    body: MedicalProviderCreate, user: CurrentUser, db: DB
) -> MedicalProviderRead:
    return providers.create_provider(db, user, body)


@router.get(
    "/medical-providers/{provider_id}",
    response_model=MedicalProviderRead,
    summary="One medical provider",
    responses=error_responses(401, 403, 404),
)
def get_medical_provider(provider_id: uuid.UUID, user: CurrentUser, db: DB) -> MedicalProviderRead:
    return providers.get_provider(db, user, provider_id)


@router.patch(
    "/medical-providers/{provider_id}",
    response_model=MedicalProviderRead,
    summary="Edit a provider (capability 148; Draft / Pending Approval; licence fields any time)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_medical_provider(
    provider_id: uuid.UUID, body: MedicalProviderUpdate, user: CurrentUser, db: DB
) -> MedicalProviderRead:
    return providers.update_provider(db, user, provider_id, body)


@router.post(
    "/medical-providers/{provider_id}/transitions",
    response_model=MedicalProviderRead,
    summary="Provider workflow (§4.1): submit (148; licence_checked_at, MP-2) · approve / "
    "return / suspend / reinstate / blacklist / lift_blacklist (149). A blacklist revokes the "
    "assessments in scope (MP-6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_medical_provider(
    provider_id: uuid.UUID, body: MedicalProviderTransition, user: CurrentUser, db: DB
) -> MedicalProviderRead:
    return providers.transition_provider(db, user, provider_id, body)


@router.get(
    "/medical-providers/{provider_id}/affected",
    response_model=list[WorkerRef],
    summary="Workers whose in-force lines come from the provider (MP-6 re-examination list; "
    "capability 157)",
    responses=error_responses(401, 403, 404),
)
def get_medical_provider_affected(
    provider_id: uuid.UUID, user: CurrentUser, db: DB
) -> list[WorkerRef]:
    return providers.affected(db, user, provider_id)


# ---- examiners -----------------------------------------------------------------------------------


@router.get(
    "/medical-examiners",
    response_model=ExaminerPage,
    summary="Examiner registrations (capability 146; licence fields with 148)",
    responses=error_responses(401, 403, 422),
)
def list_medical_examiners(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[str | None, Query(max_length=100)] = None,
    provider_id: uuid.UUID | None = None,
    status_: Annotated[list[ExaminerStatus] | None, Query(alias="status")] = None,
) -> ExaminerPage:
    return providers.list_examiners(db, user, pg.page, pg.page_size, q, provider_id, status_)


@router.post(
    "/medical-examiners",
    response_model=ExaminerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an examiner → Active (capability 148; EX-1 licence check)",
    responses=error_responses(401, 403, 409, 422),
)
def create_medical_examiner(body: ExaminerCreate, user: CurrentUser, db: DB) -> ExaminerRead:
    return providers.create_examiner(db, user, body)


@router.get(
    "/medical-examiners/{examiner_id}",
    response_model=ExaminerRead,
    response_model_exclude_unset=True,
    summary="One examiner registration",
    responses=error_responses(401, 403, 404),
)
def get_medical_examiner(examiner_id: uuid.UUID, user: CurrentUser, db: DB) -> ExaminerRead:
    return providers.get_examiner(db, user, examiner_id)


@router.patch(
    "/medical-examiners/{examiner_id}",
    response_model=ExaminerRead,
    summary="Edit names, providers or the linked user (capability 148; a licence renewal is a "
    "new registration, EX-4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_medical_examiner(
    examiner_id: uuid.UUID, body: ExaminerUpdate, user: CurrentUser, db: DB
) -> ExaminerRead:
    return providers.update_examiner(db, user, examiner_id, body)


@router.post(
    "/medical-examiners/{examiner_id}/transitions",
    response_model=ExaminerRead,
    summary="Suspend / reinstate / withdraw an examiner registration (capability 149, §4.2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_medical_examiner(
    examiner_id: uuid.UUID, body: ExaminerTransition, user: CurrentUser, db: DB
) -> ExaminerRead:
    return providers.transition_examiner(db, user, examiner_id, body)
