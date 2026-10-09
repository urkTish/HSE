"""Emergency preparedness — plan and organisation (spec 6c-emergency-drills §3.1–§3.7, §3.15,
§6.2, §8): reference lists, settings, ERP revisions with scenarios, assembly points, contacts,
zone emergency profiles, the emergency roster, rescue teams, coverage, the emergency board, the
action panel and the permit emergency-information pre-fill."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.emergency_enums import DrillShift, EmergencyRole, TeamType
from app.core.errors import error_responses
from app.schemas.emergency import (
    ApCreate,
    ApPage,
    ApRead,
    ApUpdate,
    ContactCreate,
    ContactPage,
    ContactRead,
    ContactUpdate,
    CoverageList,
    EmergencyActionPanel,
    EmergencyBoard,
    EmergencyInfo,
    EmergencyReference,
    EmergencySettingsRead,
    EmergencySettingsUpdate,
    ErpCreate,
    ErpPage,
    ErpRead,
    ErpTransition,
    ErpUpdate,
    RosterCreate,
    RosterCreated,
    RosterEnd,
    RosterPage,
    RosterRead,
    TeamCreate,
    TeamPage,
    TeamRead,
    TeamUpdate,
    ZoneProfileInput,
    ZoneProfileList,
    ZoneProfileRead,
)
from app.services.emergency import board, config, erp, org

router = APIRouter(tags=["emergency-plan"])


@router.get(
    "/emergency-reference",
    response_model=EmergencyReference,
    summary="6c reference lists ES, DT, AG, EOR, EAT, EC, DC, FC, MS, UR with EN/AR labels",
    responses=error_responses(401),
)
def get_emergency_reference(user: CurrentUser) -> EmergencyReference:
    return config.reference()


@router.get(
    "/projects/{project_id}/emergency-settings",
    response_model=EmergencySettingsRead,
    summary="6c project settings (§3.15, capability 178)",
    responses=error_responses(401, 403, 404),
)
def get_emergency_settings(
    project_id: uuid.UUID, user: CurrentUser, db: DB
) -> EmergencySettingsRead:
    return config.read_settings(db, user, project_id)


@router.patch(
    "/projects/{project_id}/emergency-settings",
    response_model=EmergencySettingsRead,
    summary="Edit 6c settings; set emergency_ptw_enforcement_from (180; ER-2, ER-9)",
    responses=error_responses(401, 403, 404, 422),
)
def update_emergency_settings(
    project_id: uuid.UUID, body: EmergencySettingsUpdate, user: CurrentUser, db: DB
) -> EmergencySettingsRead:
    return config.update_settings(db, user, project_id, body)


# ---- ERP -----------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/erps",
    response_model=ErpPage,
    summary="ERP revisions, newest first (178)",
    responses=error_responses(401, 403, 404),
)
def list_erps(project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB) -> ErpPage:
    return erp.list_erps(db, user, project_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/erps",
    response_model=ErpRead,
    status_code=status.HTTP_201_CREATED,
    summary="New Draft revision, copied from the current one (179)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_erp(project_id: uuid.UUID, body: ErpCreate, user: CurrentUser, db: DB) -> ErpRead:
    return erp.create_erp(db, user, project_id, body)


@router.get(
    "/erps/{erp_id}",
    response_model=ErpRead,
    summary="One ERP revision",
    responses=error_responses(401, 403, 404),
)
def get_erp(erp_id: uuid.UUID, user: CurrentUser, db: DB) -> ErpRead:
    return erp.read_erp(db, user, erp_id)


@router.patch(
    "/erps/{erp_id}",
    response_model=ErpRead,
    summary="Edit a Draft revision and its scenarios (179; ER-4, ER-5)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_erp(erp_id: uuid.UUID, body: ErpUpdate, user: CurrentUser, db: DB) -> ErpRead:
    return erp.update_erp(db, user, erp_id, body)


@router.post(
    "/erps/{erp_id}/transitions",
    response_model=ErpRead,
    summary="Submit / return / approve (§4.1; ER-3 ERP_INCOMPLETE, SOD_CONFLICT)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_erp(erp_id: uuid.UUID, body: ErpTransition, user: CurrentUser, db: DB) -> ErpRead:
    return erp.transition_erp(db, user, erp_id, body)


# ---- assembly points, contacts, zone profiles ----------------------------------------------------


@router.get(
    "/projects/{project_id}/assembly-points",
    response_model=ApPage,
    summary="Assembly points (178)",
    responses=error_responses(401, 403, 404),
)
def list_assembly_points(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    site_id: uuid.UUID | None = None,
) -> ApPage:
    return erp.list_aps(db, user, project_id, site_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/assembly-points",
    response_model=ApRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an assembly point with its MP sticker (179; ER-6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_assembly_point(
    project_id: uuid.UUID, body: ApCreate, user: CurrentUser, db: DB
) -> ApRead:
    return erp.create_ap(db, user, project_id, body)


@router.patch(
    "/assembly-points/{ap_id}",
    response_model=ApRead,
    summary="Edit / deactivate an assembly point (179; ZONE_WITHOUT_ASSEMBLY_POINT)",
    responses=error_responses(401, 403, 404, 422),
)
def update_assembly_point(ap_id: uuid.UUID, body: ApUpdate, user: CurrentUser, db: DB) -> ApRead:
    return erp.update_ap(db, user, ap_id, body)


@router.get(
    "/projects/{project_id}/emergency-contacts",
    response_model=ContactPage,
    summary="Emergency contact directory (178)",
    responses=error_responses(401, 403, 404),
)
def list_emergency_contacts(
    project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> ContactPage:
    return erp.list_contacts(db, user, project_id, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/emergency-contacts",
    response_model=ContactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an emergency contact (179)",
    responses=error_responses(401, 403, 404, 422),
)
def create_emergency_contact(
    project_id: uuid.UUID, body: ContactCreate, user: CurrentUser, db: DB
) -> ContactRead:
    return erp.create_contact(db, user, project_id, body)


@router.patch(
    "/emergency-contacts/{contact_id}",
    response_model=ContactRead,
    summary="Edit / deactivate a contact (179)",
    responses=error_responses(401, 403, 404, 422),
)
def update_emergency_contact(
    contact_id: uuid.UUID, body: ContactUpdate, user: CurrentUser, db: DB
) -> ContactRead:
    return erp.update_contact(db, user, contact_id, body)


@router.get(
    "/projects/{project_id}/zone-emergency-profiles",
    response_model=ZoneProfileList,
    summary="Zone emergency profiles, defaults filled in (178)",
    responses=error_responses(401, 403, 404),
)
def list_zone_emergency_profiles(
    project_id: uuid.UUID, user: CurrentUser, db: DB
) -> ZoneProfileList:
    return erp.list_profiles(db, user, project_id)


@router.put(
    "/zones/{zone_id}/emergency-profile",
    response_model=ZoneProfileRead,
    summary="Set a zone emergency profile (179; only raise above the defaults)",
    responses=error_responses(401, 403, 404, 422),
)
def put_zone_emergency_profile(
    zone_id: uuid.UUID, body: ZoneProfileInput, user: CurrentUser, db: DB
) -> ZoneProfileRead:
    return erp.put_profile(db, user, zone_id, body)


# ---- roster and rescue teams ---------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/emergency-roster",
    response_model=RosterPage,
    summary="Emergency roster with today's qualification (178; names visible, P6c-2)",
    responses=error_responses(401, 403, 404),
)
def list_emergency_roster(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    site_id: uuid.UUID | None = None,
    role: EmergencyRole | None = None,
    active_only: bool = True,
) -> RosterPage:
    return org.list_roster(db, user, project_id, site_id, role, active_only, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/emergency-roster",
    response_model=RosterCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Add a roster assignment (181; EO-1, EO-2)",
    responses=error_responses(401, 403, 404, 422),
)
def create_roster_assignment(
    project_id: uuid.UUID, body: RosterCreate, user: CurrentUser, db: DB
) -> RosterCreated:
    return org.create_assignment(db, user, project_id, body)


@router.post(
    "/emergency-roster/{assignment_id}/end",
    response_model=RosterRead,
    summary="End a roster assignment (181)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def end_roster_assignment(
    assignment_id: uuid.UUID, body: RosterEnd, user: CurrentUser, db: DB
) -> RosterRead:
    return org.end_assignment(db, user, assignment_id, body)


@router.get(
    "/projects/{project_id}/rescue-teams",
    response_model=TeamPage,
    summary="Rescue teams with readiness (178; RT-2)",
    responses=error_responses(401, 403, 404),
)
def list_rescue_teams(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    team_type: TeamType | None = None,
    as_of: date | None = None,
) -> TeamPage:
    return org.list_teams(db, user, project_id, team_type, as_of, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/rescue-teams",
    response_model=TeamRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a rescue team (181; RT-1 ALREADY_IN_TEAM)",
    responses=error_responses(401, 403, 404, 422),
)
def create_rescue_team(
    project_id: uuid.UUID, body: TeamCreate, user: CurrentUser, db: DB
) -> TeamRead:
    return org.create_team(db, user, project_id, body)


@router.get(
    "/rescue-teams/{team_id}",
    response_model=TeamRead,
    summary="One rescue team with readiness at a date",
    responses=error_responses(401, 403, 404),
)
def get_rescue_team(
    team_id: uuid.UUID, user: CurrentUser, db: DB, as_of: date | None = None
) -> TeamRead:
    return org.read_team(db, user, team_id, as_of)


@router.patch(
    "/rescue-teams/{team_id}",
    response_model=TeamRead,
    summary="Edit members / equipment / status (181)",
    responses=error_responses(401, 403, 404, 422),
)
def update_rescue_team(team_id: uuid.UUID, body: TeamUpdate, user: CurrentUser, db: DB) -> TeamRead:
    return org.update_team(db, user, team_id, body)


@router.get(
    "/projects/{project_id}/emergency-coverage",
    response_model=CoverageList,
    summary="Coverage per site, shift and date (§6.2; 178)",
    responses=error_responses(401, 403, 404, 422),
)
def get_emergency_coverage(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    date_from: date,
    date_to: date | None = None,
    site_id: uuid.UUID | None = None,
    shift: DrillShift | None = None,
) -> CoverageList:
    return org.coverage(db, user, project_id, date_from, date_to, site_id, shift)


# ---- board, action panel, permit pre-fill --------------------------------------------------------


@router.get(
    "/projects/{project_id}/emergency-board",
    response_model=EmergencyBoard,
    summary="Live emergency band: ERP, events, musters, current-shift coverage, gaps, drills due",
    responses=error_responses(401, 403, 404),
)
def get_emergency_board(project_id: uuid.UUID, user: CurrentUser, db: DB) -> EmergencyBoard:
    return board.board(db, user, project_id)


@router.get(
    "/projects/{project_id}/emergency-action-panel",
    response_model=EmergencyActionPanel,
    summary="6c action-panel items (§8.2; capability 189)",
    responses=error_responses(401, 403, 404),
)
def get_emergency_action_panel(
    project_id: uuid.UUID, user: CurrentUser, db: DB
) -> EmergencyActionPanel:
    return board.action_panel(db, user, project_id)


@router.get(
    "/projects/{project_id}/emergency-info",
    response_model=EmergencyInfo,
    summary="Pre-fill for a permit's emergency_info (PE-6): primary AP and priority-1 numbers",
    responses=error_responses(401, 403, 404),
)
def get_emergency_info(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    zone_ids: Annotated[list[uuid.UUID], Query()],
) -> EmergencyInfo:
    return board.emergency_info(db, user, project_id, zone_ids)
