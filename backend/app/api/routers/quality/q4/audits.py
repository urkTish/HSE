"""Q4 HTTP routes: processes, the quality audit programme, quality audits on the 6d engine and
management reviews (spec 8-quality §E.2)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.field_enums import AuditStatus
from app.schemas.field import AuditAnswers
from app.schemas.quality.q4 import (
    Q4AuditCreate,
    Q4AuditIssue,
    Q4AuditPage,
    Q4AuditRead,
    Q4AuditUpdate,
    Q4LineCreate,
    Q4LineRead,
    Q4LineUpdate,
    Q4MrvCreate,
    Q4MrvHold,
    Q4MrvRead,
    Q4MrvUpdate,
    Q4ProcessInput,
    Q4ProcessRead,
    Q4Reason,
)
from app.services.quality.q4 import audits

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)
P = "/projects/{project_id}/quality"


@router.get(
    P + "/processes",
    response_model=list[Q4ProcessRead],
    summary="Process register (§E.2.1)",
    responses=E,
)
def q4_list_processes(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return audits.list_processes(db, user, project_id)


@router.post(
    P + "/processes",
    response_model=Q4ProcessRead,
    status_code=status.HTTP_201_CREATED,
    summary="New process (276)",
    responses=E,
)
def q4_create_process(
    project_id: uuid.UUID, body: Q4ProcessInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return audits.save_process(db, user, project_id, body.model_dump(exclude_unset=True))


@router.patch(
    P + "/processes/{process_id}",
    response_model=Q4ProcessRead,
    summary="Edit a process (276)",
    responses=E,
)
def q4_update_process(
    project_id: uuid.UUID, process_id: uuid.UUID, body: Q4ProcessInput, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return audits.save_process(
        db, user, project_id, body.model_dump(exclude_unset=True), process_id
    )


@router.get(
    P + "/audit-programme",
    response_model=list[Q4LineRead],
    summary="Quality audit programme of a year (Q-AUD-06)",
    responses=E,
)
def q4_programme(
    project_id: uuid.UUID, year: Annotated[int, Query(ge=2020, le=2100)], user: CurrentUser, db: DB
) -> list[dict[str, Any]]:
    return audits.programme(db, user, project_id, year)


@router.post(
    P + "/audit-programme/generate",
    response_model=list[Q4LineRead],
    summary="Generate lines per process by risk (idempotent)",
    responses=E,
)
def q4_programme_generate(
    project_id: uuid.UUID, year: Annotated[int, Query(ge=2020, le=2100)], user: CurrentUser, db: DB
) -> list[dict[str, Any]]:
    return audits.programme_generate(db, user, project_id, year)


@router.post(
    P + "/audit-programme",
    response_model=Q4LineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a supplier, subcontractor or clause-set line",
    responses=E,
)
def q4_add_line(
    project_id: uuid.UUID, body: Q4LineCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return audits.add_line(db, user, project_id, body.model_dump())


@router.patch(
    "/quality/audit-programme/{line_id}",
    response_model=Q4LineRead,
    summary="Postpone, cancel or move a line",
    responses=E,
)
def q4_update_line(
    line_id: uuid.UUID, body: Q4LineUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return audits.update_line(db, user, line_id, body.model_dump(exclude_unset=True))


@router.get(
    P + "/audits",
    response_model=Q4AuditPage,
    summary="Quality audits (domain quality)",
    responses=E,
)
def q4_list_audits(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    pg: PageParams,
    status_: Annotated[list[AuditStatus] | None, Query(alias="status")] = None,
) -> dict[str, Any]:
    return audits.list_audits(db, user, project_id, status_, pg.page, pg.page_size)


@router.post(
    P + "/audits",
    response_model=Q4AuditRead,
    status_code=status.HTTP_201_CREATED,
    summary="Plan a quality audit (276; independence Q-AUD-02)",
    responses=E,
)
def q4_create_audit(
    project_id: uuid.UUID, body: Q4AuditCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return audits.create_audit(db, user, project_id, body.model_dump())


@router.get(
    "/quality/audits/{audit_id}",
    response_model=Q4AuditRead,
    summary="One quality audit",
    responses=E,
)
def q4_get_audit(audit_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return audits.read_audit(db, user, audit_id)


@router.patch(
    "/quality/audits/{audit_id}",
    response_model=Q4AuditRead,
    summary="Fieldwork dates, meetings, summary (audit team)",
    responses=E,
)
def q4_update_audit(
    audit_id: uuid.UUID, body: Q4AuditUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return audits.update_audit(db, user, audit_id, body.model_dump(exclude_unset=True))


@router.put(
    "/quality/audits/{audit_id}/answers",
    response_model=Q4AuditRead,
    summary="Save answers on the 6d engine (grades and findings)",
    responses=E,
)
def q4_audit_answers(
    audit_id: uuid.UUID, body: AuditAnswers, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return audits.save_answers(db, user, audit_id, body)


@router.post(
    "/quality/audits/{audit_id}/complete-fieldwork",
    response_model=Q4AuditRead,
    summary="Lead auditor completes the fieldwork",
    responses=E,
)
def q4_audit_complete(audit_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return audits.complete_fieldwork(db, user, audit_id)


@router.post(
    "/quality/audits/{audit_id}/issue",
    response_model=Q4AuditRead,
    summary="Issue the report (277 + RPM q_audit.issue; NCRs per NC, Q-AUD-03 / -04)",
    responses=E,
)
def q4_audit_issue(
    audit_id: uuid.UUID, body: Q4AuditIssue, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return audits.issue(db, user, audit_id, body.model_dump())


@router.post(
    "/quality/audits/{audit_id}/cancel",
    response_model=Q4AuditRead,
    summary="Cancel a planned audit",
    responses=E,
)
def q4_audit_cancel(
    audit_id: uuid.UUID, body: Q4Reason, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return audits.cancel_or_void(db, user, audit_id, "cancel", body.reason)


@router.post(
    "/quality/audits/{audit_id}/void",
    response_model=Q4AuditRead,
    summary="Void an audit (244)",
    responses=E,
)
def q4_audit_void(audit_id: uuid.UUID, body: Q4Reason, user: CurrentUser, db: DB) -> dict[str, Any]:
    return audits.cancel_or_void(db, user, audit_id, "void", body.reason)


@router.get(
    P + "/management-reviews",
    response_model=list[Q4MrvRead],
    summary="Management reviews (§E.2.2)",
    responses=E,
)
def q4_list_mrv(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return audits.list_mrv(db, user, project_id)


@router.post(
    P + "/management-reviews",
    response_model=Q4MrvRead,
    status_code=status.HTTP_201_CREATED,
    summary="New management review (276)",
    responses=E,
)
def q4_create_mrv(
    project_id: uuid.UUID, body: Q4MrvCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return audits.create_mrv(db, user, project_id, body.model_dump())


@router.get(
    "/quality/management-reviews/{mid}",
    response_model=Q4MrvRead,
    summary="One management review",
    responses=E,
)
def q4_get_mrv(mid: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return audits.read_mrv(db, user, mid)


@router.patch(
    "/quality/management-reviews/{mid}",
    response_model=Q4MrvRead,
    summary="Inputs (Draft) and outputs; an output may create a CA",
    responses=E,
)
def q4_update_mrv(mid: uuid.UUID, body: Q4MrvUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    if body.inputs is not None:
        data["inputs"] = {k: v.model_dump() for k, v in body.inputs.items()}
    return audits.update_mrv(db, user, mid, data)


@router.post(
    "/quality/management-reviews/{mid}/hold",
    response_model=Q4MrvRead,
    summary="Draft → Held (Q-MRV-01) and freeze the KPI snapshot (Q-MRV-02)",
    responses=E,
)
def q4_hold_mrv(mid: uuid.UUID, body: Q4MrvHold, user: CurrentUser, db: DB) -> dict[str, Any]:
    return audits.hold_mrv(db, user, mid, body.held_on)


@router.post(
    "/quality/management-reviews/{mid}/issue-minutes",
    response_model=Q4MrvRead,
    summary="Approve and issue the minutes (277 + RPM; EN / AR PDFs)",
    responses=E,
)
def q4_issue_mrv(mid: uuid.UUID, body: Q4Reason, user: CurrentUser, db: DB) -> dict[str, Any]:
    return audits.issue_minutes(db, user, mid, body.reason)
