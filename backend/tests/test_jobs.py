"""Scheduled jobs (§7 alerts, §4.3 inactivity, K6)."""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import now, today
from app.core.enums import NotificationKind, UserStatus
from app.jobs import (
    cr_expiry_alerts,
    inactive_accounts,
    invite_followups,
    last_manager_risk,
    role_assignment_ending,
    unlock_expired,
)
from app.models import Contractor, EmailMessage, Notification, RoleAssignment, User, UserToken
from tests.conftest import Api, Ids


def test_cr_expiry_alerts_once_per_threshold(db: Session) -> None:
    db.execute(
        update(Contractor)
        .where(Contractor.short_code == "GULFPAVE")
        .values(cr_expiry_date=today() + timedelta(days=13))
    )
    db.commit()
    assert cr_expiry_alerts(db)["alerts"] >= 1
    db.commit()
    kinds = db.scalars(
        select(Notification).where(Notification.kind == NotificationKind.contractor_cr_expiry)
    ).all()
    recipients = {n.user_id for n in kinds}
    emails = dict(db.execute(select(User.id, User.email)).all())
    names = {emails[r] for r in recipients}
    assert {
        "faisal.harbi@example.com",
        "noura.qahtani@example.com",
        "ahmed.zahrani@example.com",
    } <= names
    count = len(kinds)
    cr_expiry_alerts(db)
    db.commit()
    again = db.scalars(
        select(Notification).where(Notification.kind == NotificationKind.contractor_cr_expiry)
    ).all()
    assert len(again) == count  # not re-sent for the same threshold


def test_inactive_accounts_warn_then_deactivate(db: Session) -> None:
    db.execute(
        update(User)
        .where(User.email == "khalid.otaibi@example.com")
        .values(last_login_at=now() - timedelta(days=85))
    )
    db.execute(
        update(User)
        .where(User.email == "omar.siddiqui@example.com")
        .values(last_login_at=now() - timedelta(days=91))
    )
    db.commit()
    res = inactive_accounts(db)
    db.commit()
    assert res == {"warned": 1, "deactivated": 1}
    omar = db.scalars(select(User).where(User.email == "omar.siddiqui@example.com")).one()
    assert omar.status == UserStatus.deactivated


def test_inactive_last_manager_never_deactivated(db: Session) -> None:
    db.execute(
        update(User)
        .where(User.email == "faisal.harbi@example.com")
        .values(last_login_at=now() - timedelta(days=400))
    )
    db.commit()
    inactive_accounts(db)
    db.commit()
    faisal = db.scalars(select(User).where(User.email == "faisal.harbi@example.com")).one()
    assert faisal.status == UserStatus.active
    assert last_manager_risk(db) == {"active_managers": 1}


def test_invite_followups(api: Api, ids: Ids, db: Session) -> None:
    api.as_("faisal.harbi").post(
        "/api/v1/users",
        json={
            "email": "late.joiner@example.com",
            "full_name_en": "Late Joiner",
            "employer_type": "client",
            "role_assignments": [{"role": "viewer_client", "project_id": ids.project("RBT-52")}],
        },
    )
    db.execute(update(UserToken).values(created_at=now() - timedelta(hours=49)))
    db.commit()
    assert invite_followups(db)["reminded"] == 1
    db.commit()
    assert db.scalar(select(EmailMessage.id).where(EmailMessage.template == "invite_reminder"))
    db.execute(update(UserToken).values(expires_at=now() - timedelta(minutes=1)))
    db.commit()
    assert invite_followups(db)["expired_notified"] == 1
    db.commit()


def test_role_assignment_ending_and_unlock(db: Session, ids: Ids, api: Api) -> None:
    db.execute(
        update(RoleAssignment)
        .where(RoleAssignment.user_id == ids.user("khalid.otaibi"))
        .values(valid_to=today() + timedelta(days=5))
    )
    db.commit()
    assert role_assignment_ending(db)["notified"] == 1
    db.commit()
    for _ in range(5):
        api.login("omar.siddiqui@example.com", "Wrong-Password-1!")
    db.execute(
        update(User)
        .values(locked_until=now() - timedelta(seconds=1))
        .where(User.status == UserStatus.locked)
    )
    db.commit()
    assert unlock_expired(db)["unlocked"] == 1
    db.commit()


def test_notifications_mark_read(api: Api, ids: Ids) -> None:
    mgr = api.as_("faisal.harbi")
    mgr.patch(f"/api/v1/projects/{ids.project('ANIA-EXP')}/settings", json={"show_hijri": False})
    noura = api.as_("noura.qahtani")
    page = noura.get("/api/v1/notifications", params={"unread_only": True}).json()
    assert page["unread_count"] == 1
    nid = page["items"][0]["id"]
    assert noura.post(f"/api/v1/notifications/{nid}/read").status_code == 204
    assert noura.get("/api/v1/notifications").json()["unread_count"] == 0
    assert mgr.post(f"/api/v1/notifications/{nid}/read").status_code == 404
    assert noura.post("/api/v1/notifications/read-all").status_code == 204
