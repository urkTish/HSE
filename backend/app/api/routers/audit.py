"""Audit log, change history (spec §3.10, §5.6)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, PageParams
from app.core.enums import AuditAction, AuditResult, EntityType
from app.core.errors import error_responses, not_implemented
from app.schemas.audit import AuditChainVerification, AuditEntryPage, ChangeHistoryPage

router = APIRouter(tags=["audit"])


@router.get(
    "/audit-log",
    response_model=AuditEntryPage,
    response_model_exclude_unset=True,
    summary="Read the audit log (HSE Manager: all; HSE Officer: own projects, no IP/UA)",
    description="Newest first. Writes an `audit_log_viewed` entry.",
    responses=error_responses(401, 403, 422),
)
def list_audit_log(
    user: CurrentUser,
    pg: PageParams,
    project_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: Annotated[list[AuditAction] | None, Query()] = None,
    entity_type: EntityType | None = None,
    entity_id: uuid.UUID | None = None,
    result: AuditResult | None = None,
    occurred_from: Annotated[datetime | None, Query(description="Inclusive, ISO 8601.")] = None,
    occurred_to: Annotated[datetime | None, Query(description="Exclusive, ISO 8601.")] = None,
) -> AuditEntryPage:
    raise not_implemented()


@router.post(
    "/audit-log/verify",
    response_model=AuditChainVerification,
    summary="Verify the audit hash chain now (HSE Manager)",
    responses=error_responses(401, 403),
)
def verify_audit_chain(user: CurrentUser) -> AuditChainVerification:
    raise not_implemented()


@router.get(
    "/history/{entity_type}/{entity_id}",
    response_model=ChangeHistoryPage,
    summary="Change history of one record the caller can see (capability 17)",
    responses=error_responses(401, 403, 404, 422),
)
def get_change_history(
    entity_type: EntityType, entity_id: uuid.UUID, user: CurrentUser, pg: PageParams
) -> ChangeHistoryPage:
    raise not_implemented()
