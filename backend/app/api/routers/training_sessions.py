"""Training sessions, nominations, attendance and assessment (spec 5-training §3.6, §3.7, §4.4,
§4.5, SS-1…SS-10, AT-1…AT-7)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.train_enums import SessionStatus
from app.schemas.training_common import COURSE_CODE
from app.schemas.training_sessions import (
    AssessmentUpdate,
    AttendanceSignature,
    AttendanceUpdate,
    NominationCreate,
    NominationList,
    NominationRead,
    NominationWithdraw,
    SessionClose,
    SessionCreate,
    SessionFromPlan,
    SessionPage,
    SessionRead,
    SessionTransitionRequest,
    SessionUpdate,
    SessionVoid,
)
from app.services.train import sessions

router = APIRouter(tags=["training-sessions"])


@router.get(
    "/projects/{project_id}/training-sessions",
    response_model=SessionPage,
    summary="Session calendar / register (capability 125; no attendee names)",
    responses=error_responses(401, 403, 404, 422),
)
def list_training_sessions(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[SessionStatus] | None, Query(alias="status")] = None,
    course_code: Annotated[str | None, Query(pattern=COURSE_CODE)] = None,
    provider_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    close_overdue: bool | None = None,
    trainer_user_id: uuid.UUID | None = None,
) -> SessionPage:
    return sessions.list_sessions(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        status_,
        course_code,
        provider_id,
        date_from,
        date_to,
        close_overdue,
        trainer_user_id,
    )


@router.post(
    "/projects/{project_id}/training-sessions",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a session (capability 132) → Draft",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_training_session(
    project_id: uuid.UUID, body: SessionCreate, user: CurrentUser, db: DB
) -> SessionRead:
    return sessions.create_session(db, user, project_id, body)


@router.post(
    "/projects/{project_id}/training-sessions/from-plan",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Draft session pre-filled from the refresher plan (GP-4; capability 132)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_training_session_from_plan(
    project_id: uuid.UUID, body: SessionFromPlan, user: CurrentUser, db: DB
) -> SessionRead:
    return sessions.create_from_plan(db, user, project_id, body)


@router.get(
    "/training-sessions/{session_id}",
    response_model=SessionRead,
    summary="Session detail",
    responses=error_responses(401, 403, 404),
)
def get_training_session(session_id: uuid.UUID, user: CurrentUser, db: DB) -> SessionRead:
    return sessions.get_session(db, user, session_id)


@router.patch(
    "/training-sessions/{session_id}",
    response_model=SessionRead,
    summary="Edit a Draft session or reschedule a Scheduled one before day 1 (capability 132)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_training_session(
    session_id: uuid.UUID, body: SessionUpdate, user: CurrentUser, db: DB
) -> SessionRead:
    return sessions.update_session(db, user, session_id, body)


@router.post(
    "/training-sessions/{session_id}/transitions",
    response_model=SessionRead,
    summary="Schedule / record as delivered (SS-5) / cancel (capability 132, §4.4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_training_session(
    session_id: uuid.UUID, body: SessionTransitionRequest, user: CurrentUser, db: DB
) -> SessionRead:
    return sessions.transition(db, user, session_id, body)


@router.post(
    "/training-sessions/{session_id}/close",
    response_model=SessionRead,
    summary="Close a Delivered session and issue records (SS-8, TR-14; capability 135, closer "
    "≠ trainer / assessor)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def close_training_session(
    session_id: uuid.UUID, body: SessionClose, user: CurrentUser, db: DB
) -> SessionRead:
    return sessions.close(db, user, session_id, body)


@router.post(
    "/training-sessions/{session_id}/void",
    response_model=SessionRead,
    summary="Void a Closed session; every issued record Revoked (SS-9; capability 145)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_training_session(
    session_id: uuid.UUID, body: SessionVoid, user: CurrentUser, db: DB
) -> SessionRead:
    return sessions.void(db, user, session_id, body)


# ---- nominations and attendance -------------------------------------------------------------


@router.get(
    "/training-sessions/{session_id}/nominations",
    response_model=NominationList,
    summary="Nominees with attendance and results (capability 136; names per 46; scores per AT-7)",
    responses=error_responses(401, 403, 404),
)
def list_training_nominations(session_id: uuid.UUID, user: CurrentUser, db: DB) -> NominationList:
    return sessions.list_nominations(db, user, session_id)


@router.post(
    "/training-sessions/{session_id}/nominations",
    response_model=NominationList,
    status_code=status.HTTP_201_CREATED,
    summary="Nominate workers (capability 133; SS-6, all-or-nothing — 422 with meta.errors)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_training_nominations(
    session_id: uuid.UUID, body: NominationCreate, user: CurrentUser, db: DB
) -> NominationList:
    return sessions.create_nominations(db, user, session_id, body)


@router.post(
    "/training-nominations/{nomination_id}/withdraw",
    response_model=NominationRead,
    summary="Withdraw a nominee before day 1 (capability 133)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def withdraw_training_nomination(
    nomination_id: uuid.UUID, body: NominationWithdraw, user: CurrentUser, db: DB
) -> NominationRead:
    return sessions.withdraw(db, user, nomination_id, body)


@router.put(
    "/training-sessions/{session_id}/attendance",
    response_model=NominationList,
    summary="Record attendance per day (SS-7; capability 134 or a user trainer of the session)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_training_attendance(
    session_id: uuid.UUID, body: AttendanceUpdate, user: CurrentUser, db: DB
) -> NominationList:
    return sessions.record_attendance(db, user, session_id, body)


@router.put(
    "/training-sessions/{session_id}/assessments",
    response_model=NominationList,
    summary="Record theory scores and practical results (AT-2, AT-3; capability 134; practical "
    "by an assessor of the session)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_training_assessments(
    session_id: uuid.UUID, body: AssessmentUpdate, user: CurrentUser, db: DB
) -> NominationList:
    return sessions.record_assessments(db, user, session_id, body)


@router.post(
    "/training-nominations/{nomination_id}/signature",
    response_model=NominationRead,
    summary="Attach the attendee's on-device signature (SS-8; capability 134 or a user trainer)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def sign_training_nomination(
    nomination_id: uuid.UUID, body: AttendanceSignature, user: CurrentUser, db: DB
) -> NominationRead:
    return sessions.sign(db, user, nomination_id, body)
