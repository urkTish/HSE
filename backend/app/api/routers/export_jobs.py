"""Generic register export (spec 6g-scorecard-reports §3.8, EX-1…EX-11): the dataset registry,
asynchronous export jobs with PDPL column classes, masking and purposes, the export log (232),
subscriptions and the dashboard PDF print (EX-11)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.api.kpi_params import KpiParams
from app.core.errors import error_responses
from app.core.scorecard_enums import XpJobStatus
from app.schemas.scorecard import (
    XpDatasetList,
    XpExportRequest,
    XpFileUrl,
    XpJobPage,
    XpJobRead,
    XpSubscriptionCreate,
    XpSubscriptionList,
    XpSubscriptionRead,
)
from app.services.scorecard import exports

router = APIRouter(tags=["exports"])


@router.get(
    "/export-datasets",
    response_model=XpDatasetList,
    summary="The dataset registry with column PDPL classes and the caller's rights (EX-1)",
    responses=error_responses(401),
)
def list_export_datasets(user: CurrentUser, db: DB) -> XpDatasetList:
    return exports.datasets(db, user)


@router.post(
    "/exports",
    response_model=XpJobRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request an export (EX-2…EX-9)",
    description="Rows = what the caller can list on screen. ≤ 5,000 rows run at once (status "
    "`ready`); 5,001-100,000 run as a job with an in-app notice; more → 422 EXPORT_TOO_LARGE. "
    "422 COLUMN_NOT_EXPORTABLE, PURPOSE_REQUIRED; 403 COLUMN_NOT_PERMITTED; 429 "
    "EXPORT_RATE_LIMIT (50 per user per day). Files expire after 7 days (24 h with a sensitive "
    "column) and are never e-mailed.",
    responses=error_responses(401, 403, 404, 422, 429),
)
def request_export(body: XpExportRequest, user: CurrentUser, db: DB) -> XpJobRead:
    return exports.request(db, user, body)


@router.get(
    "/export-jobs",
    response_model=XpJobPage,
    summary="Export log (232): own jobs; HSE Officers their projects; the HSE Manager all",
    responses=error_responses(401, 403),
)
def list_export_jobs(
    user: CurrentUser,
    db: DB,
    pg: PageParams,
    project_id: uuid.UUID | None = None,
    dataset: Annotated[str | None, Query(max_length=40)] = None,
    status_: Annotated[XpJobStatus | None, Query(alias="status")] = None,
    mine: bool = False,
) -> XpJobPage:
    return exports.list_jobs(db, user, project_id, dataset, status_, mine, pg.page, pg.page_size)


@router.get(
    "/export-jobs/{job_id}",
    response_model=XpJobRead,
    summary="One export job (never the file contents)",
    responses=error_responses(401, 403, 404),
)
def get_export_job(job_id: uuid.UUID, user: CurrentUser, db: DB) -> XpJobRead:
    return exports.read(db, user, job_id)


@router.get(
    "/export-jobs/{job_id}/file-url",
    response_model=XpFileUrl,
    summary="Signed URL (≤ 5 min) of a ready export file (requester only)",
    responses=error_responses(401, 403, 404, 409),
)
def get_export_file_url(job_id: uuid.UUID, user: CurrentUser, db: DB) -> XpFileUrl:
    return exports.file_url(db, user, job_id)


@router.get(
    "/export-subscriptions",
    response_model=XpSubscriptionList,
    summary="The caller's export subscriptions (232)",
    responses=error_responses(401),
)
def list_export_subscriptions(user: CurrentUser, db: DB) -> XpSubscriptionList:
    return exports.list_subscriptions(db, user)


@router.post(
    "/export-subscriptions",
    response_model=XpSubscriptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe to a weekly (Sunday 05:30) or monthly (day 1, 05:30) export (SC-4)",
    description="422 SUBSCRIPTION_PERSONAL_DATA when any personal or sensitive column is chosen.",
    responses=error_responses(401, 403, 404, 422),
)
def create_export_subscription(
    body: XpSubscriptionCreate, user: CurrentUser, db: DB
) -> XpSubscriptionRead:
    return exports.subscribe(db, user, body)


@router.delete(
    "/export-subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel an own subscription",
    responses=error_responses(401, 404),
)
def delete_export_subscription(subscription_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    exports.unsubscribe(db, user, subscription_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/dashboard-print",
    response_class=Response,
    summary="PDF print of the dashboard KPI tiles (D-10, EX-11; capability 42)",
    description="Rendered by the 6g renderer from the KPI endpoint values with the EX-6 footer; "
    "writes an `export` audit row.",
    responses={
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}},
        **error_responses(401, 403, 404, 422),
    },
)
def print_dashboard(user: CurrentUser, db: DB, q: KpiParams) -> Response:
    content: bytes
    filename: str
    content, filename = exports.dashboard_pdf(db, user, q)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
