"""Helpers shared by the Phase 1 registers (spec 1-dashboard): reference rows, ref numbers,
scope checks, period locks, possible-ID scan (P1-8)."""

import re
import uuid
from collections.abc import Iterable
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.core.enums import (
    AuditAction,
    Capability,
    EntityType,
    NotificationKind,
    Role,
    ZoneStatus,
)
from app.core.errors import ApiError, ErrorCode, validation_error
from app.kpi.periods import month_start
from app.models import (
    PeriodLock,
    Project,
    ProjectEngagement,
    RoleAssignment,
    Site,
    User,
    Zone,
)
from app.schemas.hse_common import ApiWarning, EngagementRef, SiteRef, UserRef, ZoneRef
from app.services import audit, notify
from app.services.permissions import Grant, Principal, engagement_descendants, forbidden_error

POSSIBLE_ID = re.compile(r"(?<!\d)[12]\d{9}(?!\d)")


def project_today(project: Project) -> date:
    return today(project.settings.timezone if project.settings else "Asia/Riyadh")


# ---- refs ----------------------------------------------------------------------------------------


class Refs:
    """Batch-loaded reference rows for building read models without N+1 queries."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.sites: dict[uuid.UUID, Site] = {}
        self.zones: dict[uuid.UUID, Zone] = {}
        self.engs: dict[uuid.UUID, ProjectEngagement] = {}
        self.users: dict[uuid.UUID, User] = {}

    def load(
        self,
        sites: Iterable[uuid.UUID | None] = (),
        zones: Iterable[uuid.UUID | None] = (),
        engs: Iterable[uuid.UUID | None] = (),
        users: Iterable[uuid.UUID | None] = (),
    ) -> "Refs":
        def need(ids: Iterable[uuid.UUID | None], have: dict[uuid.UUID, Any]) -> list[uuid.UUID]:
            return [i for i in set(ids) if i is not None and i not in have]

        if ids := need(sites, self.sites):
            self.sites.update(
                {s.id: s for s in self.db.scalars(select(Site).where(Site.id.in_(ids)))}
            )
        if ids := need(zones, self.zones):
            self.zones.update(
                {z.id: z for z in self.db.scalars(select(Zone).where(Zone.id.in_(ids)))}
            )
        if ids := need(engs, self.engs):
            self.engs.update(
                {
                    e.id: e
                    for e in self.db.scalars(
                        select(ProjectEngagement).where(ProjectEngagement.id.in_(ids))
                    )
                }
            )
        if ids := need(users, self.users):
            self.users.update(
                {u.id: u for u in self.db.scalars(select(User).where(User.id.in_(ids)))}
            )
        return self

    def site(self, sid: uuid.UUID) -> SiteRef:
        self.load(sites=[sid])
        s = self.sites[sid]
        return SiteRef(id=s.id, code=s.code, name_en=s.name_en, name_ar=s.name_ar)

    def zone(self, zid: uuid.UUID | None) -> ZoneRef | None:
        if zid is None:
            return None
        self.load(zones=[zid])
        z = self.zones[zid]
        return ZoneRef(
            id=z.id, code=z.code, name_en=z.name_en, name_ar=z.name_ar, zone_type=z.zone_type
        )

    def eng(self, eid: uuid.UUID | None) -> EngagementRef | None:
        if eid is None:
            return None
        self.load(engs=[eid])
        e = self.engs.get(eid)
        if e is None:
            return None
        return EngagementRef(
            id=e.id,
            contractor_id=e.contractor_id,
            short_code=e.contractor.short_code,
            name_en=e.contractor.legal_name_en,
            name_ar=e.contractor.legal_name_ar,
            tier=min(max(e.tier, 1), 3),
        )

    def eng_required(self, eid: uuid.UUID) -> EngagementRef:
        ref = self.eng(eid)
        assert ref is not None  # noqa: S101
        return ref

    def user(self, uid: uuid.UUID | None) -> UserRef | None:
        if uid is None:
            return None
        self.load(users=[uid])
        u = self.users.get(uid)
        if u is None:
            return None
        return UserRef(id=u.id, full_name_en=u.full_name_en, full_name_ar=u.full_name_ar)


# ---- reference numbers ---------------------------------------------------------------------------


def next_seq(db: Session, model: Any, project_id: uuid.UUID, year: int) -> int:
    """Next per-project-per-year sequence (row lock on the project serialises writers)."""
    db.execute(select(Project.id).where(Project.id == project_id).with_for_update())
    cur = db.scalar(
        select(func.max(model.seq)).where(model.project_id == project_id, model.year == year)
    )
    return int(cur or 0) + 1


def make_ref(prefix: str, project_code: str, year: int, seq: int, width: int) -> str:
    return f"{prefix}-{project_code}-{year}-{seq:0{width}d}"


# ---- hierarchy and scope -------------------------------------------------------------------------


def check_site_zone(
    db: Session, project: Project, site_id: uuid.UUID, zone_id: uuid.UUID | None
) -> tuple[Site, Zone | None]:
    site = db.get(Site, site_id)
    if site is None or site.project_id != project.id:
        raise validation_error("site_id", "The site does not belong to this project.")
    zone = None
    if zone_id is not None:
        zone = db.get(Zone, zone_id)
        if zone is None or zone.site_id != site.id:
            raise validation_error("zone_id", "The zone does not belong to this site.")
        if zone.status == ZoneStatus.archived:
            raise ApiError(409, ErrorCode.ZONE_ARCHIVED, "The zone is archived.", "المنطقة مؤرشفة.")
    return site, zone


def check_engagement(
    db: Session, project: Project, engagement_id: uuid.UUID, field: str = "engagement_id"
) -> ProjectEngagement:
    eng = db.get(ProjectEngagement, engagement_id)
    if eng is None or eng.project_id != project.id:
        raise validation_error(field, "The contractor engagement is not on this project.")
    return eng


def require_in_scope(
    p: Principal,
    project_id: uuid.UUID,
    cap: Capability,
    site_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
) -> Grant:
    """Capability with its scope covering the record's site and engagement (403 otherwise)."""
    g = p.require(project_id, cap)
    if site_id is not None and not g.covers_site(site_id):
        raise forbidden_error("This site is outside your scope.")
    if g.engagement_ids is not None and not g.covers_engagement(engagement_id):
        raise forbidden_error("This contractor is outside your scope.")
    return g


