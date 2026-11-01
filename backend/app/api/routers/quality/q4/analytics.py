"""Q4 HTTP routes: supplier evaluations and scorecards, the Quality KPI page with targets and
work value, and SPC charts (spec 8-quality §E.3–§E.7)."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser
from app.core.errors import error_responses
from app.kpi import quality as qk
from app.schemas.quality.q4 import (
    Q4ContractorScore,
    Q4KpiPage,
    Q4KpiTargetInput,
    Q4KpiTargetRead,
    Q4ScoreRead,
    Q4SevAction,
    Q4SevCreate,
    Q4SevRead,
    Q4SevUpdate,
    Q4SpcInput,
    Q4SpcRead,
    Q4WorkValueInput,
    Q4WorkValueRead,
)
from app.services.quality.q4 import analytics, spc, suppliers

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)
P = "/projects/{project_id}/quality"


def _crit(body: Any) -> dict[str, Any]:
    d: dict[str, Any] = body.model_dump(exclude_unset=True)
    if "criteria" in d and d["criteria"] is not None:
        d["criteria"] = [
            {"criterion": c["criterion"], "weight": str(c["weight"]), "score": str(c["score"])}
            for c in d["criteria"]
        ]
    return d


@router.get(
    P + "/supplier-evaluations",
    response_model=list[Q4SevRead],
    summary="Supplier evaluations (§E.3)",
    responses=E,
)
def q4_list_sev(
    project_id: uuid.UUID, user: CurrentUser, db: DB, supplier_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    return suppliers.list_evaluations(db, user, project_id, supplier_id)


@router.post(
    P + "/supplier-evaluations",
    response_model=Q4SevRead,
    status_code=status.HTTP_201_CREATED,
    summary="New supplier evaluation (278)",
    responses=E,
)
def q4_create_sev(
    project_id: uuid.UUID, body: Q4SevCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return suppliers.create(db, user, project_id, _crit(body))


@router.get(
    "/quality/supplier-evaluations/{eid}",
    response_model=Q4SevRead,
    summary="One evaluation",
    responses=E,
)
def q4_get_sev(eid: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return suppliers.read(db, user, eid)


@router.patch(
    "/quality/supplier-evaluations/{eid}",
    response_model=Q4SevRead,
    summary="Edit a Draft evaluation",
    responses=E,
)
def q4_update_sev(eid: uuid.UUID, body: Q4SevUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return suppliers.update(db, user, eid, _crit(body))


@router.post(
    "/quality/supplier-evaluations/{eid}/transition",
    response_model=Q4SevRead,
    summary="Submit, approve (279 + RPM), return or cancel",
    responses=E,
)
def q4_sev_transition(
    eid: uuid.UUID, body: Q4SevAction, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return suppliers.transition(db, user, eid, body.action, body.model_dump())


@router.get(
    P + "/supplier-scores",
    response_model=list[Q4ScoreRead],
    summary="Supplier quality scorecards (Q-SUP-03; org-wide)",
    responses=E,
)
def q4_scores(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    period_start: date | None = None,
    supplier_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    return suppliers.list_scores(db, user, project_id, period_start, supplier_id)


@router.post(
    P + "/supplier-scores/recompute",
    response_model=list[Q4ScoreRead],
    summary="Recompute the provisional scores of the current period (278)",
    responses=E,
)
def q4_scores_recompute(
    project_id: uuid.UUID, user: CurrentUser, db: DB, day: date | None = None
) -> list[dict[str, Any]]:
    return suppliers.recompute(db, user, project_id, day)


@router.get(
    "/quality/contractor-quality/{contractor_id}",
    response_model=list[Q4ContractorScore],
    summary="Quality score of suppliers linked to a contractor (information only, Q-SUP-05)",
    responses=E,
)
def q4_contractor_score(
    contractor_id: uuid.UUID, user: CurrentUser, db: DB
) -> list[dict[str, Any]]:
    return suppliers.contractor_score(db, user, contractor_id)


@router.get(
    P + "/kpis",
    response_model=Q4KpiPage,
    summary="Quality KPIs K-141…K-169 with targets, warnings and charts (403 for scope N)",
    responses=E,
)
def q4_kpis(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    date_from: date | None = None,
    date_to: date | None = None,
    site_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    test_type: str | None = None,
) -> dict[str, Any]:
    flt = qk.QFilter(
        site_ids=frozenset({site_id}) if site_id else None,
        zone_id=zone_id,
        engagement_ids=frozenset({engagement_id}) if engagement_id else None,
        supplier_id=supplier_id,
        test_type=test_type,
    )
    return analytics.kpis(db, user, project_id, date_from, date_to, flt)


@router.get(
    P + "/kpi-targets",
    response_model=list[Q4KpiTargetRead],
    summary="Quality objectives",
    responses=E,
)
def q4_targets(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[Any]:
    return analytics.list_targets(db, user, project_id)


@router.put(
    P + "/kpi-targets",
    response_model=Q4KpiTargetRead,
    summary="Set a KPI target (239)",
    responses=E,
)
def q4_set_target(project_id: uuid.UUID, body: Q4KpiTargetInput, user: CurrentUser, db: DB) -> Any:
    return analytics.set_target(db, user, project_id, body.model_dump())


@router.get(
    P + "/work-value",
    response_model=list[Q4WorkValueRead],
    summary="Monthly work value behind COPQ % (239)",
    responses=E,
)
def q4_work_value(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[Any]:
    return analytics.list_work_value(db, user, project_id)


@router.put(
    P + "/work-value",
    response_model=Q4WorkValueRead,
    summary="Set a month's work value (239)",
    responses=E,
)
def q4_set_work_value(
    project_id: uuid.UUID, body: Q4WorkValueInput, user: CurrentUser, db: DB
) -> Any:
    return analytics.set_work_value(db, user, project_id, body.model_dump())


@router.get(
    P + "/spc-charts", response_model=list[Q4SpcRead], summary="SPC charts (§E.5)", responses=E
)
def q4_spc_list(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return spc.list_charts(db, user, project_id)


@router.post(
    P + "/spc-charts",
    response_model=Q4SpcRead,
    status_code=status.HTTP_201_CREATED,
    summary="New SPC chart (240)",
    responses=E,
)
def q4_spc_create(
    project_id: uuid.UUID, body: Q4SpcInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return spc.save_chart(db, user, project_id, body.model_dump(exclude_unset=True))


@router.get(
    "/quality/spc-charts/{chart_id}",
    response_model=Q4SpcRead,
    summary="One SPC chart with limits, signals and capability",
    responses=E,
)
def q4_spc_get(
    chart_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    return spc.read_chart(db, user, chart_id, date_from, date_to)


@router.patch(
    P + "/spc-charts/{chart_id}",
    response_model=Q4SpcRead,
    summary="Edit an SPC chart (240)",
    responses=E,
)
def q4_spc_update(
    project_id: uuid.UUID, chart_id: uuid.UUID, body: Q4SpcInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return spc.save_chart(db, user, project_id, body.model_dump(exclude_unset=True), chart_id)
