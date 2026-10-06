"""Projects and project settings (spec §3.1, §3.9, §4.1, §5.5)."""

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import (
    AuditAction,
    Capability,
    EntityType,
    Language,
    NotificationKind,
    ProjectStatus,
    ProjectType,
    Role,
    SiteSide,
    ZoneType,
)
from app.core.errors import validation_error
from app.core.text import like_pattern, search_blob
from app.models import Project, ProjectSettings, Site, Zone
from app.schemas.projects import (
    ProjectCreate,
    ProjectRead,
    ProjectSettingsRead,
    ProjectSettingsUpdate,
    ProjectTransitionRequest,
    ProjectUpdate,
)
from app.services import audit, notify
from app.services.common import (
    condition_not_met,
    duplicate,
    ensure_open,
    invalid_transition,
    require_reason,
)
from app.services.permissions import Principal, deny, forbidden_error

FIELDS = (
    "code",
    "name_en",
    "name_ar",
    "project_type",
    "client_name_en",
    "client_name_ar",
    "city",
    "start_date",
    "planned_end_date",
    "airport_icao",
)
SETTINGS_FIELDS = (
    "ltifr_base_hours",
    "rate_base_hours",
    "timezone",
    "show_hijri",
    "hijri_calendar",
    "default_language",
    "week_start",
    "digits",
    "date_format_en",
    "audit_retention_years",
    "inactive_account_days",
)


def _dict(p: Project) -> dict[str, Any]:
    return {f: getattr(p, f) for f in FIELDS}


def to_read(p: Project) -> ProjectRead:
    return ProjectRead(
        id=p.id,
        is_airport=p.is_airport,
        status=p.status,
        status_reason=p.status_reason,
        created_at=p.created_at,
        updated_at=p.updated_at,
        **_dict(p),
    )


def get_visible(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or not p.can_see_project(project_id):
        raise deny(db, p, EntityType.project, project_id, project_id, "Project")
    return project


def list_query(
    p: Principal,
    statuses: list[ProjectStatus] | None,
    project_type: ProjectType | None,
    q: str | None,
    sort: str,
    lang: Language,
) -> Select[Project]:
    stmt = select(Project)
    if not p.is_manager:
        stmt = stmt.where(Project.id.in_(list(p.projects)))
    if statuses:
        stmt = stmt.where(Project.status.in_(statuses))
    if project_type:
        stmt = stmt.where(Project.project_type == project_type)
    if q:
        stmt = stmt.where(Project.search_text.like(like_pattern(q)))
    key = sort.lstrip("-")
    col: Any = {
        "code": Project.code,
        "start_date": Project.start_date,
        "name": Project.name_ar.collate("ar-x-icu")
        if lang == Language.ar
        else Project.name_en.collate("en-x-icu"),
    }[key]
    return stmt.order_by(col.desc() if sort.startswith("-") else col.asc(), Project.id)


def _search(p: Project) -> str:
    return search_blob(p.code, p.name_en, p.name_ar, p.client_name_en, p.client_name_ar, p.city)


def create(db: Session, p: Principal, body: ProjectCreate) -> Project:
    p.require(None, Capability.project_manage)
    if db.scalar(select(Project.id).where(Project.code == body.code)):
        raise duplicate("code", "A project with this code already exists.")
    project = Project(id=uuid.uuid4(), status=ProjectStatus.planning, **body.model_dump())
    project.search_text = _search(project)
    db.add(project)
    db.flush()
    db.add(ProjectSettings(project_id=project.id, updated_at=now(), updated_by_user_id=p.user.id))
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.project,
        entity_id=project.id,
        project_id=project.id,
        after={**_dict(project), "status": project.status},
    )
    return project


def update(db: Session, p: Principal, project_id: uuid.UUID, body: ProjectUpdate) -> Project:
    project = get_visible(db, p, project_id)
    p.require(project_id, Capability.project_manage)
    ensure_open(project)
    changes = body.changes()
    new_type = changes.get("project_type", project.project_type)
    icao = changes.get("airport_icao", project.airport_icao)
    if new_type == ProjectType.airport and not icao:
        raise validation_error("airport_icao", "airport_icao is required for airport projects.")
    if new_type != ProjectType.airport:
        if changes.get("airport_icao"):
            raise validation_error("airport_icao", "Only airport projects have an ICAO code.")
        changes["airport_icao"] = None
        airside_sites = db.scalar(
            select(func.count())
            .select_from(Site)
            .where(
                Site.project_id == project.id,
                Site.site_side.in_([SiteSide.airside, SiteSide.mixed]),
            )
        )
        airport_zones = db.scalar(
            select(func.count())
            .select_from(Zone)
            .where(Zone.project_id == project.id, Zone.zone_type != ZoneType.other)
        )
        if airside_sites or airport_zones:
            raise validation_error(
                "project_type",
                "The project has airside/mixed sites or airside/landside zones (rule 18).",
            )
    start = changes.get("start_date", project.start_date)
    end = changes.get("planned_end_date", project.planned_end_date)
    if end and end < start:
        raise validation_error("planned_end_date", "planned_end_date must be on or after start.")
    before = _dict(project)
    for k, v in changes.items():
        setattr(project, k, v)
    project.search_text = _search(project)
    b, a = audit.diff(before, _dict(project))
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project.id),
            entity_type=EntityType.project,
            entity_id=project.id,
            project_id=project.id,
            before=b,
            after=a,
        )
    return project


