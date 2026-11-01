"""Q2 routes: material approval requests, material inspections on delivery and quarantine
(spec 8-quality §C.3)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.api.routers.quality.q2.common import paper, with_warnings
from app.core.errors import error_responses
from app.core.quality.q2 import (
    QMarStatus,
    QMaterialCategory,
    QMirResult,
    QMirStatus,
    QQuarantineStatus,
)
from app.schemas.quality.q2 import (
    QMarCreate,
    QMarDecide,
    QMarPage,
    QMarRead,
    QMarUpdate,
    QMirChecklistSave,
    QMirChecklistTemplate,
    QMirCreate,
    QMirDecide,
    QMirPage,
    QMirQuarantine,
    QMirRead,
    QMirUpdate,
    QQuarantineCreate,
    QQuarantineDispose,
    QQuarantineLink,
    QQuarantinePage,
    QQuarantineRead,
    QReasonBody,
)
from app.services.quality.q2 import materials as m

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)
Q100 = Annotated[str | None, Query(max_length=100)]


# ---- MAR ----------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/mars",
    response_model=QMarPage,
    summary="Material approval requests",
    responses=E,
)
def q_list_mars(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QMarStatus] | None, Query(alias="status")] = None,
    category: QMaterialCategory | None = None,
    q: Q100 = None,
) -> dict[str, Any]:
    return m.mar_list(db, user, project_id, pg.page, pg.page_size, status_, category, q)


@router.post(
    "/projects/{project_id}/quality/mars",
    response_model=QMarRead,
    status_code=status.HTTP_201_CREATED,
    summary="New MAR draft (255; construction)",
    responses=E,
)
def q_create_mar(
    project_id: uuid.UUID, body: QMarCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    x, w = m.mar_create(db, user, project_id, body.model_dump())
    return with_warnings(m.mar_read(db, user, x), w)


@router.get(
    "/quality/mars/{mar_id}", response_model=QMarRead, summary="One MAR revision", responses=E
)
def q_get_mar(mar_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return m.mar_read(db, user, m.get_mar(db, user, mar_id))


@router.patch(
    "/quality/mars/{mar_id}", response_model=QMarRead, summary="Edit a MAR draft", responses=E
)
def q_update_mar(mar_id: uuid.UUID, body: QMarUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    x, w = m.mar_update(db, user, mar_id, body.model_dump(exclude_unset=True))
    return with_warnings(m.mar_read(db, user, x), w)


@router.post(
    "/quality/mars/{mar_id}/submit",
    response_model=QMarRead,
    summary="Submit (Q-MAT-01 MAR_INCOMPLETE)",
    responses=E,
)
def q_submit_mar(mar_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    x, w = m.mar_submit(db, user, mar_id)
    return with_warnings(m.mar_read(db, user, x), w)


@router.post(
    "/quality/mars/{mar_id}/decide",
    response_model=QMarRead,
    summary="Approval code A–D (256 + RPM mar.approve)",
    responses=E,
)
def q_decide_mar(mar_id: uuid.UUID, body: QMarDecide, user: CurrentUser, db: DB) -> dict[str, Any]:
    x = m.mar_decide(
        db, user, mar_id, body.approval_code, body.comment, body.accept_deviations, paper(body)
    )
    return m.mar_read(db, user, x)


@router.post(
    "/quality/mars/{mar_id}/resubmit",
    response_model=QMarRead,
    status_code=status.HTTP_201_CREATED,
    summary="New revision after code C",
    responses=E,
)
def q_resubmit_mar(mar_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return m.mar_read(db, user, m.mar_resubmit(db, user, mar_id))


@router.post(
    "/quality/mars/{mar_id}/withdraw",
    response_model=QMarRead,
    summary="Withdraw an approved MAR (239, reason)",
    responses=E,
)
def q_withdraw_mar(
    mar_id: uuid.UUID, body: QReasonBody, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return m.mar_read(db, user, m.mar_withdraw(db, user, mar_id, body.reason))


# ---- MIR ----------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/mirs",
    response_model=QMirPage,
    summary="Material inspections on delivery",
    responses=E,
)
def q_list_mirs(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QMirStatus] | None, Query(alias="status")] = None,
    result: QMirResult | None = None,
    q: Q100 = None,
) -> dict[str, Any]:
    return m.mir_list(db, user, project_id, pg.page, pg.page_size, status_, result, q)


@router.post(
    "/projects/{project_id}/quality/mirs",
    response_model=QMirRead,
    status_code=status.HTTP_201_CREATED,
    summary="New MIR draft (255)",
    responses=E,
)
def q_create_mir(
    project_id: uuid.UUID, body: QMirCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    x, w = m.mir_create(db, user, project_id, body.model_dump(exclude_unset=True))
    return with_warnings(m.mir_read(db, user, x), w)


@router.get("/quality/mirs/{mir_id}", response_model=QMirRead, summary="One MIR", responses=E)
def q_get_mir(mir_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    x = m.get_mir(db, user, mir_id)
    return with_warnings(m.mir_read(db, user, x), m._heat_warning(x))


@router.patch(
    "/quality/mirs/{mir_id}", response_model=QMirRead, summary="Edit a MIR draft", responses=E
)
def q_update_mir(mir_id: uuid.UUID, body: QMirUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    x, w = m.mir_update(db, user, mir_id, body.model_dump(exclude_unset=True))
    return with_warnings(m.mir_read(db, user, x), w)


@router.post(
    "/quality/mirs/{mir_id}/submit",
    response_model=QMirRead,
    summary="Submit (Q-MAT-03 MAR_NOT_APPROVED)",
    responses=E,
)
def q_submit_mir(mir_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    x, w = m.mir_submit(db, user, mir_id)
    return with_warnings(m.mir_read(db, user, x), w)


@router.post(
    "/quality/mirs/{mir_id}/decide",
    response_model=QMirRead,
    summary="Decide (256 + RPM mir.decide; Q-MAT-04, -05)",
    responses=E,
)
def q_decide_mir(mir_id: uuid.UUID, body: QMirDecide, user: CurrentUser, db: DB) -> dict[str, Any]:
    x, w = m.mir_decide(db, user, mir_id, body.model_dump(exclude={"paper"}), paper(body))
    return with_warnings(m.mir_read(db, user, x), w)


@router.put(
    "/quality/mirs/{mir_id}/checklist",
    response_model=QMirRead,
    summary="Record the delivery checklist (6d engine, owner q_mir; §C.3.2)",
    responses=E,
)
def q_mir_checklist(
    mir_id: uuid.UUID, body: QMirChecklistSave, user: CurrentUser, db: DB
) -> dict[str, Any]:
    x, w = m.mir_checklist(db, user, mir_id, body.model_dump(exclude={"answers"}), body.answers)
    return with_warnings(m.mir_read(db, user, x), w)


@router.get(
    "/projects/{project_id}/quality/mir-checklist",
    response_model=QMirChecklistTemplate,
    summary="The material inspection checklist the project proposes (Q-CHK-04)",
    responses=E,
)
def q_mir_checklist_template(project_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return m.mir_checklist_template(db, user, project_id)


@router.post(
    "/quality/mirs/{mir_id}/cancel", response_model=QMirRead, summary="Cancel a draft", responses=E
)
def q_cancel_mir(mir_id: uuid.UUID, body: QReasonBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    return m.mir_read(db, user, m.mir_cancel(db, user, mir_id, body.reason))


@router.post(
    "/quality/mirs/{mir_id}/quarantine",
    response_model=QQuarantineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Quarantine the remaining stock (Q-MAT-06)",
    responses=E,
)
def q_mir_quarantine(
    mir_id: uuid.UUID, body: QMirQuarantine, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return m.q_read(db, user, m.mir_quarantine(db, user, mir_id, body.model_dump()))


# ---- quarantine ----------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/quarantine",
    response_model=QQuarantinePage,
    summary="Quarantined material with ageing",
    responses=E,
)
def q_list_quarantine(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[QQuarantineStatus | None, Query(alias="status")] = None,
    q: Q100 = None,
) -> dict[str, Any]:
    return m.q_list(db, user, project_id, pg.page, pg.page_size, status_, q)


@router.post(
    "/projects/{project_id}/quality/quarantine",
    response_model=QQuarantineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Quarantine material (red tag)",
    responses=E,
)
def q_create_quarantine(
    project_id: uuid.UUID, body: QQuarantineCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return m.q_read(db, user, m.q_create(db, user, project_id, body.model_dump()))


@router.get(
    "/quality/quarantine/{item_id}",
    response_model=QQuarantineRead,
    summary="One quarantine item (red-tag QR target)",
    responses=E,
)
def q_get_quarantine(item_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return m.q_read(db, user, m.get_quarantine(db, user, item_id))


@router.post(
    "/quality/quarantine/{item_id}/link-ncr",
    response_model=QQuarantineRead,
    summary="Link the NCR that decides it",
    responses=E,
)
def q_quarantine_link(
    item_id: uuid.UUID, body: QQuarantineLink, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return m.q_read(db, user, m.q_link_ncr(db, user, item_id, body.ncr_id))


@router.post(
    "/quality/quarantine/{item_id}/dispose",
    response_model=QQuarantineRead,
    summary="Release / return / scrap (256 + RPM quarantine.dispose; Q-MAT-07)",
    responses=E,
)
def q_dispose_quarantine(
    item_id: uuid.UUID, body: QQuarantineDispose, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return m.q_read(
        db, user, m.q_dispose(db, user, item_id, body.model_dump(exclude={"paper"}), paper(body))
    )
