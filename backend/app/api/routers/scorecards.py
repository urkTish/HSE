"""Contractor HSE scorecards: reference lists, settings, profiles, cards and ranking, comments and
disputes, finalisation and re-issue, the watch list and the pre-qualification summary (spec
6g-scorecard-reports §3.1-§3.5, §4.1-§4.3, SP, SN, WR, SG, RK, DP, FN, WL).

There is no endpoint that accepts points or a score (SG-2): a PATCH on a line returns 405."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.scorecard_enums import (
    ScCardStatus,
    ScGrade,
    ScRemarkKind,
    ScRemarkStatus,
    ScScope,
    ScWatchStatus,
)
from app.schemas.scorecard import (
    ScCardPage,
    ScCardRead,
    ScFinaliseRequest,
    ScFinaliseResult,
    ScLineRead,
    ScPerformanceSummary,
    ScProfileCreate,
    ScProfilePage,
    ScProfileRead,
    ScProfileUpdate,
    ScRanking,
    ScReference,
    ScReissueRequest,
    ScRemarkCreate,
    ScRemarkPage,
    ScRemarkRead,
    ScRemarkResolve,
    ScSettingsRead,
    ScSettingsUpdate,
    ScSuspensionForm,
    ScWatchCreate,
    ScWatchPage,
    ScWatchRead,
    ScWatchTransition,
)
from app.services.scorecard import cards, config, remarks, watch

router = APIRouter(tags=["contractor-scorecards"])
MONTH = Query(pattern=r"^\d{4}-\d{2}$", description="yyyy-mm")


@router.get(
    "/scorecard-reference",
    response_model=ScReference,
    summary="6g reference lists with EN/AR labels (PL, SM, CP, GB, DR, WLL, RT, EP, MM)",
    responses=error_responses(401),
)
def get_scorecard_reference(user: CurrentUser) -> ScReference:
    return config.reference()


@router.get(
    "/projects/{project_id}/scorecard-settings",
    response_model=ScSettingsRead,
    summary="6g project settings (§3.9; 224 or 225)",
    responses=error_responses(401, 403, 404),
)
def get_scorecard_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> ScSettingsRead:
    return config.get_settings(db, user, project_id)


@router.patch(
    "/projects/{project_id}/scorecard-settings",
    response_model=ScSettingsRead,
    summary="Edit 6g settings (225, HSE Manager; 422 SETTING_OUT_OF_RANGE)",
    description="Editing `source_live_from` clears the confirmation (SN-5). Audited.",
    responses=error_responses(401, 403, 404, 422),
)
def update_scorecard_settings(
    project_id: uuid.UUID, body: ScSettingsUpdate, user: CurrentUser, db: DB
) -> ScSettingsRead:
    return config.update_settings(db, user, project_id, body)


@router.post(
    "/projects/{project_id}/scorecard-settings/confirm-sources",
    response_model=ScSettingsRead,
    summary="Confirm the prefilled source live-from map (225, SN-5)",
    responses=error_responses(401, 403, 404),
)
def confirm_scorecard_sources(project_id: uuid.UUID, user: CurrentUser, db: DB) -> ScSettingsRead:
    return config.confirm_sources(db, user, project_id)


@router.get(
    "/scorecard-profiles",
    response_model=ScProfilePage,
    summary="Scorecard profile versions (ORG and project copies)",
    responses=error_responses(401, 403),
)
def list_scorecard_profiles(
    user: CurrentUser, db: DB, pg: PageParams, project_id: uuid.UUID | None = None
) -> ScProfilePage:
    return config.list_profiles(db, user, project_id, pg.page, pg.page_size)


@router.post(
    "/scorecard-profiles",
    response_model=ScProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a Draft profile version (225; SP-1, SP-5)",
    responses=error_responses(401, 403, 404, 409),
)
def create_scorecard_profile(body: ScProfileCreate, user: CurrentUser, db: DB) -> ScProfileRead:
    return config.create_profile(db, user, body)


@router.get(
    "/scorecard-profiles/{profile_id}",
    response_model=ScProfileRead,
    summary="One profile version",
    responses=error_responses(401, 403, 404),
)
def get_scorecard_profile(profile_id: uuid.UUID, user: CurrentUser, db: DB) -> ScProfileRead:
    return config.get_profile(db, user, profile_id)


@router.patch(
    "/scorecard-profiles/{profile_id}",
    response_model=ScProfileRead,
    summary="Edit a Draft profile (225; versions are immutable once active)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_scorecard_profile(
    profile_id: uuid.UUID, body: ScProfileUpdate, user: CurrentUser, db: DB
) -> ScProfileRead:
    return config.update_profile(db, user, profile_id, body)


@router.post(
    "/scorecard-profiles/{profile_id}/activate",
    response_model=ScProfileRead,
    summary="Activate a Draft profile (225; SP-1 checks)",
    description="422 WEIGHTS_NOT_100, LAGGING_WEIGHT_OUT_OF_RANGE, CAP_REQUIRED, "
    "PROFILE_BACKDATED. Final cards keep the version they were computed with.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def activate_scorecard_profile(profile_id: uuid.UUID, user: CurrentUser, db: DB) -> ScProfileRead:
    return config.activate_profile(db, user, profile_id)


@router.get(
    "/projects/{project_id}/scorecards",
    response_model=ScCardPage,
    summary="Scorecard register (224)",
    description="Stored cards (Issued, Final, Superseded) filtered by month, engagement, grade, "
    "status, scope and cap. With `month` and `provisional=true`, cards of a month not yet issued "
    "are computed on read and flagged Provisional (SG-5). Reps see their C scope only (RK-2); "
    "site engineers Issued / Final; Viewer / Client Final.",
    responses=error_responses(401, 403, 404, 422),
)
def list_scorecards(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    pg: PageParams,
    month: Annotated[str | None, MONTH] = None,
    engagement_id: uuid.UUID | None = None,
    grade: ScGrade | None = None,
    status_: Annotated[ScCardStatus | None, Query(alias="status")] = None,
    scope: ScScope | None = None,
    cap: Annotated[str | None, Query(max_length=8)] = None,
    provisional: bool = False,
) -> ScCardPage:
    return cards.list_cards(
        db, user, project_id, month, engagement_id, grade, status_, scope, cap, provisional,
        pg.page, pg.page_size,
    )  # fmt: skip


@router.get(
    "/scorecards/{card_id}",
    response_model=ScCardRead,
    summary="One scorecard with pillars and lines (224; 404 outside the caller's scope)",
    responses=error_responses(401, 403, 404),
)
def get_scorecard(card_id: uuid.UUID, user: CurrentUser, db: DB) -> ScCardRead:
    return cards.read(db, user, card_id)


@router.get(
    "/scorecards/{card_id}/lines/{metric_code}",
    response_model=ScLineRead,
    summary="One scorecard line (read only; there is no write, SG-2)",
    responses=error_responses(401, 403, 404),
)
def get_scorecard_line(
    card_id: uuid.UUID, metric_code: str, user: CurrentUser, db: DB
) -> ScLineRead:
    return cards.line(db, user, card_id, metric_code)


@router.get(
    "/projects/{project_id}/scorecard-ranking",
    response_model=ScRanking,
    summary="Ranking of own cards for a month (RK-1, RK-3; reps: own scope + median, RK-2)",
    responses=error_responses(401, 403, 404, 422),
)
def get_scorecard_ranking(
    project_id: uuid.UUID, user: CurrentUser, db: DB, month: Annotated[str, MONTH]
) -> ScRanking:
    return cards.ranking(db, user, project_id, month)


@router.post(
    "/projects/{project_id}/scorecards/finalise",
    response_model=ScFinaliseResult,
    summary="Finalise a project-month (226; FN-1)",
    description="422 COMMENT_WINDOW_OPEN, DISPUTES_OPEN. Freezes every Issued card of the month, "
    "issues and distributes the SCPs (RP-8) and evaluates WL-1 and E25.",
    responses=error_responses(401, 403, 404, 422),
)
def finalise_scorecards(
    project_id: uuid.UUID, body: ScFinaliseRequest, user: CurrentUser, db: DB
) -> ScFinaliseResult:
    return cards.finalise(db, user, project_id, body.month)


@router.post(
    "/scorecards/{card_id}/reissue",
    response_model=ScCardRead,
    summary="Re-issue a Final card as a new revision (226; FN-4, reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def reissue_scorecard(
    card_id: uuid.UUID, body: ScReissueRequest, user: CurrentUser, db: DB
) -> ScCardRead:
    return cards.reissue(db, user, card_id, body.reason)


@router.post(
    "/scorecards/{card_id}/remarks",
    response_model=ScRemarkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on or dispute a card (227; DP-1, DP-2)",
    description="422 COMMENT_WINDOW_CLOSED, IDENTITY_IN_TEXT; P1-8 warning for ID-like numbers. "
    "HSE Officers add internal comments only (not visible to reps).",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_scorecard_remark(
    card_id: uuid.UUID, body: ScRemarkCreate, user: CurrentUser, db: DB
) -> ScRemarkRead:
    return remarks.create(db, user, card_id, body)


@router.get(
    "/projects/{project_id}/scorecard-remarks",
    response_model=ScRemarkPage,
    summary="Dispute and comment register (224; never for Viewer / Client, RK-4)",
    responses=error_responses(401, 403, 404),
)
def list_scorecard_remarks(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    pg: PageParams,
    month: Annotated[str | None, MONTH] = None,
    kind: ScRemarkKind | None = None,
    status_: Annotated[ScRemarkStatus | None, Query(alias="status")] = None,
    card_id: uuid.UUID | None = None,
) -> ScRemarkPage:
    return remarks.list_remarks(
        db, user, project_id, month, kind, status_, card_id, pg.page, pg.page_size
    )


@router.post(
    "/scorecard-remarks/{remark_id}/resolve",
    response_model=ScRemarkRead,
    summary="Resolve a dispute (228; upheld_metric_excluded 226 only; DP-3…DP-5)",
    description="422 CORRECTION_NOT_FOUND, CAP_NOT_EXCLUDABLE; 403 for exclusion without 226.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def resolve_scorecard_remark(
    remark_id: uuid.UUID, body: ScRemarkResolve, user: CurrentUser, db: DB
) -> ScRemarkRead:
    return remarks.resolve(db, user, remark_id, body)


@router.post(
    "/scorecard-remarks/{remark_id}/withdraw",
    response_model=ScRemarkRead,
    summary="Withdraw an open dispute (raiser only)",
    responses=error_responses(401, 403, 404, 409),
)
def withdraw_scorecard_remark(remark_id: uuid.UUID, user: CurrentUser, db: DB) -> ScRemarkRead:
    return remarks.withdraw(db, user, remark_id)


@router.get(
    "/projects/{project_id}/watch-list",
    response_model=ScWatchPage,
    summary="Watch-list register (224; Viewer / Client sees levels only, RK-4)",
    responses=error_responses(401, 403, 404),
)
def list_watch_list(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    pg: PageParams,
    status_: Annotated[ScWatchStatus | None, Query(alias="status")] = None,
) -> ScWatchPage:
    return watch.list_entries(db, user, project_id, status_, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/watch-list",
    response_model=ScWatchRead,
    status_code=status.HTTP_201_CREATED,
    summary="Open a watch-list entry manually (226; reason ≥ 20 chars; 422 WATCH_ENTRY_OPEN)",
    responses=error_responses(401, 403, 404, 422),
)
def open_watch_entry(
    project_id: uuid.UUID, body: ScWatchCreate, user: CurrentUser, db: DB
) -> ScWatchRead:
    return watch.open_manual(db, user, project_id, body)


@router.get(
    "/watch-list/{entry_id}",
    response_model=ScWatchRead,
    summary="One watch-list entry",
    responses=error_responses(401, 403, 404),
)
def get_watch_entry(entry_id: uuid.UUID, user: CurrentUser, db: DB) -> ScWatchRead:
    return watch.read(db, user, entry_id)


@router.post(
    "/watch-list/{entry_id}/transitions",
    response_model=ScWatchRead,
    summary="Confirm an escalation, submit / accept a PIP, record a decision, close (§4.3)",
    description="confirm_escalation, accept_pip, decide, close: 226. submit_pip: the "
    "engagement's rep or 226 (422 PIP_INCOMPLETE: ≥ 3 CAs with source `scorecard`, due ≤ 30 "
    "days, one at engineering control or higher).",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_watch_entry(
    entry_id: uuid.UUID, body: ScWatchTransition, user: CurrentUser, db: DB
) -> ScWatchRead:
    return watch.transition(db, user, entry_id, body)


@router.get(
    "/watch-list/{entry_id}/suspension-form",
    response_model=ScSuspensionForm,
    summary="Prefilled Phase 0 suspension form for a `suspend` decision (226; WL-5)",
    description="The platform never changes a contractor status: the HSE Manager submits the "
    "Phase 0 contractor transition at `submit_path`.",
    responses=error_responses(401, 403, 404, 409),
)
def get_suspension_form(entry_id: uuid.UUID, user: CurrentUser, db: DB) -> ScSuspensionForm:
    return watch.suspension_form(db, user, entry_id)


@router.get(
    "/contractors/{contractor_id}/performance-summary",
    response_model=ScPerformanceSummary,
    summary="Contractor performance summary (CPS; 226, WL-8)",
    responses=error_responses(401, 403, 404),
)
def get_performance_summary(
    contractor_id: uuid.UUID, user: CurrentUser, db: DB
) -> ScPerformanceSummary:
    return watch.performance_summary(db, user, contractor_id)
