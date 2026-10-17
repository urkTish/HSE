"""Administrator deletes and the deleted-items register (D-271)."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.models import DeletedRecord, User
from app.schemas.common import ApiModel, Page, StrictInput
from app.services import admin_records as svc

router = APIRouter(prefix="/admin", tags=["admin"])


class RecordDeleteRequest(StrictInput):
    entity_type: str = Field(min_length=1, max_length=60, examples=["training_course"])
    entity_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=500)


class DeletedRecordRead(ApiModel):
    id: uuid.UUID
    deleted_at: datetime
    deleted_by_name: str | None
    entity_type: str
    entity_id: uuid.UUID
    project_id: uuid.UUID | None
    label: str
    reason: str
    row_counts: dict[str, int]
    rows_deleted: int


class DeletedRecordDetail(DeletedRecordRead):
    rows: dict[str, Any] | None = Field(description="Copies of the deleted rows per table.")


class DeletedRecordPage(Page[DeletedRecordRead]):
    pass


class DeletableTypes(ApiModel):
    entity_types: list[str]


def _read(db: DB, r: DeletedRecord) -> dict[str, Any]:
    who = db.get(User, r.deleted_by_user_id) if r.deleted_by_user_id else None
    return {
        "id": r.id,
        "deleted_at": r.deleted_at,
        "deleted_by_name": who.full_name_en if who else None,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "project_id": r.project_id,
        "label": r.label,
        "reason": r.reason,
        "row_counts": r.row_counts,
        "rows_deleted": sum(r.row_counts.values()),
    }


@router.get(
    "/deletable-types",
    response_model=DeletableTypes,
    summary="Record types the administrator can delete",
    responses=error_responses(401, 403),
)
def deletable_types(user: CurrentUser) -> DeletableTypes:
    svc.require_admin(user)
    return DeletableTypes(entity_types=sorted(svc.deletable_tables()))


@router.post(
    "/records/delete",
    response_model=DeletedRecordRead,
    summary="Delete a record and what belongs to it; kept in the deleted-items register",
    responses=error_responses(401, 403, 404, 422),
)
def delete_record(body: RecordDeleteRequest, user: CurrentUser, db: DB) -> DeletedRecordRead:
    rec = svc.delete_record(db, user, body.entity_type, body.entity_id, body.reason)
    return DeletedRecordRead(**_read(db, rec))


@router.get(
    "/deleted-records",
    response_model=DeletedRecordPage,
    summary="Deleted-items register (newest first)",
    responses=error_responses(401, 403),
)
def list_deleted_records(user: CurrentUser, pg: PageParams, db: DB) -> DeletedRecordPage:
    items, total = svc.list_deleted(db, user, pg.page, pg.page_size)
    return DeletedRecordPage(
        items=[DeletedRecordRead(**_read(db, r)) for r in items],
        total=total,
        page=pg.page,
        page_size=pg.page_size,
    )


@router.get(
    "/deleted-records/{record_id}",
    response_model=DeletedRecordDetail,
    summary="One deleted item with copies of the deleted rows",
    responses=error_responses(401, 403, 404),
)
def get_deleted_record(record_id: uuid.UUID, user: CurrentUser, db: DB) -> DeletedRecordDetail:
    rec = svc.get_deleted(db, user, record_id)
    return DeletedRecordDetail(**_read(db, rec), rows=rec.rows)
