"""PTW configuration: permit types, zone PTW profiles, zone adjacency, SIMOPS matrix, risk
matrix and Phase 3 settings (spec 3-ptw §3.1-§3.3, §3.12, §3.17, §6.1)."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser
from app.core.errors import error_responses, not_implemented
from app.core.ptw_enums import PermitType
from app.schemas.ptw_config import (
    PermitTypeConfigList,
    PermitTypeConfigRead,
    PermitTypeConfigUpdate,
    PtwSettingsRead,
    PtwSettingsUpdate,
    RiskMatrixRead,
    SimopsRuleCreate,
    SimopsRuleList,
    SimopsRuleRead,
    SimopsRuleUpdate,
    ZoneAdjacencyCreate,
    ZoneAdjacencyRead,
    ZoneAdjacencyUpdate,
    ZonePtwProfileRead,
    ZonePtwProfileUpdate,
)

router = APIRouter(tags=["ptw-configuration"])


@router.get(
    "/projects/{project_id}/permit-types",
    response_model=PermitTypeConfigList,
    summary="Permit type configuration of a project (§3.1; capability 82)",
    responses=error_responses(401, 403, 404),
)
def list_permit_types(project_id: uuid.UUID, user: CurrentUser, db: DB) -> PermitTypeConfigList:
    raise not_implemented()


@router.patch(
    "/projects/{project_id}/permit-types/{permit_type}",
    response_model=PermitTypeConfigRead,
    summary="Edit a permit type's checklists, mandatory hazards and hooks (capability 99)",
    responses=error_responses(401, 403, 404, 422),
)
def update_permit_type(
    project_id: uuid.UUID,
    permit_type: PermitType,
    body: PermitTypeConfigUpdate,
    user: CurrentUser,
    db: DB,
) -> PermitTypeConfigRead:
    raise not_implemented()


@router.get(
    "/zones/{zone_id}/ptw-profile",
    response_model=ZonePtwProfileRead,
    summary="Zone PTW profile (§3.2; created with PT-3 defaults)",
    responses=error_responses(401, 403, 404),
)
def get_zone_ptw_profile(zone_id: uuid.UUID, user: CurrentUser, db: DB) -> ZonePtwProfileRead:
    raise not_implemented()


@router.patch(
    "/zones/{zone_id}/ptw-profile",
    response_model=ZonePtwProfileRead,
    summary="Edit a zone PTW profile (capability 98; PROFILE_LOOSENING on movement areas)",
    responses=error_responses(401, 403, 404, 422),
)
def update_zone_ptw_profile(
    zone_id: uuid.UUID, body: ZonePtwProfileUpdate, user: CurrentUser, db: DB
) -> ZonePtwProfileRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/zone-adjacency",
    response_model=list[ZoneAdjacencyRead],
    summary="Zone adjacency table for SIMOPS distances (§3.3)",
    responses=error_responses(401, 403, 404),
)
def list_zone_adjacency(
    project_id: uuid.UUID, user: CurrentUser, db: DB
) -> list[ZoneAdjacencyRead]:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/zone-adjacency",
    response_model=ZoneAdjacencyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a zone pair (capability 98; unordered pair unique → 409)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_zone_adjacency(
    project_id: uuid.UUID, body: ZoneAdjacencyCreate, user: CurrentUser, db: DB
) -> ZoneAdjacencyRead:
    raise not_implemented()


@router.patch(
    "/zone-adjacency/{adjacency_id}",
    response_model=ZoneAdjacencyRead,
    summary="Edit a zone pair (capability 98)",
    responses=error_responses(401, 403, 404, 422),
)
def update_zone_adjacency(
    adjacency_id: uuid.UUID, body: ZoneAdjacencyUpdate, user: CurrentUser, db: DB
) -> ZoneAdjacencyRead:
    raise not_implemented()


@router.delete(
    "/zone-adjacency/{adjacency_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a zone pair (capability 98)",
    responses=error_responses(401, 403, 404),
)
def delete_zone_adjacency(adjacency_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/simops-rules",
    response_model=SimopsRuleList,
    summary="SIMOPS matrix of a project (SM-3 defaults SM-R01…R12 plus custom rules)",
    responses=error_responses(401, 403, 404),
)
def list_simops_rules(project_id: uuid.UUID, user: CurrentUser, db: DB) -> SimopsRuleList:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/simops-rules",
    response_model=SimopsRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a custom SIMOPS rule (capability 99)",
    responses=error_responses(401, 403, 404, 422),
)
def create_simops_rule(
    project_id: uuid.UUID, body: SimopsRuleCreate, user: CurrentUser, db: DB
) -> SimopsRuleRead:
    raise not_implemented()


@router.patch(
    "/simops-rules/{rule_id}",
    response_model=SimopsRuleRead,
    summary="Tighten a SIMOPS rule (capability 99; loosening a default → SIMOPS_RULE_LOCKED)",
    responses=error_responses(401, 403, 404, 422),
)
def update_simops_rule(
    rule_id: uuid.UUID, body: SimopsRuleUpdate, user: CurrentUser, db: DB
) -> SimopsRuleRead:
    raise not_implemented()


@router.delete(
    "/simops-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom SIMOPS rule (defaults R01–R12 → 422 SIMOPS_RULE_LOCKED, AC50)",
    responses=error_responses(401, 403, 404, 422),
)
def delete_simops_rule(rule_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    raise not_implemented()


@router.get(
    "/ptw/risk-matrix",
    response_model=RiskMatrixRead,
    summary="The 5×5 risk matrix with bands and acceptance authorities (JS-2, JS-7, §6.1)",
    responses=error_responses(401, 403),
)
def get_risk_matrix(user: CurrentUser) -> RiskMatrixRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/ptw-settings",
    response_model=PtwSettingsRead,
    summary="Phase 3 project settings (§3.17)",
    responses=error_responses(401, 403, 404),
)
def get_ptw_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> PtwSettingsRead:
    raise not_implemented()


@router.patch(
    "/projects/{project_id}/ptw-settings",
    response_model=PtwSettingsRead,
    summary="Update Phase 3 settings (HSE Manager, capability 99; Allowed ranges only; audited)",
    responses=error_responses(401, 403, 404, 422),
)
def update_ptw_settings(
    project_id: uuid.UUID, body: PtwSettingsUpdate, user: CurrentUser, db: DB
) -> PtwSettingsRead:
    raise not_implemented()
