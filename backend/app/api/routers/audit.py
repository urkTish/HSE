"""Audit log, change history (spec §3.10, §5.6)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUser, PageParams
from app.core.enums import AuditAction, AuditResult, EntityType
from app.core.errors import error_responses
from app.schemas.audit import AuditChainVerification, AuditEntryPage, ChangeHistoryPage
from app.services import audit_read as svc
from app.services.common import paginate

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
    db: DB,
    project_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: Annotated[list[AuditAction] | None, Query()] = None,
    entity_type: EntityType | None = None,
    entity_id: uuid.UUID | None = None,
    result: AuditResult | None = None,
    occurred_from: Annotated[datetime | None, Query(description="Inclusive, ISO 8601.")] = None,
    occurred_to: Annotated[datetime | None, Query(description="Exclusive, ISO 8601.")] = None,
) -> AuditEntryPage:
    filters = {
        "project_id": project_id,
        "actor_user_id": actor_user_id,
        "actions": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "result": result,
        "occurred_from": occurred_from,
        "occurred_to": occurred_to,
    }
    stmt = svc.audit_query(db, user, **filters)  # type: ignore[arg-type]
    items, total = paginate(db, stmt, pg.page, pg.page_size)
    svc.log_viewed(db, user, filters, len(items))
    return AuditEntryPage(
        items=svc.entry_reads(db, user, list(items)),
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )


@router.post(
    "/audit-log/verify",
    response_model=AuditChainVerification,
    summary="Verify the audit hash chain now (HSE Manager)",
    responses=error_responses(401, 403),
)
def verify_audit_chain(user: CurrentUser, db: DB) -> AuditChainVerification:
    return svc.verify(db, user)


@router.get(
    "/history/{entity_type}/{entity_id}",
    response_model=ChangeHistoryPage,
    summary="Change history of one record the caller can see (capability 17)",
    responses=error_responses(401, 403, 404, 422),
)
def get_change_history(
    entity_type: EntityType, entity_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB
) -> ChangeHistoryPage:
    stmt = svc.history_query(db, user, entity_type, entity_id)
    items, total = paginate(db, stmt, pg.page, pg.page_size)
    return ChangeHistoryPage(
        items=svc.history_reads(
            db, list(items), svc.hidden_fields(db, user, entity_type, entity_id)
        ),
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )
