"""Personnel certificates, scans and restriction review; certification bans and the
blacklist register (spec 4-third-party-cert §3.9, §3.12, §3.13, §4.4, §4.7, §6.2,
PC-1…PC-13, BL-1…BL-8, P4-1…P4-6)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.cert_enums import (
    BanStatus,
    BlacklistSubject,
    CertificateStatus,
    CertSource,
    VerificationStatus,
)
from app.core.errors import error_responses
from app.schemas.attachments import SignedUrlRead
from app.schemas.cert_common import (
    CertTransitionRequest,
    VerificationCreate,
    VerificationList,
    VerificationRead,
)
from app.schemas.personnel_certs import (
    BlacklistRegister,
    CertificationBanCreate,
    CertificationBanLift,
    CertificationBanPage,
    CertificationBanRead,
    PersonnelCertCreate,
    PersonnelCertPage,
    PersonnelCertPreview,
    PersonnelCertPreviewRequest,
    PersonnelCertRead,
    PersonnelCertUpdate,
    RestrictionReviewRequest,
    ScanUrlRequest,
    WorkerCertificates,
)
from app.services.cert import bans as bsvc
from app.services.cert import personnel as svc

router = APIRouter(tags=["personnel-certificates"])


@router.get(
    "/projects/{project_id}/personnel-certificates",
    response_model=PersonnelCertPage,
    summary="Personnel certification register (capability 117; names only with 46)",
    responses=error_responses(401, 403, 404, 422),
)
def list_personnel_certificates(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[str | None, Query(max_length=100, description="worker_no, cert no.")] = None,
    cert_type: Annotated[list[str] | None, Query()] = None,
    status_: Annotated[list[CertificateStatus] | None, Query(alias="status")] = None,
    verification_status: Annotated[list[VerificationStatus] | None, Query()] = None,
    tpi_id: uuid.UUID | None = None,
    worker_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    source: CertSource | None = None,
    in_force: bool | None = None,
    expiring_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    verification_overdue: bool | None = None,
) -> PersonnelCertPage:
    return svc.list_certificates(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        q,
        cert_type,
        status_,
        verification_status,
        tpi_id,
        worker_id,
        engagement_id,
        include_subcontractors,
        source,
        in_force,
        expiring_days,
        verification_overdue,
    )


@router.post(
    "/projects/{project_id}/personnel-certificates",
    response_model=PersonnelCertRead,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_unset=True,
    summary="Record a personnel certificate (capability 118) → Draft; id_on_card checked "
    "and never stored (PC-3)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_personnel_certificate(
    project_id: uuid.UUID, body: PersonnelCertCreate, user: CurrentUser, db: DB
) -> PersonnelCertRead:
    return svc.create(db, user, project_id, body)


@router.post(
    "/projects/{project_id}/personnel-certificates/preview",
    response_model=PersonnelCertPreview,
    summary="Validity (§6.2), name match and scope checks for the form; writes nothing",
    responses=error_responses(401, 403, 404, 422),
)
def preview_personnel_certificate(
    project_id: uuid.UUID, body: PersonnelCertPreviewRequest, user: CurrentUser, db: DB
) -> PersonnelCertPreview:
    return svc.preview(db, user, project_id, body)


@router.get(
    "/personnel-certificates/{certificate_id}",
    response_model=PersonnelCertRead,
    response_model_exclude_unset=True,
    summary="Personnel certificate (medical-restriction pointer only for 107/108 roles)",
    responses=error_responses(401, 403, 404),
)
def get_personnel_certificate(
    certificate_id: uuid.UUID, user: CurrentUser, db: DB
) -> PersonnelCertRead:
    return svc.read(db, user, certificate_id)


@router.patch(
    "/personnel-certificates/{certificate_id}",
    response_model=PersonnelCertRead,
    response_model_exclude_unset=True,
    summary="Edit a Draft personnel certificate (capability 118)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_personnel_certificate(
    certificate_id: uuid.UUID, body: PersonnelCertUpdate, user: CurrentUser, db: DB
) -> PersonnelCertRead:
    return svc.update(db, user, certificate_id, body)


@router.post(
    "/personnel-certificates/{certificate_id}/transitions",
    response_model=PersonnelCertRead,
    response_model_exclude_unset=True,
    summary="Submit / return / accept / reject / suspend / reinstate / revoke (§4.4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_personnel_certificate(
    certificate_id: uuid.UUID, body: CertTransitionRequest, user: CurrentUser, db: DB
) -> PersonnelCertRead:
    return svc.transition(db, user, certificate_id, body)


@router.get(
    "/personnel-certificates/{certificate_id}/verifications",
    response_model=VerificationList,
    summary="Verification records (outcome detail HSE Manager / Officer only, P4-4)",
    responses=error_responses(401, 403, 404),
)
def list_personnel_certificate_verifications(
    certificate_id: uuid.UUID, user: CurrentUser, db: DB
) -> VerificationList:
    return svc.verifications(db, user, certificate_id)


@router.post(
    "/personnel-certificates/{certificate_id}/verifications",
    response_model=VerificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a verification with the TPI (capability 108; VF-2…VF-6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def verify_personnel_certificate(
    certificate_id: uuid.UUID, body: VerificationCreate, user: CurrentUser, db: DB
) -> VerificationRead:
    return svc.verify(db, user, certificate_id, body)


@router.post(
    "/personnel-certificates/{certificate_id}/scan-url",
    response_model=SignedUrlRead,
    summary="Short-lived scan URL (capability 119 with a reason; sensitive_field_read, P4-3)",
    responses=error_responses(401, 403, 404, 422),
)
def get_personnel_certificate_scan_url(
    certificate_id: uuid.UUID, body: ScanUrlRequest, user: CurrentUser, db: DB
) -> SignedUrlRead:
    return svc.scan_url(db, user, certificate_id, body)


@router.post(
    "/personnel-certificates/{certificate_id}/restriction-review",
    response_model=PersonnelCertRead,
    response_model_exclude_unset=True,
    summary="Record 'restriction reviewed' (PC-13; capability 107)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def review_personnel_certificate_restriction(
    certificate_id: uuid.UUID, body: RestrictionReviewRequest, user: CurrentUser, db: DB
) -> PersonnelCertRead:
    return svc.review_restriction(db, user, certificate_id, body)


@router.get(
    "/workers/{worker_id}/certificates",
    response_model=WorkerCertificates,
    summary="A worker's certificates by type with the PC-12 trade requirement (117)",
    responses=error_responses(401, 403, 404),
)
def get_worker_certificates(
    worker_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    project_id: uuid.UUID | None = None,
) -> WorkerCertificates:
    return svc.worker_certificates(db, user, worker_id, project_id)


# ---- certification bans and blacklist register ----------------------------------------------


@router.get(
    "/certification-bans",
    response_model=CertificationBanPage,
    summary="Certification bans (HSE Manager / Officer; contractor roles: 'not accepted' only)",
    responses=error_responses(401, 403, 422),
)
def list_certification_bans(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[BanStatus] | None, Query(alias="status")] = None,
    worker_id: uuid.UUID | None = None,
    review_due: bool | None = None,
) -> CertificationBanPage:
    return bsvc.list_bans(db, user, pg.page, pg.page_size, status_, worker_id, review_due)


@router.post(
    "/certification-bans",
    response_model=CertificationBanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Ban a person from certification (BL-4; capability 115)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_certification_ban(
    body: CertificationBanCreate, user: CurrentUser, db: DB
) -> CertificationBanRead:
    return bsvc.create(db, user, body)


@router.get(
    "/certification-bans/{ban_id}",
    response_model=CertificationBanRead,
    summary="Certification ban detail",
    responses=error_responses(401, 403, 404),
)
def get_certification_ban(ban_id: uuid.UUID, user: CurrentUser, db: DB) -> CertificationBanRead:
    return bsvc.get(db, user, ban_id)


@router.post(
    "/certification-bans/{ban_id}/lift",
    response_model=CertificationBanRead,
    summary="Lift a certification ban (BL-8; capability 115)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def lift_certification_ban(
    ban_id: uuid.UUID, body: CertificationBanLift, user: CurrentUser, db: DB
) -> CertificationBanRead:
    return bsvc.lift(db, user, ban_id, body)


@router.get(
    "/blacklist-register",
    response_model=BlacklistRegister,
    summary="Blacklist and ban register: equipment, persons, TPIs (§8.4)",
    responses=error_responses(401, 403, 422),
)
def get_blacklist_register(
    user: CurrentUser,
    db: DB,
    subject: Annotated[list[BlacklistSubject] | None, Query()] = None,
    project_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> BlacklistRegister:
    return bsvc.register(db, user, subject, project_id, active_only)
