"""Scheduled jobs (spec §5.6 rules 37/40, §7 alerts, §4.3 inactivity).

Run one: ``uv run python -m app.jobs <name>``; ``app.scheduler`` runs them on a timetable.
"""

import sys
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import local_date, now, today
from app.core.config import get_settings
from app.core.enums import AuditAction, AuditResult, EntityType, NotificationKind, Role, UserStatus
from app.db.session import get_sessionmaker
from app.hse_jobs import PHASE1_JOBS
from app.models import (
    Contractor,
    ProjectEngagement,
    ProjectSettings,
    RoleAssignment,
    User,
    UserToken,
)
from app.models.users import TokenKind
from app.services import audit, notify
from app.services.audit import SYSTEM
from app.services.users import _active_manager_ids, deactivate

CR_THRESHOLDS = (30, 14, 7, 0)


def verify_audit_chain(db: Session) -> dict[str, Any]:
    res = audit.verify_chain(db)
    audit.record(
        db,
        AuditAction.audit_chain_verified,
        SYSTEM,
        entity_type=EntityType.audit_log,
        result=AuditResult.success if res.ok else AuditResult.failed,
        details={
            "ok": res.ok,
            "checked": res.checked_count,
            "first_break_seq": res.first_break_seq,
        },
    )
    if not res.ok:
        notify.notify(
            db,
            notify.managers(db),
            NotificationKind.audit_chain_break,
            f"Audit chain break at entry #{res.first_break_seq}",
            f"خلل في سلسلة سجل التدقيق عند القيد #{res.first_break_seq}",
            entity_type=EntityType.audit_log,
        )
    return {"ok": res.ok, "checked": res.checked_count, "first_break_seq": res.first_break_seq}


def purge_audit(db: Session) -> dict[str, Any]:
    entry = audit.purge_expired(db)
    return {"purged": (entry.details or {}).get("count", 0)}


def unlock_expired(db: Session) -> dict[str, Any]:
    current = now()
    users = db.scalars(
        select(User).where(User.status == UserStatus.locked, User.locked_until <= current)
    ).all()
    for u in users:
        u.status = UserStatus.active
        u.locked_until = None
        u.failed_login_count = 0
        u.failed_window_started_at = None
        audit.record(
            db,
            AuditAction.user_status_changed,
            SYSTEM,
            entity_type=EntityType.user,
            entity_id=u.id,
            before={"status": UserStatus.locked},
            after={"status": UserStatus.active},
            details={"reason": "lock period elapsed"},
        )
    return {"unlocked": len(users)}


def invite_followups(db: Session) -> dict[str, Any]:
    """§7: reminder at 48 h, inviter told at expiry (72 h)."""
    current = now()
    tokens = db.scalars(
        select(UserToken).where(
            UserToken.kind == TokenKind.invite,
            UserToken.used_at.is_(None),
            UserToken.superseded_at.is_(None),
        )
    ).all()
    reminded = expired = 0
    for t in tokens:
        user = db.get(User, t.user_id)
        if user is None or user.status != UserStatus.invited:
            continue
        if t.expires_at <= current:
            if t.expiry_notified_at is None and t.created_by_user_id:
                notify.notify(
                    db,
                    [t.created_by_user_id],
                    NotificationKind.invite_expired,
                    f"Invite for {user.email} expired",
                    f"انتهت صلاحية دعوة {user.email}",
                    entity_type=EntityType.user,
                    entity_id=user.id,
                )
                t.expiry_notified_at = current
                expired += 1
        elif current - t.created_at >= timedelta(hours=48) and t.reminder_sent_at is None:
            notify.send_email(
                db, user, "invite_reminder", link=notify.link("/invite", user.preferred_language)
            )
            t.reminder_sent_at = current
            reminded += 1
    return {"reminded": reminded, "expired_notified": expired}


def _inactive_limit(db: Session, user: User, day_default: int = 90) -> int:
    pids = {a.project_id for a in user.assignments if a.project_id and a.revoked_at is None}
    if not pids:
        return day_default
    limits = db.scalars(
        select(ProjectSettings.inactive_account_days).where(ProjectSettings.project_id.in_(pids))
    ).all()
    return min(limits) if limits else day_default


def inactive_accounts(db: Session) -> dict[str, Any]:
    """§4.3 / K6: deactivate after ``inactive_account_days``; warn the user 7 days before."""
    day = today()
    current = now()
    managers = _active_manager_ids(db, day)
    warned = deactivated = 0
    for u in db.scalars(select(User).where(User.status == UserStatus.active)).all():
        last = u.last_login_at or u.activated_at or u.created_at
        idle = (day - local_date(last)).days
        limit = _inactive_limit(db, u)
        if idle >= limit:
            if u.id in managers and len(managers) <= 1:
                continue  # rule 13: never leave the platform without an HSE Manager
            deactivate(db, u, f"Inactive for {idle} days", SYSTEM)
            managers.discard(u.id)
            notify.notify(
                db,
                notify.managers(db),
                NotificationKind.inactive_account,
                f"{u.full_name_en} deactivated after {idle} inactive days",
                f"تم تعطيل حساب {u.full_name_ar or u.full_name_en} لعدم النشاط",
                entity_type=EntityType.user,
                entity_id=u.id,
            )
            deactivated += 1
        elif idle >= limit - 7 and u.inactivity_warned_at is None:
            notify.send_email(
                db,
                u,
                "generic",
                subject_en="Your HSE platform account will be deactivated",
                body_en=f"Log in within {limit - idle} days to keep your account active.",
                subject_ar="سيتم تعطيل حسابك في المنصة",
                body_ar=f"سجّل الدخول خلال {limit - idle} أيام للإبقاء على حسابك نشطاً.",
            )
            u.inactivity_warned_at = current
            warned += 1
    return {"warned": warned, "deactivated": deactivated}


