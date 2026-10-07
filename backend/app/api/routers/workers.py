"""Worker register, project deployments and access cards (spec 2-access-permits §3.1, §3.2,
§4.1, §4.2, §5.1, §5.12)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.access_enums import DeploymentStatus, WorkerPersonType, WorkerStatus
from app.core.errors import error_responses
from app.core.hse_enums import Trade
from app.schemas.workers import (
    AccessCardRead,
    AccessCardReissueRequest,
    DeploymentCreate,
    DeploymentPage,
    DeploymentRead,
    DeploymentTransitionRequest,
    DeploymentUpdate,
    UnmaskRequest,
    WorkerCreate,
    WorkerDataReport,
    WorkerDataReportRequest,
    WorkerIdLookup,
    WorkerIdNumberRead,
    WorkerLookupResult,
    WorkerPage,
    WorkerRead,
    WorkerTransitionRequest,
    WorkerUpdate,
)
from app.services.access import workers as svc

router = APIRouter(tags=["workers"])


@router.get(
    "/workers",
    response_model=WorkerPage,
    summary="List workers in scope (capability 46; IDs masked)",
    description="Org-wide register filtered to workers with a deployment in the caller's scope "
    "(WK-11). `q` matches name or worker_no only — never the ID number (WK-3; use "
    "POST /workers/lookup). With `project_id` each item carries that project's deployment.",
    responses=error_responses(401, 403, 404, 422),
)
def list_workers(
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    project_id: uuid.UUID | None = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    site_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    status_: Annotated[list[WorkerStatus] | None, Query(alias="status")] = None,
    deployment_status: Annotated[list[DeploymentStatus] | None, Query()] = None,
    person_type: WorkerPersonType | None = None,
    trade: Trade | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["worker_no", "-worker_no", "name", "-name"] = "worker_no",
) -> WorkerPage:
    return svc.list_workers(
        db,
        user,
        pg.page,
        pg.page_size,
        project_id,
        engagement_id,
        include_subcontractors,
        site_id,
        status_,
        deployment_status,
        person_type,
        trade,
        q,
        sort,
    )


@router.post(
    "/workers",
    response_model=WorkerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a worker, optionally with the first deployment (capability 47)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_worker(body: WorkerCreate, user: CurrentUser, db: DB) -> WorkerRead:
    return svc.create_worker(db, user, body)


@router.post(
    "/workers/lookup",
    response_model=WorkerLookupResult,
    summary="Find a worker by full ID number (exact match through the blind index, WK-3)",
    description="POST so the ID number never appears in URLs or access logs. Returns 0 or 1 "
    "item in the caller's scope.",
    responses=error_responses(401, 403, 422),
)
def lookup_worker(body: WorkerIdLookup, user: CurrentUser, db: DB) -> WorkerLookupResult:
    return svc.lookup(db, user, body)


@router.get(
    "/workers/{worker_id}",
    response_model=WorkerRead,
    summary="Get a worker (masked ID)",
    responses=error_responses(401, 403, 404),
)
def get_worker(worker_id: uuid.UUID, user: CurrentUser, db: DB) -> WorkerRead:
    return svc.read_worker(db, user, worker_id)


@router.patch(
    "/workers/{worker_id}",
    response_model=WorkerRead,
    summary="Edit a worker (capability 47; ID change kept in encrypted history, WK-9)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_worker(
    worker_id: uuid.UUID, body: WorkerUpdate, user: CurrentUser, db: DB
) -> WorkerRead:
    return svc.update_worker(db, user, worker_id, body)


@router.post(
    "/workers/{worker_id}/transitions",
    response_model=WorkerRead,
    summary="Ban / lift ban (capability 49; ban cascades LC-9)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_worker(
    worker_id: uuid.UUID, body: WorkerTransitionRequest, user: CurrentUser, db: DB
) -> WorkerRead:
    return svc.transition_worker(db, user, worker_id, body)


@router.post(
    "/workers/{worker_id}/id-number/unmask",
    response_model=WorkerIdNumberRead,
    summary="Reveal the full ID number with a reason (capability 48; audited, WK-5)",
    description="Writes `sensitive_field_read` (field id_number, reason). Show the value only "
    "on demand and do not cache it.",
    responses=error_responses(401, 403, 404, 422),
)
def unmask_worker_id(
    worker_id: uuid.UUID, body: UnmaskRequest, user: CurrentUser, db: DB
) -> WorkerIdNumberRead:
    return svc.unmask(db, user, worker_id, body)


@router.post(
    "/workers/{worker_id}/data-report",
    response_model=WorkerDataReport,
    summary="Per-worker data report for a data-subject request (capability 79, P2-11)",
    responses=error_responses(401, 403, 404, 422),
)
def worker_data_report(
    worker_id: uuid.UUID, body: WorkerDataReportRequest, user: CurrentUser, db: DB
) -> WorkerDataReport:
    return svc.data_report(db, user, worker_id, body)


# ---- deployments --------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/deployments",
    response_model=DeploymentPage,
    summary="List deployments of a project (capability 46)",
    responses=error_responses(401, 403, 404, 422),
)
def list_deployments(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    site_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    status_: Annotated[list[DeploymentStatus] | None, Query(alias="status")] = None,
    trade: Trade | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> DeploymentPage:
    return svc.list_deployments(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        engagement_id,
        include_subcontractors,
        site_id,
        status_,
        trade,
        q,
    )


@router.post(
    "/projects/{project_id}/deployments",
    response_model=DeploymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Deploy an existing worker on the project (capability 47) → pending_induction",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_deployment(
    project_id: uuid.UUID, body: DeploymentCreate, user: CurrentUser, db: DB
) -> DeploymentRead:
    return svc.create_deployment(db, user, project_id, body)


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentRead,
    summary="Get a deployment with induction and credential badges",
    responses=error_responses(401, 403, 404),
)
def get_deployment(deployment_id: uuid.UUID, user: CurrentUser, db: DB) -> DeploymentRead:
    return svc.read_deployment(db, user, deployment_id)


@router.patch(
    "/deployments/{deployment_id}",
    response_model=DeploymentRead,
    summary="Edit a deployment (capability 47)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_deployment(
    deployment_id: uuid.UUID, body: DeploymentUpdate, user: CurrentUser, db: DB
) -> DeploymentRead:
    return svc.update_deployment(db, user, deployment_id, body)


@router.post(
    "/deployments/{deployment_id}/transitions",
    response_model=DeploymentRead,
    summary="Demobilise (capability 47; cascades LC-10)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_deployment(
    deployment_id: uuid.UUID, body: DeploymentTransitionRequest, user: CurrentUser, db: DB
) -> DeploymentRead:
    return svc.transition_deployment(db, user, deployment_id, body)


@router.get(
    "/deployments/{deployment_id}/access-card",
    response_model=AccessCardRead,
    summary="Access card QR payload to print (capability 47; mobilised deployments only)",
    description="409 TRANSITION_CONDITION_NOT_MET while pending_induction (no token yet, IN-1).",
    responses=error_responses(401, 403, 404, 409),
)
def get_access_card(deployment_id: uuid.UUID, user: CurrentUser, db: DB) -> AccessCardRead:
    return svc.access_card(db, user, deployment_id)


@router.post(
    "/deployments/{deployment_id}/access-card/reissue",
    response_model=AccessCardRead,
    summary="Reissue the access card: rotate the token (capability 47; GC-16)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def reissue_access_card(
    deployment_id: uuid.UUID, body: AccessCardReissueRequest, user: CurrentUser, db: DB
) -> AccessCardRead:
    return svc.reissue_card(db, user, deployment_id, body)
