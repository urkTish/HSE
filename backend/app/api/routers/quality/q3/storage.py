"""Q3 HTTP routes: products, imports, storage zones, points, readings, excursions, mapping,
hygiene and pest control (spec 8-quality §D.1, §D.3–§D.6)."""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.config import get_settings
from app.core.errors import error_responses
from app.core.quality.q3 import (
    QExcursionKind,
    QExcursionSeverity,
    QExcursionStatus,
    QImportKind,
    QImportTarget,
)
from app.schemas.quality.q3 import (
    Q3Annotation,
    Q3ApproveInput,
    Q3AssessInput,
    Q3CauseInput,
    Q3ChangeNote,
    Q3CheckRunInput,
    Q3CheckRunResult,
    Q3DismissInput,
    Q3ExcursionPage,
    Q3ExcursionRead,
    Q3ImpactsInput,
    Q3ImportPage,
    Q3ImportPreview,
    Q3ImportRead,
    Q3ImportResult,
    Q3LoggerAssign,
    Q3ManualReading,
    Q3ManualReadingResult,
    Q3MappingCreate,
    Q3MappingInput,
    Q3MappingListItem,
    Q3MappingRead,
    Q3Metrics,
    Q3NoteInput,
    Q3PointCreate,
    Q3PointRead,
    Q3PointUpdate,
    Q3PointWithWarnings,
    Q3ProductCreate,
    Q3ProductRead,
    Q3ProductUpdate,
    Q3ReadingRead,
    Q3ReasonInput,
    Q3ScheduleCreate,
    Q3ScheduleRead,
    Q3ScheduleUpdate,
    Q3StationCreate,
    Q3StationRead,
    Q3VisitCreate,
    Q3VisitRead,
    Q3VoidInput,
    Q3ZoneCreate,
    Q3ZoneRead,
    Q3ZoneReport,
    Q3ZoneUpdate,
)
from app.services.quality.q3 import (
    excursions,
    hygiene,
    imports,
    mapping,
    metrics,
    products,
    storage,
)

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)
P = "/projects/{project_id}/quality"


# ---- products ----------------------------------------------------------------------------------


