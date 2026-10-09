"""Drills, musters and real events (spec 6c-emergency-drills §3.10–§3.13, §4.5–§4.7, DP, DR, MU,
EV, PE-2): the drill programme, drill lifecycle and evaluation, musters (roll / count, scans by
users or muster-reader devices, resolutions, the printable sheet), emergency events and the
receiver's resume after a drill suspension."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import DB, CurrentUser, PageParams, bearer_scheme
from app.core.emergency_enums import DrillStatus, DrillType, EventStatus, EventType
from app.core.errors import error_responses
from app.schemas.emergency import (
    CountsInput,
    DrillCreate,
    DrillPage,
    DrillRead,
    DrillTransition,
    DrillUpdate,
    EvaluationInput,
    EventCreate,
    EventPage,
    EventRead,
    EventReviewInput,
    EventTransition,
    EventUpdate,
    MusterDeviceCreate,
    MusterDeviceRead,
    MusterDeviceRegistered,
    MusterEntryRead,
    MusterRead,
    MusterSessionInput,
    MusterSessionRead,
    MusterSheet,
    Programme,
    ResolveInput,
    ScanInput,
    VoidInput,
)
from app.schemas.permits import PermitRead, ShiftStartFields
from app.services.emergency import drills, events, muster, programme
from app.services.emergency import ptw as emergency_ptw

router = APIRouter(tags=["emergency-drills"])


@router.get(
    "/projects/{project_id}/drill-programme",
    response_model=Programme,
    summary="Drill programme lines with due dates (§3.10, DP-1…DP-4; 178)",
    responses=error_responses(401, 403, 404),
)
def get_drill_programme(
    project_id: uuid.UUID, user: CurrentUser, db: DB, as_of: date | None = None
) -> Programme:
    return programme.read_programme(db, user, project_id, as_of)


# ---- drills --------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/drills",
    response_model=DrillPage,
    summary="Drills (178; unannounced drills hidden before start, DR-2)",
    responses=error_responses(401, 403, 404),
)
def list_drills(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    site_id: uuid.UUID | None = None,
    drill_type: Annotated[list[DrillType] | None, Query()] = None,
    status_: Annotated[list[DrillStatus] | None, Query(alias="status")] = None,
) -> DrillPage:
    return drills.list_drills(
        db, user, project_id, site_id, drill_type, status_, pg.page, pg.page_size
    )


@router.post(
    "/projects/{project_id}/drills",
    response_model=DrillRead,
    status_code=status.HTTP_201_CREATED,
    summary="Plan a drill (184; DR-1, DR-3)",
    responses=error_responses(401, 403, 404, 422),
)
def create_drill(project_id: uuid.UUID, body: DrillCreate, user: CurrentUser, db: DB) -> DrillRead:
    return drills.create_drill(db, user, project_id, body)


@router.get(
    "/drills/{drill_id}",
    response_model=DrillRead,
    summary="One drill",
    responses=error_responses(401, 403, 404),
)
def get_drill(drill_id: uuid.UUID, user: CurrentUser, db: DB) -> DrillRead:
    return drills.read_drill(db, user, drill_id)


@router.patch(
    "/drills/{drill_id}",
    response_model=DrillRead,
    summary="Record timings and external participation (185; DR-5 TIMELINE_ORDER)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_drill(drill_id: uuid.UUID, body: DrillUpdate, user: CurrentUser, db: DB) -> DrillRead:
    return drills.update_drill(db, user, drill_id, body)


@router.post(
    "/drills/{drill_id}/transitions",
    response_model=DrillRead,
    summary="Start / conduct / cancel / void a drill (§4.5; DR-4, PE-2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_drill(
    drill_id: uuid.UUID, body: DrillTransition, user: CurrentUser, db: DB
) -> DrillRead:
    return drills.transition_drill(db, user, drill_id, body)


@router.post(
    "/drills/{drill_id}/evaluation",
    response_model=DrillRead,
    summary="Evaluate a Conducted drill (186; DR-6, findings → CAs, result §6.4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def evaluate_drill(
    drill_id: uuid.UUID, body: EvaluationInput, user: CurrentUser, db: DB
) -> DrillRead:
    return drills.evaluate(db, user, drill_id, body)


# ---- musters -------------------------------------------------------------------------------------


@router.get(
    "/musters/{muster_id}",
    response_model=MusterRead,
    summary="A muster with counts; named roll per P6c-4 (reads after Closed are audited)",
    responses=error_responses(401, 403, 404),
)
def get_muster(muster_id: uuid.UUID, user: CurrentUser, db: DB) -> MusterRead:
    return muster.read_muster(db, user, muster_id)


@router.post(
    "/musters/{muster_id}/scan",
    response_model=MusterEntryRead,
    summary="Scan an access card at an assembly point (185; MU-4, MU-5; no gate-log row)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def scan_muster(
    muster_id: uuid.UUID, body: ScanInput, user: CurrentUser, db: DB
) -> MusterEntryRead:
    return muster.scan(db, user, muster_id, body)


@router.post(
    "/musters/{muster_id}/entries/{entry_id}/tick",
    response_model=MusterEntryRead,
    summary="Tick a roll entry as accounted (185)",
    responses=error_responses(401, 403, 404, 409),
)
def tick_muster_entry(
    muster_id: uuid.UUID, entry_id: uuid.UUID, user: CurrentUser, db: DB
) -> MusterEntryRead:
    return muster.tick(db, user, muster_id, entry_id)


@router.post(
    "/musters/{muster_id}/entries/{entry_id}/resolve",
    response_model=MusterEntryRead,
    summary="Resolve an unaccounted entry with a UR reason (185; MU-6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def resolve_muster_entry(
    muster_id: uuid.UUID, entry_id: uuid.UUID, body: ResolveInput, user: CurrentUser, db: DB
) -> MusterEntryRead:
    return muster.resolve(db, user, muster_id, entry_id, body)


@router.put(
    "/musters/{muster_id}/counts",
    response_model=MusterRead,
    summary="Count mode: expected / accounted per engagement and resolutions (185; MU-3)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def put_muster_counts(
    muster_id: uuid.UUID, body: CountsInput, user: CurrentUser, db: DB
) -> MusterRead:
    return muster.put_counts(db, user, muster_id, body)


@router.get(
    "/musters/{muster_id}/sheet",
    response_model=MusterSheet,
    summary="Printable muster sheet for an Open muster (185; MU-9, audited export)",
    responses=error_responses(401, 403, 404, 409),
)
def get_muster_sheet(muster_id: uuid.UUID, user: CurrentUser, db: DB) -> MusterSheet:
    return muster.sheet(db, user, muster_id)


@router.post(
    "/musters/{muster_id}/void",
    response_model=MusterRead,
    summary="Void a muster (190)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_muster(muster_id: uuid.UUID, body: VoidInput, user: CurrentUser, db: DB) -> MusterRead:
    return muster.void(db, user, muster_id, body)


@router.post(
    "/projects/{project_id}/muster-devices",
    response_model=MusterDeviceRegistered,
    status_code=status.HTTP_201_CREATED,
    summary="Register a muster_reader device bound to an assembly point (182; §11.3)",
    responses=error_responses(401, 403, 404, 422),
)
def register_muster_device(
    project_id: uuid.UUID, body: MusterDeviceCreate, user: CurrentUser, db: DB
) -> MusterDeviceRegistered:
    return muster.register_device(db, user, project_id, body)


@router.post(
    "/muster-devices/{device_pk}/revoke",
    response_model=MusterDeviceRead,
    summary="Revoke a muster_reader device (182)",
    responses=error_responses(401, 403, 404, 409),
)
def revoke_muster_device(device_pk: uuid.UUID, user: CurrentUser, db: DB) -> MusterDeviceRead:
    return muster.revoke_device(db, user, device_pk)


@router.post(
    "/emergency/muster-session",
    response_model=MusterSessionRead,
    summary="Exchange a muster_reader device token for a session (scan endpoint only)",
    responses=error_responses(401),
)
def muster_device_session(body: MusterSessionInput, db: DB) -> MusterSessionRead:
    return muster.device_session(db, body)


@router.post(
    "/emergency/muster-scan",
    response_model=MusterEntryRead,
    summary="Device scan at its assembly point into the open muster (MU-4; 403 for another AP)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def muster_device_scan(
    body: ScanInput,
    db: DB,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
) -> MusterEntryRead:
    return muster.device_scan(db, bearer.credentials if bearer else None, body)


# ---- events --------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/emergency-events",
    response_model=EventPage,
    summary="Real emergency events (178)",
    responses=error_responses(401, 403, 404),
)
def list_emergency_events(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    event_type: Annotated[list[EventType] | None, Query()] = None,
    status_: Annotated[list[EventStatus] | None, Query(alias="status")] = None,
) -> EventPage:
    return events.list_events(db, user, project_id, event_type, status_, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/emergency-events",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Declare an emergency (187; EV-1…EV-3, PE-1 suspensions, alerts within 60 s)",
    responses=error_responses(401, 403, 404, 422),
)
def declare_emergency_event(
    project_id: uuid.UUID, body: EventCreate, user: CurrentUser, db: DB
) -> EventRead:
    return events.declare(db, user, project_id, body)


@router.get(
    "/emergency-events/{event_id}",
    response_model=EventRead,
    summary="One event with response times (§6.7)",
    responses=error_responses(401, 403, 404),
)
def get_emergency_event(event_id: uuid.UUID, user: CurrentUser, db: DB) -> EventRead:
    return events.read_event(db, user, event_id)


@router.patch(
    "/emergency-events/{event_id}",
    response_model=EventRead,
    summary="Record the timeline, external services and the incident link (187)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_emergency_event(
    event_id: uuid.UUID, body: EventUpdate, user: CurrentUser, db: DB
) -> EventRead:
    return events.update_event(db, user, event_id, body)


@router.post(
    "/emergency-events/{event_id}/transitions",
    response_model=EventRead,
    summary="All Clear (188) or void (190) (§4.6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_emergency_event(
    event_id: uuid.UUID, body: EventTransition, user: CurrentUser, db: DB
) -> EventRead:
    return events.transition(db, user, event_id, body)


@router.post(
    "/emergency-events/{event_id}/review",
    response_model=EventRead,
    summary="Review an event after All Clear (188, not site engineers; EV-4, EV-5)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def review_emergency_event(
    event_id: uuid.UUID, body: EventReviewInput, user: CurrentUser, db: DB
) -> EventRead:
    return events.review(db, user, event_id, body)


# ---- Phase 3 -------------------------------------------------------------------------------------


@router.post(
    "/permits/{permit_id}/drill-resume",
    response_model=PermitRead,
    summary="Receiver resumes a permit suspended `emergency_drill` after the drill (PE-2)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def drill_resume_permit(
    permit_id: uuid.UUID, body: ShiftStartFields, user: CurrentUser, db: DB
) -> PermitRead:
    return emergency_ptw.drill_resume(db, user, permit_id, body)
