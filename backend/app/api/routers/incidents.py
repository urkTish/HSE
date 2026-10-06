"""Incident register, injury cases, investigations, external notifications (spec 1-dashboard
§3.3-§3.5, §4.2, §5.2, §5.8)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
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
from app.services import incidents as svc
from app.services import injury_cases as cases
from app.services import investigations as inv

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
    return svc.list_page(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        statuses=status_,
        incident_types=incident_type,
        case_categories=case_category,
        classification_status=classification_status,
        site_ids=site_id,
        zone_ids=zone_id,
        engagement_ids=engagement_id,
        include_subcontractors=include_subcontractors,
        activity=activity,
        mechanism=mechanism,
        airside_flag=airside_flag,
        hipo=hipo,
        late_report=late_report,
        investigation_level=investigation_level,
        investigation_overdue_=investigation_overdue,
        unclassified_over_hours=unclassified_over_hours,
        notification_due=notification_due,
        open_lti_=open_lti,
        date_from=date_from,
        date_to=date_to,
        q=q,
        sort=sort,
    )


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
    return svc.create(db, user, project_id, body)


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
    return svc.excluded_cases(db, user, project_id, date_from, date_to)


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentRead,
    summary="Get an incident (cases shown de-identified; see /injury-cases/{id})",
    responses=error_responses(401, 403, 404),
)
def get_incident(incident_id: uuid.UUID, user: CurrentUser, db: DB) -> IncidentRead:
    return svc.read(db, user, incident_id)


@router.patch(
    "/incidents/{incident_id}",
    response_model=IncidentRead,
    summary="Edit an incident",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_incident(
    incident_id: uuid.UUID, body: IncidentUpdate, user: CurrentUser, db: DB
) -> IncidentRead:
    return svc.update(db, user, incident_id, body)


@router.delete(
    "/incidents/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft (creator only; reported incidents can only be voided, I-1)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_incident(incident_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    svc.delete(db, user, incident_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/incidents/{incident_id}/transitions",
    response_model=IncidentRead,
    summary="Change incident status (§4.2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_incident(
    incident_id: uuid.UUID, body: IncidentTransitionRequest, user: CurrentUser, db: DB
) -> IncidentRead:
    return svc.transition(db, user, incident_id, body)


# ---- external notifications ----------------------------------------------------------------------


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
    return svc.record_notification(db, user, incident_id, body, payload)


# ---- injury cases --------------------------------------------------------------------------------


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
    return cases.create(db, user, incident_id, body)


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
    return cases.get(db, user, case_id, as_of)


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
    return cases.update(db, user, case_id, body)


@router.delete(
    "/injury-cases/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a case from a draft incident",
    responses=error_responses(401, 403, 404, 409),
)
def delete_injury_case(case_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    cases.delete(db, user, case_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    return cases.confirm(db, user, case_id, body)


@router.get(
    "/injury-cases/{case_id}/id-number",
    response_model=IdNumberRead,
    summary="Reveal the full ID number (capability 29; privacy cases HSE Manager only; audited)",
    responses=error_responses(401, 403, 404),
)
def reveal_case_id_number(case_id: uuid.UUID, user: CurrentUser, db: DB) -> IdNumberRead:
    return cases.reveal_id(db, user, case_id)


# ---- investigation -------------------------------------------------------------------------------


@router.get(
    "/incidents/{incident_id}/investigation",
    response_model=InvestigationRead,
    summary="Get the investigation of an incident",
    responses=error_responses(401, 403, 404),
)
def get_investigation(incident_id: uuid.UUID, user: CurrentUser, db: DB) -> InvestigationRead:
    return inv.get(db, user, incident_id)


@router.patch(
    "/incidents/{incident_id}/investigation",
    response_model=InvestigationRead,
    summary="Edit the investigation (lead/team, capability 27; level never below minimum)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_investigation(
    incident_id: uuid.UUID, body: InvestigationUpdate, user: CurrentUser, db: DB
) -> InvestigationRead:
    return inv.update(db, user, incident_id, body)


@router.post(
    "/incidents/{incident_id}/investigation/extensions",
    response_model=InvestigationRead,
    summary="Extend the investigation due date (HSE Manager, reason)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def extend_investigation(
    incident_id: uuid.UUID, body: InvestigationExtensionRequest, user: CurrentUser, db: DB
) -> InvestigationRead:
    return inv.extend(db, user, incident_id, body)
