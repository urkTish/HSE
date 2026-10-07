"""Induction courses and records, zone access profiles, eligibility and hook providers
(spec 2-access-permits §3.3-§3.5, §4.3, §5.2, §5.3)."""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.access_enums import EligibilityContext, InductionStatus, InductionType
from app.core.errors import error_responses
from app.schemas.inductions import (
    EligibilityResult,
    HookProviderInfo,
    InductionCourseCreate,
    InductionCourseList,
    InductionCourseRead,
    InductionCourseUpdate,
    InductionCourseVersionPublish,
    InductionRecordCreate,
    InductionRecordPage,
    InductionRecordRead,
    InductionRecordUpdate,
    InductionRetrainingNote,
    InductionRetrainingNoteRead,
    InductionSessionCreate,
    InductionSessionResult,
    ZoneAccessProfileList,
    ZoneAccessProfileRead,
    ZoneAccessProfileUpdate,
)
from app.services.access import inductions as svc
from app.services.access import profiles

router = APIRouter(tags=["inductions"])


# ---- courses ------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/induction-courses",
    response_model=InductionCourseList,
    summary="Induction courses of a project",
    responses=error_responses(401, 403, 404),
)
def list_induction_courses(
    project_id: uuid.UUID, user: CurrentUser, db: DB, active: bool | None = None
) -> InductionCourseList:
    return svc.list_courses(db, user, project_id, active)


@router.post(
    "/projects/{project_id}/induction-courses",
    response_model=InductionCourseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an induction course (capability 50)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_induction_course(
    project_id: uuid.UUID, body: InductionCourseCreate, user: CurrentUser, db: DB
) -> InductionCourseRead:
    return svc.create_course(db, user, project_id, body)


@router.get(
    "/induction-courses/{course_id}",
    response_model=InductionCourseRead,
    summary="Get an induction course",
    responses=error_responses(401, 403, 404),
)
def get_induction_course(course_id: uuid.UUID, user: CurrentUser, db: DB) -> InductionCourseRead:
    return svc.read_course(db, user, course_id)


@router.patch(
    "/induction-courses/{course_id}",
    response_model=InductionCourseRead,
    summary="Edit an induction course (capability 50)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_induction_course(
    course_id: uuid.UUID, body: InductionCourseUpdate, user: CurrentUser, db: DB
) -> InductionCourseRead:
    return svc.update_course(db, user, course_id, body)


@router.post(
    "/induction-courses/{course_id}/versions",
    response_model=InductionCourseRead,
    summary="Publish a new course version (capability 50; IN-9 re-induction)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def publish_induction_course_version(
    course_id: uuid.UUID, body: InductionCourseVersionPublish, user: CurrentUser, db: DB
) -> InductionCourseRead:
    return svc.publish_version(db, user, course_id, body)


# ---- records ------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/inductions",
    response_model=InductionRecordPage,
    summary="Induction register (capability 46 in scope)",
    responses=error_responses(401, 403, 404, 422),
)
def list_inductions(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    worker_id: uuid.UUID | None = None,
    course_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    induction_type: InductionType | None = None,
    status_: Annotated[list[InductionStatus] | None, Query(alias="status")] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    language_mismatch: Annotated[
        bool | None, Query(description="Action panel: IN-6 records (last 30 days with since).")
    ] = None,
    expiring_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    delivered_from: date | None = None,
    delivered_to: date | None = None,
    session_ref: Annotated[str | None, Query(max_length=30)] = None,
) -> InductionRecordPage:
    return svc.list_records(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        worker_id,
        course_id,
        induction_type,
        status_,
        engagement_id,
        include_subcontractors,
        language_mismatch,
        expiring_within_days,
        delivered_from,
        delivered_to,
        session_ref,
    )


