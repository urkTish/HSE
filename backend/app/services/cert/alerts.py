"""Phase 4 alert helpers (spec 4-third-party-cert §7): de-duplication per (subject, step),
recipients, and in-app + email delivery (email via the outbox, DECISIONS #12)."""

import uuid
from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import EntityType, NotificationKind, Role
from app.models import JobMark, User
from app.services import notify
from app.services.hse_common import contractor_reps, project_role_users


def once(db: Session, key: str) -> bool:
    """True the first time a key is seen (idempotent alerts)."""
    key = key[:200]
    if db.get(JobMark, key) is not None:
        return False
    db.add(JobMark(key=key, created_at=now()))
    db.flush()
    return True


def seen(db: Session, key: str) -> bool:
    return db.get(JobMark, key[:200]) is not None


def officers(db: Session, project_id: uuid.UUID) -> set[uuid.UUID]:
    return set(notify.users_with_role(db, Role.hse_officer, [project_id]))


def managers(db: Session) -> set[uuid.UUID]:
    return set(notify.managers(db))


def reps(db: Session, project_id: uuid.UUID, engagement_id: uuid.UUID | None) -> set[uuid.UUID]:
    return set(contractor_reps(db, project_id, engagement_id))


def site_engineers(db: Session, project_id: uuid.UUID) -> set[uuid.UUID]:
    return set(project_role_users(db, project_id, Role.site_engineer))


def send(
    db: Session,
    users: Iterable[uuid.UUID],
    kind: NotificationKind,
    en: str,
    ar: str,
    entity_type: EntityType | None = None,
    entity_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    email: bool = False,
    body_en: str | None = None,
    body_ar: str | None = None,
) -> int:
    ids = set(users)
    if not ids:
        return 0
    notify.notify(db, ids, kind, en, ar, body_en, body_ar, entity_type, entity_id, project_id)
    if email:
        for u in db.scalars(select(User).where(User.id.in_(ids))):
            notify.send_email(
                db,
                u,
                "generic",
                subject_en=en.replace("{", "(").replace("}", ")"),
                body_en=(body_en or en).replace("{", "(").replace("}", ")"),
                subject_ar=ar.replace("{", "(").replace("}", ")"),
                body_ar=(body_ar or ar).replace("{", "(").replace("}", ")"),
            )
    return len(ids)


def long_step(
    db: Session, base: str, until: date | None, day: date, sched: Iterable[int]
) -> int | None:
    """§7 long schedule 30 / 14 / 7 / 0 days before the last valid day: the most urgent unsent
    step that is due (earlier missed steps are marked sent with it). None when nothing is due."""
    if until is None:
        return None
    left = (until - day).days
    if left < 0:
        return None
    due = sorted(t for t in sched if left <= t)
    if not due:
        return None
    if not once(db, f"{base}:{until.isoformat()}:{due[0]}"):
        return None
    for t in due[1:]:
        once(db, f"{base}:{until.isoformat()}:{t}")
    return due[0]


def scheduled_steps(until: date | None, sched: Iterable[int]) -> list[date]:
    """Dates of the long-schedule steps (TP-8 'scheduled for' displays)."""
    if until is None:
        return []
    from datetime import timedelta  # noqa: PLC0415

    return sorted(until - timedelta(days=n) for n in sched)
