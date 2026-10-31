"""Q2 routes: WPS / PQR, welders, WPQs, the weld log, NDT lots, repair rates and the continuity
board (spec 8-quality §C.6)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, PageParams
from app.api.routers.quality.q2.common import paper, with_warnings
from app.core.errors import error_responses
from app.core.quality.q2 import QWeldStatus
from app.models.quality.q2 import QWeld
from app.schemas.quality.q2 import (
    QContinuityRow,
    QDecisionBody,
    QLotSummary,
    QPqrCreate,
    QPqrRead,
    QReasonBody,
    QRepairRate,
    QWeldCreate,
    QWelderCreate,
    QWelderRead,
    QWelderUpdate,
    QWeldLot,
    QWeldLotItem,
    QWeldNdt,
    QWeldPage,
    QWeldPick,
    QWeldRead,
    QWeldRepair,
    QWeldSelect,
    QWeldSign,
    QWeldVisual,
    QWpqConfirm,
    QWpqCreate,
    QWpqRead,
    QWpsCreate,
    QWpsRead,
    QWpsUpdate,
)
from app.services.quality import common as qc
from app.services.quality.q2 import welding as w

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/projects/{project_id}/quality/wps",
    response_model=list[QWpsRead],
    summary="WPS register",
    responses=E,
)
def q_list_wps(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return w.wps_list(db, user, project_id)


@router.post(
    "/projects/{project_id}/quality/wps",
    response_model=QWpsRead,
    status_code=status.HTTP_201_CREATED,
    summary="New WPS draft (259; construction)",
    responses=E,
)
def q_create_wps(
    project_id: uuid.UUID, body: QWpsCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return w.wps_read(db, user, w.wps_create(db, user, project_id, body.model_dump()))


@router.patch(
    "/quality/wps/{wps_id}", response_model=QWpsRead, summary="Edit a WPS draft", responses=E
)
def q_update_wps(wps_id: uuid.UUID, body: QWpsUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return w.wps_read(db, user, w.wps_update(db, user, wps_id, body.model_dump(exclude_unset=True)))


@router.post(
    "/quality/wps/{wps_id}/submit",
    response_model=QWpsRead,
    summary="Submit for approval",
    responses=E,
)
def q_submit_wps(wps_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return w.wps_read(db, user, w.wps_submit(db, user, wps_id))


@router.post(
    "/quality/wps/{wps_id}/approve",
    response_model=QWpsRead,
    summary="Approve (260 + RPM wps.approve)",
    responses=E,
)
def q_approve_wps(
    wps_id: uuid.UUID, body: QDecisionBody, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return w.wps_read(
        db, user, w.wps_approve(db, user, wps_id, body.decision, body.comment, paper(body))
    )


@router.post(
    "/quality/wps/{wps_id}/revise",
    response_model=QWpsRead,
    status_code=status.HTTP_201_CREATED,
    summary="New revision of an approved WPS",
    responses=E,
)
def q_revise_wps(wps_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return w.wps_read(db, user, w.wps_revise(db, user, wps_id))


@router.post(
    "/quality/wps/{wps_id}/withdraw",
    response_model=QWpsRead,
    summary="Withdraw (260, reason)",
    responses=E,
)
def q_withdraw_wps(
    wps_id: uuid.UUID, body: QReasonBody, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return w.wps_read(db, user, w.wps_withdraw(db, user, wps_id, body.reason))


@router.get(
    "/projects/{project_id}/quality/pqrs",
    response_model=list[QPqrRead],
    summary="PQR register",
    responses=E,
)
def q_list_pqrs(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return w.pqr_list(db, user, project_id)


@router.post(
    "/projects/{project_id}/quality/pqrs",
    response_model=QPqrRead,
    status_code=status.HTTP_201_CREATED,
    summary="New PQR (259)",
    responses=E,
)
def q_create_pqr(
    project_id: uuid.UUID, body: QPqrCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    x, warn = w.pqr_create(db, user, project_id, body.model_dump())
    return with_warnings(w.pqr_read(db, user, x), warn)


@router.post(
    "/quality/pqrs/{pqr_id}/approve",
    response_model=QPqrRead,
    summary="Approve (260 + RPM pqr.approve)",
    responses=E,
)
def q_approve_pqr(
    pqr_id: uuid.UUID, body: QDecisionBody, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return w.pqr_read(db, user, w.pqr_approve(db, user, pqr_id, body.decision, body.comment))


@router.get(
    "/projects/{project_id}/quality/welders",
    response_model=list[QWelderRead],
    summary="Welders (Phase 2 workers with a stamp)",
    responses=E,
)
def q_list_welders(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return w.welders_list(db, user, project_id)


@router.post(
    "/projects/{project_id}/quality/welders",
    response_model=QWelderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a welder (259)",
    responses=E,
)
def q_create_welder(
    project_id: uuid.UUID, body: QWelderCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return w.welder_read(db, w.welder_create(db, user, project_id, body.model_dump()))


@router.patch(
    "/quality/welders/{welder_id}",
    response_model=QWelderRead,
    summary="Activate or deactivate a welder",
    responses=E,
)
def q_update_welder(
    welder_id: uuid.UUID, body: QWelderUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return w.welder_read(db, w.welder_status(db, user, welder_id, body.status))


@router.get(
    "/projects/{project_id}/quality/wpqs",
    response_model=list[QWpqRead],
    summary="Welder qualifications",
    responses=E,
)
def q_list_wpqs(
    project_id: uuid.UUID, user: CurrentUser, db: DB, welder_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    return w.wpq_list(db, user, project_id, welder_id)


@router.post(
    "/projects/{project_id}/quality/wpqs",
    response_model=QWpqRead,
    status_code=status.HTTP_201_CREATED,
    summary="New WPQ draft (259)",
    responses=E,
)
def q_create_wpq(
    project_id: uuid.UUID, body: QWpqCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    x = w.wpq_create(db, user, project_id, body.model_dump())
    return w.wpq_read(db, user, x, qc.project_day(qc.get_project(db, user, project_id)))


def _wpq(db: Any, user: Any, x: Any) -> dict[str, Any]:
    return w.wpq_read(db, user, x, qc.project_day(qc.get_project(db, user, x.project_id)))


@router.post(
    "/quality/wpqs/{wpq_id}/approve",
    response_model=QWpqRead,
    summary="Approve (260 + RPM wpq.approve) → Active",
    responses=E,
)
def q_approve_wpq(
    wpq_id: uuid.UUID, body: QDecisionBody, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _wpq(db, user, w.wpq_approve(db, user, wpq_id, body.decision, body.comment, paper(body)))


@router.post(
    "/quality/wpqs/{wpq_id}/revoke",
    response_model=QWpqRead,
    summary="Revoke (260, reason)",
    responses=E,
)
def q_revoke_wpq(wpq_id: uuid.UUID, body: QReasonBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _wpq(db, user, w.wpq_revoke(db, user, wpq_id, body.reason))


@router.post(
    "/quality/wpqs/{wpq_id}/confirm",
    response_model=QWpqRead,
    summary="Six-monthly confirmation (ISO 9606-1 mode)",
    responses=E,
)
def q_confirm_wpq(
    wpq_id: uuid.UUID, body: QWpqConfirm, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _wpq(db, user, w.wpq_confirm(db, user, wpq_id, body.date))


@router.get(
    "/projects/{project_id}/quality/welds",
    response_model=QWeldPage,
    summary="Weld log",
    responses=E,
)
def q_list_welds(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    lot_code: Annotated[str | None, Query(max_length=40)] = None,
    status_: Annotated[list[QWeldStatus] | None, Query(alias="status")] = None,
    stamp: Annotated[str | None, Query(max_length=10)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    return w.weld_list(db, user, project_id, pg.page, pg.page_size, lot_code, status_, stamp, q)


@router.post(
    "/projects/{project_id}/quality/welds",
    response_model=QWeldRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a weld (Q-WLD-01, -02)",
    responses=E,
)
def q_create_weld(
    project_id: uuid.UUID, body: QWeldCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    x, warn = w.weld_create(db, user, project_id, body.model_dump())
    return with_warnings(w.weld_read(db, user, x), warn)


@router.get("/quality/welds/{weld_id}", response_model=QWeldRead, summary="One weld", responses=E)
def q_get_weld(weld_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return w.weld_read(db, user, w.get_weld(db, user, weld_id))


@router.post(
    "/quality/welds/{weld_id}/visual",
    response_model=QWeldRead,
    summary="Visual result",
    responses=E,
)
def q_weld_visual(
    weld_id: uuid.UUID, body: QWeldVisual, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return w.weld_read(db, user, w.weld_visual(db, user, weld_id, body.model_dump()))


@router.post(
    "/quality/welds/{weld_id}/lot",
    response_model=QWeldRead,
    summary="Assign to an NDT lot",
    responses=E,
)
def q_weld_lot(weld_id: uuid.UUID, body: QWeldLot, user: CurrentUser, db: DB) -> dict[str, Any]:
    return w.weld_read(db, user, w.assign_lot(db, user, weld_id, body.model_dump()))


@router.post(
    "/quality/welds/{weld_id}/select",
    response_model=QWeldRead,
    summary="Select for NDT",
    responses=E,
)
def q_weld_select(
    weld_id: uuid.UUID, body: QWeldSelect, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return w.weld_read(db, user, w.weld_select(db, user, weld_id, body.reason))


@router.post(
    "/quality/welds/{weld_id}/ndt",
    response_model=QWeldRead,
    summary="NDT result (Q-WLD-05 progressive; Q-WLD-08 competence)",
    responses=E,
)
def q_weld_ndt(weld_id: uuid.UUID, body: QWeldNdt, user: CurrentUser, db: DB) -> dict[str, Any]:
    x, warn, extra = w.weld_ndt(db, user, weld_id, body.model_dump())
    return with_warnings(w.weld_read(db, user, x), warn, **extra)


@router.post(
    "/quality/welds/{weld_id}/repair",
    response_model=QWeldRead,
    summary="Repair R1 / R2 (Q-WLD-06 SIGNOFF_REQUIRED)",
    responses=E,
)
def q_weld_repair(
    weld_id: uuid.UUID, body: QWeldRepair, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return w.weld_read(db, user, w.weld_repair(db, user, weld_id, body.model_dump()))


@router.post(
    "/quality/welds/{weld_id}/sign-repair2",
    response_model=QWeldRead,
    summary="Approve a second repair (RPM weld.repair2_approve)",
    responses=E,
)
def q_weld_sign(weld_id: uuid.UUID, body: QWeldSign, user: CurrentUser, db: DB) -> dict[str, Any]:
    return w.weld_read(
        db, user, w.weld_sign_repair2(db, user, weld_id, body.decision, body.comment, paper(body))
    )


@router.post(
    "/quality/welds/{weld_id}/void", response_model=QWeldRead, summary="Void (244)", responses=E
)
def q_weld_void(weld_id: uuid.UUID, body: QReasonBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    return w.weld_read(db, user, w.weld_void(db, user, weld_id, body.reason))


@router.get(
    "/projects/{project_id}/quality/weld-lots",
    response_model=list[QWeldLotItem],
    summary="NDT lots of the project",
    responses=E,
)
def q_weld_lots(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    project = qc.get_project(db, user, project_id)
    w._view(user, project.id)
    rows = db.execute(
        select(QWeld.lot_code, func.count())
        .where(
            QWeld.project_id == project.id,
            QWeld.lot_code.is_not(None),
            QWeld.status != QWeldStatus.voided,
        )
        .group_by(QWeld.lot_code)
        .order_by(QWeld.lot_code)
    ).all()
    return [{"lot_code": r[0], "welds": r[1]} for r in rows]


@router.get(
    "/projects/{project_id}/quality/weld-lots/{lot_code}",
    response_model=QLotSummary,
    summary="Lot NDT % and shortfall (Q-WLD-04)",
    responses=E,
)
def q_weld_lot_summary(
    project_id: uuid.UUID, lot_code: str, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return w.lot_summary(db, user, project_id, lot_code)


@router.get(
    "/projects/{project_id}/quality/weld-lots/{lot_code}/pick",
    response_model=list[QWeldPick],
    summary="Proposed random selection covering every welder",
    responses=E,
)
def q_weld_lot_pick(
    project_id: uuid.UUID, lot_code: str, user: CurrentUser, db: DB
) -> list[dict[str, Any]]:
    return w.pick_welds(db, user, project_id, lot_code)


@router.get(
    "/projects/{project_id}/quality/weld-repair-rates",
    response_model=list[QRepairRate],
    summary="Repair rate per welder (Q-WLD-07)",
    responses=E,
)
def q_weld_rates(
    project_id: uuid.UUID, user: CurrentUser, db: DB, days: Annotated[int, Query(ge=7, le=730)] = 90
) -> list[dict[str, Any]]:
    return w.rates_api(db, user, project_id, days)


@router.get(
    "/projects/{project_id}/quality/welder-continuity",
    response_model=list[QContinuityRow],
    summary="Continuity board (welder × process, days left)",
    responses=E,
)
def q_welder_continuity(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return w.continuity_board(db, user, project_id)
