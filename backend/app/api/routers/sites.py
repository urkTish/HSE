"""Sites and zones (spec §3.2, §3.3, §4.4, §5.3)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, PageParams
from app.core.enums import AirsideArea, SiteSide, SiteStatus, ZoneStatus, ZoneType
from app.core.errors import error_responses, not_implemented
from app.schemas.org import (
    SiteCreate,
    SitePage,
    SiteRead,
    SiteTransitionRequest,
    SiteUpdate,
    ZoneCreate,
    ZonePage,
    ZoneRead,
    ZoneTransitionRequest,
    ZoneUpdate,
)

router = APIRouter(tags=["sites & zones"])

OrgSort = Literal["code", "-code", "name", "-name"]
Q = Annotated[str | None, Query(max_length=100, description="Code/name search.")]


@router.get(
    "/projects/{project_id}/sites",
    response_model=SitePage,
    summary="List sites of a project (restricted to assigned sites when scoped)",
    responses=error_responses(401, 403, 404, 422),
)
def list_sites(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    status_: Annotated[SiteStatus | None, Query(alias="status")] = None,
    site_side: SiteSide | None = None,
    q: Q = None,
    sort: OrgSort = "code",
) -> SitePage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/sites",
    response_model=SiteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a site",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_site(project_id: uuid.UUID, body: SiteCreate, user: CurrentUser) -> SiteRead:
    raise not_implemented()


@router.get(
    "/sites/{site_id}",
    response_model=SiteRead,
    summary="Get a site",
    responses=error_responses(401, 403, 404),
)
def get_site(site_id: uuid.UUID, user: CurrentUser) -> SiteRead:
    raise not_implemented()


@router.patch(
    "/sites/{site_id}",
    response_model=SiteRead,
    summary="Update a site",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_site(site_id: uuid.UUID, body: SiteUpdate, user: CurrentUser) -> SiteRead:
    raise not_implemented()


@router.post(
    "/sites/{site_id}/transitions",
    response_model=SiteRead,
    summary="Activate / inactivate a site",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_site(site_id: uuid.UUID, body: SiteTransitionRequest, user: CurrentUser) -> SiteRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/zones",
    response_model=ZonePage,
    summary="List zones of a project (restricted to assigned sites when scoped)",
    responses=error_responses(401, 403, 404, 422),
)
def list_zones(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    site_id: uuid.UUID | None = None,
    zone_type: ZoneType | None = None,
    airside_area: AirsideArea | None = None,
    status_: Annotated[ZoneStatus | None, Query(alias="status")] = None,
    q: Q = None,
    sort: OrgSort = "code",
) -> ZonePage:
    raise not_implemented()


@router.post(
    "/sites/{site_id}/zones",
    response_model=ZoneRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a zone in a site",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_zone(site_id: uuid.UUID, body: ZoneCreate, user: CurrentUser) -> ZoneRead:
    raise not_implemented()


@router.get(
    "/zones/{zone_id}",
    response_model=ZoneRead,
    summary="Get a zone",
    responses=error_responses(401, 403, 404),
)
def get_zone(zone_id: uuid.UUID, user: CurrentUser) -> ZoneRead:
    raise not_implemented()


@router.patch(
    "/zones/{zone_id}",
    response_model=ZoneRead,
    summary="Update a zone (airside attribute changes audited with before/after)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_zone(zone_id: uuid.UUID, body: ZoneUpdate, user: CurrentUser) -> ZoneRead:
    raise not_implemented()


@router.post(
    "/zones/{zone_id}/transitions",
    response_model=ZoneRead,
    summary="Close temporarily / reopen / archive a zone",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_zone(zone_id: uuid.UUID, body: ZoneTransitionRequest, user: CurrentUser) -> ZoneRead:
    raise not_implemented()
