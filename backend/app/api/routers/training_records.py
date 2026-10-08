"""Training records, verification, certificate print / QR, the worker passport and the
per-worker data-subject report (spec 5-training §3.8, §3.9, §4.6, TR, VR, CK5, P5-3…P5-9)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.cert_enums import VerificationStatus
from app.core.errors import error_responses
from app.core.train_enums import (
    DataSubjectPurpose,
    TrainingRecordSource,
    TrainingRecordStatus,
    TrainingVerificationMethod,
)
from app.schemas.attachments import SignedUrlRead
from app.schemas.training_records import (
    CertificateReissue,
    DataSubjectReport,
    TrainingCertificatePrint,
    TrainingPassport,
    TrainingRecordCreate,
    TrainingRecordPage,
    TrainingRecordPreview,
    TrainingRecordPreviewRequest,
    TrainingRecordRead,
    TrainingRecordTransition,
    TrainingRecordUpdate,
    TrainingScanUrlRequest,
    TrainingVerificationCreate,
    TrainingVerificationList,
    TrainingVerificationLogPage,
    TrainingVerificationRead,
)
from app.services.train import records

router = APIRouter(tags=["training-records"])


@router.get(
    "/projects/{project_id}/training-records",
    response_model=TrainingRecordPage,
    summary="Training record register (capability 136; names only with 46). Records of "
    "workers deployed on the project, validity effective on the project (TR-16)",
    responses=error_responses(401, 403, 404, 422),
)
def list_training_records(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[
        str | None, Query(max_length=100, description="worker_no, record_no, certificate_no.")
    ] = None,
    course_code: Annotated[list[str] | None, Query()] = None,
    status_: Annotated[list[TrainingRecordStatus] | None, Query(alias="status")] = None,
    verification_status: Annotated[list[VerificationStatus] | None, Query()] = None,
    source: Annotated[list[TrainingRecordSource] | None, Query()] = None,
    provider_id: uuid.UUID | None = None,
    worker_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    in_force: bool | None = None,
    expiring_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    awaiting_review: bool | None = None,
    verification_overdue: bool | None = None,
    historic: bool | None = None,
) -> TrainingRecordPage:
    return records.list_records(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        q,
        course_code,
        status_,
        verification_status,
        source,
        provider_id,
        worker_id,
        session_id,
        engagement_id,
        include_subcontractors,
        in_force,
        expiring_days,
        awaiting_review,
        verification_overdue,
        historic,
    )


@router.post(
    "/projects/{project_id}/training-records",
    response_model=TrainingRecordRead,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_unset=True,
    summary="Record an external training certificate (capability 137) → Draft; id_on_card "
    "checked and never stored (TR-6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_training_record(
    project_id: uuid.UUID, body: TrainingRecordCreate, user: CurrentUser, db: DB
) -> TrainingRecordRead:
    return records.create(db, user, project_id, body)


@router.post(
    "/projects/{project_id}/training-records/preview",
    response_model=TrainingRecordPreview,
    summary="Validity (§6.1), name match, provider acceptability and refresher eligibility for "
    "the form; writes nothing",
    responses=error_responses(401, 403, 404, 422),
)
def preview_training_record(
    project_id: uuid.UUID, body: TrainingRecordPreviewRequest, user: CurrentUser, db: DB
) -> TrainingRecordPreview:
    return records.preview(db, user, project_id, body)


@router.get(
    "/training-records/{record_id}",
    response_model=TrainingRecordRead,
    response_model_exclude_unset=True,
    summary="Training record (scores per AT-7; reasons per P5-4)",
    responses=error_responses(401, 403, 404),
)
def get_training_record(
    record_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    project_id: Annotated[
        uuid.UUID | None, Query(description="Apply this project's validity override (§6.1).")
    ] = None,
) -> TrainingRecordRead:
    return records.read(db, user, record_id, project_id)


@router.patch(
    "/training-records/{record_id}",
    response_model=TrainingRecordRead,
    response_model_exclude_unset=True,
    summary="Edit a Draft record (137); an Accepted record after 24 h: HSE Manager with reason "
    "(TR-12)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_training_record(
    record_id: uuid.UUID, body: TrainingRecordUpdate, user: CurrentUser, db: DB
) -> TrainingRecordRead:
    return records.update(db, user, record_id, body)


@router.post(
    "/training-records/{record_id}/transitions",
    response_model=TrainingRecordRead,
    response_model_exclude_unset=True,
    summary="Submit / return / accept / reject / suspend / reinstate / revoke (§4.6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_training_record(
    record_id: uuid.UUID, body: TrainingRecordTransition, user: CurrentUser, db: DB
) -> TrainingRecordRead:
    return records.transition(db, user, record_id, body)


@router.get(
    "/training-records/{record_id}/verifications",
    response_model=TrainingVerificationList,
    summary="Verification records (outcome detail HSE Manager / Officer only, P5-1)",
    responses=error_responses(401, 403, 404),
)
def list_training_record_verifications(
    record_id: uuid.UUID, user: CurrentUser, db: DB
) -> TrainingVerificationList:
    return records.verifications(db, user, record_id)


@router.post(
    "/training-records/{record_id}/verifications",
    response_model=TrainingVerificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a verification with the provider / awarding body (capability 138; VR-2…VR-6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def verify_training_record(
    record_id: uuid.UUID, body: TrainingVerificationCreate, user: CurrentUser, db: DB
) -> TrainingVerificationRead:
    return records.verify(db, user, record_id, body)


@router.get(
    "/projects/{project_id}/training-verification-log",
    response_model=TrainingVerificationLogPage,
    summary="Verification log (§8.4; capability 138)",
    responses=error_responses(401, 403, 404, 422),
)
def list_training_verification_log(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    method: Annotated[list[TrainingVerificationMethod] | None, Query()] = None,
    failed_only: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
) -> TrainingVerificationLogPage:
    return records.verification_log(
        db, user, project_id, pg.page, pg.page_size, method, failed_only, date_from, date_to
    )


@router.post(
    "/training-records/{record_id}/scan-url",
    response_model=SignedUrlRead,
    summary="Short-lived scan URL (capability 139 with a reason; sensitive_field_read, P5-3)",
    responses=error_responses(401, 403, 404, 422),
)
def get_training_record_scan_url(
    record_id: uuid.UUID, body: TrainingScanUrlRequest, user: CurrentUser, db: DB
) -> SignedUrlRead:
    return records.scan_url(db, user, record_id, body)


@router.get(
    "/training-records/{record_id}/certificate",
    response_model=TrainingCertificatePrint,
    summary="Certificate print data with the TR QR (session records only, TR-14; capability "
    "136); external records → 404",
    responses=error_responses(401, 403, 404),
)
def get_training_certificate(
    record_id: uuid.UUID, user: CurrentUser, db: DB
) -> TrainingCertificatePrint:
    return records.certificate(db, user, record_id)


@router.post(
    "/training-records/{record_id}/certificate/reissue",
    response_model=TrainingCertificatePrint,
    summary="Rotate the TR QR token (capability 138); the old token shows REVOKED",
    responses=error_responses(401, 403, 404, 409, 422),
)
def reissue_training_certificate(
    record_id: uuid.UUID, body: CertificateReissue, user: CurrentUser, db: DB
) -> TrainingCertificatePrint:
    return records.reissue(db, user, record_id, body)


@router.get(
    "/workers/{worker_id}/training-records",
    response_model=TrainingPassport,
    summary="The worker's training passport across projects (capability 136; TR-16)",
    responses=error_responses(401, 403, 404, 422),
)
def get_worker_training_passport(
    worker_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    project_id: uuid.UUID | None = None,
    as_of: date | None = None,
) -> TrainingPassport:
    return records.passport(db, user, worker_id, project_id, as_of)


@router.get(
    "/workers/{worker_id}/training-report",
    response_model=DataSubjectReport,
    summary="Per-worker training report for a data-subject request (P5-9; capability 144, HSE "
    "Manager; audited as an export)",
    responses=error_responses(401, 403, 404, 422),
)
def get_worker_training_report(
    worker_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    purpose: DataSubjectPurpose,
) -> DataSubjectReport:
    return records.data_subject_report(db, user, worker_id, purpose)
