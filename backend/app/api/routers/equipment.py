"""Equipment register (org-wide), project deployments, arrival inspection, configuration events,
EQ stickers and service-status actions (spec 4-third-party-cert §3.4, §3.5, §3.7, §4.2, §4.3,
EQ-1…EQ-6, EM-1…EM-6, CF-1…CF-4, DF-6, DF-8, BL-3)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.cert_enums import (
    EquipmentCertCategory,
    EquipmentDeploymentStatus,
    ServiceStatus,
)
from app.core.errors import error_responses
from app.schemas.equipment import (
    ArrivalInspectionInput,
    ArrivalInspectionRead,
    ConfigurationEventCreate,
    ConfigurationEventList,
    ConfigurationEventRead,
    EquipmentBlacklistRequest,
    EquipmentCreate,
    EquipmentDeploymentCreate,
    EquipmentDeploymentPage,
    EquipmentDeploymentRead,
    EquipmentDeploymentTransition,
    EquipmentDeploymentUpdate,
    EquipmentLookupRequest,
    EquipmentLookupResult,
    EquipmentPage,
    EquipmentRead,
    EquipmentStatusEventList,
    EquipmentStickerRead,
    EquipmentUpdate,
    LiftBlacklistRequest,
    RetireRequest,
    ReturnToServiceRequest,
    StickerReissueRequest,
    TagOutRequest,
)
from app.services.cert import deployments as dsvc
from app.services.cert import equipment as svc

router = APIRouter(tags=["equipment"])


# ---- equipment items (org-wide master) ------------------------------------------------------


@router.get(
    "/equipment",
    response_model=EquipmentPage,
    summary="Equipment register (capability 105; scoped to items deployed in the caller's "
    "projects / contractor tree)",
    responses=error_responses(401, 403, 422),
)
def list_equipment(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[
        str | None, Query(max_length=100, description="Equipment no., tag, serial, model.")
    ] = None,
    project_id: uuid.UUID | None = None,
    category: Annotated[list[EquipmentCertCategory] | None, Query()] = None,
    service_status: Annotated[list[ServiceStatus] | None, Query()] = None,
    owner_contractor_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    expiring_days: Annotated[
        int | None, Query(ge=0, le=365, description="valid_until within N days.")
    ] = None,
) -> EquipmentPage:
    return svc.list_items(
        db,
        user,
        pg.page,
        pg.page_size,
        q,
        project_id,
        category,
        service_status,
        owner_contractor_id,
        engagement_id,
        expiring_days,
    )


@router.post(
    "/equipment",
    response_model=EquipmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an equipment item (capability 106) → Awaiting Certificate",
    responses=error_responses(401, 403, 409, 422),
)
def create_equipment(body: EquipmentCreate, user: CurrentUser, db: DB) -> EquipmentRead:
    return svc.create(db, user, body)


@router.post(
    "/equipment/lookup",
    response_model=EquipmentLookupResult,
    summary="Duplicate / blacklist check by manufacturer + serial before registering (EQ-1)",
    responses=error_responses(401, 403, 422),
)
def lookup_equipment(
    body: EquipmentLookupRequest, user: CurrentUser, db: DB
) -> EquipmentLookupResult:
    return svc.lookup(db, user, body)


@router.get(
    "/equipment/{equipment_id}",
    response_model=EquipmentRead,
    summary="Equipment item with deployments, current lines, defects and blacklist record",
    responses=error_responses(401, 403, 404),
)
def get_equipment(equipment_id: uuid.UUID, user: CurrentUser, db: DB) -> EquipmentRead:
    return svc.read(db, user, equipment_id)


@router.patch(
    "/equipment/{equipment_id}",
    response_model=EquipmentRead,
    summary="Edit an equipment item (capability 106; serial / manufacturer locked once a "
    "certificate references it)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_equipment(
    equipment_id: uuid.UUID, body: EquipmentUpdate, user: CurrentUser, db: DB
) -> EquipmentRead:
    return svc.update(db, user, equipment_id, body)


@router.get(
    "/equipment/{equipment_id}/status-events",
    response_model=EquipmentStatusEventList,
    summary="Service-status history (§4.2)",
    responses=error_responses(401, 403, 404),
)
def list_equipment_status_events(
    equipment_id: uuid.UUID, user: CurrentUser, db: DB
) -> EquipmentStatusEventList:
    return svc.status_events(db, user, equipment_id)


@router.post(
    "/equipment/{equipment_id}/tag-out",
    response_model=EquipmentRead,
    summary="Manual tag-out → Out of Service (DF-8; capability 110; never blocked)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def tag_out_equipment(
    equipment_id: uuid.UUID, body: TagOutRequest, user: CurrentUser, db: DB
) -> EquipmentRead:
    return svc.tag_out(db, user, equipment_id, body)


@router.post(
    "/equipment/{equipment_id}/return-to-service",
    response_model=EquipmentRead,
    summary="Return to service (DF-6; capability 112; defects closed, SoD)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def return_equipment_to_service(
    equipment_id: uuid.UUID, body: ReturnToServiceRequest, user: CurrentUser, db: DB
) -> EquipmentRead:
    return svc.return_to_service(db, user, equipment_id, body)


@router.post(
    "/equipment/{equipment_id}/retire",
    response_model=EquipmentRead,
    summary="Retire an item (capability 112; terminal)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def retire_equipment(
    equipment_id: uuid.UUID, body: RetireRequest, user: CurrentUser, db: DB
) -> EquipmentRead:
    return svc.retire(db, user, equipment_id, body)


@router.post(
    "/equipment/{equipment_id}/blacklist",
    response_model=EquipmentRead,
    summary="Blacklist an item (BL-3; capability 115, HSE Manager only)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def blacklist_equipment(
    equipment_id: uuid.UUID, body: EquipmentBlacklistRequest, user: CurrentUser, db: DB
) -> EquipmentRead:
    return svc.blacklist(db, user, equipment_id, body)


@router.post(
    "/equipment/{equipment_id}/lift-blacklist",
    response_model=EquipmentRead,
    summary="Lift an equipment blacklist → Out of Service (BL-8; capability 115)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def lift_equipment_blacklist(
    equipment_id: uuid.UUID, body: LiftBlacklistRequest, user: CurrentUser, db: DB
) -> EquipmentRead:
    return svc.lift_blacklist(db, user, equipment_id, body)


@router.get(
    "/equipment/{equipment_id}/configuration-events",
    response_model=ConfigurationEventList,
    summary="Configuration events of an item (§3.7)",
    responses=error_responses(401, 403, 404),
)
def list_configuration_events(
    equipment_id: uuid.UUID, user: CurrentUser, db: DB
) -> ConfigurationEventList:
    return svc.list_config(db, user, equipment_id)


@router.post(
    "/equipment/{equipment_id}/configuration-events",
    response_model=ConfigurationEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a configuration change (CF-1; capability 106): suspends lines, quarantines",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_configuration_event(
    equipment_id: uuid.UUID, body: ConfigurationEventCreate, user: CurrentUser, db: DB
) -> ConfigurationEventRead:
    return svc.create_config(db, user, equipment_id, body)


# ---- deployments --------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/equipment-deployments",
    response_model=EquipmentDeploymentPage,
    summary="Equipment deployed on the project (capability 105)",
    responses=error_responses(401, 403, 404, 422),
)
def list_equipment_deployments(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: Annotated[str | None, Query(max_length=100, description="Tag, equipment no.")] = None,
    status_: Annotated[list[EquipmentDeploymentStatus] | None, Query(alias="status")] = None,
    category: Annotated[list[EquipmentCertCategory] | None, Query()] = None,
    service_status: Annotated[list[ServiceStatus] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    site_id: uuid.UUID | None = None,
    arrival_inspection_due: bool | None = None,
) -> EquipmentDeploymentPage:
    return dsvc.list_deployments(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        q,
        status_,
        category,
        service_status,
        engagement_id,
        include_subcontractors,
        site_id,
        arrival_inspection_due,
    )


@router.post(
    "/projects/{project_id}/equipment-deployments",
    response_model=EquipmentDeploymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Plan a deployment of an item on the project (capability 106) → Planned",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_equipment_deployment(
    project_id: uuid.UUID, body: EquipmentDeploymentCreate, user: CurrentUser, db: DB
) -> EquipmentDeploymentRead:
    return dsvc.create(db, user, project_id, body)


@router.get(
    "/equipment-deployments/{deployment_id}",
    response_model=EquipmentDeploymentRead,
    summary="Deployment detail",
    responses=error_responses(401, 403, 404),
)
def get_equipment_deployment(
    deployment_id: uuid.UUID, user: CurrentUser, db: DB
) -> EquipmentDeploymentRead:
    return dsvc.read(db, user, deployment_id)


@router.patch(
    "/equipment-deployments/{deployment_id}",
    response_model=EquipmentDeploymentRead,
    summary="Edit a deployment (capability 106; tag, sites, vehicle link)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_equipment_deployment(
    deployment_id: uuid.UUID, body: EquipmentDeploymentUpdate, user: CurrentUser, db: DB
) -> EquipmentDeploymentRead:
    return dsvc.update(db, user, deployment_id, body)


@router.post(
    "/equipment-deployments/{deployment_id}/transitions",
    response_model=EquipmentDeploymentRead,
    summary="Approve for mobilisation / arrive / demobilise / cancel (§4.3; capability 109)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_equipment_deployment(
    deployment_id: uuid.UUID, body: EquipmentDeploymentTransition, user: CurrentUser, db: DB
) -> EquipmentDeploymentRead:
    return dsvc.transition(db, user, deployment_id, body)


@router.post(
    "/equipment-deployments/{deployment_id}/arrival-inspection",
    response_model=ArrivalInspectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record the arrival inspection (EM-3; capability 109)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_arrival_inspection(
    deployment_id: uuid.UUID, body: ArrivalInspectionInput, user: CurrentUser, db: DB
) -> ArrivalInspectionRead:
    return dsvc.record_arrival_inspection(db, user, deployment_id, body)


@router.get(
    "/equipment-deployments/{deployment_id}/sticker",
    response_model=EquipmentStickerRead,
    summary="EQ sticker payload and printed ref (after approval, EM-2)",
    responses=error_responses(401, 403, 404, 409),
)
def get_equipment_sticker(
    deployment_id: uuid.UUID, user: CurrentUser, db: DB
) -> EquipmentStickerRead:
    return dsvc.get_sticker(db, user, deployment_id)


@router.post(
    "/equipment-deployments/{deployment_id}/sticker/reissue",
    response_model=EquipmentStickerRead,
    summary="Rotate the EQ sticker token (capability 109; old sticker → CREDENTIAL_REVOKED)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def reissue_equipment_sticker(
    deployment_id: uuid.UUID, body: StickerReissueRequest, user: CurrentUser, db: DB
) -> EquipmentStickerRead:
    return dsvc.reissue_sticker(db, user, deployment_id, body)
