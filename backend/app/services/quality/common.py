"""Helpers shared by every Quality service (spec 8-quality Part A): errors, reasons, profile
checks (Q-PRF-01 / -04), scope checks with the responsible-person scope N (Q-ROL-04), Riyadh dates
and the notification fan-out (in-app + email in the recipient's language, §A.13)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import local_date, now
from app.core.enums import (
    Capability,
    CapabilityScope,
    EntityType,
    NotificationKind,
    Role,
    UserStatus,
)
from app.core.errors import ApiError, ErrorCode, FieldError
from app.core.quality.common import (
    RECORD_TYPES,
    QProfileScope,
    QRecordType,
    QSectorProfile,
    profile_allows,
)
from app.models import JobMark, Project, RoleAssignment, User
from app.models.quality import QSettings
from app.schemas.hse_common import ApiWarning
from app.services import notify
from app.services.common import ensure_open
from app.services.permissions import (
    CONTRACTOR_QUALITY_EXCLUDED,
    MATRIX,
    QUALITY_ROLES,
    Grant,
    Principal,
    forbidden_error,
)

C = Capability
S = CapabilityScope


def err(status: int, code: ErrorCode, en: str, ar: str, **meta: Any) -> ApiError:
    return ApiError(status, code, en, ar, meta=meta or None)


def field_err(field: str, en: str, ar: str = "قيمة غير صالحة.") -> ApiError:
    return ApiError(
        422,
        ErrorCode.VALIDATION_ERROR,
        en,
        ar,
        errors=[FieldError(loc=["body", field], msg=en, msg_ar=ar, type="value_error")],
    )


def reason(text: str | None, minimum: int = 20, field: str = "reason") -> str:
    t = (text or "").strip()
    if len(t) < minimum:
        raise field_err(
            field,
            f"Give a reason of at least {minimum} characters.",
            f"اكتب سبباً لا يقل عن {minimum} حرفاً.",
        )
    return t


def warning(code: ErrorCode | str, en: str, ar: str, field: str | None = None) -> ApiWarning:
    return ApiWarning(code=str(code), message=en, message_ar=ar, field=field)


def tz(project: Project) -> str:
    return project.settings.timezone if project.settings else "Asia/Riyadh"


def project_day(project: Project, at: datetime | None = None) -> date:
    return local_date(at or now(), tz(project))


def get_project(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    from app.services import projects  # noqa: PLC0415

    return projects.get_visible(db, p, project_id)


def writable(project: Project, p: Principal) -> None:
    ensure_open(project)
    p.ensure_writer()


# ---- settings row and profile -------------------------------------------------------------------


def settings_row(db: Session, project_id: uuid.UUID) -> QSettings | None:
    return db.get(QSettings, project_id)


def profile_of(db: Session, project_id: uuid.UUID) -> QSectorProfile | None:
    row = settings_row(db, project_id)
    return row.sector_profile if row else None


def require_profile(db: Session, project: Project) -> QSectorProfile:
    """Q-PRF-01: nothing is created before the profile is chosen."""
    prof = profile_of(db, project.id)
    if prof is None:
        raise err(
            422,
            ErrorCode.PROFILE_REQUIRED,
            "Choose the project's Quality sector profile first (Quality settings).",
            "اختر قطاع الجودة للمشروع أولاً (إعدادات الجودة).",
        )
    return prof


def ensure_profile_for(
    db: Session, project: Project, scope: QProfileScope | QRecordType, what_en: str = ""
) -> QSectorProfile:
    """Q-PRF-04: creating a record of the inactive profile → 409 PROFILE_INACTIVE."""
    prof = require_profile(db, project)
    sc = RECORD_TYPES[scope].profile if isinstance(scope, QRecordType) else scope
    if not profile_allows(sc, prof):
        raise err(
            409,
            ErrorCode.PROFILE_INACTIVE,
            f"{what_en or 'This record type'} belongs to the {sc.value} profile; the project "
            f"uses {prof.value}. Open records can still be finished.",
            "هذا النوع يخص قطاعاً غير مفعّل في المشروع؛ يمكن إكمال السجلات المفتوحة فقط.",
        )
    return prof


# ---- scope ---------------------------------------------------------------------------------------


def grant(p: Principal, project_id: uuid.UUID, cap: Capability) -> Grant | None:
    return p.grant(project_id, cap)


def covers(g: Grant | None, site_id: uuid.UUID | None, eng_id: uuid.UUID | None) -> bool:
    """Scope check for P / S / C grants; an N grant never covers by itself (Q-ROL-04)."""
    if g is None or g.scope == S.responsible:
        return False
    if site_id is not None and not g.covers_site(site_id):
        return False
    return g.engagement_ids is None or (eng_id is not None and eng_id in g.engagement_ids)


def is_n(g: Grant | None) -> bool:
    return g is not None and g.scope == S.responsible


def require(p: Principal, project_id: uuid.UUID, cap: Capability) -> Grant:
    return p.require(project_id, cap)


def require_cover(
    p: Principal, project_id: uuid.UUID, cap: Capability, site_id: Any, eng_id: Any
) -> Grant:
    g = p.require(project_id, cap)
    if not covers(g, site_id, eng_id):
        raise forbidden_error("This site or contractor is outside your scope.")
    return g


# ---- people -------------------------------------------------------------------------------------


def _assignments(db: Session, project_id: uuid.UUID, day: date) -> list[RoleAssignment]:
    rows = db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.revoked_at.is_(None),
            (RoleAssignment.project_id == project_id) | (RoleAssignment.role == Role.hse_manager),
        )
    ).all()
    return [a for a in rows if a.is_active_on(day)]


def holders_of(
    db: Session, project: Project, cap: Capability, *, include_manager: bool = True
) -> list[uuid.UUID]:
    """Active users holding a capability on the project (not narrowed by engagement)."""
    from app.services.permissions import MANAGER_EXCLUDED  # noqa: PLC0415

    day = project_day(project)
    out: set[uuid.UUID] = set()
    for a in _assignments(db, project.id, day):
        if a.role == Role.hse_manager:
            if include_manager and cap not in MANAGER_EXCLUDED:
                out.add(a.user_id)
            continue
        if cap in MATRIX.get(a.role, {}):
            if (
                a.role in QUALITY_ROLES
                and a.contractor_engagement_id is not None
                and cap in CONTRACTOR_QUALITY_EXCLUDED
            ):
                continue
            out.add(a.user_id)
    return sorted(out)


def role_holders(db: Session, project: Project, role: Role) -> list[RoleAssignment]:
    day = project_day(project)
    return [a for a in _assignments(db, project.id, day) if a.role == role]


def active_user(db: Session, uid: uuid.UUID) -> User | None:
    u = db.get(User, uid)
    return u if u is not None and u.status == UserStatus.active else None


# ---- notifications (§A.13) ----------------------------------------------------------------------


def once(db: Session, key: str) -> bool:
    """True the first time a key is seen (each record, step and recipient alerted once)."""
    if db.get(JobMark, key) is not None:
        return False
    db.add(JobMark(key=key[:200], created_at=now()))
    db.flush()
    return True


def send(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    title_en: str,
    title_ar: str,
    *,
    body_en: str | None = None,
    body_ar: str | None = None,
    entity_type: EntityType | None = None,
    entity_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    email: bool = True,
    key: str | None = None,
    path: str | None = None,
) -> int:
    """In-app notification + email in the recipient's language. With `key`, each recipient
    gets it once (re-running a job never sends twice)."""
    n = 0
    for uid in sorted(set(user_ids)):
        if key is not None and not once(db, f"q:{key}:{uid}"):
            continue
        user = active_user(db, uid)
        if user is None:
            continue
        notify.notify(
            db,
            [uid],
            NotificationKind.quality,
            title_en,
            title_ar,
            body_en,
            body_ar,
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=project_id,
        )
        if email:
            link_en = notify.link(path, user.preferred_language) if path else ""
            notify.send_email(
                db,
                user,
                "generic",
                subject_en=title_en,
                subject_ar=title_ar,
                body_en=f"{body_en or title_en}\n{link_en}".strip(),
                body_ar=f"{body_ar or title_ar}\n{link_en}".strip(),
            )
        n += 1
    return n


def ids(*xs: uuid.UUID | None) -> frozenset[uuid.UUID]:
    return frozenset(x for x in xs if x is not None)


def text_of(en: str | None, ar: str | None) -> str:
    return (en or ar or "").strip()
