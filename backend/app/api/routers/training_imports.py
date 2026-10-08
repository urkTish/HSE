"""Training imports: CSV/XLSX dry-run → commit valid rows (spec 5-training §3.13, §4.8,
IM5-1…IM5-7)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.enums import Capability, ExportFormat
from app.core.errors import error_responses
from app.core.train_enums import (
    TrainingImportSource,
    TrainingImportStatus,
    TrainingImportTemplate,
)
from app.schemas.training_imports import TrainingImportPage, TrainingImportRead
from app.services.train import imports

router = APIRouter(tags=["training-imports"])

_TEMPLATE_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "description": "Training import template (EN or AR headers).",
        "content": {
            "text/csv": {"schema": {"type": "string", "format": "binary"}},
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                "schema": {"type": "string", "format": "binary"}
            },
        },
    },
    **error_responses(401, 403, 422),
}


@router.get(
    "/training-imports/template",
    summary="Download a training import template (IM5-2 / IM5-3)",
    response_class=Response,
    responses=_TEMPLATE_RESPONSES,
)
def training_import_template(
    user: CurrentUser,
    template: TrainingImportTemplate,
    format_: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.xlsx,
    headers: Annotated[Literal["en", "ar"], Query()] = "en",
) -> Response:
    user.require_any(Capability.training_import)
    content, media_type, filename = imports.template(template, format_, headers)
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/projects/{project_id}/training-imports",
    response_model=TrainingImportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a training file and run the dry-run validation (capability 141)",
    description="Validates every row (codes E01-E12, W01-W06, IM5-7) and writes nothing. "
    "`.csv` (UTF-8, comma or semicolon) or `.xlsx` (first sheet), ≤ 5 MB, ≤ 5,000 rows; headers "
    "EN or AR. Whole-file problems (E12, size) → 422 IMPORT_FILE_INVALID. `session_attendance` "
    "needs `session_id` (a Delivered session). `source` provider_register_file is HSE Officer / "
    "Manager only (403, IM5-6) and needs `provider_id` and `evidence_file` (the provider's "
    "email, PDF/EML, from one of its verification_domains). `scans_zip` ≤ 200 MB with "
    "`<certificate_no>.pdf|jpg|png`. Commit within 60 min.",
    responses=error_responses(401, 403, 404, 422),
)
def create_training_import(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    file: Annotated[UploadFile, File(description=".csv or .xlsx")],
    template: Annotated[TrainingImportTemplate, Form()],
    source: Annotated[TrainingImportSource, Form()] = TrainingImportSource.contractor_file,
    session_id: Annotated[
        uuid.UUID | None, Form(description="session_attendance: the Delivered session.")
    ] = None,
    provider_id: Annotated[
        uuid.UUID | None, Form(description="provider_register_file: the sender provider.")
    ] = None,
    scans_zip: Annotated[UploadFile | None, File(description=".zip of scans")] = None,
    evidence_file: Annotated[
        UploadFile | None, File(description="PDF / EML of the provider's email")
    ] = None,
) -> TrainingImportRead:
    return imports.upload(
        db,
        user,
        project_id,
        file,
        template,
        source,
        session_id,
        provider_id,
        scans_zip,
        evidence_file,
    )


@router.get(
    "/projects/{project_id}/training-imports",
    response_model=TrainingImportPage,
    summary="Training import history (§8.4)",
    responses=error_responses(401, 403, 404, 422),
)
def list_training_imports(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[TrainingImportStatus | None, Query(alias="status")] = None,
    template: TrainingImportTemplate | None = None,
) -> TrainingImportPage:
    return imports.list_batches(db, user, project_id, pg.page, pg.page_size, status_, template)


@router.get(
    "/training-imports/{batch_id}",
    response_model=TrainingImportRead,
    summary="Import batch with its validation report (IDs masked, IM5-4)",
    responses=error_responses(401, 403, 404),
)
def get_training_import(
    batch_id: uuid.UUID, user: CurrentUser, db: DB, include_ok_rows: bool = False
) -> TrainingImportRead:
    return imports.get(db, user, batch_id, include_ok_rows)


@router.post(
    "/training-imports/{batch_id}/commit",
    response_model=TrainingImportRead,
    summary="Commit the valid rows of a validated batch (IM5-1, IM5-5)",
    description="As Phase 4 (AC98): rows with errors are skipped and the valid rows are "
    "committed. training_records rows become Submitted (Draft when no scan, W03); never "
    "Accepted. session_attendance rows update attendance (Close stays separate, IM5-3). 409 "
    "IMPORT_EXPIRED after 60 min; 409 IMPORT_NOT_VALIDATED when already committed/discarded; "
    "409 IMPORT_HAS_ERRORS when no row is valid.",
    responses=error_responses(401, 403, 404, 409),
)
def commit_training_import(batch_id: uuid.UUID, user: CurrentUser, db: DB) -> TrainingImportRead:
    return imports.commit(db, user, batch_id)


@router.post(
    "/training-imports/{batch_id}/discard",
    response_model=TrainingImportRead,
    summary="Discard a validated batch (the file is deleted, IM5-4)",
    responses=error_responses(401, 403, 404, 409),
)
def discard_training_import(batch_id: uuid.UUID, user: CurrentUser, db: DB) -> TrainingImportRead:
    return imports.discard(db, user, batch_id)
