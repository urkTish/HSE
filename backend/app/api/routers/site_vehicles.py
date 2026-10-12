"""Option 7b Site Vehicle & Plant Readiness — **Prototype** (spec 7b-fleet-driver v2.0): settings,
reference lists, site vehicles and readiness, driver / operator authorisations, daily pre-use
checks and the minimal journey-plan form. KPIs K-138…K-140 are on GET /kpi/site-vehicles.

Every endpoint except settings and the reference lists answers 422 SITE_VEHICLES_NOT_LIVE while
the project's `site_vehicles_from` is null. The Viewer / Client gets aggregates only (the summary
and the KPIs); registers answer 403 for that role (P7b-1)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.site_vehicle_enums import (
    SiteVehAuthStatus,
    SiteVehCheckSource,
    SiteVehDocsFilter,
    SiteVehDriverGroup,
    SiteVehJourneyStatus,
    SiteVehReadiness,
    SiteVehUseClass,
)
from app.schemas.site_vehicle import (
    SiteVehAuthCreate,
    SiteVehAuthPage,
    SiteVehAuthPrefill,
    SiteVehAuthRead,
    SiteVehAuthTransition,
    SiteVehAuthUpdate,
    SiteVehCheckCreate,
    SiteVehCheckForm,
    SiteVehCheckPage,
    SiteVehCheckRead,
    SiteVehClearHold,
    SiteVehCreate,
    SiteVehJourneyArrive,
    SiteVehJourneyCancel,
    SiteVehJourneyCreate,
    SiteVehJourneyHint,
    SiteVehJourneyHintInput,
    SiteVehJourneyPage,
    SiteVehJourneyRead,
    SiteVehMissingRead,
    SiteVehPage,
    SiteVehRead,
    SiteVehReference,
    SiteVehSettingsRead,
    SiteVehSettingsUpdate,
    SiteVehSummary,
    SiteVehUpdate,
    SiteVehWithdraw,
)
from app.services.site_vehicle import (
    authorisations,
    checks,
    journeys,
    reference,
    settings,
    vehicles,
)

router = APIRouter(tags=["site-vehicles"])
NOT_LIVE = " 422 SITE_VEHICLES_NOT_LIVE while site_vehicles_from is null."
PERSONAL = (
    " Driver names follow capability 46 (WA-19); a Site engineer sees authorisation status only "
    "(`redacted`, P7b-1)."
)


# ---- settings and reference ----------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/site-vehicle-settings",
    response_model=SiteVehSettingsRead,
    summary="7b settings (§3.5; capability 233 or 237)",
    responses=error_responses(401, 403, 404),
)
def get_site_vehicle_settings(
    project_id: uuid.UUID, user: CurrentUser, db: DB
) -> SiteVehSettingsRead:
    return settings.get_settings(db, user, project_id)


@router.patch(
    "/projects/{project_id}/site-vehicle-settings",
    response_model=SiteVehSettingsRead,
    summary="Update 7b settings (capability 237, HSE Manager; SETTING_OUT_OF_RANGE)",
    description="Setting site_vehicles_from switches 7b on (and adds the Phase 5 courses DEF-DRV "
    "and BUS-DRV when missing); null switches it off.",
    responses=error_responses(401, 403, 404, 422),
)
def update_site_vehicle_settings(
    project_id: uuid.UUID, body: SiteVehSettingsUpdate, user: CurrentUser, db: DB
) -> SiteVehSettingsRead:
    return settings.update_settings(db, user, project_id, body)


@router.get(
    "/site-vehicles/reference",
    response_model=SiteVehReference,
    summary="7b reference lists SU, DG and EN/AR labels of states and warnings (§3.6)",
    responses=error_responses(401),
)
def get_site_vehicle_reference(user: CurrentUser) -> SiteVehReference:
    del user
    return reference.reference()


# ---- site vehicles -------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/site-vehicles",
    response_model=SiteVehPage,
    summary="Site vehicles & plant with readiness (capability 233; not Viewer)",
    description="Readiness is derived for today (§4.1). Contractor HSE Reps list their own "
    "engagement's vehicles (SV-4)." + NOT_LIVE,
    responses=error_responses(401, 403, 404, 422),
)
def list_site_vehicles(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    readiness: Annotated[list[SiteVehReadiness] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    use_class: Annotated[list[SiteVehUseClass] | None, Query()] = None,
    driver_group: Annotated[list[SiteVehDriverGroup] | None, Query()] = None,
    documents: SiteVehDocsFilter | None = None,
    phase4_linked: bool | None = None,
    q: Annotated[str | None, Query(max_length=60)] = None,
) -> SiteVehPage:
    return vehicles.list_vehicles(
        db, user, project_id, readiness, engagement_id, use_class, driver_group, documents,
        phase4_linked, q, pg.page, pg.page_size,
    )  # fmt: skip


@router.get(
    "/projects/{project_id}/site-vehicles/summary",
    response_model=SiteVehSummary,
    summary="Site vehicle aggregates for today (capability 233, Viewer included)",
    responses=error_responses(401, 403, 404, 422),
)
def site_vehicle_summary(project_id: uuid.UUID, user: CurrentUser, db: DB) -> SiteVehSummary:
    return vehicles.summary(db, user, project_id)


@router.post(
    "/projects/{project_id}/site-vehicles",
    response_model=SiteVehRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a site vehicle or plant (capability 234; reps: own engagement)",
    description="Creates the Phase 2 vehicle with the 7b fields (BD7b-1). 422 "
    "OPERATING_CARD_REQUIRED; Phase 2 duplicate plate / VIN → 409 DUPLICATE_VALUE." + NOT_LIVE,
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_site_vehicle(
    project_id: uuid.UUID, body: SiteVehCreate, user: CurrentUser, db: DB
) -> SiteVehRead:
    return vehicles.create_vehicle(db, user, project_id, body)


@router.get(
    "/site-vehicles/{vehicle_id}",
    response_model=SiteVehRead,
    summary="A site vehicle with readiness, documents, Phase 4 link and today's check",
    responses=error_responses(401, 403, 404, 422),
)
def get_site_vehicle(vehicle_id: uuid.UUID, user: CurrentUser, db: DB) -> SiteVehRead:
    return vehicles.read_vehicle(db, user, vehicle_id)


@router.patch(
    "/site-vehicles/{vehicle_id}",
    response_model=SiteVehRead,
    summary="Edit 7b fields / documents, or enrol a Phase 2 vehicle (capability 234)",
    description="Changing a document date clears the verification (SV-4). 7b never edits "
    "Phase 4 status (SV-3)." + NOT_LIVE,
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_site_vehicle(
    vehicle_id: uuid.UUID, body: SiteVehUpdate, user: CurrentUser, db: DB
) -> SiteVehRead:
    return vehicles.update_vehicle(db, user, vehicle_id, body)


@router.post(
    "/site-vehicles/{vehicle_id}/verify-documents",
    response_model=SiteVehRead,
    summary="Verify the document scans (capability 234; HSE Officer / Manager, not reps)",
    responses=error_responses(401, 403, 404, 422),
)
def verify_site_vehicle_documents(vehicle_id: uuid.UUID, user: CurrentUser, db: DB) -> SiteVehRead:
    return vehicles.verify_documents(db, user, vehicle_id)


@router.post(
    "/site-vehicles/{vehicle_id}/clear-hold",
    response_model=SiteVehRead,
    summary="Clear the defect hold (capability 234; repair note + passing check, PU-3)",
    description="409 VEHICLE_DEFECT_HOLD without a passing check completed after the hold.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def clear_site_vehicle_hold(
    vehicle_id: uuid.UUID, body: SiteVehClearHold, user: CurrentUser, db: DB
) -> SiteVehRead:
    return vehicles.clear_hold(db, user, vehicle_id, body)


@router.post(
    "/site-vehicles/{vehicle_id}/withdraw",
    response_model=SiteVehRead,
    summary="Withdraw a site vehicle (capability 234; Phase 2 status withdrawn)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def withdraw_site_vehicle(
    vehicle_id: uuid.UUID, body: SiteVehWithdraw, user: CurrentUser, db: DB
) -> SiteVehRead:
    return vehicles.withdraw(db, user, vehicle_id, body)


# ---- driver / operator authorisations ----------------------------------------------------------


@router.get(
    "/projects/{project_id}/driver-authorisations",
    response_model=SiteVehAuthPage,
    summary="Driver / operator authorisations (capability 233; not Viewer)",
    description=PERSONAL + NOT_LIVE,
    responses=error_responses(401, 403, 404, 422),
)
def list_driver_authorisations(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[SiteVehAuthStatus] | None, Query(alias="status")] = None,
    group: Annotated[list[SiteVehDriverGroup] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    worker_id: uuid.UUID | None = None,
    expiring_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
) -> SiteVehAuthPage:
    return authorisations.list_auths(
        db, user, project_id, status_, group, engagement_id, worker_id, expiring_within_days,
        pg.page, pg.page_size,
    )  # fmt: skip


@router.get(
    "/projects/{project_id}/driver-authorisations/prefill",
    response_model=SiteVehAuthPrefill,
    summary="Licence prefill from the worker's ADP (capability 235)",
    responses=error_responses(401, 403, 404, 422),
)
def prefill_driver_authorisation(
    project_id: uuid.UUID, worker_id: uuid.UUID, user: CurrentUser, db: DB
) -> SiteVehAuthPrefill:
    return authorisations.prefill(db, user, project_id, worker_id)


@router.post(
    "/projects/{project_id}/driver-authorisations",
    response_model=SiteVehAuthRead,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a driver / operator authorisation → Draft (capability 235; reps propose)",
    description="One live authorisation per worker (409 DUPLICATE_VALUE). 422 "
    "LICENCE_CLASS_NOT_COVERING, ASSESSMENT_TOO_OLD. Hooks are evaluated at once (DA-2); "
    "warning HOOK_NOT_MET_WARN." + NOT_LIVE,
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_driver_authorisation(
    project_id: uuid.UUID, body: SiteVehAuthCreate, user: CurrentUser, db: DB
) -> SiteVehAuthRead:
    return authorisations.create_auth(db, user, project_id, body)


@router.get(
    "/driver-authorisations/{auth_id}",
    response_model=SiteVehAuthRead,
    summary="A driver / operator authorisation",
    description=PERSONAL,
    responses=error_responses(401, 403, 404, 422),
)
def get_driver_authorisation(auth_id: uuid.UUID, user: CurrentUser, db: DB) -> SiteVehAuthRead:
    return authorisations.read_auth(db, user, auth_id)


@router.patch(
    "/driver-authorisations/{auth_id}",
    response_model=SiteVehAuthRead,
    summary="Edit a Draft authorisation (capability 235)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_driver_authorisation(
    auth_id: uuid.UUID, body: SiteVehAuthUpdate, user: CurrentUser, db: DB
) -> SiteVehAuthRead:
    return authorisations.update_auth(db, user, auth_id, body)


@router.post(
    "/driver-authorisations/{auth_id}/transition",
    response_model=SiteVehAuthRead,
    summary="Activate, suspend, reinstate or revoke (capability 235; not reps; §4.2)",
    description="Activation re-checks DA-1 and the hooks: policy block → 422 HOOK_NOT_MET; warn "
    "→ warning HOOK_NOT_MET_WARN. Suspend needs a reason ≥ 20 characters.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_driver_authorisation(
    auth_id: uuid.UUID, body: SiteVehAuthTransition, user: CurrentUser, db: DB
) -> SiteVehAuthRead:
    return authorisations.transition(db, user, auth_id, body)


# ---- pre-use checks ------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/pre-use-checks",
    response_model=SiteVehCheckPage,
    summary="Pre-use checks (capability 233; not Viewer)",
    description=PERSONAL + NOT_LIVE,
    responses=error_responses(401, 403, 404, 422),
)
def list_pre_use_checks(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    date_from: date | None = None,
    date_to: date | None = None,
    vehicle_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    passed: bool | None = None,
    source: SiteVehCheckSource | None = None,
    driver_authorised: bool | None = None,
) -> SiteVehCheckPage:
    return checks.list_checks(
        db, user, project_id, date_from, date_to, vehicle_id, engagement_id, passed, source,
        driver_authorised, pg.page, pg.page_size,
    )  # fmt: skip


@router.get(
    "/projects/{project_id}/pre-use-checks/form",
    response_model=SiteVehCheckForm,
    summary="Template and today's state for one vehicle (capability 236)",
    responses=error_responses(401, 403, 404, 422),
)
def pre_use_check_form(
    project_id: uuid.UUID, vehicle_id: uuid.UUID, user: CurrentUser, db: DB
) -> SiteVehCheckForm:
    return checks.form(db, user, project_id, vehicle_id)


@router.get(
    "/projects/{project_id}/pre-use-checks/missing",
    response_model=SiteVehMissingRead,
    summary="Required vehicles without a check for a day, per contractor (PU-1)",
    responses=error_responses(401, 403, 404, 422),
)
def missing_pre_use_checks(
    project_id: uuid.UUID, user: CurrentUser, db: DB, day: date | None = None
) -> SiteVehMissingRead:
    return checks.missing(db, user, project_id, day)


@router.post(
    "/projects/{project_id}/pre-use-checks",
    response_model=SiteVehCheckRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a pre-use check (capability 236; PU-1…PU-6)",
    description="6d answer rules apply. A failed critical item puts a vehicle without a Phase 4 "
    "link on defect hold with a finding and a CA (source site_vehicle); a Phase 4-linked item "
    "gets a Phase 4 Defect (source pre_use_check, category A). 422 PRE_USE_CHECK_EXISTS, "
    "DRIVER_NOT_AUTHORISED (policy block); warnings DRIVER_NOT_AUTHORISED_WARN, "
    "VEHICLE_DOCS_UNVERIFIED." + NOT_LIVE,
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_pre_use_check(
    project_id: uuid.UUID, body: SiteVehCheckCreate, user: CurrentUser, db: DB
) -> SiteVehCheckRead:
    return checks.create_check(db, user, project_id, body)


@router.get(
    "/pre-use-checks/{check_id}",
    response_model=SiteVehCheckRead,
    summary="A pre-use check with findings, CA and Phase 4 defect links",
    responses=error_responses(401, 403, 404, 422),
)
def get_pre_use_check(check_id: uuid.UUID, user: CurrentUser, db: DB) -> SiteVehCheckRead:
    return checks.read_check(db, user, check_id)


# ---- journey plans (prototype) -----------------------------------------------------------------


@router.post(
    "/projects/{project_id}/journey-plans/hint",
    response_model=SiteVehJourneyHint,
    summary="Is a journey plan recommended? (JM-1 hint only)",
    responses=error_responses(401, 403, 404, 422),
)
def journey_plan_hint(
    project_id: uuid.UUID, body: SiteVehJourneyHintInput, user: CurrentUser, db: DB
) -> SiteVehJourneyHint:
    return journeys.hint(db, user, project_id, body)


@router.get(
    "/projects/{project_id}/journey-plans",
    response_model=SiteVehJourneyPage,
    summary="Journey plans (capability 233; not Viewer); `overdue` is a display flag",
    responses=error_responses(401, 403, 404, 422),
)
def list_journey_plans(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[SiteVehJourneyStatus] | None, Query(alias="status")] = None,
    overdue: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    vehicle_id: uuid.UUID | None = None,
) -> SiteVehJourneyPage:
    return journeys.list_plans(
        db, user, project_id, status_, overdue, date_from, date_to, vehicle_id, pg.page,
        pg.page_size,
    )  # fmt: skip


@router.post(
    "/projects/{project_id}/journey-plans",
    response_model=SiteVehJourneyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a journey plan (capability 236; JM-2)",
    description="409 VEHICLE_NOT_READY; 422 PASSENGERS_EXCEED_SEATS, JOURNEY_TIMES_INVALID, "
    "JOURNEY_CONTACT_IS_DRIVER, DRIVER_NOT_AUTHORISED (policy block); warnings "
    "DRIVER_NOT_AUTHORISED_WARN, JOURNEY_PLAN_RECOMMENDED." + NOT_LIVE,
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_journey_plan(
    project_id: uuid.UUID, body: SiteVehJourneyCreate, user: CurrentUser, db: DB
) -> SiteVehJourneyRead:
    return journeys.create_plan(db, user, project_id, body)


@router.get(
    "/journey-plans/{plan_id}",
    response_model=SiteVehJourneyRead,
    summary="A journey plan",
    responses=error_responses(401, 403, 404, 422),
)
def get_journey_plan(plan_id: uuid.UUID, user: CurrentUser, db: DB) -> SiteVehJourneyRead:
    return journeys.read_plan(db, user, plan_id)


@router.post(
    "/journey-plans/{plan_id}/arrive",
    response_model=SiteVehJourneyRead,
    summary='"Mark arrived" (capability 236)',
    responses=error_responses(401, 403, 404, 409, 422),
)
def arrive_journey_plan(
    plan_id: uuid.UUID, body: SiteVehJourneyArrive, user: CurrentUser, db: DB
) -> SiteVehJourneyRead:
    return journeys.arrive(db, user, plan_id, body)


@router.post(
    "/journey-plans/{plan_id}/cancel",
    response_model=SiteVehJourneyRead,
    summary="Cancel a Planned journey plan (capability 236)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def cancel_journey_plan(
    plan_id: uuid.UUID, body: SiteVehJourneyCancel, user: CurrentUser, db: DB
) -> SiteVehJourneyRead:
    return journeys.cancel(db, user, plan_id, body)
