"""Spec 0-foundation §5.1 — AC1-AC5, AC35 and session/password rules."""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, UserStatus
from app.models import AuditEntry, EmailMessage, User, UserSession, UserToken
from tests.conftest import PASSWORD, Api, Ids

INVITE = {
    "email": "new.officer.helper@example.com",
    "full_name_en": "Hassan Al-Mutairi",
    "full_name_ar": "حسن المطيري",
    "mobile": "+966500000020",
    "employer_type": "client",
    "role_assignments": [],
}
NEW_PASSWORD = "Fresh-Start#2026x"


def _invite(api: Api, ids: Ids, email: str = INVITE["email"]) -> str:
    """Invite a viewer on ANIA-EXP as the HSE Manager and return the raw invite token."""
    c = api.as_("faisal.harbi")
    body = {
        **INVITE,
        "email": email,
        "role_assignments": [{"role": "viewer_client", "project_id": ids.project("ANIA-EXP")}],
    }
    res = c.post("/api/v1/users", json=body)
    assert res.status_code == 201, res.text
    msg = ids.db.scalars(
        select(EmailMessage)
        .where(EmailMessage.to_email == email, EmailMessage.template == "invite")
        .order_by(EmailMessage.created_at.desc())
    ).first()
    assert msg is not None
    return msg.body.split("token=")[1].split()[0]


def test_AC1_login_success_audited(api: Api, db: Session) -> None:
    res = api.login("faisal.harbi@example.com")
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == "faisal.harbi@example.com"
    assert body["token_type"] == "bearer"
    cookie = res.headers["set-cookie"]
    assert "hse_session=" in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    entry = db.scalars(
        select(AuditEntry).where(AuditEntry.action == AuditAction.login_success)
    ).one()
    assert str(entry.actor_user_id) == body["user"]["id"]


