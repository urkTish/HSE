"""Q1 HTTP routes: ITPs, revisions, approval and the coverage grid (spec 8-quality §B.3)."""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.quality.common import QDiscipline
from app.core.quality.q1 import QItpStatus
from app.schemas.quality.q1 import (
    QChecklistRead,
    QIrCounts,
    QItpCoverage,
    QItpCreate,
    QItpDecide,
    QItpNewRevision,
    QItpPage,
    QItpRead,
    QItpUpdate,
    QReason,
)
from app.services.permissions import forbidden_error
from app.services.quality import common as qc
from app.services.quality.q1 import checklists, itp, kpi

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


def _r(db: Any, user: Any, it: Any) -> dict[str, Any]:
    return itp.read(db, user, it)


@router.get(
    "/projects/{project_id}/quality/itps",
    response_model=QItpPage,
    summary="ITP register",
    responses=E,
)
def q1_list_itps(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QItpStatus] | None, Query(alias="status")] = None,
    discipline: QDiscipline | None = None,
    engagement_id: uuid.UUID | None = None,
    current_only: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    return itp.list_page(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        statuses=status_,
        discipline=discipline,
        engagement_id=engagement_id,
        current_only=current_only,
        q=q,
    )


@router.post(
    "/projects/{project_id}/quality/itps",
    response_model=QItpRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an ITP draft (247; construction profile, else 409 PROFILE_INACTIVE)",
    responses=E,
)
def q1_create_itp(
    project_id: uuid.UUID, body: QItpCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, itp.create(db, user, project_id, body.model_dump(mode="python")))


@router.get(
    "/quality/itps/{itp_id}", response_model=QItpRead, summary="One ITP revision", responses=E
)
def q1_get_itp(itp_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, itp.get_itp(db, user, itp_id))


@router.patch(
    "/quality/itps/{itp_id}",
    response_model=QItpRead,
    summary="Edit a draft or revise-and-resubmit ITP (approved → 409 ITP_IMMUTABLE)",
    responses=E,
)
def q1_update_itp(itp_id: uuid.UUID, body: QItpUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(
        db, user, itp.update(db, user, itp_id, body.model_dump(exclude_unset=True, mode="python"))
    )


@router.delete(
    "/quality/itps/{itp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a never-submitted draft",
    responses=E,
)
def q1_delete_itp(itp_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    itp.delete_draft(db, user, itp_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/quality/itps/{itp_id}/submit",
    response_model=QItpRead,
    summary="Submit (Q-ITP-02 → 422 ITP_INCOMPLETE)",
    responses=E,
)
def q1_submit_itp(itp_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, itp.submit(db, user, itp_id))


@router.post(
    "/quality/itps/{itp_id}/decide",
    response_model=QItpRead,
    summary="Approve (A / B), revise (C) or reject (D) — responsible person for itp.approve",
    responses=E,
)
def q1_decide_itp(itp_id: uuid.UUID, body: QItpDecide, user: CurrentUser, db: DB) -> dict[str, Any]:
    paper = body.paper.model_dump(mode="python") if body.paper else None
    return _r(db, user, itp.decide(db, user, itp_id, body.code, body.comment, paper))


@router.post(
    "/quality/itps/{itp_id}/revisions",
    response_model=QItpRead,
    status_code=status.HTTP_201_CREATED,
    summary="New revision (Draft) copied from the current Approved revision",
    responses=E,
)
def q1_new_revision(
    itp_id: uuid.UUID, body: QItpNewRevision, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, itp.new_revision(db, user, itp_id, body.change_note))


@router.post(
    "/quality/itps/{itp_id}/withdraw",
    response_model=QItpRead,
    summary="Withdraw an approved ITP (239, reason ≥ 20)",
    responses=E,
)
def q1_withdraw_itp(itp_id: uuid.UUID, body: QReason, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, itp.withdraw(db, user, itp_id, body.reason))


@router.get(
    "/quality/itps/{itp_id}/coverage",
    response_model=QItpCoverage,
    summary="Coverage grid: points × location keys (Q-ITP-06)",
    responses=E,
)
def q1_itp_coverage(itp_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return itp.coverage(db, user, itp_id)


@router.get(
    "/projects/{project_id}/quality/q1-checklists",
    response_model=list[QChecklistRead],
    summary="Published Part B quality checklists with their items (builder, runner, walkdown)",
    responses=E,
)
def q1_checklists(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    quality_type: Literal["ir_inspection", "punch_walkdown"] = "ir_inspection",
) -> list[dict[str, Any]]:
    pr = qc.get_project(db, user, project_id)
    if not any(
        user.grant(pr.id, c) for c in (qc.C.quality_view, qc.C.itp_author, qc.C.punch_record)
    ):
        raise forbidden_error()
    return [checklists.template_read(t) for t in checklists.published(db, quality_type)]


@router.get(
    "/projects/{project_id}/quality/q1-counts",
    response_model=QIrCounts,
    summary="IR and punch counts behind K-141, K-142, K-149 (ir_inspection) and K-156 for a period",
    responses=E,
)
def q1_counts(
    project_id: uuid.UUID, user: CurrentUser, db: DB, date_from: date, date_to: date
) -> dict[str, Any]:
    from app.kpi.quality_views import kpi_filter  # noqa: PLC0415

    pr = qc.get_project(db, user, project_id)
    # the caller's grant narrows the counts to its sites / engagement tree, as the Q4 KPI page
    # does (D-360, D-370); scope N sees no counts (Q-ROL-04)
    f = kpi_filter(user, pr.id)
    c = kpi.ir_counts(
        db, pr.id, date_from, date_to, site_ids=f.site_ids, engagement_ids=f.engagement_ids
    )
    pc = kpi.punch_counts(
        db,
        pr.id,
        date_from,
        date_to,
        min(date_to, qc.project_day(pr)),
        site_ids=f.site_ids,
        engagement_ids=f.engagement_ids,
    )
    return {
        "project_id": pr.id,
        "date_from": date_from,
        "date_to": date_to,
        "first_rounds": c.first_rounds,
        "first_passes": c.first_passes,
        "first_time_pass_pct": str(c.ftpr) if c.ftpr is not None else None,
        "rounds_decided": c.rounds_decided,
        "rounds_failed": c.rounds_failed,
        "rejection_rate_pct": str(c.rejection_rate) if c.rejection_rate is not None else None,
        "waived": c.waived,
        "short_notice": c.short_notice,
        "paper_signoffs": c.paper_signoffs,
        "opportunities": c.opportunities,
        "defects": c.defects,
        "punch_with_target": pc.with_target,
        "punch_closed_on_time": pc.closed_on_time,
        "punch_closure_pct": str(pc.closure_pct) if pc.closure_pct is not None else None,
        "punch_open_a": pc.open_a,
        "punch_open_b": pc.open_b,
    }
