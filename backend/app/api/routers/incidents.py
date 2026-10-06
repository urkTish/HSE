"""Incident register, injury cases, investigations, external notifications (spec 1-dashboard
§3.3-§3.5, §4.2, §5.2, §5.8)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses, not_implemented
from app.core.hse_enums import (
    Activity,
    AirsideFlag,
    CaseCategory,
    ClassificationStatus,
    ExternalBody,
    IncidentStatus,
    IncidentType,
    InvestigationLevel,
    Mechanism,
)
from app.schemas.incidents import (
    ClassificationConfirm,
    ExcludedCaseList,
    ExternalNotificationRead,
    ExternalNotificationRecord,
    IdNumberRead,
    IncidentCreate,
    IncidentPage,
    IncidentRead,
    IncidentTransitionRequest,
    IncidentUpdate,
    InjuryCaseCreate,
    InjuryCaseRead,
    InjuryCaseUpdate,
    InvestigationExtensionRequest,
    InvestigationRead,
    InvestigationUpdate,
)

router = APIRouter(tags=["incidents"])

IncidentSort = Literal["occurred_at", "-occurred_at", "ref", "-ref", "status"]


@router.get(
    "/projects/{project_id}/incidents",
    response_model=IncidentPage,
    summary="Incident register, de-identified (capability 31, scoped)",
    description="Voided incidents are listed only when `status=voided` is requested (AC26). "
    "No person names appear in list rows (P6).",
    responses=error_responses(401, 403, 404, 422),
)
def list_incidents(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[IncidentStatus] | None, Query(alias="status")] = None,
    incident_type: Annotated[list[IncidentType] | None, Query()] = None,
    case_category: Annotated[list[CaseCategory] | None, Query()] = None,
    classification_status: ClassificationStatus | None = None,
    site_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    zone_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    activity: Activity | None = None,
    mechanism: Mechanism | None = None,
    airside_flag: AirsideFlag | None = None,
    hipo: bool | None = None,
    late_report: bool | None = None,
    investigation_level: InvestigationLevel | None = None,
    investigation_overdue: bool | None = None,
    unclassified_over_hours: Annotated[
        int | None, Query(ge=1, description="Action panel: still Reported after N hours.")
    ] = None,
    notification_due: Annotated[
        bool | None, Query(description="Action panel: external notifications due/overdue.")
    ] = None,
    open_lti: Annotated[bool | None, Query(description="Has an LTI case without rtw_date.")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Ref/title search.")] = None,
    sort: IncidentSort = "-occurred_at",
) -> IncidentPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/incidents",
    response_model=IncidentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an incident draft (capability 25)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_incident(
    project_id: uuid.UUID, body: IncidentCreate, user: CurrentUser, db: DB
) -> IncidentRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/incidents/excluded-cases",
    response_model=ExcludedCaseList,
    summary="Cases/events listed but excluded from rates, with reasons (I-4, AC21)",
    responses=error_responses(401, 403, 404, 422),
)
def list_excluded_cases(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ExcludedCaseList:
    raise not_implemented()


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentRead,
    summary="Get an incident (cases shown de-identified; see /injury-cases/{id})",
    responses=error_responses(401, 403, 404),
)
def get_incident(incident_id: uuid.UUID, user: CurrentUser, db: DB) -> IncidentRead:
    raise not_implemented()


@router.patch(
    "/incidents/{incident_id}",
    response_model=IncidentRead,
    summary="Edit an incident",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_incident(
    incident_id: uuid.UUID, body: IncidentUpdate, user: CurrentUser, db: DB
) -> IncidentRead:
    raise not_implemented()


@router.delete(
    "/incidents/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft (creator only; reported incidents can only be voided, I-1)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_incident(incident_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    raise not_implemented()


@router.post(
    "/incidents/{incident_id}/transitions",
    response_model=IncidentRead,
    summary="Change incident status (§4.2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_incident(
    incident_id: uuid.UUID, body: IncidentTransitionRequest, user: CurrentUser, db: DB
) -> IncidentRead:
    raise not_implemented()


# ---- external notifications ------------------------------------------------------------------


@router.put(
    "/incidents/{incident_id}/external-notifications/{body}",
    response_model=ExternalNotificationRead,
    summary="Record that an external body was notified (tracking only, I-21)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_external_notification(
    incident_id: uuid.UUID,
    body: ExternalBody,
    payload: ExternalNotificationRecord,
    user: CurrentUser,
    db: DB,
) -> ExternalNotificationRead:
    raise not_implemented()


# ---- injury cases ------------------------------------------------------------------------------


@router.post(
    "/incidents/{incident_id}/injury-cases",
    response_model=InjuryCaseRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
    summary="Add an injured/ill person (category derived, provisional)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_injury_case(
    incident_id: uuid.UUID, body: InjuryCaseCreate, user: CurrentUser, db: DB
) -> InjuryCaseRead:
    raise not_implemented()


@router.get(
    "/injury-cases/{case_id}",
    response_model=InjuryCaseRead,
    response_model_exclude_unset=True,
    summary="Get an injury case (identity/medical field groups per capability 29/30; audited)",
    responses=error_responses(401, 403, 404),
)
def get_injury_case(
    case_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    as_of: Annotated[date | None, Query(description="Day counts at this date.")] = None,
) -> InjuryCaseRead:
    raise not_implemented()


@router.patch(
    "/injury-cases/{case_id}",
    response_model=InjuryCaseRead,
    response_model_exclude_unset=True,
    summary="Edit an injury case (re-derives the category, I-9)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_injury_case(
    case_id: uuid.UUID, body: InjuryCaseUpdate, user: CurrentUser, db: DB
) -> InjuryCaseRead:
    raise not_implemented()


@router.delete(
    "/injury-cases/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a case from a draft incident",
    responses=error_responses(401, 403, 404, 409),
)
def delete_injury_case(case_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    raise not_implemented()


@router.post(
    "/injury-cases/{case_id}/classification",
    response_model=InjuryCaseRead,
    response_model_exclude_unset=True,
    summary="Confirm (or override with justification) the case category (capability 26)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def confirm_case_classification(
    case_id: uuid.UUID, body: ClassificationConfirm, user: CurrentUser, db: DB
) -> InjuryCaseRead:
    raise not_implemented()


@router.get(
    "/injury-cases/{case_id}/id-number",
    response_model=IdNumberRead,
    summary="Reveal the full ID number (capability 29; privacy cases HSE Manager only; audited)",
    responses=error_responses(401, 403, 404),
)
def reveal_case_id_number(case_id: uuid.UUID, user: CurrentUser, db: DB) -> IdNumberRead:
    raise not_implemented()


# ---- investigation ---------------------------------------------------------------------------


@router.get(
    "/incidents/{incident_id}/investigation",
    response_model=InvestigationRead,
    summary="Get the investigation of an incident",
    responses=error_responses(401, 403, 404),
)
def get_investigation(incident_id: uuid.UUID, user: CurrentUser, db: DB) -> InvestigationRead:
    raise not_implemented()


@router.patch(
    "/incidents/{incident_id}/investigation",
    response_model=InvestigationRead,
    summary="Edit the investigation (lead/team, capability 27; level never below minimum)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_investigation(
    incident_id: uuid.UUID, body: InvestigationUpdate, user: CurrentUser, db: DB
) -> InvestigationRead:
    raise not_implemented()


@router.post(
    "/incidents/{incident_id}/investigation/extensions",
    response_model=InvestigationRead,
    summary="Extend the investigation due date (HSE Manager, reason)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def extend_investigation(
    incident_id: uuid.UUID, body: InvestigationExtensionRequest, user: CurrentUser, db: DB
) -> InvestigationRead:
    raise not_implemented()