def cr_expiry_alerts(db: Session) -> dict[str, Any]:
    """§7: CR expiry at 30/14/7/0 days (most urgent unsent threshold only)."""
    day = today()
    sent = 0
    for c in db.scalars(select(Contractor).where(Contractor.cr_expiry_date.is_not(None))).all():
        assert c.cr_expiry_date is not None  # noqa: S101
        days_left = (c.cr_expiry_date - day).days
        due = [t for t in CR_THRESHOLDS if days_left <= t]
        if not due:
            continue
        threshold = min(due)
        state = dict(c.cr_alerts or {})
        if state.get("date") != c.cr_expiry_date.isoformat():
            state = {"date": c.cr_expiry_date.isoformat(), "sent": []}
        if threshold in state["sent"]:
            continue
        engs = db.scalars(
            select(ProjectEngagement).where(ProjectEngagement.contractor_id == c.id)
        ).all()
        recipients = set(notify.managers(db))
        recipients |= set(
            notify.users_with_role(db, Role.hse_officer, {e.project_id for e in engs})
        )
        chain: set[Any] = set()
        for e in engs:  # the contractor's engagements and their ancestors (rep scope "C")
            cur: ProjectEngagement | None = e
            while cur is not None:
                chain.add(cur.id)
                parent_id = cur.parent_engagement_id
                cur = db.get(ProjectEngagement, parent_id) if parent_id else None
        reps = db.scalars(
            select(RoleAssignment.user_id).where(
                RoleAssignment.role == Role.contractor_hse_rep,
                RoleAssignment.contractor_engagement_id.in_(chain or [None]),
                RoleAssignment.revoked_at.is_(None),
            )
        ).all()
        recipients |= set(reps)
        notify.notify(
            db,
            recipients,
            NotificationKind.contractor_cr_expiry,
            f"{c.short_code} CR expires on {c.cr_expiry_date.isoformat()} ({days_left} days)",
            f"ينتهي السجل التجاري لـ {c.short_code} في {c.cr_expiry_date.isoformat()}",
            entity_type=EntityType.contractor,
            entity_id=c.id,
        )
        state["sent"] = sorted({*state["sent"], *due})
        c.cr_alerts = state
        sent += 1
    return {"alerts": sent}


def role_assignment_ending(db: Session) -> dict[str, Any]:
    day = today()
    count = 0
    rows = db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.revoked_at.is_(None),
            RoleAssignment.valid_to.is_not(None),
            RoleAssignment.valid_to <= day + timedelta(days=7),
            RoleAssignment.valid_to >= day,
            RoleAssignment.ending_notified_at.is_(None),
        )
    ).all()
    for a in rows:
        user = db.get(User, a.user_id)
        if user is None:
            continue
        notify.send_email(
            db,
            user,
            "generic",
            subject_en=f"Your {a.role.value} role ends on {a.valid_to}",
            body_en="Contact your HSE Officer if it should be extended.",
            subject_ar=f"ينتهي دورك في {a.valid_to}",
            body_ar="تواصل مع مسؤول السلامة إذا لزم التمديد.",
        )
        recipients = [a.created_by_user_id] if a.created_by_user_id else []
        notify.notify(
            db,
            recipients,
            NotificationKind.role_assignment_ending,
            f"{user.full_name_en}: {a.role.value} ends on {a.valid_to}",
            f"ينتهي دور {user.full_name_ar or user.full_name_en} في {a.valid_to}",
            entity_type=EntityType.role_assignment,
            entity_id=a.id,
            project_id=a.project_id,
        )
        a.ending_notified_at = now()
        count += 1
    return {"notified": count}


def last_manager_risk(db: Session) -> dict[str, Any]:
    managers = _active_manager_ids(db, today())
    if len(managers) == 1:
        notify.notify(
            db,
            managers,
            NotificationKind.last_hse_manager_risk,
            "You are the only active HSE Manager",
            "أنت مدير الصحة والسلامة والبيئة النشط الوحيد",
            body_en="Assign a second HSE Manager to avoid lock-out.",
            body_ar="يُنصح بإسناد مدير ثانٍ لتجنب فقدان الوصول.",
        )
    return {"active_managers": len(managers)}


JOBS: dict[str, Callable[[Session], dict[str, Any]]] = {
    "verify_audit_chain": verify_audit_chain,
    "purge_audit": purge_audit,
    "unlock_expired": unlock_expired,
    "invite_followups": invite_followups,
    "inactive_accounts": inactive_accounts,
    "cr_expiry_alerts": cr_expiry_alerts,
    "role_assignment_ending": role_assignment_ending,
    "last_manager_risk": last_manager_risk,
    **PHASE1_JOBS,
}


def run(name: str) -> dict[str, Any]:
    with get_sessionmaker()() as db:
        result = JOBS[name](db)
        db.commit()
    return result


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in JOBS:
        print("usage: python -m app.jobs <" + "|".join(JOBS) + ">", file=sys.stderr)
        return 2
    print(argv[0], run(argv[0]))
    return 0


if __name__ == "__main__":
    _ = get_settings()
    raise SystemExit(main(sys.argv[1:]))
