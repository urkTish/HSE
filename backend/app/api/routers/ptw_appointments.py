"""PTW appointments (spec 3-ptw §3.4, §4.7, PR-1…PR-10)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses, not_implemented
from app.core.ptw_enums import AppointmentDiscipline, AppointmentFunction, AppointmentStatus
from app.schemas.ptw_appointments import (
    AppointmentCreate,
    AppointmentPage,
    AppointmentRead,
    AppointmentTransition,
    AppointmentUpdate,
)

router = APIRouter(tags=["ptw-appointments"])


@router.get(
    "/projects/{project_id}/ptw-appointments",
    response_model=AppointmentPage,
    summary="Appointment register (capability 82; worker holder names need capability 46)",
    responses=error_responses(401, 403, 404, 422),
)
def list_ptw_appointments(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    function: Annotated[list[AppointmentFunction] | None, Query()] = None,
    discipline: AppointmentDiscipline | None = None,
    status_: Annotated[list[AppointmentStatus] | None, Query(alias="status")] = None,
    holder_user_id: uuid.UUID | None = None,
    holder_worker_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    expiring_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> AppointmentPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/ptw-appointments",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Appoint a person (capability 100; issuer appointments HSE Manager only → 403)",
    responses=error_responses(401, 403, 404, 422),
)
def create_ptw_appointment(
    project_id: uuid.UUID, body: AppointmentCreate, user: CurrentUser, db: DB
) -> AppointmentRead:
    raise not_implemented()


@router.get(
    "/ptw-appointments/{appointment_id}",
    response_model=AppointmentRead,
    summary="Get an appointment",
    responses=error_responses(401, 403, 404),
)
def get_ptw_appointment(appointment_id: uuid.UUID, user: CurrentUser, db: DB) -> AppointmentRead:
    raise not_implemented()


@router.patch(
    "/ptw-appointments/{appointment_id}",
    response_model=AppointmentRead,
    summary="Edit an appointment (capability 100; re-evaluates live permits, PR-8)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_ptw_appointment(
    appointment_id: uuid.UUID, body: AppointmentUpdate, user: CurrentUser, db: DB
) -> AppointmentRead:
    raise not_implemented()


@router.post(
    "/ptw-appointments/{appointment_id}/transitions",
    response_model=AppointmentRead,
    summary="Suspend / reinstate / revoke an appointment (§4.7; capability 100)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_ptw_appointment(
    appointment_id: uuid.UUID, body: AppointmentTransition, user: CurrentUser, db: DB
) -> AppointmentRead:
    raise not_implemented()
