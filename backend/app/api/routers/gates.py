"""Gates, gate devices, QR gate checks and the gate log (spec 2-access-permits §3.19, §3.20,
§5.10)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.api.gate_deps import GateCallerDep
from app.core.access_enums import GateDirection, GateReasonCode, GateResult, GateSubjectKind
from app.core.errors import error_responses, not_implemented
from app.schemas.gates import (
    AdmittedDespiteDenialRequest,
    GateCallerContext,
    GateCheckRequest,
    GateCheckResponse,
    GateCreate,
    GateDeviceCreate,
    GateDeviceLogin,
    GateDeviceRead,
    GateDeviceRegistered,
    GateDeviceSession,
    GateList,
    GateLogEntry,
    GateLogPage,
    GateRead,
    GateUpdate,
    PairingRead,
)

router = APIRouter(tags=["gates"])

# ---- gates and devices --------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/gates",
    response_model=GateList,
    summary="Gates of a project with their devices",
    responses=error_responses(401, 403, 404),
)
def list_gates(project_id: uuid.UUID, user: CurrentUser, db: DB) -> GateList:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/gates",
    response_model=GateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a gate (capability 75)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_gate(project_id: uuid.UUID, body: GateCreate, user: CurrentUser, db: DB) -> GateRead:
    raise not_implemented()


@router.get(
    "/gates/{gate_id}",
    response_model=GateRead,
    summary="Get a gate",
    responses=error_responses(401, 403, 404),
)
def get_gate(gate_id: uuid.UUID, user: CurrentUser, db: DB) -> GateRead:
    raise not_implemented()


@router.patch(
    "/gates/{gate_id}",
    response_model=GateRead,
    summary="Edit a gate (capability 75)",
    responses=error_responses(401, 403, 404, 422),
)
def update_gate(gate_id: uuid.UUID, body: GateUpdate, user: CurrentUser, db: DB) -> GateRead:
    raise not_implemented()


@router.post(
    "/gates/{gate_id}/devices",
    response_model=GateDeviceRegistered,
    status_code=status.HTTP_201_CREATED,
    summary="Register a gate device; returns its device token once (capability 75)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def register_gate_device(
    gate_id: uuid.UUID, body: GateDeviceCreate, user: CurrentUser, db: DB
) -> GateDeviceRegistered:
    raise not_implemented()


@router.post(
    "/gates/{gate_id}/devices/{device_pk}/revoke",
    response_model=GateDeviceRead,
    summary="Revoke a gate device and end its sessions (capability 75)",
    responses=error_responses(401, 403, 404, 409),
)
def revoke_gate_device(
    gate_id: uuid.UUID, device_pk: uuid.UUID, user: CurrentUser, db: DB
) -> GateDeviceRead:
    raise not_implemented()


@router.post(
    "/gate-device/login",
    response_model=GateDeviceSession,
    summary="Start a gate-device session with the device token (no user login)",
    description="Sets the httpOnly cookie `hse_gate_session` and returns the same token for "
    "`Authorization: Bearer`. The session can only call /gate-checks/* (any other endpoint → "
    "403 GATE_DEVICE_FORBIDDEN); 12 h idle timeout; revoked with the device (401 "
    "GATE_DEVICE_REVOKED).",
    responses=error_responses(401, 422, 429),
)
def gate_device_login(body: GateDeviceLogin, response: Response, db: DB) -> GateDeviceSession:
    raise not_implemented()


@router.post(
    "/gate-device/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End the gate-device session",
    responses=error_responses(401),
)
def gate_device_logout(caller: GateCallerDep, response: Response, db: DB) -> None:
    raise not_implemented()


# ---- gate checks (user with capability 74, or a gate-device session) -----------------------------


@router.get(
    "/gate-checks/context",
    response_model=GateCallerContext,
    summary="Gates the caller may scan at (device: its own gate) and screen timings",
    responses=error_responses(401, 403),
)
def get_gate_context(
    caller: GateCallerDep, db: DB, project_id: uuid.UUID | None = None
) -> GateCallerContext:
    raise not_implemented()


@router.post(
    "/gate-checks",
    response_model=GateCheckResponse,
    response_model_exclude_unset=True,
    summary="Scan a QR (or typed printed ref) at a gate and get the verdict (GC-2…GC-13)",
    description="Every call writes an immutable gate-log row (GC-12). Rate limit 120/min per "
    "device or user (429 GATE_RATE_LIMITED). Lost/revoked/rotated tokens return DENIED "
    "CREDENTIAL_LOST / CREDENTIAL_REVOKED and alert the HSE Officer (LC-12).",
    responses=error_responses(401, 403, 404, 422, 429),
)
def gate_check(body: GateCheckRequest, caller: GateCallerDep, db: DB) -> GateCheckResponse:
    raise not_implemented()


@router.get(
    "/gate-checks/pairings/{pairing_id}",
    response_model=PairingRead,
    summary="Poll a pending escort/driver/escort-vehicle pairing (finalises on timeout)",
    responses=error_responses(401, 403, 404),
)
def get_gate_pairing(pairing_id: uuid.UUID, caller: GateCallerDep, db: DB) -> PairingRead:
    raise not_implemented()


@router.post(
    "/gate-checks/pairings/{pairing_id}/cancel",
    response_model=PairingRead,
    summary="Cancel a pending pairing (the started subject is DENIED ESCORT_REQUIRED etc.)",
    responses=error_responses(401, 403, 404, 409),
)
def cancel_gate_pairing(pairing_id: uuid.UUID, caller: GateCallerDep, db: DB) -> PairingRead:
    raise not_implemented()


@router.post(
    "/gate-checks/{check_id}/admitted-despite-denial",
    response_model=GateLogEntry,
    summary="Record that a DENIED subject was admitted anyway (GC-14; alerts immediately)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_admitted_despite_denial(
    check_id: uuid.UUID, body: AdmittedDespiteDenialRequest, caller: GateCallerDep, db: DB
) -> GateLogEntry:
    raise not_implemented()


# ---- gate log -----------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/gate-log",
    response_model=GateLogPage,
    summary="Gate-check log (capability 76)",
    description="Never exposed as a time-and-attendance export (P2-8). Action-panel links use "
    "`reason_code=CREDENTIAL_LOST&reason_code=CREDENTIAL_REVOKED` or "
    "`admitted_despite_denial=true` with `since`.",
    responses=error_responses(401, 403, 404, 422),
)
def list_gate_log(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    gate_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    zone_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    direction: GateDirection | None = None,
    result: Annotated[list[GateResult] | None, Query()] = None,
    reason_code: Annotated[list[GateReasonCode] | None, Query()] = None,
    subject_kind: GateSubjectKind | None = None,
    worker_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    admitted_despite_denial: bool | None = None,
    late_exit: bool | None = None,
    since: Annotated[datetime | None, Query(description="UTC.")] = None,
    until: Annotated[datetime | None, Query(description="UTC.")] = None,
) -> GateLogPage:
    raise not_implemented()