def covers(g: Grant | None, site_id: uuid.UUID | None, engagement_id: uuid.UUID | None) -> bool:
    return (
        g is not None
        and (site_id is None or g.covers_site(site_id))
        and (g.engagement_ids is None or g.covers_engagement(engagement_id))
    )


# ---- period locks (W-10, I-9) --------------------------------------------------------------------


def lock_row(db: Session, project_id: uuid.UUID, d: date) -> PeriodLock | None:
    return db.get(PeriodLock, (project_id, month_start(d)))


def is_locked(db: Session, project_id: uuid.UUID, d: date) -> bool:
    row = lock_row(db, project_id, d)
    return bool(row and row.locked)


def ensure_unlocked(db: Session, project_id: uuid.UUID, d: date) -> None:
    if is_locked(db, project_id, d):
        raise ApiError(
            409,
            ErrorCode.PERIOD_LOCKED,
            f"{d.strftime('%Y-%m')} is locked. The HSE Manager must unlock it first.",
            "الشهر مقفل. يجب أن يفتحه مدير الصحة والسلامة أولاً.",
        )


def mark_restated(
    db: Session, p: Principal | None, project_id: uuid.UUID, d: date, why: str
) -> bool:
    """Mark a month restated when its inputs change after it was locked. Returns True when the
    month had been locked (now or before)."""
    row = lock_row(db, project_id, d)
    if row is None or row.locked_at is None:
        return False
    if not row.restated:
        row.restated = True
        row.restated_at = now()
        audit.record(
            db,
            AuditAction.update,
            p.actor(project_id) if p else audit.SYSTEM,
            entity_type=EntityType.workforce_month,
            project_id=project_id,
            details={"month": row.month.strftime("%Y-%m"), "restated": True, "why": why},
        )
    return True


def notify_restated(db: Session, project: Project, d: date, what_en: str, what_ar: str) -> None:
    month = d.strftime("%Y-%m")
    notify.notify(
        db,
        notify.managers(db),
        NotificationKind.case_restated,
        f"{project.code} {month} restated: {what_en}",
        f"تعديل أرقام {project.code} لشهر {month}: {what_ar}",
        project_id=project.id,
    )


# ---- P1-8 possible ID number ---------------------------------------------------------------------


def id_warnings(**fields: str | None) -> list[ApiWarning]:
    out = []
    for name, value in fields.items():
        if value and POSSIBLE_ID.search(value):
            out.append(
                ApiWarning(
                    code=ErrorCode.POSSIBLE_ID_NUMBER.value,
                    message="This text looks like it contains an ID number. Please remove ID "
                    "numbers and personal details.",
                    message_ar="يبدو أن النص يحتوي على رقم هوية. يرجى حذف أرقام الهوية "
                    "والبيانات الشخصية.",
                    field=name,
                )
            )
    return out


# ---- people on a project -------------------------------------------------------------------------


def user_roles(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> set[Role]:
    """Active roles of a user on a project (hse_manager counts everywhere)."""
    day = today()
    out: set[Role] = set()
    for a in db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == user_id)):
        if not a.is_active_on(day) or a.revoked_at is not None:
            continue
        if a.role == Role.hse_manager or a.project_id == project_id:
            out.add(a.role)
    return out


def project_role_users(db: Session, project_id: uuid.UUID, *roles: Role) -> list[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for role in roles:
        if role == Role.hse_manager:
            out.update(notify.managers(db))
        else:
            out.update(notify.users_with_role(db, role, [project_id]))
    return sorted(out)


def contractor_reps(
    db: Session, project_id: uuid.UUID, engagement_id: uuid.UUID | None
) -> list[uuid.UUID]:
    """Contractor HSE Reps whose contractor tree contains the engagement."""
    if engagement_id is None:
        return []
    day = today()
    out: set[uuid.UUID] = set()
    for a in db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.project_id == project_id,
            RoleAssignment.role == Role.contractor_hse_rep,
            RoleAssignment.revoked_at.is_(None),
        )
    ):
        if not a.is_active_on(day) or a.contractor_engagement_id is None:
            continue
        if engagement_id in engagement_descendants(db, a.contractor_engagement_id):
            out.add(a.user_id)
    return sorted(out)