@router.post(
    "/projects/{project_id}/inductions",
    response_model=InductionRecordRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record an induction attendance/result (capability 51)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_induction(
    project_id: uuid.UUID, body: InductionRecordCreate, user: CurrentUser, db: DB
) -> InductionRecordRead:
    return svc.create_record(db, user, project_id, body)


@router.post(
    "/projects/{project_id}/induction-sessions",
    response_model=InductionSessionResult,
    status_code=status.HTTP_201_CREATED,
    summary="Record a whole session (several attendees) in one call (capability 51)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_induction_session(
    project_id: uuid.UUID, body: InductionSessionCreate, user: CurrentUser, db: DB
) -> InductionSessionResult:
    return svc.create_session(db, user, project_id, body)


@router.post(
    "/projects/{project_id}/induction-retraining-notes",
    response_model=InductionRetrainingNoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a re-training note after the attempt limit (HSE Officer, IN-5)",
    responses=error_responses(401, 403, 404, 422),
)
def create_induction_retraining_note(
    project_id: uuid.UUID, body: InductionRetrainingNote, user: CurrentUser, db: DB
) -> InductionRetrainingNoteRead:
    return svc.retraining_note(db, user, project_id, body)


@router.get(
    "/inductions/{induction_id}",
    response_model=InductionRecordRead,
    summary="Get an induction record",
    responses=error_responses(401, 403, 404),
)
def get_induction(induction_id: uuid.UUID, user: CurrentUser, db: DB) -> InductionRecordRead:
    return svc.read_record(db, user, induction_id)


@router.patch(
    "/inductions/{induction_id}",
    response_model=InductionRecordRead,
    summary="Correct an induction record (after 24 h HSE Manager with reason, IN-11)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_induction(
    induction_id: uuid.UUID, body: InductionRecordUpdate, user: CurrentUser, db: DB
) -> InductionRecordRead:
    return svc.update_record(db, user, induction_id, body)


# ---- zone access profiles, eligibility, hooks ----------------------------------------------------


@router.get(
    "/projects/{project_id}/zone-access-profiles",
    response_model=ZoneAccessProfileList,
    summary="Access profiles of every zone of a project",
    responses=error_responses(401, 403, 404),
)
def list_zone_access_profiles(
    project_id: uuid.UUID, user: CurrentUser, db: DB, site_id: uuid.UUID | None = None
) -> ZoneAccessProfileList:
    return profiles.list_for(db, user, project_id, site_id)


@router.get(
    "/zones/{zone_id}/access-profile",
    response_model=ZoneAccessProfileRead,
    summary="Access profile of a zone (defaults per ZP-1)",
    responses=error_responses(401, 403, 404),
)
def get_zone_access_profile(zone_id: uuid.UUID, user: CurrentUser, db: DB) -> ZoneAccessProfileRead:
    return profiles.read(db, user, zone_id)


@router.patch(
    "/zones/{zone_id}/access-profile",
    response_model=ZoneAccessProfileRead,
    summary="Tighten a zone access profile (capability 81; ZP-2 PROFILE_LOOSENING)",
    responses=error_responses(401, 403, 404, 422),
)
def update_zone_access_profile(
    zone_id: uuid.UUID, body: ZoneAccessProfileUpdate, user: CurrentUser, db: DB
) -> ZoneAccessProfileRead:
    return profiles.update(db, user, zone_id, body)


@router.get(
    "/workers/{worker_id}/eligibility",
    response_model=EligibilityResult,
    summary="Evaluate E(worker, zone, at, context) (ZP-3/ZP-4)",
    description="Read-only. context `check` (default) skips the WAP step; `gate` includes it. "
    "Hook items under `warn` policy come back as status warn / HOOK_NOT_AVAILABLE.",
    responses=error_responses(401, 403, 404, 422),
)
def get_worker_eligibility(
    worker_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    zone_id: uuid.UUID,
    at: Annotated[datetime | None, Query(description="UTC; default now.")] = None,
    context: EligibilityContext = EligibilityContext.check,
) -> EligibilityResult:
    return svc.worker_eligibility(db, user, worker_id, zone_id, at, context)


@router.get(
    "/hook-providers",
    response_model=list[HookProviderInfo],
    summary="Phase 3/4/5/6 hook providers and the project's policy per kind (HK-3, HK-4)",
    responses=error_responses(401, 403, 404),
)
def list_hook_providers(user: CurrentUser, db: DB, project_id: uuid.UUID) -> list[HookProviderInfo]:
    return svc.hook_providers(db, user, project_id)
