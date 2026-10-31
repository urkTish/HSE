"""Q0 HTTP routes: NCRs with containment, root cause, disposition, sign-offs, costs, actions,
supplier response and PDF; quality observations, quality alerts and customer complaints
(spec 8-quality §A.9, §A.10). Every write follows the licence read-only guard (D-290)."""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.quality.common import (
    QAlertStatus,
    QComplaintStatus,
    QDetectionStage,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QNcrStatus,
    QObservationStatus,
)
from app.schemas.quality.q0 import (
    QAlertCreate,
    QAlertPage,
    QAlertRead,
    QAlertUpdate,
    QCommentInput,
    QComplaintCreate,
    QComplaintPage,
    QComplaintRead,
    QComplaintTransition,
    QNcrActionCreate,
    QNcrClassChange,
    QNcrContainment,
    QNcrCostCreate,
    QNcrCostUpdate,
    QNcrCreate,
    QNcrDispositionSave,
    QNcrEffectiveness,
    QNcrImplement,
    QNcrLineUpdate,
    QNcrNoCost,
    QNcrPage,
    QNcrRcaSave,
    QNcrRead,
    QNcrSign,
    QNcrSupplierResponse,
    QNcrUpdate,
    QNcrVoid,
    QObservationCreate,
    QObservationPage,
    QObservationRead,
    QReasonInput,
)
from app.services.quality import alerts, complaints, observations
from app.services.quality.ncr import core, costs, disposition, pdf, rca

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


def _r(db: Any, user: Any, n: Any, warnings: list[Any] | None = None) -> dict[str, Any]:
    return core.read(db, user, n, warnings)


# ---- NCRs ----------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/ncrs",
    response_model=QNcrPage,
    summary="NCR register (scoped: P / S / C; N = steps of the responsible person)",
    responses=E,
)
def q_list_ncrs(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QNcrStatus] | None, Query(alias="status")] = None,
    classification: Annotated[list[QNcrClass] | None, Query()] = None,
    category: Annotated[list[QNcrCategory] | None, Query()] = None,
    source_type: QNcrSourceType | None = None,
    source_id: uuid.UUID | None = None,
    detection_stage: QDetectionStage | None = None,
    profile: Literal["construction", "logistics"] | None = None,
    repeat: bool | None = None,
    mine: bool = False,
    open_only: bool = False,
    overdue: bool | None = None,
    supplier_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["-opened_at", "opened_at", "target_close_date", "-cost", "ncr_no"] = "-opened_at",
) -> dict[str, Any]:
    return core.list_page(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        statuses=status_,
        classes=classification,
        categories=category,
        source_type=source_type,
        source_id=source_id,
        detection_stage=detection_stage,
        profile=profile,
        repeat=repeat,
        mine=mine,
        open_only=open_only,
        overdue=overdue,
        supplier_id=supplier_id,
        engagement_id=engagement_id,
        site_id=site_id,
        q=q,
        sort=sort,
    )


