"""Sites and zones (spec §3.2, §3.3, §4.4, §5.3 rules 17-23)."""

import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.enums import (
    AirsideArea,
    AuditAction,
    Capability,
    EntityType,
    Language,
    SiteSide,
    SiteStatus,
    ZoneStatus,
    ZoneType,
)
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.text import like_pattern, search_blob
from app.models import Project, Site, Zone
from app.models.org import AIRSIDE_FIELDS
from app.schemas.org import (
    AirsideAttributes,
    AirsideAttributesInput,
    SiteCreate,
    SiteRead,
    SiteTransitionRequest,
    SiteUpdate,
    ZoneCreate,
    ZoneRead,
    ZoneTransitionRequest,
    ZoneUpdate,
)
from app.services import audit, projects
from app.services.common import duplicate, ensure_open, invalid_transition
from app.services.permissions import Grant, Principal, deny, forbidden_error

SITE_FIELDS = ("code", "name_en", "name_ar", "site_side", "gps_lat", "gps_lng")
ZONE_FIELDS = ("code", "name_en", "name_ar", "zone_type", *AIRSIDE_FIELDS)


def site_read(s: Site) -> SiteRead:
    return SiteRead.model_validate(s)


def zone_read(z: Zone) -> ZoneRead:
    airside = None
    if z.zone_type == ZoneType.airside:
        airside = AirsideAttributes(**{f: getattr(z, f) for f in AIRSIDE_FIELDS})
    return ZoneRead(
        id=z.id,
        project_id=z.project_id,
        site_id=z.site_id,
        code=z.code,
        name_en=z.name_en,
        name_ar=z.name_ar,
        zone_type=z.zone_type,
        status=z.status,
        status_reason=z.status_reason,
        airside=airside,
        created_at=z.created_at,
        updated_at=z.updated_at,
    )


def _sort(stmt: Select[Any], model: type[Site] | type[Zone], sort: str, lang: Language) -> Any:
    key = sort.lstrip("-")
    if key == "name":
        col: Any = (
            model.name_ar.collate("ar-x-icu")
            if lang == Language.ar
            else model.name_en.collate("en-x-icu")
        )
    else:
        col = model.code
    return stmt.order_by(col.desc() if sort.startswith("-") else col.asc(), model.id)


def _view_grant(db: Session, p: Principal, project: Project) -> Grant:
    g = p.grant(project.id, Capability.site_zone_view)
    if g is None:
        raise forbidden_error()
    return g


# ---- sites -----------------------------------------------------------------------------
def list_sites_query(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    status: SiteStatus | None = None,
    site_side: SiteSide | None = None,
    q: str | None = None,
    sort: str = "code",
    lang: Language = Language.en,
) -> Select[Site]:
    project = projects.get_visible(db, p, project_id)
    g = _view_grant(db, p, project)
    stmt = select(Site).where(Site.project_id == project_id)
    if g.site_ids is not None:
        stmt = stmt.where(Site.id.in_(g.site_ids))
    if status:
        stmt = stmt.where(Site.status == status)
    if site_side:
        stmt = stmt.where(Site.site_side == site_side)
    if q:
        stmt = stmt.where(Site.search_text.like(like_pattern(q)))
    return _sort(stmt, Site, sort, lang)  # type: ignore[no-any-return]


def get_site(db: Session, p: Principal, site_id: uuid.UUID) -> Site:
    site = db.get(Site, site_id)
    if site is None or not p.can_see_project(site.project_id):
        raise deny(db, p, EntityType.site, site_id, site.project_id if site else None, "Site")
    g = p.grant(site.project_id, Capability.site_zone_view)
    if g is None or not g.covers_site(site.id):
        raise deny(db, p, EntityType.site, site_id, site.project_id, "Site")
    return site


def _check_site_side(project: Project, side: SiteSide) -> None:
    if side in (SiteSide.airside, SiteSide.mixed) and not project.is_airport:
        raise validation_error(
            "site_side", "airside/mixed sites are only allowed on airport projects."
        )


def _allowed_zone_types(project: Project, side: SiteSide) -> set[ZoneType]:
    if not project.is_airport:
        return {ZoneType.other}
    return {
        SiteSide.airside: {ZoneType.airside},
        SiteSide.landside: {ZoneType.landside, ZoneType.other},
        SiteSide.mixed: {ZoneType.airside, ZoneType.landside, ZoneType.other},
        SiteSide.other: {ZoneType.landside, ZoneType.other},
    }[side]