@router.get(P + "/products", response_model=list[Q3ProductRead], summary="Product master (§D.1.3)", responses=E)
def q3_list_products(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    owner_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[dict[str, Any]]:
    return products.list_products(db, user, project_id, owner_id, q)


@router.post(P + "/products", response_model=Q3ProductRead, status_code=status.HTTP_201_CREATED, summary="Create a product (269)", responses=E)
def q3_create_product(project_id: uuid.UUID, body: Q3ProductCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return products.create(db, user, project_id, body.model_dump())


@router.patch("/quality/products/{product_id}", response_model=Q3ProductRead, summary="Update a product (269)", responses=E)
def q3_update_product(product_id: uuid.UUID, body: Q3ProductUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return products.update(db, user, product_id, body.model_dump(exclude_unset=True))


# ---- imports (Q-IMP) ---------------------------------------------------------------------------


@router.post(
    P + "/imports",
    response_model=Q3ImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="Import a CSV file: logger readings, stock snapshot, shipments, products or cycle count",
    description="Readings are accepted row by row (bad rows listed); the other kinds are all-or-nothing "
    "(422 IMPORT_ROWS_INVALID with `meta.errors`). 409 IMPORT_DUPLICATE_FILE for the same file and "
    "target; 422 IMPORT_TOO_LARGE over `import_max_rows`. `profile` is JSON: {columns, date_format, "
    "timezone, unit C|F, decimal, delimiter, logger_serial_column}. Excursions found are returned.",
    responses=E,
)
def q3_import(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    kind: Annotated[QImportKind, Form()],
    target_type: Annotated[QImportTarget, Form()],
    target_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
    profile: Annotated[str | None, Form()] = None,
    as_of: Annotated[datetime | None, Form()] = None,
) -> dict[str, Any]:
    content = file.file.read(get_settings().attachment_max_bytes + 1)
    prof = json.loads(profile) if profile else None
    return imports.import_file(db, user, project_id, kind, target_type, target_id, file.filename or "import.csv", content, prof, as_of=as_of)


@router.post(P + "/imports/preview", response_model=Q3ImportPreview, summary="Preview the first rows of a CSV file as it will be read", responses=E)
def q3_import_preview(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    kind: Annotated[QImportKind, Form()],
    file: Annotated[UploadFile, File()],
    profile: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    from app.services.quality import common as qc  # noqa: PLC0415

    qc.get_project(db, user, project_id)
    content = file.file.read(get_settings().attachment_max_bytes + 1)
    return imports.preview(content, kind, json.loads(profile) if profile else None)


@router.get(P + "/imports", response_model=Q3ImportPage, summary="Import history", responses=E)
def q3_list_imports(project_id: uuid.UUID, user: CurrentUser, pg: PageParams, db: DB, kind: QImportKind | None = None) -> dict[str, Any]:
    return imports.list_batches(db, user, project_id, pg.page, pg.page_size, kind)


@router.get(P + "/import-profiles", response_model=list[dict[str, Any]], summary="Saved column mappings of a kind", responses=E)
def q3_import_profiles(project_id: uuid.UUID, kind: QImportKind, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return imports.profiles(db, user, project_id, kind)


@router.post("/quality/imports/{batch_id}/void", response_model=Q3ImportRead, summary="Void a batch within 24 h (244, Q-IMP-05)", responses=E)
def q3_void_import(batch_id: uuid.UUID, body: Q3VoidInput, user: CurrentUser, db: DB) -> dict[str, Any]:
    return imports.void(db, user, batch_id, body.model_dump())


# ---- storage zones, points, readings -------------------------------------------------------------


@router.get(P + "/storage-zones", response_model=list[Q3ZoneRead], summary="Storage zones with live status (§D.3)", responses=E)
def q3_list_zones(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return storage.list_zones(db, user, project_id)


@router.post(P + "/storage-zones", response_model=Q3ZoneRead, status_code=status.HTTP_201_CREATED, summary="Storage settings for a zone (266; class defaults)", responses=E)
def q3_create_zone(project_id: uuid.UUID, body: Q3ZoneCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return storage.create_zone(db, user, project_id, body.model_dump())


@router.get("/quality/storage-zones/{zone_id}", response_model=Q3ZoneRead, summary="One storage zone", responses=E)
def q3_get_zone(zone_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    z, _ = storage.zone_row(db, user, zone_id)
    return storage.zone_read(db, user, z, status=True)


@router.patch("/quality/storage-zones/{zone_id}", response_model=Q3ZoneRead, summary="Edit range or bands (audited; a range change requires re-mapping)", responses=E)
def q3_update_zone(zone_id: uuid.UUID, body: Q3ZoneUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return storage.update_zone(db, user, zone_id, body.model_dump(exclude_unset=True))


@router.post("/quality/storage-zones/{zone_id}/change-notes", response_model=Q3ZoneRead, summary="Layout or HVAC change note (Q-MAP-06)", responses=E)
def q3_zone_change(zone_id: uuid.UUID, body: Q3ChangeNote, user: CurrentUser, db: DB) -> dict[str, Any]:
    return storage.change_note(db, user, zone_id, body.model_dump())


@router.get("/quality/storage-zones/{zone_id}/report", response_model=Q3ZoneReport, summary="Profile chart C48, coverage, TOR, gaps and MKT for a period", responses=E)
def q3_zone_report(zone_id: uuid.UUID, start: datetime, end: datetime, user: CurrentUser, db: DB) -> dict[str, Any]:
    return storage.zone_report(db, user, zone_id, start, end)


@router.post("/quality/storage-zones/{zone_id}/points", response_model=Q3PointRead, status_code=status.HTTP_201_CREATED, summary="Add a monitoring point (266)", responses=E)
def q3_create_point(zone_id: uuid.UUID, body: Q3PointCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return storage.create_point(db, user, zone_id, body.model_dump())


@router.patch("/quality/monitoring-points/{point_id}", response_model=Q3PointRead, summary="Edit a monitoring point", responses=E)
def q3_update_point(point_id: uuid.UUID, body: Q3PointUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return storage.update_point(db, user, point_id, body.model_dump(exclude_unset=True))


@router.post("/quality/monitoring-points/{point_id}/loggers", response_model=Q3PointWithWarnings, summary="Assign a logger (Q-STO-03; usage recorded)", responses=E)
def q3_assign_logger(point_id: uuid.UUID, body: Q3LoggerAssign, user: CurrentUser, db: DB) -> dict[str, Any]:
    return storage.assign_logger(db, user, point_id, body.model_dump(by_alias=True))


@router.post(
    "/quality/monitoring-points/{point_id}/readings",
    response_model=Q3ManualReadingResult,
    status_code=status.HTTP_201_CREATED,
    summary="Manual reading with the probe's M&TE (267; 422 CLOCK_SKEW / READING_TOO_OLD / MTE_REQUIRED)",
    responses=E,
)
def q3_manual_reading(point_id: uuid.UUID, body: Q3ManualReading, user: CurrentUser, db: DB) -> dict[str, Any]:
    return storage.manual_reading(db, user, point_id, body.model_dump())


@router.post("/quality/readings/{reading_id}/annotation", response_model=Q3ReadingRead, summary="Annotate a reading (values are never edited, Q-STO-07)", responses=E)
def q3_annotate(reading_id: int, body: Q3Annotation, user: CurrentUser, db: DB) -> dict[str, Any]:
    return storage.annotate(db, user, reading_id, body.model_dump())


# ---- excursions --------------------------------------------------------------------------------


@router.get(P + "/excursions", response_model=Q3ExcursionPage, summary="Excursion register (§D.4)", responses=E)
def q3_list_excursions(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QExcursionStatus] | None, Query(alias="status")] = None,
    severity: QExcursionSeverity | None = None,
    zone_id: uuid.UUID | None = None,
    kind: QExcursionKind | None = None,
    transients: bool = False,
) -> dict[str, Any]:
    return excursions.list_page(db, user, project_id, pg.page, pg.page_size, statuses=status_, severity=severity, zone_id=zone_id, kind=kind, transients=transients)


@router.get("/quality/excursions/{exc_id}", response_model=Q3ExcursionRead, summary="One excursion", responses=E)
def q3_get_excursion(exc_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    x, _ = excursions.get_exc(db, user, exc_id)
    return excursions.read(db, user, x)


@router.post("/quality/excursions/{exc_id}/acknowledge", response_model=Q3ExcursionRead, summary="Acknowledge the alert", responses=E)
def q3_ack_excursion(exc_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return excursions.acknowledge(db, user, exc_id)


@router.post("/quality/excursions/{exc_id}/cause", response_model=Q3ExcursionRead, summary="Record the cause (Detected → Under Assessment)", responses=E)
def q3_excursion_cause(exc_id: uuid.UUID, body: Q3CauseInput, user: CurrentUser, db: DB) -> dict[str, Any]:
    return excursions.set_cause(db, user, exc_id, body.model_dump())


@router.put("/quality/excursions/{exc_id}/impacts", response_model=Q3ExcursionRead, summary="Save impact-assessment lines (Q-EXC-07…09)", responses=E)
def q3_excursion_impacts(exc_id: uuid.UUID, body: Q3ImpactsInput, user: CurrentUser, db: DB) -> dict[str, Any]:
    return excursions.save_impacts(db, user, exc_id, body.model_dump())


@router.post(
    "/quality/excursions/{exc_id}/assess",
    response_model=Q3ExcursionRead,
    summary="Sign the impact assessment (RPM excursion.impact; 422 IMPACT_LINES_INCOMPLETE / IMPACT_EVIDENCE_REQUIRED / OWNER_DECISION_REQUIRED)",
    responses=E,
)
def q3_excursion_assess(exc_id: uuid.UUID, body: Q3AssessInput, user: CurrentUser, db: DB) -> dict[str, Any]:
    return excursions.assess(db, user, exc_id, body.model_dump())


@router.post("/quality/excursions/{exc_id}/reopen", response_model=Q3ExcursionRead, summary="Reopen an assessed excursion", responses=E)
def q3_excursion_reopen(exc_id: uuid.UUID, body: Q3ReasonInput, user: CurrentUser, db: DB) -> dict[str, Any]:
    return excursions.reopen(db, user, exc_id, body.model_dump())


@router.post("/quality/excursions/{exc_id}/close", response_model=Q3ExcursionRead, summary="Close with a no-product-impact note (Q-EXC-06)", responses=E)
def q3_excursion_close(exc_id: uuid.UUID, body: Q3NoteInput, user: CurrentUser, db: DB) -> dict[str, Any]:
    return excursions.close_no_impact(db, user, exc_id, body.model_dump())


@router.post("/quality/excursions/{exc_id}/dismiss", response_model=Q3ExcursionRead, summary="Dismiss as a probe fault (Q-EXC-11)", responses=E)
def q3_excursion_dismiss(exc_id: uuid.UUID, body: Q3DismissInput, user: CurrentUser, db: DB) -> dict[str, Any]:
    return excursions.dismiss(db, user, exc_id, body.model_dump())


# ---- mapping -----------------------------------------------------------------------------------


@router.get(P + "/mapping-studies", response_model=list[Q3MappingListItem], summary="Temperature mapping studies (§D.5)", responses=E)
def q3_list_studies(project_id: uuid.UUID, user: CurrentUser, db: DB, zone_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    return mapping.list_studies(db, user, project_id, zone_id)


@router.post(
    P + "/mapping-studies",
    response_model=Q3MappingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Design a study (266; 422 MAPPING_LOGGER_NOT_CALIBRATED / MAPPING_DESIGN_INSUFFICIENT)",
    responses=E,
)
def q3_create_study(project_id: uuid.UUID, body: Q3MappingCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return mapping.create(db, user, project_id, body.model_dump(by_alias=True))


@router.get("/quality/mapping-studies/{study_id}", response_model=Q3MappingRead, summary="One study", responses=E)
def q3_get_study(study_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    m, _ = mapping.get_study(db, user, study_id)
    return mapping.read(db, user, m)


@router.patch("/quality/mapping-studies/{study_id}", response_model=Q3MappingRead, summary="Edit the study design", responses=E)
def q3_update_study(study_id: uuid.UUID, body: Q3MappingInput, user: CurrentUser, db: DB) -> dict[str, Any]:
    return mapping.update(db, user, study_id, body.model_dump(exclude_unset=True, by_alias=True))


@router.post("/quality/mapping-studies/{study_id}/evaluate", response_model=Q3MappingRead, summary="Evaluate the imported data (Q-MAP-03)", responses=E)
def q3_evaluate_study(study_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return mapping.evaluate(db, user, study_id)


@router.post("/quality/mapping-studies/{study_id}/approve", response_model=Q3MappingRead, summary="Approve or reject (RPM mapping_study.approve)", responses=E)
def q3_approve_study(study_id: uuid.UUID, body: Q3ApproveInput, user: CurrentUser, db: DB) -> dict[str, Any]:
    return mapping.approve(db, user, study_id, body.model_dump())


# ---- hygiene and pest --------------------------------------------------------------------------


@router.get(P + "/check-schedules", response_model=list[Q3ScheduleRead], summary="Hygiene and pest check schedules with due / overdue periods", responses=E)
def q3_list_schedules(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return hygiene.list_schedules(db, user, project_id)


@router.post(P + "/check-schedules", response_model=Q3ScheduleRead, status_code=status.HTTP_201_CREATED, summary="Create a schedule (266)", responses=E)
def q3_create_schedule(project_id: uuid.UUID, body: Q3ScheduleCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return hygiene.create_schedule(db, user, project_id, body.model_dump())


@router.patch("/quality/check-schedules/{schedule_id}", response_model=Q3ScheduleRead, summary="Edit a schedule", responses=E)
def q3_update_schedule(schedule_id: uuid.UUID, body: Q3ScheduleUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return hygiene.update_schedule(db, user, schedule_id, body.model_dump(exclude_unset=True))


@router.post("/quality/check-schedules/{schedule_id}/checks", response_model=Q3CheckRunResult, status_code=status.HTTP_201_CREATED, summary="Run a hygiene check (6d engine; Q-HYG-02 proposals)", responses=E)
def q3_run_check(schedule_id: uuid.UUID, body: Q3CheckRunInput, user: CurrentUser, db: DB) -> dict[str, Any]:
    return hygiene.run_check(db, user, schedule_id, {**body.model_dump(), "answers": body.answers})


@router.get(P + "/pest-stations", response_model=list[Q3StationRead], summary="Pest station register", responses=E)
def q3_list_stations(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return hygiene.list_stations(db, user, project_id)


@router.post(P + "/pest-stations", response_model=Q3StationRead, status_code=status.HTTP_201_CREATED, summary="Add a pest station (266)", responses=E)
def q3_create_station(project_id: uuid.UUID, body: Q3StationCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return hygiene.create_station(db, user, project_id, body.model_dump())


@router.get(P + "/pest-visits", response_model=list[Q3VisitRead], summary="Pest-control visits", responses=E)
def q3_list_visits(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return hygiene.list_visits(db, user, project_id)


@router.post(
    P + "/pest-visits",
    response_model=Q3VisitRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a pest-control visit (warning STATION_NOT_SERVICED; Q-HYG-03 proposals)",
    responses=E,
)
def q3_create_visit(project_id: uuid.UUID, body: Q3VisitCreate, user: CurrentUser, db: DB) -> dict[str, Any]:
    data = body.model_dump()
    if body.answers is None:
        data.pop("answers")
    else:
        data["answers"] = body.answers
    return hygiene.create_visit(db, user, project_id, data)


@router.get("/quality/pest-visits/{visit_id}", response_model=Q3VisitRead, summary="One pest visit", responses=E)
def q3_get_visit(visit_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return hygiene.get_visit(db, user, visit_id)


# ---- metrics -----------------------------------------------------------------------------------


@router.get(P + "/logistics-metrics", response_model=Q3Metrics, summary="K-160…K-168 inputs for a month (§E.4)", responses=E)
def q3_metrics(
    project_id: uuid.UUID,
    year: Annotated[int, Query(ge=2020, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
    user: CurrentUser,
    db: DB,
) -> dict[str, Any]:
    return metrics.month_api(db, user, project_id, year, month)
