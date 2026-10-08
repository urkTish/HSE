"""SIMOPS: conflict check, conflicts and coordination (spec 3-ptw §3.12, §4.8, §5.6,
§6.4, §6.5)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.ptw_enums import SimopsConflictStatus, SimopsResult
from app.schemas.simops import (
    CoordinationCreate,
    CoordinationSignInput,
    SimopsCheckResult,
    SimopsConflictPage,
    SimopsConflictRead,
    SimopsPreviewRequest,
)
from app.services.ptw import simops as svc

router = APIRouter(tags=["simops"])


@router.post(
    "/projects/{project_id}/simops-check",
    response_model=SimopsCheckResult,
    summary="SIMOPS preview for unsaved permit data (nothing stored)",
    responses=error_responses(401, 403, 404, 422),
)
def preview_simops_check(
    project_id: uuid.UUID,
    body: SimopsPreviewRequest,
    user: CurrentUser,
    db: DB,
) -> SimopsCheckResult:
    return svc.preview(db, user, project_id, body)


@router.post(
    "/permits/{permit_id}/simops-check",
    response_model=SimopsCheckResult,
    summary="Run the SIMOPS check for a permit (conflicts stored)",
    responses=error_responses(401, 403, 404, 409),
)
def run_permit_simops_check(permit_id: uuid.UUID, user: CurrentUser, db: DB) -> SimopsCheckResult:
    return svc.run_for_permit(db, user, permit_id)


@router.get(
    "/projects/{project_id}/simops-conflicts",
    response_model=SimopsConflictPage,
    summary="SIMOPS conflict register",
    responses=error_responses(401, 403, 404, 422),
)
def list_simops_conflicts(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[SimopsConflictStatus] | None, Query(alias="status")] = None,
    result: SimopsResult | None = None,
    permit_id: uuid.UUID | None = None,
    zone_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    awaiting_me: bool = False,
    detected_from: datetime | None = None,
    detected_to: datetime | None = None,
) -> SimopsConflictPage:
    return svc.list_conflicts(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        status_,
        result,
        permit_id,
        zone_id,
        awaiting_me,
        detected_from,
        detected_to,
    )


@router.get(
    "/simops-conflicts/{conflict_id}",
    response_model=SimopsConflictRead,
    summary="Get a SIMOPS conflict",
    responses=error_responses(401, 403, 404),
)
def get_simops_conflict(conflict_id: uuid.UUID, user: CurrentUser, db: DB) -> SimopsConflictRead:
    return svc.read(db, user, conflict_id)


@router.post(
    "/simops-conflicts/{conflict_id}/coordination",
    response_model=SimopsConflictRead,
    status_code=status.HTTP_201_CREATED,
    summary="Coordination record for a conditional conflict (capability 97; signed)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_simops_coordination(
    conflict_id: uuid.UUID,
    body: CoordinationCreate,
    user: CurrentUser,
    db: DB,
) -> SimopsConflictRead:
    return svc.create_coordination(db, user, conflict_id, body)


@router.post(
    "/simops-coordinations/{coordination_id}/sign",
    response_model=SimopsConflictRead,
    summary="Add the caller's signature to a coordination record (signed)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def sign_simops_coordination(
    coordination_id: uuid.UUID,
    body: CoordinationSignInput,
    user: CurrentUser,
    db: DB,
) -> SimopsConflictRead:
    return svc.sign(db, user, coordination_id, body)
