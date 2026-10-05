"""Sites and zones (spec §3.2, §3.3, §4.4, §5.3)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.enums import AirsideArea, SiteSide, SiteStatus, ZoneStatus, ZoneType
from app.core.errors import error_responses
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
from app.services import org as svc
from app.services.common import paginate

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
    db: DB,
    status_: Annotated[SiteStatus | None, Query(alias="status")] = None,
    site_side: SiteSide | None = None,
    q: Q = None,
    sort: OrgSort = "code",
) -> SitePage:
    stmt = svc.list_sites_query(
        db, user, project_id, status_, site_side, q, sort, user.user.preferred_language
    )
    items, total = paginate(db, stmt, pg.page, pg.page_size)
    return SitePage(
        items=[svc.site_read(x) for x in items], total=total, page=pg.page, page_size=pg.page_size
    )


@router.post(
    "/projects/{project_id}/sites",
    response_model=SiteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a site",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_site(project_id: uuid.UUID, body: SiteCreate, user: CurrentUser, db: DB) -> SiteRead:
    return svc.site_read(svc.create_site(db, user, project_id, body))


@router.get(
    "/sites/{site_id}",
    response_model=SiteRead,
    summary="Get a site",
    responses=error_responses(401, 403, 404),
)
def get_site(site_id: uuid.UUID, user: CurrentUser, db: DB) -> SiteRead:
    return svc.site_read(svc.get_site(db, user, site_id))


@router.patch(
    "/sites/{site_id}",
    response_model=SiteRead,
    summary="Update a site",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_site(site_id: uuid.UUID, body: SiteUpdate, user: CurrentUser, db: DB) -> SiteRead:
    return svc.site_read(svc.update_site(db, user, site_id, body))


@router.post(
    "/sites/{site_id}/transitions",
    response_model=SiteRead,
    summary="Activate / inactivate a site",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_site(
    site_id: uuid.UUID, body: SiteTransitionRequest, user: CurrentUser, db: DB
) -> SiteRead:
    return svc.site_read(svc.transition_site(db, user, site_id, body))


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
    db: DB,
    site_id: uuid.UUID | None = None,
    zone_type: ZoneType | None = None,
    airside_area: AirsideArea | None = None,
    status_: Annotated[ZoneStatus | None, Query(alias="status")] = None,
    q: Q = None,
    sort: OrgSort = "code",
) -> ZonePage:
    stmt = svc.list_zones_query(
        db,
        user,
        project_id,
        site_id,
        zone_type,
        airside_area,
        status_,
        q,
        sort,
        user.user.preferred_language,
    )
    items, total = paginate(db, stmt, pg.page, pg.page_size)
    return ZonePage(
        items=[svc.zone_read(x) for x in items], total=total, page=pg.page, page_size=pg.page_size
    )


@router.post(
    "/sites/{site_id}/zones",
    response_model=ZoneRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a zone in a site",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_zone(site_id: uuid.UUID, body: ZoneCreate, user: CurrentUser, db: DB) -> ZoneRead:
    return svc.zone_read(svc.create_zone(db, user, site_id, body))


@router.get(
    "/zones/{zone_id}",
    response_model=ZoneRead,
    summary="Get a zone",
    responses=error_responses(401, 403, 404),
)
def get_zone(zone_id: uuid.UUID, user: CurrentUser, db: DB) -> ZoneRead:
    return svc.zone_read(svc.get_zone(db, user, zone_id))


@router.patch(
    "/zones/{zone_id}",
    response_model=ZoneRead,
    summary="Update a zone (airside attribute changes audited with before/after)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_zone(zone_id: uuid.UUID, body: ZoneUpdate, user: CurrentUser, db: DB) -> ZoneRead:
    return svc.zone_read(svc.update_zone(db, user, zone_id, body))


@router.post(
    "/zones/{zone_id}/transitions",
    response_model=ZoneRead,
    summary="Close temporarily / reopen / archive a zone",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_zone(
    zone_id: uuid.UUID, body: ZoneTransitionRequest, user: CurrentUser, db: DB
) -> ZoneRead:
    return svc.zone_read(svc.transition_zone(db, user, zone_id, body))
