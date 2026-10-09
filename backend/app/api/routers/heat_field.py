"""Acclimatisation plans, welfare checks, midday-ban patrols and exemptions, the heat-illness log,
season reports and the action panel (spec 6b-heat-stress §3.6–§3.12, AP, RS, MB, HI, HM)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.heat_enums import (
    BanExemptionStatus,
    HeatLogStatus,
    PatrolOutcome,
    PlanStatus,
    PlanType,
)
from app.schemas.heat import (
    BanExemptionCreate,
    BanExemptionPage,
    BanExemptionRead,
    HeatActionPanel,
    HeatLogPage,
    HeatLogRead,
    HeatReviewInput,
    PatrolCreate,
    PatrolPage,
    PatrolRead,
    PlanCancel,
    PlanDayConfirm,
    PlanPage,
    PlanRead,
    PriorExperienceInput,
    ReopenInput,
    RevokeInput,
    SeasonReportIssue,
    SeasonReportList,
    SeasonReportRead,
    VoidInput,
    WelfareCheckCreate,
    WelfareCheckPage,
    WelfareCheckRead,
)
from app.services.heat import ban, log, plans, report, welfare

router = APIRouter(tags=["heat-field"])

# ---- acclimatisation plans -----------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/acclimatisation-plans",
    response_model=PlanPage,
    summary="Acclimatisation plans (capability 166; type per P6b-3; C scope)",
    responses=error_responses(401, 403, 404),
)
def list_acclimatisation_plans(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[PlanStatus] | None, Query(alias="status")] = None,
    plan_type: PlanType | None = None,
    worker_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
) -> PlanPage:
    return plans.list_plans(
        db, user, project_id, pg.page, pg.page_size, status_, plan_type, worker_id, engagement_id
    )


@router.get(
    "/acclimatisation-plans/{plan_id}",
    response_model=PlanRead,
    summary="One plan (P6b-3 masking below 6a tier 2)",
    responses=error_responses(401, 403, 404),
)
def get_acclimatisation_plan(plan_id: uuid.UUID, user: CurrentUser, db: DB) -> PlanRead:
    return plans.read_plan(db, user, plan_id)


@router.post(
    "/acclimatisation-plans/{plan_id}/prior-experience",
    response_model=PlanRead,
    summary="Record prior heat experience (capability 172; AP-3; TOO_LATE_TO_CHANGE)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_prior_experience(
    plan_id: uuid.UUID, body: PriorExperienceInput, user: CurrentUser, db: DB
) -> PlanRead:
    return plans.prior_experience(db, user, plan_id, body)


@router.post(
    "/acclimatisation-plans/{plan_id}/days/{day_no}/confirm",
    response_model=PlanRead,
    summary="Confirm a worked plan day (capability 172; AP-8)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def confirm_plan_day(
    plan_id: uuid.UUID, day_no: int, body: PlanDayConfirm, user: CurrentUser, db: DB
) -> PlanRead:
    return plans.confirm_day(db, user, plan_id, day_no, body)


@router.post(
    "/acclimatisation-plans/{plan_id}/cancel",
    response_model=PlanRead,
    summary="Cancel a plan (capability 172; reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def cancel_acclimatisation_plan(
    plan_id: uuid.UUID, body: PlanCancel, user: CurrentUser, db: DB
) -> PlanRead:
    return plans.cancel(db, user, plan_id, body)


# ---- welfare checks ------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/heat-welfare-checks",
    response_model=WelfareCheckPage,
    summary="Heat welfare checks (capability 166)",
    responses=error_responses(401, 403, 404),
)
def list_welfare_checks(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    station_id: uuid.UUID | None = None,
    day: date | None = None,
) -> WelfareCheckPage:
    return welfare.list_checks(db, user, project_id, pg.page, pg.page_size, station_id, day)


@router.post(
    "/projects/{project_id}/heat-welfare-checks",
    response_model=WelfareCheckRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a welfare check (capability 169; RS-2, RS-3 critical fail → CA)",
    responses=error_responses(401, 403, 404, 422),
)
def create_welfare_check(
    project_id: uuid.UUID, body: WelfareCheckCreate, user: CurrentUser, db: DB
) -> WelfareCheckRead:
    return welfare.create_check(db, user, project_id, body)


@router.post(
    "/heat-welfare-checks/{check_id}/void",
    response_model=WelfareCheckRead,
    summary="Void a welfare check (capability 177; reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_welfare_check(
    check_id: uuid.UUID, body: VoidInput, user: CurrentUser, db: DB
) -> WelfareCheckRead:
    return welfare.void(db, user, check_id, body)


# ---- midday-ban patrols and exemptions -----------------------------------------------------------


@router.get(
    "/projects/{project_id}/ban-patrols",
    response_model=PatrolPage,
    summary="Midday-ban patrol checks (capability 166)",
    responses=error_responses(401, 403, 404),
)
def list_ban_patrols(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    zone_id: uuid.UUID | None = None,
    outcome: PatrolOutcome | None = None,
    day: date | None = None,
) -> PatrolPage:
    return ban.list_patrols(db, user, project_id, pg.page, pg.page_size, zone_id, outcome, day)


@router.post(
    "/projects/{project_id}/ban-patrols",
    response_model=PatrolRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a midday-ban patrol (capability 170; MB-1…MB-5)",
    responses=error_responses(401, 403, 404, 422),
)
def create_ban_patrol(
    project_id: uuid.UUID, body: PatrolCreate, user: CurrentUser, db: DB
) -> PatrolRead:
    return ban.create_patrol(db, user, project_id, body)


@router.post(
    "/ban-patrols/{patrol_id}/void",
    response_model=PatrolRead,
    summary="Void a patrol (capability 177; reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_ban_patrol(patrol_id: uuid.UUID, body: VoidInput, user: CurrentUser, db: DB) -> PatrolRead:
    return ban.void_patrol(db, user, patrol_id, body)


@router.get(
    "/projects/{project_id}/ban-exemptions",
    response_model=BanExemptionPage,
    summary="Non-permit midday-ban exemptions (capability 166)",
    responses=error_responses(401, 403, 404),
)
def list_ban_exemptions(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[BanExemptionStatus | None, Query(alias="status")] = None,
) -> BanExemptionPage:
    return ban.list_exemptions(db, user, project_id, pg.page, pg.page_size, status_)


@router.post(
    "/projects/{project_id}/ban-exemptions",
    response_model=BanExemptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a non-permit exemption (capability 171, HSE Manager; MB-5)",
    responses=error_responses(401, 403, 404, 422),
)
def create_ban_exemption(
    project_id: uuid.UUID, body: BanExemptionCreate, user: CurrentUser, db: DB
) -> BanExemptionRead:
    return ban.grant(db, user, project_id, body)


@router.post(
    "/ban-exemptions/{exemption_id}/revoke",
    response_model=BanExemptionRead,
    summary="Revoke an exemption (capability 171; reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def revoke_ban_exemption(
    exemption_id: uuid.UUID, body: RevokeInput, user: CurrentUser, db: DB
) -> BanExemptionRead:
    return ban.revoke(db, user, exemption_id, body)


# ---- heat-illness log ----------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/heat-illness-log",
    response_model=HeatLogPage,
    summary="Heat-illness log (capability 173; P6b-2; every read audited)",
    responses=error_responses(401, 403, 404),
)
def list_heat_illness_log(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[HeatLogStatus | None, Query(alias="status")] = None,
) -> HeatLogPage:
    return log.list_entries(db, user, project_id, pg.page, pg.page_size, status_)


@router.get(
    "/heat-illness-log/{entry_id}",
    response_model=HeatLogRead,
    summary="One heat-illness entry (capability 173)",
    responses=error_responses(401, 403, 404),
)
def get_heat_illness_entry(entry_id: uuid.UUID, user: CurrentUser, db: DB) -> HeatLogRead:
    return log.read_entry(db, user, entry_id)


@router.post(
    "/heat-illness-log/{entry_id}/review",
    response_model=HeatLogRead,
    summary="Review an entry (HC1–HC6; HSE Manager / Officer; HI-4, HI-5)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def review_heat_illness_entry(
    entry_id: uuid.UUID, body: HeatReviewInput, user: CurrentUser, db: DB
) -> HeatLogRead:
    return log.review(db, user, entry_id, body)


@router.post(
    "/heat-illness-log/{entry_id}/reopen",
    response_model=HeatLogRead,
    summary="Re-open a reviewed entry (reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def reopen_heat_illness_entry(
    entry_id: uuid.UUID, body: ReopenInput, user: CurrentUser, db: DB
) -> HeatLogRead:
    return log.reopen(db, user, entry_id, body)


# ---- action panel and season report --------------------------------------------------------------


@router.get(
    "/projects/{project_id}/heat-action-panel",
    response_model=HeatActionPanel,
    summary="6b action-panel items (capability 174, §8.2)",
    responses=error_responses(401, 403, 404),
)
def get_heat_action_panel(project_id: uuid.UUID, user: CurrentUser, db: DB) -> HeatActionPanel:
    return report.action_panel(db, user, project_id)


@router.get(
    "/projects/{project_id}/heat-season-reports",
    response_model=SeasonReportList,
    summary="Season report: live draft and issued revisions (capability 174; HM-4)",
    responses=error_responses(401, 403, 404),
)
def list_heat_season_reports(
    project_id: uuid.UUID, user: CurrentUser, db: DB, season_year: int | None = None
) -> SeasonReportList:
    return report.season_reports(db, user, project_id, season_year)


@router.post(
    "/projects/{project_id}/heat-season-reports",
    response_model=SeasonReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Issue (freeze) the season report; re-issue supersedes (capability 175)",
    responses=error_responses(401, 403, 404, 422),
)
def issue_heat_season_report(
    project_id: uuid.UUID, body: SeasonReportIssue, user: CurrentUser, db: DB
) -> SeasonReportRead:
    return report.issue(db, user, project_id, body)