PS = ProjectStatus
PROJECT_TRANSITIONS: dict[tuple[ProjectStatus, ProjectStatus], bool] = {
    # (from, to): reason required   — spec §4.1, HSE Manager only
    (PS.planning, PS.active): False,
    (PS.active, PS.on_hold): True,
    (PS.on_hold, PS.active): False,
    (PS.active, PS.closed): True,
    (PS.on_hold, PS.closed): True,
    (PS.closed, PS.active): True,
}


def transition(
    db: Session, p: Principal, project_id: uuid.UUID, body: ProjectTransitionRequest
) -> Project:
    project = get_visible(db, p, project_id)
    p.require(project_id, Capability.project_manage)
    key = (project.status, body.to_status)
    if key not in PROJECT_TRANSITIONS:
        raise invalid_transition("Project", *key)
    reason = body.reason
    if PROJECT_TRANSITIONS[key]:
        reason = require_reason(reason, f"move the project to {body.to_status.value}")
    if key == (PS.planning, PS.active):
        sites = db.scalar(
            select(func.count()).select_from(Site).where(Site.project_id == project.id)
        )
        if not sites:
            raise condition_not_met(
                "Add at least one site before activating the project.",
                "أضف موقعاً واحداً على الأقل قبل تفعيل المشروع.",
            )
        if project.settings.saved_at is None:
            raise condition_not_met(
                "Save the project settings before activating the project.",
                "احفظ إعدادات المشروع قبل تفعيله.",
            )
    project.status = body.to_status
    project.status_reason = reason
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id),
        entity_type=EntityType.project,
        entity_id=project.id,
        project_id=project.id,
        before={"status": key[0]},
        after={"status": key[1]},
        details={"reason": reason},
    )
    return project


# ---- settings ------------------------------------------------------------------------------------
def base_label(base: int, lang: Language) -> str:
    """Rule 31: the base is printed next to every rate."""
    return f"per {base:,} h" if lang == Language.en else f"لكل {base:,} ساعة"


def settings_read(s: ProjectSettings) -> ProjectSettingsRead:
    return ProjectSettingsRead(
        project_id=s.project_id,
        ltifr_base_label_en=base_label(s.ltifr_base_hours, Language.en),
        ltifr_base_label_ar=base_label(s.ltifr_base_hours, Language.ar),
        rate_base_label_en=base_label(s.rate_base_hours, Language.en),
        rate_base_label_ar=base_label(s.rate_base_hours, Language.ar),
        saved_at=s.saved_at,
        updated_at=s.updated_at,
        updated_by_user_id=s.updated_by_user_id,
        **{f: getattr(s, f) for f in SETTINGS_FIELDS},
    )


def get_settings_for(db: Session, p: Principal, project_id: uuid.UUID) -> ProjectSettings:
    project = get_visible(db, p, project_id)
    if p.grant(project_id, Capability.settings_view) is None:
        raise forbidden_error()
    return project.settings


def update_settings(
    db: Session, p: Principal, project_id: uuid.UUID, body: ProjectSettingsUpdate
) -> ProjectSettings:
    project = get_visible(db, p, project_id)
    p.require(project_id, Capability.settings_edit)
    ensure_open(project)
    s = project.settings
    changes = body.changes()
    before = {f: getattr(s, f) for f in SETTINGS_FIELDS}
    for k, v in changes.items():
        setattr(s, k, v)
    current = now()
    s.saved_at = s.saved_at or current
    s.updated_at = current
    s.updated_by_user_id = p.user.id
    b, a = audit.diff(before, {f: getattr(s, f) for f in SETTINGS_FIELDS})
    if a:
        audit.record(
            db,
            AuditAction.settings_changed,
            p.actor(project.id),
            entity_type=EntityType.project_settings,
            entity_id=project.id,
            project_id=project.id,
            before=b,
            after=a,
        )
        notify.notify(
            db,
            notify.users_with_role(db, Role.hse_officer, [project.id]),
            NotificationKind.settings_changed,
            f"Settings changed on {project.code}",
            f"تم تغيير إعدادات المشروع {project.code}",
            body_en=", ".join(sorted(a)),
            entity_type=EntityType.project_settings,
            entity_id=project.id,
            project_id=project.id,
        )
    return s
