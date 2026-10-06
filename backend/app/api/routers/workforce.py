"""Workforce daily returns, month locks and import (spec 1-dashboard §3.1, §3.2, §4.1, §5.1)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.enums import ExportFormat
from app.core.errors import error_responses
from app.core.hse_enums import ImportMode, ImportStatus, Shift, WorkforceSource, WorkforceStatus
from app.schemas.workforce import (
    MONTH,
    BulkVerifyRequest,
    BulkVerifyResult,
    MonthLockRequest,
    MonthUnlockRequest,
    WorkforceImportPage,
    WorkforceImportRead,
    WorkforceMonthList,
    WorkforceMonthRead,
    WorkforceReturnCreate,
    WorkforceReturnPage,
    WorkforceReturnRead,
    WorkforceReturnUpdate,
    WorkforceTransitionRequest,
)
from app.services import workforce as svc
from app.services import workforce_import as imp

router = APIRouter(tags=["workforce"])

ReturnSort = Literal["work_date", "-work_date", "man_hours", "-man_hours"]
MonthPath = Annotated[str, Path(pattern=MONTH, description="YYYY-MM", examples=["2026-08"])]


@router.get(
    "/projects/{project_id}/workforce-returns",
    response_model=WorkforceReturnPage,
    summary="List workforce daily returns (capability 24, scoped)",
    responses=error_responses(401, 403, 404, 422),
)
def list_workforce_returns(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    date_from: date | None = None,
    date_to: date | None = None,
    site_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    zone_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = False,
    shift: Shift | None = None,
    status_: Annotated[list[WorkforceStatus] | None, Query(alias="status")] = None,
    source: WorkforceSource | None = None,
    import_batch_id: uuid.UUID | None = None,
    has_warnings: bool | None = None,
    sort: ReturnSort = "-work_date",
) -> WorkforceReturnPage:
    return svc.list_page(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        date_from=date_from,
        date_to=date_to,
        site_ids=site_id,
        zone_id=zone_id,
        engagement_ids=engagement_id,
        include_subcontractors=include_subcontractors,
        shift=shift,
        statuses=status_,
        source=source,
        import_batch_id=import_batch_id,
        has_warnings=has_warnings,
        sort=sort,
    )


@router.post(
    "/projects/{project_id}/workforce-returns",
    response_model=WorkforceReturnRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a daily return (capability 20; draft, or submitted with submit=true)",
    description="409 DUPLICATE_RETURN when the key (date, site, zone, engagement, shift) exists "
    "(AC2); 409 PERIOD_LOCKED for a locked month; 403 CONTRACTOR_SUSPENDED for users of a "
    "suspended contractor (AC11). A return for a suspended contractor entered by others is "
    "accepted with warning W03.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_workforce_return(
    project_id: uuid.UUID, body: WorkforceReturnCreate, user: CurrentUser, db: DB
) -> WorkforceReturnRead:
    return svc.create(db, user, project_id, body)


@router.get(
    "/workforce-returns/{return_id}",
    response_model=WorkforceReturnRead,
    summary="Get a daily return",
    responses=error_responses(401, 403, 404),
)
def get_workforce_return(return_id: uuid.UUID, user: CurrentUser, db: DB) -> WorkforceReturnRead:
    return svc.get(db, user, return_id)


@router.patch(
    "/workforce-returns/{return_id}",
    response_model=WorkforceReturnRead,
    summary="Edit a draft/submitted return",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_workforce_return(
    return_id: uuid.UUID, body: WorkforceReturnUpdate, user: CurrentUser, db: DB
) -> WorkforceReturnRead:
    return svc.update(db, user, return_id, body)


@router.delete(
    "/workforce-returns/{return_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft return (creator / HSE Officer)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_workforce_return(return_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    svc.delete(db, user, return_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/workforce-returns/{return_id}/transitions",
    response_model=WorkforceReturnRead,
    summary="Submit / return to draft / verify / correct / unlock a return (§4.1)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_workforce_return(
    return_id: uuid.UUID, body: WorkforceTransitionRequest, user: CurrentUser, db: DB
) -> WorkforceReturnRead:
    return svc.transition(db, user, return_id, body.to_status, body.reason)


@router.post(
    "/projects/{project_id}/workforce-returns/verify",
    response_model=BulkVerifyResult,
    summary="Bulk verify submitted returns (capability 22; verifier ≠ creator)",
    responses=error_responses(401, 403, 404, 422),
)
def bulk_verify_workforce_returns(
    project_id: uuid.UUID, body: BulkVerifyRequest, user: CurrentUser, db: DB
) -> BulkVerifyResult:
    return svc.bulk_verify(db, user, project_id, body.ids)


@router.get(
    "/projects/{project_id}/workforce-months",
    response_model=WorkforceMonthList,
    summary="Month lock status per month (newest first)",
    responses=error_responses(401, 403, 404, 422),
)
def list_workforce_months(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> WorkforceMonthList:
    return svc.list_months(db, user, project_id, year)


@router.post(
    "/projects/{project_id}/workforce-months/{month}/lock",
    response_model=WorkforceMonthRead,
    summary="Lock a month (HSE Manager, capability 23); also automatic on month_lock_day",
    responses=error_responses(401, 403, 404, 409, 422),
)
def lock_workforce_month(
    project_id: uuid.UUID,
    month: MonthPath,
    body: MonthLockRequest,
    user: CurrentUser,
    db: DB,
) -> WorkforceMonthRead:
    return svc.lock(db, user, project_id, month, body.reason)


@router.post(
    "/projects/{project_id}/workforce-months/{month}/unlock",
    response_model=WorkforceMonthRead,
    summary="Unlock a month (HSE Manager, reason): all its rows Locked → Verified",
    description="Changes after unlock mark the month `restated` in KPI responses (W-10).",
    responses=error_responses(401, 403, 404, 409, 422),
)
def unlock_workforce_month(
    project_id: uuid.UUID,
    month: MonthPath,
    body: MonthUnlockRequest,
    user: CurrentUser,
    db: DB,
) -> WorkforceMonthRead:
    return svc.unlock(db, user, project_id, month, body.reason)


# ---- import --------------------------------------------------------------------------------------

_TEMPLATE_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "description": "Import template (EN or AR headers).",
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
    "/workforce-imports/template",
    summary="Download the import template",
    response_class=Response,
    responses=_TEMPLATE_RESPONSES,
)
def workforce_import_template(
    user: CurrentUser,
    format_: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.xlsx,
    headers: Annotated[Literal["en", "ar"], Query()] = "en",
) -> Response:
    content, media_type, filename = imp.template(format_, headers)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/projects/{project_id}/workforce-imports",
    response_model=WorkforceImportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CSV/Excel file and run the dry-run validation (capability 21)",
    description="Validates every row (codes E01-E14, W01-W06) and writes nothing to returns "
    "(W-5a). `.csv` UTF-8 (BOM optional, comma or semicolon) or `.xlsx` (first sheet), ≤ 5 MB, "
    "≤ 20,000 data rows; headers EN or AR. Whole-file problems (E14, size) → 422 "
    "IMPORT_FILE_INVALID. Commit within 60 min.",
    responses=error_responses(401, 403, 404, 422),
)
def create_workforce_import(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    file: Annotated[UploadFile, File(description=".csv or .xlsx")],
    mode: Annotated[ImportMode, Form()] = ImportMode.insert_only,
) -> WorkforceImportRead:
    content = file.file.read(imp.MAX_BYTES + 1)
    return imp.dry_run(db, user, project_id, file.filename or "upload", content, mode)


@router.get(
    "/projects/{project_id}/workforce-imports",
    response_model=WorkforceImportPage,
    summary="List import batches",
    responses=error_responses(401, 403, 404, 422),
)
def list_workforce_imports(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[ImportStatus | None, Query(alias="status")] = None,
) -> WorkforceImportPage:
    return imp.list_page(db, user, project_id, pg.page, pg.page_size, status_)


@router.get(
    "/workforce-imports/{batch_id}",
    response_model=WorkforceImportRead,
    summary="Get an import batch with its validation report",
    responses=error_responses(401, 403, 404),
)
def get_workforce_import(
    batch_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    include_ok_rows: bool = False,
) -> WorkforceImportRead:
    return imp.get(db, user, batch_id, include_ok_rows)


@router.post(
    "/workforce-imports/{batch_id}/commit",
    response_model=WorkforceImportRead,
    summary="Commit a validated batch (atomic; rows become submitted)",
    description="409 IMPORT_HAS_ERRORS when rows_error > 0 (AC3); 409 IMPORT_EXPIRED after "
    "60 min (AC5); 409 IMPORT_NOT_VALIDATED when already committed/discarded. The data is "
    "re-validated at commit; if it changed since the dry-run the batch is re-reported and "
    "409 IMPORT_HAS_ERRORS is returned when new errors appear.",
    responses=error_responses(401, 403, 404, 409),
)
def commit_workforce_import(batch_id: uuid.UUID, user: CurrentUser, db: DB) -> WorkforceImportRead:
    return imp.commit(db, user, batch_id)


@router.post(
    "/workforce-imports/{batch_id}/discard",
    response_model=WorkforceImportRead,
    summary="Discard a validated batch",
    responses=error_responses(401, 403, 404, 409),
)
def discard_workforce_import(batch_id: uuid.UUID, user: CurrentUser, db: DB) -> WorkforceImportRead:
    return imp.discard(db, user, batch_id)
