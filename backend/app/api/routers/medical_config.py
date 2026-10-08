"""Phase 6a project settings, enabling medical hooks and medical imports (spec
6a-occupational-health §3.11, §3.12, HK6-1, IM6)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.enums import Capability, ExportFormat
from app.core.errors import error_responses
from app.core.med_enums import MedicalImportSource, MedicalImportStatus
from app.schemas.cert_config import HookPolicyRead
from app.schemas.medical import (
    MedicalHooksEnableRequest,
    MedicalImportBatchPage,
    MedicalImportBatchRead,
    MedicalSettingsRead,
    MedicalSettingsUpdate,
    MedicalSettingsUpdateResult,
)
from app.services.med import config as mconfig
from app.services.med import imports

router = APIRouter(tags=["medical-settings"])

_TEMPLATE_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "description": "Medical import template (EN or AR headers).",
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
    "/projects/{project_id}/medical-settings",
    response_model=MedicalSettingsRead,
    summary="Phase 6a project settings (§3.12; capability 146 to read)",
    responses=error_responses(401, 403, 404),
)
def get_medical_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> MedicalSettingsRead:
    return mconfig.get_settings(db, user, project_id)


@router.patch(
    "/projects/{project_id}/medical-settings",
    response_model=MedicalSettingsUpdateResult,
    summary="Edit Phase 6a settings (capability 164, HSE Manager; allowed ranges only; "
    "tighten-only keys → SETTING_LOOSENING; audited)",
    responses=error_responses(401, 403, 404, 422),
)
def update_medical_settings(
    project_id: uuid.UUID, body: MedicalSettingsUpdate, user: CurrentUser, db: DB
) -> MedicalSettingsUpdateResult:
    return mconfig.update_settings(db, user, project_id, body)


@router.post(
    "/projects/{project_id}/medical-hooks/enable",
    response_model=HookPolicyRead,
    summary="Enable medical hooks → kind medical_fitness in transition (HK6-1; capability 164; "
    "MEDICAL_REGISTER_NOT_LIVE / NO_MEDICAL_PROVIDER)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def enable_medical_hooks(
    project_id: uuid.UUID, body: MedicalHooksEnableRequest, user: CurrentUser, db: DB
) -> HookPolicyRead:
    return mconfig.enable_hooks(db, user, project_id, body)


# ---- imports (§3.11) -----------------------------------------------------------------------------


@router.get(
    "/medical-imports/template",
    summary="Download the medical import template (IM6-2)",
    response_class=Response,
    responses=_TEMPLATE_RESPONSES,
)
def medical_import_template(
    user: CurrentUser,
    format_: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.xlsx,
    headers: Annotated[Literal["en", "ar"], Query()] = "en",
) -> Response:
    user.require_any(Capability.fitness_import)
    content, media_type, filename = imports.template(format_, headers)
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/projects/{project_id}/medical-imports",
    response_model=MedicalImportBatchRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a fitness-status file and run the dry-run validation (capability 161)",
    description="Validates every row (E01-E10, W01-W04) and writes nothing. Status data only: "
    "a column that looks clinical → E10 for the file. `.csv` or `.xlsx`, ≤ 5 MB, ≤ 5,000 rows. "
    "`clinic_register_file` needs capability 157 and `provider_id`; rows become Submitted (never "
    "Accepted). Commit within 60 min.",
    responses=error_responses(401, 403, 404, 422),
)
def create_medical_import(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    file: Annotated[UploadFile, File(description=".csv or .xlsx")],
    source: Annotated[MedicalImportSource, Form()] = MedicalImportSource.contractor_file,
    provider_id: Annotated[uuid.UUID | None, Form()] = None,
) -> MedicalImportBatchRead:
    return imports.upload(db, user, project_id, file, source, provider_id)


@router.get(
    "/projects/{project_id}/medical-imports",
    response_model=MedicalImportBatchPage,
    summary="Medical import history",
    responses=error_responses(401, 403, 404, 422),
)
def list_medical_imports(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[MedicalImportStatus | None, Query(alias="status")] = None,
) -> MedicalImportBatchPage:
    return imports.list_batches(db, user, project_id, pg.page, pg.page_size, status_)


@router.get(
    "/medical-imports/{batch_id}",
    response_model=MedicalImportBatchRead,
    summary="Import batch with its validation report (IDs masked)",
    responses=error_responses(401, 403, 404),
)
def get_medical_import(batch_id: uuid.UUID, user: CurrentUser, db: DB) -> MedicalImportBatchRead:
    return imports.get(db, user, batch_id)


@router.post(
    "/medical-imports/{batch_id}/commit",
    response_model=MedicalImportBatchRead,
    summary="Commit the valid rows (Submitted; 409 IMPORT_EXPIRED after 60 min)",
    responses=error_responses(401, 403, 404, 409),
)
def commit_medical_import(batch_id: uuid.UUID, user: CurrentUser, db: DB) -> MedicalImportBatchRead:
    return imports.commit(db, user, batch_id)


@router.post(
    "/medical-imports/{batch_id}/discard",
    response_model=MedicalImportBatchRead,
    summary="Discard a validated batch",
    responses=error_responses(401, 403, 404, 409),
)
def discard_medical_import(
    batch_id: uuid.UUID, user: CurrentUser, db: DB
) -> MedicalImportBatchRead:
    return imports.discard(db, user, batch_id)
