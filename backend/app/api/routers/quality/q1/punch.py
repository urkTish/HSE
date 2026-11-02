"""Q1 HTTP routes: punch items, walkdowns, floor plans and pins (spec 8-quality §B.5, §B.6)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.quality.q1 import PLAN_MAX_BYTES, QPunchCategory, QPunchStatus
from app.schemas.quality.q1 import (
    QFloorPlanRead,
    QPunchCreate,
    QPunchPage,
    QPunchRead,
    QPunchReady,
    QPunchUpdate,
    QPunchVerify,
    QReason,
    QWalkdown,
    QWalkdownResult,
)
from app.services.quality.q1 import common as q1c
from app.services.quality.q1 import punch

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/projects/{project_id}/quality/punch",
    response_model=QPunchPage,
    summary="Punch register",
    responses=E,
)
def q1_list_punch(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QPunchStatus] | None, Query(alias="status")] = None,
    zone_id: uuid.UUID | None = None,
    category: QPunchCategory | None = None,
    engagement_id: uuid.UUID | None = None,
    floor_plan_id: uuid.UUID | None = None,
    overdue: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    return punch.list_page(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        statuses=status_,
        zone_id=zone_id,
        category=category,
        engagement_id=engagement_id,
        floor_plan_id=floor_plan_id,
        overdue_only=overdue,
        q=q,
    )


@router.post(
    "/projects/{project_id}/quality/punch",
    response_model=QPunchRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a punch item (251; ≥ 1 photo; numbered at once)",
    responses=E,
)
def q1_create_punch(
    project_id: uuid.UUID, body: QPunchCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    it, warnings = punch.create(db, user, project_id, body.model_dump(mode="python"))
    return punch.read(db, user, it, warnings)


@router.post(
    "/projects/{project_id}/quality/punch/walkdown",
    response_model=QWalkdownResult,
    status_code=status.HTTP_201_CREATED,
    summary="Walkdown session: each non-compliant answer or free entry becomes an item (Q-PUN-01)",
    responses=E,
)
def q1_walkdown(
    project_id: uuid.UUID, body: QWalkdown, user: CurrentUser, db: DB
) -> dict[str, Any]:
    items, warnings = punch.walkdown(db, user, project_id, body.model_dump(mode="python"))
    pr = q1c.project(db, project_id)
    return {
        "items": [punch.list_item(db, i, q1c.day(pr), False) for i in items],
        "warnings": warnings,
    }


@router.get(
    "/quality/punch/{item_id}", response_model=QPunchRead, summary="One punch item", responses=E
)
def q1_get_punch(item_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return punch.read(db, user, punch.get_item(db, user, item_id))


@router.patch(
    "/quality/punch/{item_id}",
    response_model=QPunchRead,
    summary="Edit, move or confirm the pin",
    responses=E,
)
def q1_update_punch(
    item_id: uuid.UUID, body: QPunchUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return punch.read(
        db,
        user,
        punch.update(db, user, item_id, body.model_dump(exclude_unset=True, mode="python")),
    )


@router.post(
    "/quality/punch/{item_id}/ready",
    response_model=QPunchRead,
    summary="Mark fixed: Ready for Review (after photo, note ≥ 10)",
    responses=E,
)
def q1_ready_punch(
    item_id: uuid.UUID, body: QPunchReady, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return punch.read(db, user, punch.mark_ready(db, user, item_id, body.note, body.photos))


@router.post(
    "/quality/punch/{item_id}/verify",
    response_model=QPunchRead,
    summary="Verify: close or re-open (252 + RPM punch_item.verify)",
    responses=E,
)
def q1_verify_punch(
    item_id: uuid.UUID, body: QPunchVerify, user: CurrentUser, db: DB
) -> dict[str, Any]:
    paper = body.paper.model_dump(mode="python") if body.paper else None
    return punch.read(db, user, punch.verify(db, user, item_id, body.decision, body.comment, paper))


@router.post(
    "/quality/punch/{item_id}/void",
    response_model=QPunchRead,
    summary="Void (244, reason ≥ 20)",
    responses=E,
)
def q1_void_punch(item_id: uuid.UUID, body: QReason, user: CurrentUser, db: DB) -> dict[str, Any]:
    return punch.read(db, user, punch.void(db, user, item_id, body.reason))


# ---- floor plans --------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/quality/floor-plans",
    response_model=list[QFloorPlanRead],
    summary="Floor plans",
    responses=E,
)
def q1_list_plans(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    zone_id: uuid.UUID | None = None,
    current_only: bool = True,
) -> list[dict[str, Any]]:
    return punch.list_plans(db, user, project_id, zone_id, current_only)


@router.post(
    "/projects/{project_id}/quality/floor-plans",
    response_model=QFloorPlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a plan image (PNG / JPEG ≤ 10 MB, edge ≤ 6000 px); `revision_of` revises",
    responses=E,
)
def q1_upload_plan(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    file: Annotated[UploadFile, File()],
    zone_id: Annotated[uuid.UUID | None, Form()] = None,
    level_label: Annotated[str | None, Form(max_length=60)] = None,
    title_en: Annotated[str | None, Form(max_length=150)] = None,
    title_ar: Annotated[str | None, Form(max_length=150)] = None,
    revision: Annotated[str | None, Form(max_length=20)] = None,
    revision_of: Annotated[uuid.UUID | None, Form()] = None,
) -> dict[str, Any]:
    content = file.file.read(PLAN_MAX_BYTES + 1)
    meta = {
        "zone_id": zone_id,
        "level_label": level_label,
        "title_en": title_en,
        "title_ar": title_ar,
        "revision": revision,
    }
    fp = punch.upload_plan(
        db, user, project_id, meta, file.filename or "plan.png", content, revision_of
    )
    return punch.plan_read(db, user, fp)


@router.get(
    "/quality/floor-plans/{plan_id}",
    response_model=QFloorPlanRead,
    summary="A plan with its pins (coloured by status)",
    responses=E,
)
def q1_get_plan(plan_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return punch.plan_read(db, user, punch.get_plan(db, user, plan_id))


@router.get(
    "/quality/floor-plans/{plan_id}/image",
    summary="The plan image",
    responses={
        **E,
        200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}},
    },
    response_class=Response,
)
def q1_plan_image(plan_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    content, ctype, name = punch.plan_image(db, user, plan_id)
    return Response(
        content=content,
        media_type=ctype,
        headers={
            "Content-Disposition": f'inline; filename="{name}"',
            "Cache-Control": "private, max-age=300",
        },
    )
