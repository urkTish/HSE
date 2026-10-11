"""Option 7a vehicle accident details: vehicle rows, prefill and the Najm / police report archive
(spec 7a-vehicle-accident-details v1.1 §3.1, §3.2, §8). Incident-level fields (road type, journey
purpose, report record …) are also on POST/PATCH /incidents."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.core.errors import error_responses
from app.schemas.vehicle import (
    PLATE_DIGITS,
    VehAccidentReportRead,
    VehAccidentReportUpdate,
    VehIncidentVehicleCreate,
    VehIncidentVehicleList,
    VehIncidentVehicleRead,
    VehIncidentVehicleUpdate,
    VehPrefillRead,
)
from app.services import incident_vehicles as svc

router = APIRouter(tags=["incident-vehicles"])

PERSONAL = (
    "Driver identity, licence fields, hours on duty, insurer / policy and third-party plates are "
    "null without capability 29 (P7a-1; `redacted_groups`); identity reads are audited."
)


@router.get(
    "/incidents/{incident_id}/vehicles",
    response_model=VehIncidentVehicleList,
    summary="List the vehicles of an incident (7a §3.2)",
    description=PERSONAL,
    responses=error_responses(401, 403, 404),
)
def list_incident_vehicles(
    incident_id: uuid.UUID, user: CurrentUser, db: DB
) -> VehIncidentVehicleList:
    return svc.list_rows(db, user, incident_id)


@router.post(
    "/incidents/{incident_id}/vehicles",
    response_model=VehIncidentVehicleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a vehicle row (V1…V10; incident must be vehicle_involved)",
    description="Editable until the incident is Closed; after the investigation is approved a "
    "`reason` ≥ 20 characters is required. 422 PLATE_IS_REGISTERED for a third_party plate in "
    "the Phase 2 register (VA-6). licence_check is computed (VA-3); warnings "
    "VEHICLE_DOCS_EXPIRED_AT_TIME / LICENCE_NOT_VALID_AT_TIME are not blocking (VA-4).",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_incident_vehicle(
    incident_id: uuid.UUID, body: VehIncidentVehicleCreate, user: CurrentUser, db: DB
) -> VehIncidentVehicleRead:
    return svc.create_row(db, user, incident_id, body)


@router.patch(
    "/incident-vehicles/{vehicle_row_id}",
    response_model=VehIncidentVehicleRead,
    summary="Edit a vehicle row",
    description=PERSONAL,
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_incident_vehicle(
    vehicle_row_id: uuid.UUID, body: VehIncidentVehicleUpdate, user: CurrentUser, db: DB
) -> VehIncidentVehicleRead:
    return svc.update_row(db, user, vehicle_row_id, body)


@router.delete(
    "/incident-vehicles/{vehicle_row_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a vehicle row (a reported incident keeps ≥ 1, VEHICLE_REQUIRED)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def delete_incident_vehicle(
    vehicle_row_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    reason: Annotated[
        str | None,
        Query(max_length=1000, description="≥ 20 characters once the investigation is approved."),
    ] = None,
) -> Response:
    svc.delete_row(db, user, vehicle_row_id, reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/incidents/{incident_id}/vehicle-prefill",
    response_model=VehPrefillRead,
    summary="Prefill a vehicle row from the Phase 2 register and a driver's ADP (VA-3, VA-6)",
    description="Vehicle by vehicle_id or by normalised plate (Arabic letters mapped to Latin). "
    "The driver block (licence from the ADP) needs capability 29 and is audited.",
    responses=error_responses(401, 403, 404, 422),
)
def prefill_incident_vehicle(
    incident_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    vehicle_id: uuid.UUID | None = None,
    plate_letters_ar: Annotated[str | None, Query(max_length=5)] = None,
    plate_letters_en: Annotated[str | None, Query(max_length=3)] = None,
    plate_digits: Annotated[str | None, Query(pattern=PLATE_DIGITS)] = None,
    worker_id: uuid.UUID | None = None,
) -> VehPrefillRead:
    return svc.prefill(
        db,
        user,
        incident_id,
        vehicle_id,
        plate_letters_ar,
        plate_letters_en,
        plate_digits,
        worker_id,
    )


@router.get(
    "/incidents/{incident_id}/accident-report",
    response_model=VehAccidentReportRead,
    summary="The Najm / police accident report archive card (VA-14, VA-15)",
    description="Internal record, no client copy. Files are listed for capability 29 only.",
    responses=error_responses(401, 403, 404),
)
def get_accident_report(incident_id: uuid.UUID, user: CurrentUser, db: DB) -> VehAccidentReportRead:
    return svc.get_report(db, user, incident_id)


@router.put(
    "/incidents/{incident_id}/accident-report",
    response_model=VehAccidentReportRead,
    summary="Set the accident report authority, number, date and liability",
    description="Allowed until the incident is Closed. Creates no 6f requirement or notification "
    "to the client (VA-15). 422 ACCIDENT_REPORT_AUTHORITY_REQUIRED for public_road + "
    "none_internal.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def put_accident_report(
    incident_id: uuid.UUID, body: VehAccidentReportUpdate, user: CurrentUser, db: DB
) -> VehAccidentReportRead:
    return svc.put_report(db, user, incident_id, body)


@router.post(
    "/incidents/{incident_id}/accident-report/files",
    response_model=VehAccidentReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Archive a report file (PDF / image ≤ 10 MB; ≤ 5 current files; capability 29)",
    description="`supersedes_id` replaces a current file: the earlier one stays archived as "
    "superseded (audited). Files may be added after Closed; none can be deleted then (DELETE "
    "/attachments/{id} → 409 ACCIDENT_REPORT_LOCKED). Download through POST "
    "/attachments/{id}/signed-url (403 without capability 29).",
    responses=error_responses(401, 403, 404, 409, 422),
)
def upload_accident_report_file(
    incident_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    file: Annotated[UploadFile, File()],
    supersedes_id: Annotated[uuid.UUID | None, Form()] = None,
) -> VehAccidentReportRead:
    content = file.file.read(get_settings().attachment_max_bytes + 1)
    return svc.upload_file(db, user, incident_id, file.filename or "file", content, supersedes_id)
