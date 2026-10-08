"""PTW audits: field, document review and unpermitted work (spec 3-ptw §3.15, §4.9, §5.11,
§6.8)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.ptw_enums import PtwAuditStatus, PtwAuditType
from app.schemas.ptw_audits import (
    PtwAuditChecklist,
    PtwAuditCompleteInput,
    PtwAuditCreate,
    PtwAuditPage,
    PtwAuditRead,
    PtwAuditUpdate,
)
from app.services.ptw import audits as svc

router = APIRouter(tags=["ptw-audits"])


@router.get(
    "/projects/{project_id}/ptw-audits",
    response_model=PtwAuditPage,
    summary="PTW audit register",
    responses=error_responses(401, 403, 404, 422),
)
def list_ptw_audits(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    audit_type: Annotated[list[PtwAuditType] | None, Query()] = None,
    status_: Annotated[list[PtwAuditStatus] | None, Query(alias="status")] = None,
    permit_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    auditor_user_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> PtwAuditPage:
    return svc.list_audits(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        audit_type,
        status_,
        permit_id,
        engagement_id,
        auditor_user_id,
        date_from,
        date_to,
    )


@router.post(
    "/projects/{project_id}/ptw-audits",
    response_model=PtwAuditRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a PTW audit (capability 101; SoD AU-2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_ptw_audit(
    project_id: uuid.UUID,
    body: PtwAuditCreate,
    user: CurrentUser,
    db: DB,
) -> PtwAuditRead:
    return svc.create(db, user, project_id, body)


@router.get(
    "/projects/{project_id}/ptw-audits/checklist",
    response_model=PtwAuditChecklist,
    summary="Applicable audit items for a permit or unpermitted work",
    responses=error_responses(401, 403, 404, 422),
)
def get_ptw_audit_checklist(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    audit_type: PtwAuditType,
    permit_id: uuid.UUID | None = None,
) -> PtwAuditChecklist:
    return svc.checklist(db, user, project_id, audit_type, permit_id)


@router.get(
    "/ptw-audits/{audit_id}",
    response_model=PtwAuditRead,
    summary="Get a PTW audit",
    responses=error_responses(401, 403, 404),
)
def get_ptw_audit(audit_id: uuid.UUID, user: CurrentUser, db: DB) -> PtwAuditRead:
    return svc.read(db, user, audit_id)


@router.patch(
    "/ptw-audits/{audit_id}",
    response_model=PtwAuditRead,
    summary="Edit a PTW audit (draft; completed within 7 days; else AUDIT_LOCKED)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_ptw_audit(
    audit_id: uuid.UUID,
    body: PtwAuditUpdate,
    user: CurrentUser,
    db: DB,
) -> PtwAuditRead:
    return svc.update(db, user, audit_id, body)


@router.post(
    "/ptw-audits/{audit_id}/complete",
    response_model=PtwAuditRead,
    summary="Complete an audit (score; CA_REQUIRED; critical → permit suspended)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def complete_ptw_audit(
    audit_id: uuid.UUID,
    body: PtwAuditCompleteInput,
    user: CurrentUser,
    db: DB,
) -> PtwAuditRead:
    return svc.complete(db, user, audit_id, body)