def create_site(db: Session, p: Principal, project_id: uuid.UUID, body: SiteCreate) -> Site:
    project = projects.get_visible(db, p, project_id)
    g = p.require(project_id, Capability.site_zone_manage)
    if g.site_ids is not None:
        raise forbidden_error("Your role is limited to specific sites.")
    ensure_open(project)
    _check_site_side(project, body.site_side)
    if db.scalar(select(Site.id).where(Site.project_id == project_id, Site.code == body.code)):
        raise duplicate("code", "A site with this code already exists in the project.")
    site = Site(
        id=uuid.uuid4(), project_id=project_id, status=SiteStatus.active, **body.model_dump()
    )
    site.search_text = search_blob(site.code, site.name_en, site.name_ar)
    db.add(site)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project_id),
        entity_type=EntityType.site,
        entity_id=site.id,
        project_id=project_id,
        after={f: getattr(site, f) for f in SITE_FIELDS},
    )
    return site


def _manage_site(db: Session, p: Principal, site: Site) -> Project:
    g = p.require(site.project_id, Capability.site_zone_manage)
    if not g.covers_site(site.id):
        raise forbidden_error()
    project = db.get(Project, site.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    return project


def update_site(db: Session, p: Principal, site_id: uuid.UUID, body: SiteUpdate) -> Site:
    site = get_site(db, p, site_id)
    project = _manage_site(db, p, site)
    changes = body.changes()
    if "site_side" in changes:
        _check_site_side(project, changes["site_side"])
        allowed = _allowed_zone_types(project, changes["site_side"])
        types = set(db.scalars(select(Zone.zone_type).where(Zone.site_id == site.id)).all())
        if not types <= allowed:
            raise validation_error("site_side", "Existing zones contradict the new site side.")
    if (
        "code" in changes
        and changes["code"] != site.code
        and db.scalar(
            select(Site.id).where(Site.project_id == site.project_id, Site.code == changes["code"])
        )
    ):
        raise duplicate("code", "A site with this code already exists in the project.")
    before = {f: getattr(site, f) for f in SITE_FIELDS}
    for k, v in changes.items():
        setattr(site, k, v)
    site.search_text = search_blob(site.code, site.name_en, site.name_ar)
    b, a = audit.diff(before, {f: getattr(site, f) for f in SITE_FIELDS})
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(site.project_id),
            entity_type=EntityType.site,
            entity_id=site.id,
            project_id=site.project_id,
            before=b,
            after=a,
        )
    return site


def transition_site(
    db: Session, p: Principal, site_id: uuid.UUID, body: SiteTransitionRequest
) -> Site:
    site = get_site(db, p, site_id)
    _manage_site(db, p, site)
    if site.status == body.to_status:
        raise invalid_transition("Site", site.status, body.to_status)
    before = site.status
    site.status = body.to_status
    site.status_reason = body.reason
    audit.record(
        db,
        AuditAction.archive if body.to_status == SiteStatus.inactive else AuditAction.status_change,
        p.actor(site.project_id),
        entity_type=EntityType.site,
        entity_id=site.id,
        project_id=site.project_id,
        before={"status": before},
        after={"status": site.status},
        details={"reason": body.reason},
    )
    return site


# ---- zones -----------------------------------------------------------------------------
def list_zones_query(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    zone_type: ZoneType | None = None,
    airside_area: AirsideArea | None = None,
    status: ZoneStatus | None = None,
    q: str | None = None,
    sort: str = "code",
    lang: Language = Language.en,
) -> Select[Zone]:
    project = projects.get_visible(db, p, project_id)
    g = _view_grant(db, p, project)
    stmt = select(Zone).where(Zone.project_id == project_id)
    if g.site_ids is not None:
        stmt = stmt.where(Zone.site_id.in_(g.site_ids))  # rule 11 / AC10
    if site_id:
        stmt = stmt.where(Zone.site_id == site_id)
    if zone_type:
        stmt = stmt.where(Zone.zone_type == zone_type)
    if airside_area:
        stmt = stmt.where(Zone.airside_area == airside_area)
    if status:
        stmt = stmt.where(Zone.status == status)
    if q:
        stmt = stmt.where(Zone.search_text.like(like_pattern(q)))
    return _sort(stmt, Zone, sort, lang)  # type: ignore[no-any-return]


def get_zone(db: Session, p: Principal, zone_id: uuid.UUID) -> Zone:
    zone = db.get(Zone, zone_id)
    if zone is None or not p.can_see_project(zone.project_id):
        raise deny(db, p, EntityType.zone, zone_id, zone.project_id if zone else None, "Zone")
    g = p.grant(zone.project_id, Capability.site_zone_view)
    if g is None or not g.covers_site(zone.site_id):
        raise deny(db, p, EntityType.zone, zone_id, zone.project_id, "Zone")
    return zone


def _zone_dict(z: Zone) -> dict[str, Any]:
    return {f: getattr(z, f) for f in ZONE_FIELDS}