def test_AC1_cookie_auth_works(api: Api) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    assert (
        c.post(
            "/api/v1/auth/login", json={"email": "faisal.harbi@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    assert c.get("/api/v1/auth/me").status_code == 200  # cookie only


def test_AC1_email_case_insensitive(api: Api) -> None:
    assert api.login("Faisal.Harbi@EXAMPLE.com").status_code == 200


def test_AC2_identical_failure_responses(api: Api) -> None:
    unknown = api.login("nobody@example.com", "Whatever-123!x")
    wrong = api.login("faisal.harbi@example.com", "Wrong-Password-1!")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    assert unknown.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_AC3_lockout_after_five_failures(api: Api, db: Session) -> None:
    for _ in range(5):
        assert api.login("noura.qahtani@example.com", "Wrong-Password-1!").status_code == 401
    res = api.login("noura.qahtani@example.com")
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "ACCOUNT_LOCKED"
    user = db.scalars(select(User).where(User.email == "noura.qahtani@example.com")).one()
    assert user.status == UserStatus.locked
    assert db.scalar(select(AuditEntry.id).where(AuditEntry.action == AuditAction.account_locked))


def test_AC3_failures_outside_window_do_not_lock(api: Api, db: Session) -> None:
    for _ in range(4):
        api.login("noura.qahtani@example.com", "Wrong-Password-1!")
    db.execute(
        update(User)
        .where(User.email == "noura.qahtani@example.com")
        .values(failed_window_started_at=now() - timedelta(minutes=16))
    )
    db.commit()
    api.login("noura.qahtani@example.com", "Wrong-Password-1!")
    assert api.login("noura.qahtani@example.com").status_code == 200


def test_AC3_lock_lifts_after_15_minutes(api: Api, db: Session) -> None:
    for _ in range(5):
        api.login("noura.qahtani@example.com", "Wrong-Password-1!")
    db.execute(
        update(User)
        .where(User.email == "noura.qahtani@example.com")
        .values(locked_until=now() - timedelta(seconds=1))
    )
    db.commit()
    assert api.login("noura.qahtani@example.com").status_code == 200


def test_AC4_invite_expired_after_72h(api: Api, ids: Ids, db: Session) -> None:
    token = _invite(api, ids)
    db.execute(
        update(UserToken).values(
            created_at=now() - timedelta(hours=73), expires_at=now() - timedelta(hours=1)
        )
    )
    db.commit()
    res = api.anon.post("/api/v1/auth/invitations/validate", json={"token": token})
    assert res.status_code == 410
    assert res.json()["detail"]["code"] == "INVITE_EXPIRED"


def test_invite_accept_flow_and_resend_invalidates_old(api: Api, ids: Ids) -> None:
    old = _invite(api, ids)
    info = api.anon.post("/api/v1/auth/invitations/validate", json={"token": old})
    assert info.status_code == 200 and info.json()["privacy_notice"]["version"] == "PN-1.0"
    c = api.as_("faisal.harbi")
    uid = c.get("/api/v1/users", params={"q": "Mutairi"}).json()["items"][0]["id"]
    assert c.post(f"/api/v1/users/{uid}/resend-invite").status_code == 200
    stale = api.anon.post("/api/v1/auth/invitations/validate", json={"token": old})
    assert stale.status_code == 404 and stale.json()["detail"]["code"] == "INVITE_INVALID"
    new = _latest_token(ids, INVITE["email"], "invite")
    weak = api.anon.post(
        "/api/v1/auth/invitations/accept",
        json={"token": new, "password": "password1234", "privacy_notice_version": "PN-1.0"},
    )
    assert weak.status_code == 422 and weak.json()["detail"]["code"] == "WEAK_PASSWORD"
    ok = api.anon.post(
        "/api/v1/auth/invitations/accept",
        json={"token": new, "password": NEW_PASSWORD, "privacy_notice_version": "PN-1.0"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["status"] == "active"
    assert ok.json()["user"]["privacy_ack_required"] is False
    assert api.login(INVITE["email"], NEW_PASSWORD).status_code == 200


def _latest_token(ids: Ids, email: str, template: str) -> str:
    msg = ids.db.scalars(
        select(EmailMessage)
        .where(EmailMessage.to_email == email, EmailMessage.template == template)
        .order_by(EmailMessage.created_at.desc())
    ).first()
    assert msg is not None
    return msg.body.split("token=")[1].split()[0]


def test_AC5_privacy_ack_required(api: Api, ids: Ids, db: Session) -> None:
    db.execute(
        update(User)
        .where(User.email == "khalid.otaibi@example.com")
        .values(privacy_notice_version=None, privacy_notice_ack_at=None)
    )
    db.commit()
    login = api.login("khalid.otaibi@example.com")
    assert login.status_code == 200
    assert login.json()["user"]["privacy_ack_required"] is True
    c = api.as_("khalid.otaibi")
    for method, path in [
        ("get", "/api/v1/auth/me"),
        ("get", "/api/v1/projects"),
        ("get", f"/api/v1/projects/{ids.project('ANIA-EXP')}/zones"),
        ("get", "/api/v1/contractors"),
    ]:
        res = getattr(c, method)(path)
        assert res.status_code == 403, path
        assert res.json()["detail"]["code"] == "PRIVACY_ACK_REQUIRED"
    assert api.anon.get("/api/v1/privacy-notice").status_code == 200
    bad = c.post("/api/v1/auth/privacy-notice/ack", json={"version": "PN-0.9"})
    assert bad.status_code == 409
    ack = c.post("/api/v1/auth/privacy-notice/ack", json={"version": "PN-1.0"})
    assert ack.status_code == 200 and ack.json()["privacy_ack_required"] is False
    assert c.get("/api/v1/projects").status_code == 200


def test_AC5_logout_allowed_before_ack(api: Api, db: Session) -> None:
    db.execute(
        update(User)
        .where(User.email == "khalid.otaibi@example.com")
        .values(privacy_notice_version="PN-0.1")
    )
    db.commit()
    c = api.as_("khalid.otaibi")
    assert c.post("/api/v1/auth/logout").status_code == 204
    assert c.get("/api/v1/auth/me").json()["detail"]["code"] == "SESSION_EXPIRED"


def test_AC35_no_password_hash_in_user_responses(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    uid = ids.user("noura.qahtani")
    responses = [
        c.get(f"/api/v1/users/{uid}"),
        c.patch(f"/api/v1/users/{uid}", json={"job_title": "Senior HSE Officer"}),
        c.get("/api/v1/users"),
        c.get("/api/v1/auth/me"),
        c.patch("/api/v1/auth/me", json={"mobile": "+966500000001"}),
    ]
    for res in responses:
        assert res.status_code == 200, res.text
        assert "password" not in res.text


def test_session_idle_timeout(api: Api, db: Session) -> None:
    c = api.as_("faisal.harbi")
    db.execute(update(UserSession).values(last_seen_at=now() - timedelta(minutes=31)))
    db.commit()
    res = c.get("/api/v1/auth/me")
    assert res.status_code == 401 and res.json()["detail"]["code"] == "SESSION_EXPIRED"


def test_session_absolute_timeout(api: Api, db: Session) -> None:
    c = api.as_("faisal.harbi")
    db.execute(update(UserSession).values(expires_at=now() - timedelta(seconds=1)))
    db.commit()
    assert c.get("/api/v1/auth/me").status_code == 401


def test_password_change_policy_and_reset_flow(api: Api, ids: Ids) -> None:
    c = api.as_("omar.siddiqui")
    res = c.post(
        "/api/v1/auth/me/password",
        json={"current_password": PASSWORD, "new_password": "omar.siddiqui"},
    )
    assert res.status_code == 422
    res = c.post(
        "/api/v1/auth/me/password",
        json={"current_password": "nope", "new_password": NEW_PASSWORD},
    )
    assert res.json()["detail"]["code"] == "CURRENT_PASSWORD_INCORRECT"
    reset = api.anon.post(
        "/api/v1/auth/password-reset", json={"email": "omar.siddiqui@example.com"}
    )
    unknown = api.anon.post("/api/v1/auth/password-reset", json={"email": "ghost@example.com"})
    assert reset.status_code == unknown.status_code == 202
    assert reset.json() == unknown.json()
    token = _latest_token(ids, "omar.siddiqui@example.com", "password_reset")
    ok = api.anon.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert ok.status_code == 204
    again = api.anon.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert again.status_code == 404  # single use (rule 5)
    assert c.get("/api/v1/auth/me").status_code == 401  # sessions revoked
    assert api.login("omar.siddiqui@example.com", NEW_PASSWORD).status_code == 200


def test_reset_token_expires_after_60_minutes(api: Api, ids: Ids, db: Session) -> None:
    api.anon.post("/api/v1/auth/password-reset", json={"email": "omar.siddiqui@example.com"})
    token = _latest_token(ids, "omar.siddiqui@example.com", "password_reset")
    db.execute(update(UserToken).values(expires_at=now() - timedelta(minutes=1)))
    db.commit()
    res = api.anon.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert res.status_code == 410


def test_me_capabilities(api: Api, ids: Ids) -> None:
    me = api.as_("omar.siddiqui").get("/api/v1/auth/me").json()
    assert me["is_hse_manager"] is False
    [proj] = me["projects"]
    assert proj["project_code"] == "ANIA-EXP"
    assert proj["roles"] == ["site_engineer"]
    assert proj["site_ids"] == [ids.site("S-AIR")]
    caps = {c["capability"]: c["scope"] for c in proj["capabilities"]}
    assert caps["site_zone.view"] == "sites"
    assert "site_zone.manage" not in caps
    sarah = api.as_("sarah.mitchell").get("/api/v1/auth/me").json()
    assert all(p["read_only"] for p in sarah["projects"]) and len(sarah["projects"]) == 2
