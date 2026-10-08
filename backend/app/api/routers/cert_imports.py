"""Certificate imports: CSV/XLSX dry-run → commit valid rows (spec 4-third-party-cert §3.15,
§4.9, IM-1…IM-7)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.cert_enums import CertImportSource, CertImportStatus, CertImportTemplate
from app.core.enums import Capability, ExportFormat
from app.core.errors import error_responses
from app.schemas.cert_imports import CertImportPage, CertImportRead
from app.services.cert import imports as svc

router = APIRouter(tags=["certificate-imports"])

_TEMPLATE_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "description": "Certificate import template (EN or AR headers).",
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
    "/certificate-imports/template",
    summary="Download a certificate import template (IM-2 / IM-3)",
    response_class=Response,
    responses=_TEMPLATE_RESPONSES,
)
def certificate_import_template(
    user: CurrentUser,
    template: CertImportTemplate,
    format_: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.xlsx,
    headers: Annotated[Literal["en", "ar"], Query()] = "en",
) -> Response:
    user.require_any(Capability.cert_import)
    content, media, name = svc.template(template, format_, headers)
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post(
    "/projects/{project_id}/certificate-imports",
    response_model=CertImportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a certificate file and run the dry-run validation (capability 120)",
    description="Validates every row (codes E01-E12, W01-W06, IM-7) and writes no "
    "certificate. `.csv` (UTF-8, comma or semicolon) or `.xlsx` (first sheet), ≤ 5 MB, ≤ 5,000 "
    "rows; headers EN or AR. Whole-file problems (E12, size) → 422 IMPORT_FILE_INVALID. "
    "`create_items` = true is HSE Officer / Manager only (403). `source` tpi_register_file "
    "needs HSE Officer / Manager (403, IM-6) and `evidence_file` (the TPI's email, PDF/EML, "
    "from one of its verification_domains). `scans_zip` ≤ 200 MB with `<cert_no>.pdf|jpg|png` "
    "(`_front` / `_back` for cards). Commit within 60 min.",
    responses=error_responses(401, 403, 404, 422),
)
def create_certificate_import(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    file: Annotated[UploadFile, File(description=".csv or .xlsx")],
    template: Annotated[CertImportTemplate, Form()],
    source: Annotated[CertImportSource, Form()] = CertImportSource.contractor_file,
    create_items: Annotated[bool, Form()] = False,
    tpi_id: Annotated[
        uuid.UUID | None, Form(description="Required for tpi_register_file: the sender TPI.")
    ] = None,
    scans_zip: Annotated[UploadFile | None, File(description=".zip of scans")] = None,
    evidence_file: Annotated[
        UploadFile | None, File(description="PDF / EML of the TPI's email")
    ] = None,
) -> CertImportRead:
    return svc.upload(
        db, user, project_id, file, template, source, create_items, tpi_id, scans_zip, evidence_file
    )


@router.get(
    "/projects/{project_id}/certificate-imports",
    response_model=CertImportPage,
    summary="Certificate import history (§8.4)",
    responses=error_responses(401, 403, 404, 422),
)
def list_certificate_imports(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[CertImportStatus | None, Query(alias="status")] = None,
    template: CertImportTemplate | None = None,
) -> CertImportPage:
    return svc.list_batches(db, user, project_id, pg.page, pg.page_size, status_, template)


@router.get(
    "/certificate-imports/{batch_id}",
    response_model=CertImportRead,
    summary="Import batch with its validation report (IDs masked, IM-4)",
    responses=error_responses(401, 403, 404),
)
def get_certificate_import(
    batch_id: uuid.UUID, user: CurrentUser, db: DB, include_ok_rows: bool = False
) -> CertImportRead:
    return svc.get(db, user, batch_id, include_ok_rows)


@router.post(
    "/certificate-imports/{batch_id}/commit",
    response_model=CertImportRead,
    summary="Commit the valid rows of a validated batch (IM-1, IM-5; AC98)",
    description="Unlike the Phase 1 workforce import, rows with errors are skipped and the "
    "valid rows are committed (AC98). Certificates become Submitted (Draft when no scan, W03); "
    "never Accepted. 409 IMPORT_EXPIRED after 60 min; 409 IMPORT_NOT_VALIDATED when already "
    "committed/discarded; 409 IMPORT_HAS_ERRORS when no row is valid. Rows are re-validated at "
    "commit; rows that became invalid are skipped and reported.",
    responses=error_responses(401, 403, 404, 409),
)
def commit_certificate_import(batch_id: uuid.UUID, user: CurrentUser, db: DB) -> CertImportRead:
    return svc.commit(db, user, batch_id)


@router.post(
    "/certificate-imports/{batch_id}/discard",
    response_model=CertImportRead,
    summary="Discard a validated batch (the sensitive file is deleted, IM-4)",
    responses=error_responses(401, 403, 404, 409),
)
def discard_certificate_import(batch_id: uuid.UUID, user: CurrentUser, db: DB) -> CertImportRead:
    return svc.discard(db, user, batch_id)
