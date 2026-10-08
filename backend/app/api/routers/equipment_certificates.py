"""Equipment inspection certificates, their verification and the project verification log
(spec 4-third-party-cert §3.6, §3.10, §4.4, §6.1, EC-1…EC-14, VF-1…VF-7)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.cert_enums import (
    CertificateStatus,
    CertInspectionType,
    CertKind,
    CertSource,
    EquipmentCertCategory,
    VerificationOutcome,
    VerificationStatus,
)
from app.core.errors import error_responses, not_implemented
from app.schemas.cert_common import (
    CertTransitionRequest,
    VerificationCreate,
    VerificationList,
    VerificationLogPage,
    VerificationRead,
)
from app.schemas.equipment_certs import (
    EquipmentCertificateCreate,
    EquipmentCertificatePage,
    EquipmentCertificateRead,
    EquipmentCertificateUpdate,
    EquipmentCertPreview,
)

router = APIRouter(tags=["equipment-certificates"])


@router.get(
    "/projects/{project_id}/equipment-certificates",
    response_model=EquipmentCertificatePage,
    summary="Equipment certificate register (capability 105)",
    responses=error_responses(401, 403, 404, 422),
)
def list_equipment_certificates(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[str | None, Query(max_length=100, description="Cert no., tag.")] = None,
    status_: Annotated[list[CertificateStatus] | None, Query(alias="status")] = None,
    verification_status: Annotated[list[VerificationStatus] | None, Query()] = None,
    tpi_id: uuid.UUID | None = None,
    equipment_id: uuid.UUID | None = None,
    category: Annotated[list[EquipmentCertCategory] | None, Query()] = None,
    inspection_type: Annotated[list[CertInspectionType] | None, Query()] = None,
    source: CertSource | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    in_force: bool | None = None,
    expiring_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    verification_overdue: bool | None = None,
) -> EquipmentCertificatePage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/equipment-certificates",
    response_model=EquipmentCertificateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record an equipment certificate (capability 106) → Draft",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_equipment_certificate(
    project_id: uuid.UUID, body: EquipmentCertificateCreate, user: CurrentUser, db: DB
) -> EquipmentCertificateRead:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/equipment-certificates/preview",
    response_model=EquipmentCertPreview,
    summary="Validity per line (§6.1) and Submit errors / warnings; writes nothing",
    responses=error_responses(401, 403, 404, 422),
)
def preview_equipment_certificate(
    project_id: uuid.UUID, body: EquipmentCertificateCreate, user: CurrentUser, db: DB
) -> EquipmentCertPreview:
    raise not_implemented()


@router.get(
    "/equipment-certificates/{certificate_id}",
    response_model=EquipmentCertificateRead,
    summary="Equipment certificate with lines, validity and allowed actions",
    responses=error_responses(401, 403, 404),
)
def get_equipment_certificate(
    certificate_id: uuid.UUID, user: CurrentUser, db: DB
) -> EquipmentCertificateRead:
    raise not_implemented()


@router.patch(
    "/equipment-certificates/{certificate_id}",
    response_model=EquipmentCertificateRead,
    summary="Edit a Draft certificate (capability 106)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_equipment_certificate(
    certificate_id: uuid.UUID, body: EquipmentCertificateUpdate, user: CurrentUser, db: DB
) -> EquipmentCertificateRead:
    raise not_implemented()


@router.post(
    "/equipment-certificates/{certificate_id}/transitions",
    response_model=EquipmentCertificateRead,
    summary="Submit / return / accept / reject / suspend / reinstate / revoke (§4.4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_equipment_certificate(
    certificate_id: uuid.UUID, body: CertTransitionRequest, user: CurrentUser, db: DB
) -> EquipmentCertificateRead:
    raise not_implemented()


@router.get(
    "/equipment-certificates/{certificate_id}/verifications",
    response_model=VerificationList,
    summary="Verification records of the certificate",
    responses=error_responses(401, 403, 404),
)
def list_equipment_certificate_verifications(
    certificate_id: uuid.UUID, user: CurrentUser, db: DB
) -> VerificationList:
    raise not_implemented()


@router.post(
    "/equipment-certificates/{certificate_id}/verifications",
    response_model=VerificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a verification with the TPI (capability 108; VF-2…VF-6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def verify_equipment_certificate(
    certificate_id: uuid.UUID, body: VerificationCreate, user: CurrentUser, db: DB
) -> VerificationRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/verification-log",
    response_model=VerificationLogPage,
    summary="Verification log, equipment and personnel (capability 105; outcome detail "
    "HSE Manager / Officer only, P4-4)",
    responses=error_responses(401, 403, 404, 422),
)
def get_verification_log(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    cert_kind: CertKind | None = None,
    outcome: Annotated[list[VerificationOutcome] | None, Query()] = None,
    tpi_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> VerificationLogPage:
    raise not_implemented()
