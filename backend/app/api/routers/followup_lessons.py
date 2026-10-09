"""Lessons learned: library, drafting, review and publication, distribution and acknowledgement,
6d links, similar lessons and effectiveness checks (spec 6f-incident-followup §3.6-§3.9, §4.4, LL,
DS, LK, EF)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.followup_enums import FuCheckStatus, FuDistributionStatus, FuLessonStatus
from app.core.hse_enums import Activity, DangerousOccurrenceCategory, Mechanism, Trade
from app.schemas.followup import (
    FuAckRequest,
    FuCheckComplete,
    FuCheckPage,
    FuCheckRead,
    FuDistributionList,
    FuDistributionRead,
    FuLessonCreate,
    FuLessonPage,
    FuLessonRead,
    FuLessonTransition,
    FuLessonUpdate,
    FuLinkCreate,
    FuLinkDecision,
    FuLinkPage,
    FuLinkRead,
    FuSimilarLessons,
)
from app.services.followup import effectiveness, lessons

router = APIRouter(tags=["lessons-learned"])


@router.get(
    "/lessons",
    response_model=FuLessonPage,
    summary="Lesson library and drafts (222; LL-5 Arabic-normalised search)",
    description="Published and Archived lessons for every 222 holder; drafts and lessons in "
    "review only for 219 / 220 holders (`status`). `q` searches EN and AR text (diacritics "
    "removed; أ إ آ → ا; ة → ه; ى → ي; leading ال ignored).",
    responses=error_responses(401, 403),
)
def list_lessons(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    q: str | None = Query(default=None, max_length=200),
    status_: Annotated[list[FuLessonStatus] | None, Query(alias="status")] = None,
    activity: Activity | None = None,
    mechanism: Mechanism | None = None,
    do_category: DangerousOccurrenceCategory | None = None,
    root_cause_code: str | None = None,
    zone_type: str | None = None,
    trade: Trade | None = None,
    project_id: uuid.UUID | None = None,
    year: int | None = None,
) -> FuLessonPage:
    return lessons.library(
        db, user, q, status_, activity, mechanism, do_category, root_cause_code, zone_type, trade,
        project_id, year, pg.page, pg.page_size,
    )  # fmt: skip


@router.post(
    "/lessons",
    response_model=FuLessonRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a manual lesson Draft (219)",
    responses=error_responses(401, 403, 404, 422),
)
def create_lesson(body: FuLessonCreate, user: CurrentUser, db: DB) -> FuLessonRead:
    return lessons.create(db, user, body)


@router.get(
    "/lessons/{lesson_id}",
    response_model=FuLessonRead,
    summary="One lesson",
    responses=error_responses(401, 403, 404),
)
def get_lesson(lesson_id: uuid.UUID, user: CurrentUser, db: DB) -> FuLessonRead:
    return lessons.read(db, user, lesson_id)


@router.patch(
    "/lessons/{lesson_id}",
    response_model=FuLessonRead,
    summary="Edit a Draft lesson (219; 422 IDENTITY_IN_TEXT, P6f-3)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_lesson(
    lesson_id: uuid.UUID, body: FuLessonUpdate, user: CurrentUser, db: DB
) -> FuLessonRead:
    return lessons.update(db, user, lesson_id, body)


@router.delete(
    "/lessons/{lesson_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a manual Draft (author only; system drafts are archived by 220)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_lesson(lesson_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    lessons.delete(db, user, lesson_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/lessons/{lesson_id}/transitions",
    response_model=FuLessonRead,
    summary="Submit (219), return / publish / archive (220) a lesson (§4.4)",
    description="422 LESSON_INCOMPLETE (with `meta.missing`), REDACTION_NOT_CONFIRMED, "
    "SELF_APPROVAL, NOT_DISTRIBUTED, IDENTITY_IN_TEXT.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_lesson(
    lesson_id: uuid.UUID, body: FuLessonTransition, user: CurrentUser, db: DB
) -> FuLessonRead:
    return lessons.transition(db, user, lesson_id, body)


@router.get(
    "/lessons/{lesson_id}/distribution",
    response_model=FuDistributionList,
    summary="Distribution status of a lesson (DS-1)",
    responses=error_responses(401, 403, 404),
)
def get_lesson_distribution(lesson_id: uuid.UUID, user: CurrentUser, db: DB) -> FuDistributionList:
    return lessons.distribution(db, user, lesson_id)


@router.get(
    "/projects/{project_id}/lesson-distribution",
    response_model=FuDistributionList,
    summary="Distribution items of a project (reps see their scope; 215 / 221)",
    responses=error_responses(401, 403, 404),
)
def list_project_lesson_distribution(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    status_: Annotated[list[FuDistributionStatus] | None, Query(alias="status")] = None,
) -> FuDistributionList:
    return lessons.project_distribution(db, user, project_id, status_)


@router.post(
    "/lesson-distribution/{item_id}/acknowledge",
    response_model=FuDistributionRead,
    summary="Acknowledge a lesson for an engagement (221; DS-3, 422 ON_BEHALF_NOTE_REQUIRED)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def acknowledge_lesson(
    item_id: uuid.UUID, body: FuAckRequest, user: CurrentUser, db: DB
) -> FuDistributionRead:
    return lessons.acknowledge(db, user, item_id, body)


@router.get(
    "/lessons/{lesson_id}/links",
    response_model=FuLinkPage,
    summary="6d links and template change requests of a lesson",
    responses=error_responses(401, 403, 404),
)
def list_lesson_links(lesson_id: uuid.UUID, user: CurrentUser, db: DB) -> FuLinkPage:
    return lessons.links(db, user, lesson_id)


@router.post(
    "/lessons/{lesson_id}/links",
    response_model=FuLinkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Link a 6d topic, open a topic / campaign Draft, or raise a change request (219)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def add_lesson_link(
    lesson_id: uuid.UUID, body: FuLinkCreate, user: CurrentUser, db: DB
) -> FuLinkRead:
    return lessons.add_link(db, user, lesson_id, body)


@router.get(
    "/template-change-requests",
    response_model=FuLinkPage,
    summary="Open template change requests for the 6d library (192 / 193; LK-3)",
    responses=error_responses(401, 403),
)
def list_template_change_requests(
    user: CurrentUser, db: DB, template_code: str | None = None
) -> FuLinkPage:
    return lessons.change_requests(db, user, template_code)


@router.post(
    "/lesson-links/{link_id}/reject",
    response_model=FuLinkRead,
    summary="Reject a template change request (193, reason ≥ 20 chars; LK-3)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def reject_lesson_link(
    link_id: uuid.UUID, body: FuLinkDecision, user: CurrentUser, db: DB
) -> FuLinkRead:
    return lessons.reject_link(db, user, link_id, body)


@router.get(
    "/incidents/{incident_id}/similar-lessons",
    response_model=FuSimilarLessons,
    summary="Up to 3 similar Published lessons (LL-6)",
    responses=error_responses(401, 403, 404),
)
def get_similar_lessons(incident_id: uuid.UUID, user: CurrentUser, db: DB) -> FuSimilarLessons:
    return lessons.similar(db, user, incident_id)


@router.get(
    "/projects/{project_id}/effectiveness-checks",
    response_model=FuCheckPage,
    summary="Effectiveness register (215)",
    responses=error_responses(401, 403, 404),
)
def list_effectiveness_checks(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[FuCheckStatus] | None, Query(alias="status")] = None,
) -> FuCheckPage:
    return effectiveness.list_checks(db, user, project_id, status_, pg.page, pg.page_size)


@router.get(
    "/effectiveness-checks/{check_id}",
    response_model=FuCheckRead,
    summary="One effectiveness check with the current facts and suggestion (EF-2, EF-3)",
    responses=error_responses(401, 403, 404),
)
def get_effectiveness_check(check_id: uuid.UUID, user: CurrentUser, db: DB) -> FuCheckRead:
    return effectiveness.read_check(db, user, check_id)


@router.post(
    "/effectiveness-checks/{check_id}/complete",
    response_model=FuCheckRead,
    summary="Complete a check (223; 422 RATIONALE_REQUIRED, FOLLOW_UP_REQUIRED)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def complete_effectiveness_check(
    check_id: uuid.UUID, body: FuCheckComplete, user: CurrentUser, db: DB
) -> FuCheckRead:
    return effectiveness.complete(db, user, check_id, body)
