"""HSE audits (spec 6d-field-assurance §3.7, §3.8, §4.4, AUD-1…AUD-8): contractor HSE and ISO 45001
internal audits, answers, issue with CAs and the EN / AR report, and the audit programme."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.field_enums import AuditStatus, AuditType
from app.schemas.field import (
    AuditAnswers,
    AuditCreate,
    AuditPage,
    AuditProgramme,
    AuditRead,
    AuditTransition,
    AuditUpdate,
)
from app.services.field import audits

router = APIRouter(tags=["field-audits"])


@router.get(
    "/projects/{project_id}/field-audits",
    response_model=AuditPage,
    summary="Audit register (200)",
    responses=error_responses(401, 403, 404),
)
def list_field_audits(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    audit_type: AuditType | None = None,
    status_: Annotated[list[AuditStatus] | None, Query(alias="status")] = None,
    auditee_engagement_id: uuid.UUID | None = None,
) -> AuditPage:
    return audits.list_audits(
        db, user, project_id, audit_type, status_, auditee_engagement_id, pg.page, pg.page_size
    )


@router.post(
    "/projects/{project_id}/field-audits",
    response_model=AuditRead,
    status_code=status.HTTP_201_CREATED,
    summary="Plan an audit (194; AUD-1…AUD-3, SOD_CONFLICT)",
    responses=error_responses(401, 403, 404, 422),
)
def create_field_audit(
    project_id: uuid.UUID, body: AuditCreate, user: CurrentUser, db: DB
) -> AuditRead:
    return audits.create_audit(db, user, project_id, body)


@router.get(
    "/field-audits/{audit_id}",
    response_model=AuditRead,
    summary="One audit with its response and findings",
    responses=error_responses(401, 403, 404),
)
def get_field_audit(audit_id: uuid.UUID, user: CurrentUser, db: DB) -> AuditRead:
    return audits.read_audit(db, user, audit_id)


@router.patch(
    "/field-audits/{audit_id}",
    response_model=AuditRead,
    summary="Edit team, dates, meetings and summary (lead auditor / 194)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_field_audit(
    audit_id: uuid.UUID, body: AuditUpdate, user: CurrentUser, db: DB
) -> AuditRead:
    return audits.update_audit(db, user, audit_id, body)


@router.put(
    "/field-audits/{audit_id}/answers",
    response_model=AuditRead,
    summary="Save answers and manual findings (lead or team; Planned → In Progress)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def save_field_audit_answers(
    audit_id: uuid.UUID, body: AuditAnswers, user: CurrentUser, db: DB
) -> AuditRead:
    return audits.save_answers(db, user, audit_id, body)


@router.post(
    "/field-audits/{audit_id}/transitions",
    response_model=AuditRead,
    summary="Start, complete fieldwork, issue (195 ≠ lead), cancel or void an audit (§4.4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_field_audit(
    audit_id: uuid.UUID, body: AuditTransition, user: CurrentUser, db: DB
) -> AuditRead:
    return audits.transition_audit(db, user, audit_id, body)


@router.get(
    "/projects/{project_id}/audit-programme",
    response_model=AuditProgramme,
    summary="Audit programme lines computed on read (194 / 200; §3.8, §6.4, AUD-6, AUD-7)",
    responses=error_responses(401, 403, 404),
)
def get_audit_programme(project_id: uuid.UUID, user: CurrentUser, db: DB) -> AuditProgramme:
    return audits.programme(db, user, project_id)
