"""Airside driving permits, offences, vehicles and AVPs (spec 2-access-permits §3.10-§3.13,
§5.5, §5.6). Airport projects only (AP-2)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.access_enums import (
    AreaCategory,
    OffenceStatus,
    ValidityStatus,
    VehicleCategory,
    VehicleStatus,
)
from app.core.errors import error_responses, not_implemented
from app.schemas.airside_driving import (
    AdpCreate,
    AdpIssueRequest,
    AdpPage,
    AdpRead,
    AdpUpdate,
    AvpCreate,
    AvpIssueRequest,
    AvpPage,
    AvpRead,
    AvpStickerRead,
    AvpStickerReissueRequest,
    AvpUpdate,
    OffenceCreate,
    OffencePage,
    OffenceRead,
    OffenceTransitionRequest,
    VehicleCreate,
    VehiclePage,
    VehicleRead,
    VehicleTransitionRequest,
    VehicleUpdate,
)

router = APIRouter(tags=["airside-driving"])

# ---- ADP ----------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/adps",
    response_model=AdpPage,
    summary="ADP register",
    responses=error_responses(401, 403, 404, 422),
)
def list_adps(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    validity_status: Annotated[list[ValidityStatus] | None, Query()] = None,
    category: AreaCategory | None = None,
    worker_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    expiring_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> AdpPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/adps",
    response_model=AdpRead,
    status_code=status.HTTP_201_CREATED,
    summary="Apply for an ADP (capability 60) → pending",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_adp(project_id: uuid.UUID, body: AdpCreate, user: CurrentUser, db: DB) -> AdpRead:
    raise not_implemented()


@router.get(
    "/adps/{adp_id}",
    response_model=AdpRead,
    summary="Get an ADP with points (§6.5) and validity",
    responses=error_responses(401, 403, 404),
)
def get_adp(
    adp_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    points_as_of: Annotated[date | None, Query(description="Default today.")] = None,
) -> AdpRead:
    raise not_implemented()


@router.patch(
    "/adps/{adp_id}",
    response_model=AdpRead,
    summary="Edit a pending ADP: licence data (60), tests (61)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_adp(adp_id: uuid.UUID, body: AdpUpdate, user: CurrentUser, db: DB) -> AdpRead:
    raise not_implemented()


@router.post(
    "/adps/{adp_id}/issue",
    response_model=AdpRead,
    summary="Issue the ADP: pending → active (capability 61; DP-3…DP-6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def issue_adp(adp_id: uuid.UUID, body: AdpIssueRequest, user: CurrentUser, db: DB) -> AdpRead:
    raise not_implemented()


@router.post(
    "/adps/{adp_id}/withdraw",
    response_model=AdpRead,
    summary="Withdraw a pending ADP application (capability 60)",
    responses=error_responses(401, 403, 404, 409),
)
def withdraw_adp(adp_id: uuid.UUID, user: CurrentUser, db: DB) -> AdpRead:
    raise not_implemented()


# ---- offences -----------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/airside-offences",
    response_model=OffencePage,
    summary="Airside driving offence register",
    responses=error_responses(401, 403, 404, 422),
)
def list_offences(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[OffenceStatus] | None, Query(alias="status")] = None,
    offence_code: Annotated[list[str] | None, Query()] = None,
    worker_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    date_from: date | None = None,
    date_to: date | None = None,
) -> OffencePage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/airside-offences",
    response_model=OffenceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record an airside driving offence (capability 62; DP-8, DP-9)",
    responses=error_responses(401, 403, 404, 422),
)
def create_offence(
    project_id: uuid.UUID, body: OffenceCreate, user: CurrentUser, db: DB
) -> OffenceRead:
    raise not_implemented()


@router.get(
    "/airside-offences/{offence_id}",
    response_model=OffenceRead,
    summary="Get an offence",
    responses=error_responses(401, 403, 404),
)
def get_offence(offence_id: uuid.UUID, user: CurrentUser, db: DB) -> OffenceRead:
    raise not_implemented()


@router.post(
    "/airside-offences/{offence_id}/transitions",
    response_model=OffenceRead,
    summary="Dispute / uphold / withdraw an offence (capability 58; DP-10)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_offence(
    offence_id: uuid.UUID, body: OffenceTransitionRequest, user: CurrentUser, db: DB
) -> OffenceRead:
    raise not_implemented()


# ---- vehicles -----------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/vehicles",
    response_model=VehiclePage,
    summary="Vehicle / mobile plant register",
    responses=error_responses(401, 403, 404, 422),
)
def list_vehicles(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[VehicleStatus] | None, Query(alias="status")] = None,
    category: Annotated[list[VehicleCategory] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    documents_expiring_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    q: Annotated[
        str | None, Query(max_length=60, description="vehicle_no, fleet_no, plate, serial.")
    ] = None,
) -> VehiclePage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/vehicles",
    response_model=VehicleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a vehicle (capability 63)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_vehicle(
    project_id: uuid.UUID, body: VehicleCreate, user: CurrentUser, db: DB
) -> VehicleRead:
    raise not_implemented()


@router.get(
    "/vehicles/{vehicle_id}",
    response_model=VehicleRead,
    summary="Get a vehicle",
    responses=error_responses(401, 403, 404),
)
def get_vehicle(vehicle_id: uuid.UUID, user: CurrentUser, db: DB) -> VehicleRead:
    raise not_implemented()


@router.patch(
    "/vehicles/{vehicle_id}",
    response_model=VehicleRead,
    summary="Edit a vehicle (capability 63; later document expiry auto-reinstates, VP-5)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_vehicle(
    vehicle_id: uuid.UUID, body: VehicleUpdate, user: CurrentUser, db: DB
) -> VehicleRead:
    raise not_implemented()


@router.post(
    "/vehicles/{vehicle_id}/transitions",
    response_model=VehicleRead,
    summary="Set vehicle status active / off_site / withdrawn (capability 63)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_vehicle(
    vehicle_id: uuid.UUID, body: VehicleTransitionRequest, user: CurrentUser, db: DB
) -> VehicleRead:
    raise not_implemented()


# ---- AVP ----------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/avps",
    response_model=AvpPage,
    summary="AVP register",
    responses=error_responses(401, 403, 404, 422),
)
def list_avps(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    validity_status: Annotated[list[ValidityStatus] | None, Query()] = None,
    area: AreaCategory | None = None,
    vehicle_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    expiring_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
) -> AvpPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/avps",
    response_model=AvpRead,
    status_code=status.HTTP_201_CREATED,
    summary="Apply for an AVP (capability 63) → pending",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_avp(project_id: uuid.UUID, body: AvpCreate, user: CurrentUser, db: DB) -> AvpRead:
    raise not_implemented()


@router.get(
    "/avps/{avp_id}",
    response_model=AvpRead,
    summary="Get an AVP",
    responses=error_responses(401, 403, 404),
)
def get_avp(avp_id: uuid.UUID, user: CurrentUser, db: DB) -> AvpRead:
    raise not_implemented()


@router.patch(
    "/avps/{avp_id}",
    response_model=AvpRead,
    summary="Record inspection and checklist on a pending AVP (capability 64)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_avp(avp_id: uuid.UUID, body: AvpUpdate, user: CurrentUser, db: DB) -> AvpRead:
    raise not_implemented()


@router.post(
    "/avps/{avp_id}/issue",
    response_model=AvpRead,
    summary="Issue the AVP: pending → active (capability 64; VP-3/VP-4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def issue_avp(avp_id: uuid.UUID, body: AvpIssueRequest, user: CurrentUser, db: DB) -> AvpRead:
    raise not_implemented()


@router.post(
    "/avps/{avp_id}/withdraw",
    response_model=AvpRead,
    summary="Withdraw a pending AVP application (capability 63)",
    responses=error_responses(401, 403, 404, 409),
)
def withdraw_avp(avp_id: uuid.UUID, user: CurrentUser, db: DB) -> AvpRead:
    raise not_implemented()


@router.get(
    "/avps/{avp_id}/sticker",
    response_model=AvpStickerRead,
    summary="AVP sticker QR payload to print (capability 64; active AVPs)",
    responses=error_responses(401, 403, 404, 409),
)
def get_avp_sticker(avp_id: uuid.UUID, user: CurrentUser, db: DB) -> AvpStickerRead:
    raise not_implemented()


@router.post(
    "/avps/{avp_id}/sticker/reissue",
    response_model=AvpStickerRead,
    summary="Reissue the sticker: rotate the token (capability 64; GC-16)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def reissue_avp_sticker(
    avp_id: uuid.UUID, body: AvpStickerReissueRequest, user: CurrentUser, db: DB
) -> AvpStickerRead:
    raise not_implemented()