@router.post(
    "/projects/{project_id}/quality/ncrs",
    response_model=QNcrRead,
    status_code=status.HTTP_201_CREATED,
    summary="Raise an NCR (241): Draft, or Open with `open = true`; 422 PROFILE_REQUIRED "
    "before the profile is chosen",
    responses=E,
)
def q_create_ncr(
    project_id: uuid.UUID, body: QNcrCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    n, warnings = core.create(db, user, project_id, body.model_dump(exclude_unset=True))
    return _r(db, user, n, warnings)


@router.get("/quality/ncrs/{ncr_id}", response_model=QNcrRead, summary="One NCR", responses=E)
def q_get_ncr(ncr_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, core.get_ncr(db, user, ncr_id))


@router.patch(
    "/quality/ncrs/{ncr_id}",
    response_model=QNcrRead,
    summary="Edit (raiser on a Draft; 242 in scope later; not source / item key)",
    responses=E,
)
def q_update_ncr(ncr_id: uuid.UUID, body: QNcrUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    n, warnings = core.update(db, user, ncr_id, body.model_dump(exclude_unset=True))
    return _r(db, user, n, warnings)


@router.delete(
    "/quality/ncrs/{ncr_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Draft never opened (raiser)",
    responses=E,
)
def q_delete_ncr(ncr_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    core.delete_draft(db, user, ncr_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/quality/ncrs/{ncr_id}/open",
    response_model=QNcrRead,
    summary="Draft → Open (Q-NCR-03; critical needs evidence: EVIDENCE_REQUIRED)",
    responses=E,
)
def q_open_ncr(ncr_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    n, warnings = core.open_ncr(db, user, ncr_id)
    return _r(db, user, n, warnings)


@router.post(
    "/quality/ncrs/{ncr_id}/classification",
    response_model=QNcrRead,
    summary="Raise (242) or lower (disposition resolver + reason; else 422 "
    "CLASS_LOWERED_NEEDS_APPROVAL) the class (Q-NCR-05)",
    responses=E,
)
def q_ncr_class(
    ncr_id: uuid.UUID, body: QNcrClassChange, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, core.set_class(db, user, ncr_id, body.classification, body.reason))


@router.put(
    "/quality/ncrs/{ncr_id}/containment",
    response_model=QNcrRead,
    summary="Containment (Q-NCR-07)",
    responses=E,
)
def q_ncr_containment(
    ncr_id: uuid.UUID, body: QNcrContainment, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, core.set_containment(db, user, ncr_id, body.model_dump(exclude_unset=True)))


@router.put(
    "/quality/ncrs/{ncr_id}/rca",
    response_model=QNcrRead,
    summary="Root-cause analysis (Q-NCR-09; RCA_METHOD_NOT_ALLOWED, RCA_INCOMPLETE)",
    responses=E,
)
def q_ncr_rca(ncr_id: uuid.UUID, body: QNcrRcaSave, user: CurrentUser, db: DB) -> dict[str, Any]:
    n, warnings = rca.save(db, user, ncr_id, body.model_dump(mode="json"))
    return _r(db, user, n, warnings)


@router.put(
    "/quality/ncrs/{ncr_id}/disposition",
    response_model=QNcrRead,
    summary="Disposition lines (Q-NCR-11; DISPOSITION_QTY_MISMATCH, CONCESSION_EVIDENCE_REQUIRED)",
    responses=E,
)
def q_ncr_disposition(
    ncr_id: uuid.UUID, body: QNcrDispositionSave, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, disposition.save(db, user, ncr_id, body.model_dump()))


@router.patch(
    "/quality/ncr-lines/{line_id}",
    response_model=QNcrRead,
    summary="Return note / destruction evidence of a reject line",
    responses=E,
)
def q_ncr_line(
    line_id: uuid.UUID, body: QNcrLineUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(
        db, user, disposition.update_line(db, user, line_id, body.model_dump(exclude_unset=True))
    )


@router.post(
    "/quality/ncrs/{ncr_id}/propose",
    response_model=QNcrRead,
    summary="Open → Disposition Proposed (CONTAINMENT_REQUIRED, RCA_INCOMPLETE, CA_REQUIRED)",
    responses=E,
)
def q_ncr_propose(ncr_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, core.propose(db, user, ncr_id))


@router.post(
    "/quality/ncrs/{ncr_id}/sign",
    response_model=QNcrRead,
    summary="Responsible-person sign-off of disposition, concession or close (in app or "
    "on paper); NCR_CLOSE_BLOCKED lists blockers",
    responses=E,
)
def q_ncr_sign(ncr_id: uuid.UUID, body: QNcrSign, user: CurrentUser, db: DB) -> dict[str, Any]:
    paper = body.paper.model_dump(mode="json") if body.paper else None
    return _r(
        db, user, core.sign_step(db, user, ncr_id, body.step, body.decision, body.comment, paper)
    )


@router.post(
    "/quality/ncrs/{ncr_id}/implement",
    response_model=QNcrRead,
    summary="Disposition Approved → Pending Verification (242)",
    responses=E,
)
def q_ncr_implement(
    ncr_id: uuid.UUID, body: QNcrImplement, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, core.implement(db, user, ncr_id, body.implementation_note))


@router.post(
    "/quality/ncrs/{ncr_id}/reopen",
    response_model=QNcrRead,
    summary="Closed → Open within 30 days (239, reason)",
    responses=E,
)
def q_ncr_reopen(
    ncr_id: uuid.UUID, body: QReasonInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, core.reopen(db, user, ncr_id, body.reason))


@router.post(
    "/quality/ncrs/{ncr_id}/void",
    response_model=QNcrRead,
    summary="Void (244, reason; duplicate_of when a duplicate; CAs stay)",
    responses=E,
)
def q_ncr_void(ncr_id: uuid.UUID, body: QNcrVoid, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, core.void(db, user, ncr_id, body.reason, body.duplicate_of))


@router.post(
    "/quality/ncrs/{ncr_id}/effectiveness",
    response_model=QNcrRead,
    summary="Confirm the effectiveness check (Q-NCR-17, 242)",
    responses=E,
)
def q_ncr_effectiveness(
    ncr_id: uuid.UUID, body: QNcrEffectiveness, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, core.confirm_effectiveness(db, user, ncr_id, body.result, body.note))


@router.post(
    "/quality/ncrs/{ncr_id}/supplier-response",
    response_model=QNcrRead,
    summary="Supplier response / SCAR (Q-NCR-13)",
    responses=E,
)
def q_ncr_supplier_response(
    ncr_id: uuid.UUID, body: QNcrSupplierResponse, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(
        db,
        user,
        core.supplier_response(db, user, ncr_id, body.action, body.model_dump(exclude_unset=True)),
    )


@router.post(
    "/quality/ncrs/{ncr_id}/no-cost",
    response_model=QNcrRead,
    summary='Confirm "no cost incurred" with a reason (Q-NCR-14)',
    responses=E,
)
def q_ncr_no_cost(ncr_id: uuid.UUID, body: QNcrNoCost, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, core.no_cost(db, user, ncr_id, body.reason))


@router.post(
    "/quality/ncrs/{ncr_id}/costs",
    response_model=QNcrRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a cost line (§A.9.6; DELAY_RATE_NOT_SET)",
    responses=E,
)
def q_ncr_add_cost(
    ncr_id: uuid.UUID, body: QNcrCostCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, costs.add(db, user, ncr_id, body.model_dump()))


@router.patch(
    "/quality/ncr-costs/{cost_id}",
    response_model=QNcrRead,
    summary="Edit the recovered amount of a cost line",
    responses=E,
)
def q_ncr_update_cost(
    cost_id: uuid.UUID, body: QNcrCostUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, costs.update(db, user, cost_id, body.model_dump(exclude_unset=True)))


@router.delete(
    "/quality/ncr-costs/{cost_id}",
    response_model=QNcrRead,
    summary="Remove a cost line before closure",
    responses=E,
)
def q_ncr_delete_cost(cost_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, costs.delete(db, user, cost_id))


@router.post(
    "/quality/ncrs/{ncr_id}/actions",
    response_model=QNcrRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a corrective action inline (source quality_ncr; Q-CAP-02…05)",
    responses=E,
)
def q_ncr_add_action(
    ncr_id: uuid.UUID, body: QNcrActionCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    n, warnings = core.add_action(db, user, ncr_id, body.model_dump())
    return _r(db, user, n, warnings)


@router.get(
    "/quality/ncrs/{ncr_id}/pdf",
    summary="NCR PDF in EN or AR with the Hijri issue date (Q-NCR-19)",
    responses={
        **E,
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}},
    },
    response_class=Response,
)
def q_ncr_pdf(
    ncr_id: uuid.UUID, user: CurrentUser, db: DB, lang: Literal["en", "ar"] = "en"
) -> Response:
    content, name = pdf.pdf(db, user, ncr_id, lang)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# ---- observations --------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/observations",
    response_model=QObservationPage,
    summary="Quality observations",
    responses=E,
)
def q_list_observations(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QObservationStatus] | None, Query(alias="status")] = None,
    mine: bool = False,
) -> dict[str, Any]:
    return observations.list_page(db, user, project_id, pg.page, pg.page_size, status_, mine)


@router.post(
    "/projects/{project_id}/quality/observations",
    response_model=QObservationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Raise an observation (241)",
    responses=E,
)
def q_create_observation(
    project_id: uuid.UUID, body: QObservationCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return observations.create(db, user, project_id, body.model_dump())


@router.get(
    "/quality/observations/{obs_id}",
    response_model=QObservationRead,
    summary="One observation",
    responses=E,
)
def q_get_observation(obs_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return observations.read(db, user, observations.get_obs(db, user, obs_id))


@router.post(
    "/quality/observations/{obs_id}/ncr",
    response_model=QNcrRead,
    status_code=status.HTTP_201_CREATED,
    summary="Escalate to an NCR (Q-OBS-01; observation → actioned)",
    responses=E,
)
def q_observation_to_ncr(
    obs_id: uuid.UUID, body: QNcrCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    data.pop("source_type", None)
    data.pop("source_id", None)
    return observations.to_ncr(db, user, obs_id, data)


@router.post(
    "/quality/observations/{obs_id}/actions",
    response_model=QObservationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Corrective action from an observation (source quality_observation)",
    responses=E,
)
def q_observation_action(
    obs_id: uuid.UUID, body: QNcrActionCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return observations.add_action(db, user, obs_id, body.model_dump())


@router.post(
    "/quality/observations/{obs_id}/close",
    response_model=QObservationRead,
    summary="Close (RPM observation.close, reason)",
    responses=E,
)
def q_close_observation(
    obs_id: uuid.UUID, body: QReasonInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return observations.close(db, user, obs_id, body.reason)


# ---- quality alerts ------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/alerts",
    response_model=QAlertPage,
    summary="Quality alerts",
    responses=E,
)
def q_list_alerts(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QAlertStatus] | None, Query(alias="status")] = None,
) -> dict[str, Any]:
    return alerts.list_page(db, user, project_id, pg.page, pg.page_size, status_)


@router.post(
    "/projects/{project_id}/quality/alerts",
    response_model=QAlertRead,
    status_code=status.HTTP_201_CREATED,
    summary="Draft an alert (242)",
    responses=E,
)
def q_create_alert(
    project_id: uuid.UUID, body: QAlertCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return alerts.create(db, user, project_id, body.model_dump())


@router.get(
    "/quality/alerts/{alert_id}", response_model=QAlertRead, summary="One alert", responses=E
)
def q_get_alert(alert_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return alerts.read(db, user, alerts.get_alert(db, user, alert_id))


@router.patch(
    "/quality/alerts/{alert_id}",
    response_model=QAlertRead,
    summary="Edit a draft alert (242)",
    responses=E,
)
def q_update_alert(
    alert_id: uuid.UUID, body: QAlertUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return alerts.update(db, user, alert_id, body.model_dump(exclude_unset=True))


@router.post(
    "/quality/alerts/{alert_id}/issue",
    response_model=QAlertRead,
    summary="Issue (RPM quality_alert.issue); notifies the distribution",
    responses=E,
)
def q_issue_alert(
    alert_id: uuid.UUID, body: QCommentInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return alerts.issue(db, user, alert_id, body.comment)


@router.post(
    "/quality/alerts/{alert_id}/ack",
    response_model=QAlertRead,
    summary="Acknowledge (275; once per member, idempotent)",
    responses=E,
)
def q_ack_alert(alert_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return alerts.ack(db, user, alert_id)


@router.post(
    "/quality/alerts/{alert_id}/withdraw",
    response_model=QAlertRead,
    summary="Withdraw (239, reason)",
    responses=E,
)
def q_withdraw_alert(
    alert_id: uuid.UUID, body: QReasonInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return alerts.withdraw(db, user, alert_id, body.reason)


# ---- complaints ----------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/complaints",
    response_model=QComplaintPage,
    summary="Customer complaints",
    responses=E,
)
def q_list_complaints(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QComplaintStatus] | None, Query(alias="status")] = None,
) -> dict[str, Any]:
    return complaints.list_page(db, user, project_id, pg.page, pg.page_size, status_)


@router.post(
    "/projects/{project_id}/quality/complaints",
    response_model=QComplaintRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a complaint (245)",
    responses=E,
)
def q_create_complaint(
    project_id: uuid.UUID, body: QComplaintCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return complaints.create(db, user, project_id, body.model_dump())


@router.get(
    "/quality/complaints/{complaint_id}",
    response_model=QComplaintRead,
    summary="One complaint",
    responses=E,
)
def q_get_complaint(complaint_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return complaints.read(db, user, complaints.get_complaint(db, user, complaint_id))


@router.post(
    "/quality/complaints/{complaint_id}/transitions",
    response_model=QComplaintRead,
    summary="Complaint status (§A.10.3; NCR_REQUIRED_FOR_JUSTIFIED)",
    responses=E,
)
def q_complaint_transition(
    complaint_id: uuid.UUID, body: QComplaintTransition, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return complaints.transition(
        db, user, complaint_id, body.to_status, body.model_dump(exclude_unset=True)
    )


@router.post(
    "/quality/complaints/{complaint_id}/ncr",
    response_model=QNcrRead,
    status_code=status.HTTP_201_CREATED,
    summary="Raise an NCR from the complaint (source complaint, detection at_customer)",
    responses=E,
)
def q_complaint_ncr(
    complaint_id: uuid.UUID, body: QNcrCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    data.pop("source_type", None)
    data.pop("source_id", None)
    return complaints.raise_ncr(db, user, complaint_id, data)


_ = date
