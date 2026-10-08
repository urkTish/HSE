"""TPI organisations, accreditations and client approvals (spec 4-third-party-cert §3.1–§3.3,
§4.1, TP-1…TP-8, BL-6…BL-8)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.cert_enums import ClientApprovalStatus, EquipmentCertCategory, TpiKind, TpiStatus
from app.core.errors import error_responses, not_implemented
from app.schemas.tpi import (
    AccreditationCreate,
    AccreditationRead,
    AccreditationUpdate,
    ClientApprovalCreate,
    ClientApprovalList,
    ClientApprovalRead,
    ClientApprovalUpdate,
    RegisterCheckInput,
    TpiCreate,
    TpiImpact,
    TpiPage,
    TpiRead,
    TpiTransitionRequest,
    TpiUpdate,
)

router = APIRouter(tags=["tpis"])


@router.get(
    "/tpis",
    response_model=TpiPage,
    summary="TPI register (org-wide; capability 105). Contractor roles see accepted / not "
    "accepted only (P4-5)",
    responses=error_responses(401, 403, 422),
)
def list_tpis(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[str | None, Query(max_length=100, description="Code or name.")] = None,
    status_: Annotated[list[TpiStatus] | None, Query(alias="status")] = None,
    kind: Annotated[list[TpiKind] | None, Query()] = None,
    category: Annotated[
        EquipmentCertCategory | None,
        Query(description="Accredited (and, with project_id, client-approved) for it."),
    ] = None,
    cert_type: Annotated[str | None, Query(max_length=40)] = None,
    project_id: Annotated[
        uuid.UUID | None,
        Query(description="Adds `acceptable_on_project` (TP-4/TP-5) for this project."),
    ] = None,
    accreditation_expiring_days: Annotated[int | None, Query(ge=0, le=365)] = None,
) -> TpiPage:
    raise not_implemented()


@router.post(
    "/tpis",
    response_model=TpiRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a TPI (capability 114) → Draft",
    responses=error_responses(401, 403, 409, 422),
)
def create_tpi(body: TpiCreate, user: CurrentUser, db: DB) -> TpiRead:
    raise not_implemented()


@router.get(
    "/tpis/{tpi_id}",
    response_model=TpiRead,
    summary="TPI detail with accreditations and client approvals",
    responses=error_responses(401, 403, 404),
)
def get_tpi(tpi_id: uuid.UUID, user: CurrentUser, db: DB) -> TpiRead:
    raise not_implemented()


@router.patch(
    "/tpis/{tpi_id}",
    response_model=TpiRead,
    summary="Edit a TPI (capability 114; tpi_code immutable)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_tpi(tpi_id: uuid.UUID, body: TpiUpdate, user: CurrentUser, db: DB) -> TpiRead:
    raise not_implemented()


@router.post(
    "/tpis/{tpi_id}/transitions",
    response_model=TpiRead,
    summary="TPI status transition (§4.1; approve / suspend / blacklist / lift: capability 115)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_tpi(
    tpi_id: uuid.UUID, body: TpiTransitionRequest, user: CurrentUser, db: DB
) -> TpiRead:
    raise not_implemented()


@router.get(
    "/tpis/{tpi_id}/affected",
    response_model=TpiImpact,
    summary="Items, holders and detectors affected by the TPI's suspension / blacklist (BL-7)",
    responses=error_responses(401, 403, 404),
)
def get_tpi_impact(tpi_id: uuid.UUID, user: CurrentUser, db: DB) -> TpiImpact:
    raise not_implemented()


@router.post(
    "/tpis/{tpi_id}/accreditations",
    response_model=AccreditationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an accreditation (capability 114; standard ↔ kind, §3.2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_tpi_accreditation(
    tpi_id: uuid.UUID, body: AccreditationCreate, user: CurrentUser, db: DB
) -> AccreditationRead:
    raise not_implemented()


@router.patch(
    "/tpi-accreditations/{accreditation_id}",
    response_model=AccreditationRead,
    summary="Edit an accreditation (capability 114)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_tpi_accreditation(
    accreditation_id: uuid.UUID, body: AccreditationUpdate, user: CurrentUser, db: DB
) -> AccreditationRead:
    raise not_implemented()


@router.post(
    "/tpi-accreditations/{accreditation_id}/register-check",
    response_model=AccreditationRead,
    summary="Record the accreditation-body register check (TP-3; capability 114)",
    responses=error_responses(401, 403, 404, 422),
)
def record_accreditation_register_check(
    accreditation_id: uuid.UUID, body: RegisterCheckInput, user: CurrentUser, db: DB
) -> AccreditationRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/tpi-approvals",
    response_model=ClientApprovalList,
    summary="Client approvals of TPIs on the project (§3.3)",
    responses=error_responses(401, 403, 404, 422),
)
def list_tpi_client_approvals(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    status_: Annotated[list[ClientApprovalStatus] | None, Query(alias="status")] = None,
    tpi_id: uuid.UUID | None = None,
) -> ClientApprovalList:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/tpi-approvals",
    response_model=ClientApprovalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a client approval of a TPI (capability 114)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_tpi_client_approval(
    project_id: uuid.UUID, body: ClientApprovalCreate, user: CurrentUser, db: DB
) -> ClientApprovalRead:
    raise not_implemented()


@router.patch(
    "/tpi-approvals/{approval_id}",
    response_model=ClientApprovalRead,
    summary="Edit / withdraw a client approval (capability 114)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_tpi_client_approval(
    approval_id: uuid.UUID, body: ClientApprovalUpdate, user: CurrentUser, db: DB
) -> ClientApprovalRead:
    raise not_implemented()
