"""Fitness assessments (site clinic and external certificates), verification, scans, the worker
fitness status and the per-worker data-subject report (spec 6a-occupational-health §3.6, §4.3,
FA, FV, OH-2, P6-5, P6-9)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.cert_enums import VerificationStatus
from app.core.errors import error_responses
from app.core.hse_enums import ExportPurpose
from app.core.med_enums import AssessmentSource, AssessmentStatus, AssessmentType
from app.schemas.attachments import SignedUrlRead
from app.schemas.medical import (
    FitnessAssessmentCreate,
    FitnessAssessmentPage,
    FitnessAssessmentRead,
    FitnessAssessmentTransition,
    FitnessAssessmentUpdate,
    FitnessDataSubjectReport,
    FitnessScanUrlRequest,
    FitnessVerificationCreate,
    FitnessVerificationList,
    FitnessVerificationRead,
    WorkerFitnessRead,
)
from app.services.med import assessments, status_view

router = APIRouter(tags=["fitness-assessments"])


@router.get(
    "/projects/{project_id}/fitness-assessments",
    response_model=FitnessAssessmentPage,
    response_model_exclude_unset=True,
    summary="Fitness assessment register (capability 156; tier-3 fields with 157; C scope)",
    responses=error_responses(401, 403, 404, 422),
)
def list_fitness_assessments(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[str | None, Query(max_length=100, description="worker_no, numbers.")] = None,
    status_: Annotated[list[AssessmentStatus] | None, Query(alias="status")] = None,
    source: Annotated[list[AssessmentSource] | None, Query()] = None,
    assessment_type: Annotated[list[AssessmentType] | None, Query()] = None,
    verification_status: Annotated[list[VerificationStatus] | None, Query()] = None,
    worker_id: uuid.UUID | None = None,
    awaiting_signoff_mine: bool = False,
) -> FitnessAssessmentPage:
    return assessments.list_assessments(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        q,
        status_,
        source,
        assessment_type,
        verification_status,
        worker_id,
        awaiting_signoff_mine,
    )


@router.post(
    "/projects/{project_id}/fitness-assessments",
    response_model=FitnessAssessmentRead,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_unset=True,
    summary="Record a site-clinic assessment (152; the examiner's linked user signs on save "
    "with step-up re-auth) or an external certificate (153 → Draft)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_fitness_assessment(
    project_id: uuid.UUID, body: FitnessAssessmentCreate, user: CurrentUser, db: DB
) -> FitnessAssessmentRead:
    return assessments.create(db, user, project_id, body)


@router.get(
    "/fitness-assessments/{assessment_id}",
    response_model=FitnessAssessmentRead,
    response_model_exclude_unset=True,
    summary="One assessment (tiered, OH-2; tier-2/3 reads audited sensitive_field_read)",
    responses=error_responses(401, 403, 404),
)
def get_fitness_assessment(
    assessment_id: uuid.UUID, user: CurrentUser, db: DB
) -> FitnessAssessmentRead:
    return assessments.read(db, user, assessment_id)


@router.patch(
    "/fitness-assessments/{assessment_id}",
    response_model=FitnessAssessmentRead,
    response_model_exclude_unset=True,
    summary="Edit a Draft / Awaiting Sign-off assessment; Accepted > 24 h → 409 "
    "ASSESSMENT_LOCKED (FA-14)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_fitness_assessment(
    assessment_id: uuid.UUID, body: FitnessAssessmentUpdate, user: CurrentUser, db: DB
) -> FitnessAssessmentRead:
    return assessments.update(db, user, assessment_id, body)


@router.post(
    "/fitness-assessments/{assessment_id}/transitions",
    response_model=FitnessAssessmentRead,
    response_model_exclude_unset=True,
    summary="§4.3: sign (linked examiner, re-auth) · return · submit (scan) · accept / reject "
    "(154 ≠ submitter; clinical_data_present) · revoke (157, reason ≥ 20)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_fitness_assessment(
    assessment_id: uuid.UUID, body: FitnessAssessmentTransition, user: CurrentUser, db: DB
) -> FitnessAssessmentRead:
    return assessments.transition(db, user, assessment_id, body)


@router.get(
    "/fitness-assessments/{assessment_id}/verifications",
    response_model=FitnessVerificationList,
    summary="Verification log of an assessment (capability 157)",
    responses=error_responses(401, 403, 404),
)
def list_fitness_verifications(
    assessment_id: uuid.UUID, user: CurrentUser, db: DB
) -> FitnessVerificationList:
    return assessments.list_verifications(db, user, assessment_id)


@router.post(
    "/fitness-assessments/{assessment_id}/verifications",
    response_model=FitnessVerificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a verification with the issuing clinic (154; FV-2…FV-5)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_fitness_verification(
    assessment_id: uuid.UUID, body: FitnessVerificationCreate, user: CurrentUser, db: DB
) -> FitnessVerificationRead:
    return assessments.verify(db, user, assessment_id, body)


@router.post(
    "/fitness-assessments/{assessment_id}/scan-url",
    response_model=SignedUrlRead,
    summary="Signed URL ≤ 5 min to the certificate scan (capability 160, reason required; "
    "audited sensitive_field_read ['fitness_scan'])",
    responses=error_responses(401, 403, 404, 409, 422),
)
def get_fitness_scan_url(
    assessment_id: uuid.UUID, body: FitnessScanUrlRequest, user: CurrentUser, db: DB
) -> SignedUrlRead:
    return assessments.scan_url(db, user, assessment_id, body)


@router.get(
    "/workers/{worker_id}/fitness",
    response_model=WorkerFitnessRead,
    response_model_exclude_unset=True,
    summary="Worker fitness status per code on a project (HK6-6 at `at`; tiered OH-2)",
    responses=error_responses(401, 403, 404),
)
def get_worker_fitness(
    worker_id: uuid.UUID,
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    at: datetime | None = None,
) -> WorkerFitnessRead:
    return status_view.worker_fitness(db, user, worker_id, project_id, at)


@router.get(
    "/workers/{worker_id}/fitness-report",
    response_model=FitnessDataSubjectReport,
    summary="Per-worker data-subject report (capability 165; audited export, P6-9)",
    responses=error_responses(401, 403, 404, 422),
)
def get_worker_fitness_report(
    worker_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    purpose: ExportPurpose = ExportPurpose.data_subject_request,
) -> FitnessDataSubjectReport:
    return status_view.subject_report(db, user, worker_id, purpose)