def _apply_type(
    project: Project, site: Site, zone_type: ZoneType, airside: AirsideAttributesInput | None
) -> dict[str, Any]:
    if zone_type in (ZoneType.airside, ZoneType.landside) and not project.is_airport:
        raise validation_error(
            "zone_type", "airside/landside zones are only allowed on airport projects (rule 18)."
        )
    if zone_type not in _allowed_zone_types(project, site.site_side):
        raise validation_error(
            "zone_type",
            f"zone_type {zone_type.value} contradicts the site side {site.site_side.value}.",
        )
    if zone_type == ZoneType.airside:
        if airside is None:
            raise validation_error("airside", "Airside attributes are required (rule 19).")
        return airside.model_dump()
    if airside is not None:
        raise validation_error("airside", "Airside attributes must be null for non-airside zones.")
    return dict.fromkeys(AIRSIDE_FIELDS)


def create_zone(db: Session, p: Principal, site_id: uuid.UUID, body: ZoneCreate) -> Zone:
    site = get_site(db, p, site_id)
    project = _manage_site(db, p, site)
    if site.status != SiteStatus.active:
        raise ApiError(409, ErrorCode.SITE_INACTIVE, "The site is inactive.", "الموقع غير نشط.")
    attrs = _apply_type(project, site, body.zone_type, body.airside)
    if db.scalar(select(Zone.id).where(Zone.site_id == site_id, Zone.code == body.code)):
        raise duplicate("code", "A zone with this code already exists in the site.")
    zone = Zone(
        id=uuid.uuid4(),
        project_id=site.project_id,
        site_id=site.id,
        code=body.code,
        name_en=body.name_en,
        name_ar=body.name_ar,
        zone_type=body.zone_type,
        status=ZoneStatus.active,
        **attrs,
    )
    zone.search_text = search_blob(zone.code, zone.name_en, zone.name_ar)
    db.add(zone)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(site.project_id),
        entity_type=EntityType.zone,
        entity_id=zone.id,
        project_id=site.project_id,
        after=_zone_dict(zone),
    )
    return zone


def _manage_zone(db: Session, p: Principal, zone: Zone) -> tuple[Project, Site]:
    site = db.get(Site, zone.site_id)
    assert site is not None  # noqa: S101
    return _manage_site(db, p, site), site


def update_zone(db: Session, p: Principal, zone_id: uuid.UUID, body: ZoneUpdate) -> Zone:
    zone = get_zone(db, p, zone_id)
    project, site = _manage_zone(db, p, zone)
    if zone.status == ZoneStatus.archived:
        raise ApiError(409, ErrorCode.ZONE_ARCHIVED, "The zone is archived.", "المنطقة مؤرشفة.")
    changes = body.changes()
    new_type = changes.pop("zone_type", zone.zone_type)
    airside_sent = "airside" in changes
    changes.pop("airside", None)
    if new_type != zone.zone_type or airside_sent:
        airside = body.airside
        if not airside_sent and new_type == ZoneType.airside:
            airside = None
        changes.update(_apply_type(project, site, new_type, airside))
        changes["zone_type"] = new_type
    if (
        "code" in changes
        and changes["code"] != zone.code
        and db.scalar(
            select(Zone.id).where(Zone.site_id == zone.site_id, Zone.code == changes["code"])
        )
    ):
        raise duplicate("code", "A zone with this code already exists in the site.")
    before = _zone_dict(zone)
    for k, v in changes.items():
        setattr(zone, k, v)
    zone.search_text = search_blob(zone.code, zone.name_en, zone.name_ar)
    b, a = audit.diff(before, _zone_dict(zone))
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(zone.project_id),
            entity_type=EntityType.zone,
            entity_id=zone.id,
            project_id=zone.project_id,
            before=b,
            after=a,
        )
    return zone


ZS = ZoneStatus
ZONE_TRANSITIONS = {
    (ZS.active, ZS.temporarily_closed),
    (ZS.temporarily_closed, ZS.active),
    (ZS.active, ZS.archived),
    (ZS.temporarily_closed, ZS.archived),
}


def transition_zone(
    db: Session, p: Principal, zone_id: uuid.UUID, body: ZoneTransitionRequest
) -> Zone:
    zone = get_zone(db, p, zone_id)
    _manage_zone(db, p, zone)
    key = (zone.status, body.to_status)
    if key not in ZONE_TRANSITIONS:
        raise invalid_transition("Zone", *key)
    zone.status = body.to_status
    zone.status_reason = body.reason
    audit.record(
        db,
        AuditAction.archive if body.to_status == ZS.archived else AuditAction.status_change,
        p.actor(zone.project_id),
        entity_type=EntityType.zone,
        entity_id=zone.id,
        project_id=zone.project_id,
        before={"status": key[0]},
        after={"status": key[1]},
        details={"reason": body.reason},
    )
    return zone
