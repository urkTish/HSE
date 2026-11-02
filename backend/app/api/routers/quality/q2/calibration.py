"""Q2 routes: calibration and verification records, M&TE status override and label, range check
and out-of-tolerance reviews (spec 8-quality §C.4)."""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.api.routers.quality.q2.common import paper, with_warnings
from app.core.errors import error_responses
from app.core.quality.q2 import QCalRecordStatus, QOotStatus
from app.schemas.hse_common import ApiWarning
from app.schemas.quality.q0 import QMteRead
from app.schemas.quality.q2 import (
    QCalibrationCreate,
    QCalibrationDecide,
    QCalibrationPage,
    QCalibrationRead,
    QCalibrationUpdate,
    QMteLabelRead,
    QMteOverrideSet,
    QOotAccepted,
    QOotAcceptProposals,
    QOotClose,
    QOotItemDecide,
    QOotItemRead,
    QOotReviewListItem,
    QOotReviewRead,
)
from app.services.quality.q2 import calibration as cal

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/projects/{project_id}/quality/calibrations",
    response_model=QCalibrationPage,
    summary="Calibration records of the project",
    responses=E,
)
def q_list_calibrations(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[QCalRecordStatus | None, Query(alias="status")] = None,
) -> dict[str, Any]:
    return cal.list_page(db, user, project_id, pg.page, pg.page_size, status_)


@router.get(
    "/quality/mte/{mte_id}/calibrations",
    response_model=list[QCalibrationRead],
    summary="Calibration history of an instrument",
    responses=E,
)
def q_mte_calibrations(mte_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return cal.list_for_mte(db, user, mte_id)


@router.post(
    "/quality/mte/{mte_id}/calibrations",
    response_model=QCalibrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a calibration or verification (261)",
    responses=E,
)
def q_create_calibration(
    mte_id: uuid.UUID, body: QCalibrationCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    c, w = cal.create(db, user, mte_id, body.model_dump())
    return with_warnings(cal.read(db, c, user), w)


@router.get(
    "/quality/calibrations/{cal_id}",
    response_model=QCalibrationRead,
    summary="One calibration",
    responses=E,
)
def q_get_calibration(cal_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return cal.read(db, cal.get_cal(db, user, cal_id), user)


@router.patch(
    "/quality/calibrations/{cal_id}",
    response_model=QCalibrationRead,
    summary="Edit a draft calibration",
    responses=E,
)
def q_update_calibration(
    cal_id: uuid.UUID, body: QCalibrationUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    c, w = cal.update(db, user, cal_id, body.model_dump(exclude_unset=True))
    return with_warnings(cal.read(db, c, user), w)


@router.post(
    "/quality/calibrations/{cal_id}/decide",
    response_model=QCalibrationRead,
    summary="Accept or reject (262 + RPM calibration.accept)",
    responses=E,
)
def q_decide_calibration(
    cal_id: uuid.UUID, body: QCalibrationDecide, user: CurrentUser, db: DB
) -> dict[str, Any]:
    c, w = cal.decide(db, user, cal_id, body.decision, body.comment, paper(body))
    return with_warnings(cal.read(db, c, user), w)


@router.put(
    "/quality/mte/{mte_id}/manual-status",
    response_model=QMteRead,
    summary="Manual out of service / limited use (or clear)",
    responses=E,
)
def q_mte_manual_status(
    mte_id: uuid.UUID, body: QMteOverrideSet, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return cal.set_override(db, user, mte_id, body.status, body.reason)


@router.get(
    "/quality/mte/{mte_id}/label",
    response_model=QMteLabelRead,
    summary="Status label data (Q-CAL-05)",
    responses=E,
)
def q_mte_label(mte_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return cal.label_data(db, user, mte_id, False)


@router.post(
    "/quality/mte/{mte_id}/label",
    response_model=QMteLabelRead,
    summary="Mark the label printed",
    responses=E,
)
def q_mte_label_printed(mte_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return cal.label_data(db, user, mte_id, True)


@router.get(
    "/quality/mte/{mte_id}/range-check",
    response_model=list[ApiWarning],
    summary="Calibration points cover a range? (Q-CAL-07 CAL_RANGE_NOT_COVERED)",
    responses=E,
)
def q_mte_range_check(
    mte_id: uuid.UUID, lo: Decimal, hi: Decimal, user: CurrentUser, db: DB
) -> list[ApiWarning]:
    return cal.range_check_api(db, user, mte_id, lo, hi)


@router.get(
    "/projects/{project_id}/quality/oot-reviews",
    response_model=list[QOotReviewListItem],
    summary="Out-of-tolerance reviews",
    responses=E,
)
def q_list_oot(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    status_: Annotated[QOotStatus | None, Query(alias="status")] = None,
) -> list[dict[str, Any]]:
    return cal.list_reviews(db, user, project_id, status_)


@router.get(
    "/quality/oot-reviews/{review_id}",
    response_model=QOotReviewRead,
    summary="One OOT review with its items",
    responses=E,
)
def q_get_oot(review_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    r, m = cal.get_review(db, user, review_id)
    return cal.review_read(db, user, r, m)


@router.post(
    "/quality/oot-items/{item_id}/decision",
    response_model=QOotItemRead,
    summary="Decide one item (no_impact · recheck · ncr)",
    responses=E,
)
def q_oot_item(
    item_id: uuid.UUID, body: QOotItemDecide, user: CurrentUser, db: DB
) -> dict[str, Any]:
    i = cal.decide_item(db, user, item_id, body.model_dump())
    r, _m = cal.get_review(db, user, i.review_id)
    return cal.item_read(i, r.error_abs)


@router.post(
    "/quality/oot-reviews/{review_id}/accept-proposals",
    response_model=QOotAccepted,
    summary="Decide every proposed no_impact item with one justification",
    responses=E,
)
def q_oot_accept(
    review_id: uuid.UUID, body: QOotAcceptProposals, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return {"decided": cal.accept_proposals(db, user, review_id, body.justification)}


@router.post(
    "/quality/oot-reviews/{review_id}/close",
    response_model=QOotReviewRead,
    summary="Close (every item decided; RPM oot_review.decide)",
    responses=E,
)
def q_close_oot(review_id: uuid.UUID, body: QOotClose, user: CurrentUser, db: DB) -> dict[str, Any]:
    r = cal.close_review(db, user, review_id, body.comment, paper(body))
    r2, m = cal.get_review(db, user, r.id)
    return cal.review_read(db, user, r2, m)
