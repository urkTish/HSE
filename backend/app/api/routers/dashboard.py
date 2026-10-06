"""Dashboard action panel, expiring items and saved filters (spec 1-dashboard §8.1, D-2)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUser
from app.api.kpi_params import KpiParams
from app.core.errors import error_responses
from app.schemas.dashboard import (
    ActionPanelResponse,
    DashboardFilters,
    DashboardPreferencesRead,
    ExpiringItemsResponse,
)
from app.services import dashboard as svc

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/action-panel",
    response_model=ActionPanelResponse,
    summary="Action panel counts with links to pre-filtered lists (§8.1 item 6)",
    description="Uses the /kpi filters (site, zone, contractor…); counts are evaluated at "
    "`as_of`. Exactly one project.",
    responses=error_responses(401, 403, 404, 422),
)
def get_action_panel(user: CurrentUser, db: DB, q: KpiParams) -> ActionPanelResponse:
    return svc.action_panel(db, user, q)


@router.get(
    "/expiring-items",
    response_model=ExpiringItemsResponse,
    summary="Items falling due soon or overdue (CAs, investigations, notifications, inspections)",
    responses=error_responses(401, 403, 404, 422),
)
def get_expiring_items(
    user: CurrentUser,
    db: DB,
    project_id: uuid.UUID,
    within_days: Annotated[int, Query(ge=0, le=90)] = 14,
    include_overdue: bool = True,
    as_of: date | None = None,
) -> ExpiringItemsResponse:
    return svc.expiring_items(db, user, project_id, within_days, include_overdue, as_of)


@router.get(
    "/preferences",
    response_model=DashboardPreferencesRead,
    summary="My saved dashboard filters",
    responses=error_responses(401, 403),
)
def get_dashboard_preferences(user: CurrentUser, db: DB) -> DashboardPreferencesRead:
    return svc.get_preferences(db, user)


@router.put(
    "/preferences",
    response_model=DashboardPreferencesRead,
    summary="Save my dashboard filters",
    responses=error_responses(401, 403, 422),
)
def put_dashboard_preferences(
    body: DashboardFilters, user: CurrentUser, db: DB
) -> DashboardPreferencesRead:
    return svc.put_preferences(db, user, body)
