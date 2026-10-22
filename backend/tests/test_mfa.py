"""Two-step verification (TOTP) and recovery codes (D-299, D-300)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.enums import AuditAction, UserStatus
from app.main import app
from app.models import AuditEntry, User, UserSession
from app.services import mfa
from tests.conftest import PASSWORD, Api

T0 = datetime(2026, 10, 22, 7, 0, 5, tzinfo=UTC)
NOURA = "noura.qahtani@example.com"
FAISAL = "faisal.harbi@example.com"


@pytest.fixture
def at() -> Iterator[datetime]:
    with clock.frozen(T0) as t:
        yield t


@pytest.fixture
def enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "mfa_required_roles", "hse_manager,admin")


def _client(token: str) -> TestClient:
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def _login(email: str) -> dict[str, Any]:
    res = TestClient(app).post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


def _enrol(api: Api, email: str) -> tuple[TestClient, str, list[str]]:
    c = api.as_(email)
    start = c.post("/api/v1/auth/mfa/setup")
    assert start.status_code == 200, start.text
    secret = start.json()["secret"]
    assert start.json()["otpauth_uri"].startswith("otpauth://totp/")
    res = c.post("/api/v1/auth/mfa/confirm", json={"code": mfa.current_code(secret)})
    assert res.status_code == 200, res.text
    codes = res.json()["codes"]
    clock.advance(timedelta(seconds=30))  # the confirm code's step cannot be used again
    return c, secret, codes


def test_totp_matches_rfc6238_vector() -> None:
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
    assert mfa.code_at(secret, 59 // 30) == "287082"
    assert mfa.code_at(secret, 1111111109 // 30) == "081804"


def test_optional_enrolment_then_two_step_sign_in(api: Api, db: Session, at: datetime) -> None:
    _c, secret, codes = _enrol(api, NOURA)
    assert len(codes) == 10 and len(set(codes)) == 10
    body = _login(NOURA)
    assert body["mfa_pending"] is True and body["user"] is None
    pending = _client(body["access_token"])
    me = pending.get("/api/v1/auth/me")
    assert me.status_code == 401 and me.json()["detail"]["code"] == "MFA_REQUIRED"
    assert pending.get("/api/v1/projects").json()["detail"]["code"] == "MFA_REQUIRED"
    wrong = pending.post("/api/v1/auth/mfa/verify", json={"code": "000000"})
    assert wrong.status_code == 401 and wrong.json()["detail"]["code"] == "MFA_CODE_INVALID"
    ok = pending.post("/api/v1/auth/mfa/verify", json={"code": mfa.current_code(secret)})
    assert ok.status_code == 200, ok.text
    assert ok.json()["mfa_pending"] is False and ok.json()["user"]["mfa_enabled"] is True
    full = _client(ok.json()["access_token"])
    assert full.get("/api/v1/auth/me").status_code == 200
    # a code is single use, even on another sign-in within its 30 s
    again = _client(_login(NOURA)["access_token"])
    reuse = again.post("/api/v1/auth/mfa/verify", json={"code": mfa.current_code(secret)})
    assert reuse.status_code == 401
    entries = db.scalars(
        select(AuditEntry).where(AuditEntry.action == AuditAction.login_success)
    ).all()
    assert any((e.details or {}).get("mfa") == "totp" for e in entries)
    failed = db.scalars(
        select(AuditEntry).where(AuditEntry.action == AuditAction.login_failed)
    ).all()
    assert any((e.details or {}).get("reason") == "mfa_wrong_totp" for e in failed)


def test_verify_needs_a_pending_session(api: Api, at: datetime) -> None:
    c = api.as_(NOURA)
    res = c.post("/api/v1/auth/mfa/verify", json={"code": "123456"})
    assert res.status_code == 409
    both = c.post(
        "/api/v1/auth/mfa/verify", json={"code": "123456", "recovery_code": "abcde-fghij"}
    )
    assert both.status_code == 422


def test_recovery_code_works_once_and_regeneration_replaces_them(
    api: Api, db: Session, at: datetime
) -> None:
    c, secret, codes = _enrol(api, NOURA)
    p1 = _client(_login(NOURA)["access_token"])
    ok = p1.post("/api/v1/auth/mfa/verify", json={"recovery_code": codes[0].upper()})
    assert ok.status_code == 200, ok.text
    p2 = _client(_login(NOURA)["access_token"])
    assert p2.post("/api/v1/auth/mfa/verify", json={"recovery_code": codes[0]}).status_code == 401
    st = c.get("/api/v1/auth/mfa").json()
    assert st["enabled"] is True and st["recovery_codes_remaining"] == 9
    bad = c.post("/api/v1/auth/mfa/recovery-codes", json={"code": "000000"})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "MFA_CODE_INVALID"
    new = c.post("/api/v1/auth/mfa/recovery-codes", json={"code": mfa.current_code(secret)})
    assert new.status_code == 200
    p3 = _client(_login(NOURA)["access_token"])
    assert p3.post("/api/v1/auth/mfa/verify", json={"recovery_code": codes[1]}).status_code == 401
    p4 = _client(_login(NOURA)["access_token"])
    ok4 = p4.post("/api/v1/auth/mfa/verify", json={"recovery_code": new.json()["codes"][3]})
    assert ok4.status_code == 200
    used = db.scalars(select(AuditEntry).where(AuditEntry.action == AuditAction.mfa_changed)).all()
    changes = {(e.details or {}).get("change") for e in used}
    assert {"enabled", "recovery_code_used", "recovery_codes_regenerated"} <= changes


def test_optional_user_turns_mfa_off(api: Api, at: datetime) -> None:
    c, secret, _codes = _enrol(api, NOURA)
    bad_pw = c.post(
        "/api/v1/auth/mfa/disable",
        json={"password": "Wrong-Passw0rd!", "code": mfa.current_code(secret)},
    )
    assert bad_pw.status_code == 422
    res = c.post(
        "/api/v1/auth/mfa/disable", json={"password": PASSWORD, "code": mfa.current_code(secret)}
    )
    assert res.status_code == 204, res.text
    assert _login(NOURA)["mfa_pending"] is False


def test_setup_states(api: Api, at: datetime) -> None:
    c = api.as_(NOURA)
    res = c.post("/api/v1/auth/mfa/confirm", json={"code": "123456"})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "MFA_SETUP_NOT_STARTED"
    secret = c.post("/api/v1/auth/mfa/setup").json()["secret"]
    wrong = c.post("/api/v1/auth/mfa/confirm", json={"code": "000000"})
    assert wrong.status_code == 422
    assert (
        c.post("/api/v1/auth/mfa/confirm", json={"code": mfa.current_code(secret)}).status_code
        == 200
    )
    assert c.post("/api/v1/auth/mfa/setup").json()["detail"]["code"] == "MFA_ALREADY_ENABLED"


def test_required_role_grace_then_block_until_enrolled(
    api: Api, db: Session, at: datetime, enforced: None
) -> None:
    body = _login(FAISAL)
    me = body["user"]
    assert me["mfa_required"] is True and me["mfa_setup_blocking"] is False
    assert me["mfa_setup_due"].startswith("2026-10-29")
    c = _client(body["access_token"])
    assert c.get("/api/v1/projects").status_code == 200
    # not required for an HSE Officer
    assert _login(NOURA)["user"]["mfa_required"] is False
    clock.advance(timedelta(days=7, minutes=1))
    late = _client(_login(FAISAL)["access_token"])
    blocked = late.get("/api/v1/projects")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "MFA_ENROLMENT_REQUIRED"
    me2 = late.get("/api/v1/auth/me")
    assert me2.status_code == 200 and me2.json()["mfa_setup_blocking"] is True
    secret = late.post("/api/v1/auth/mfa/setup").json()["secret"]
    res = late.post("/api/v1/auth/mfa/confirm", json={"code": mfa.current_code(secret)})
    assert res.status_code == 200
    assert late.get("/api/v1/projects").status_code == 200
    clock.advance(timedelta(seconds=30))
    off = late.post(
        "/api/v1/auth/mfa/disable", json={"password": PASSWORD, "code": mfa.current_code(secret)}
    )
    assert off.status_code == 409 and off.json()["detail"]["code"] == "MFA_REQUIRED_FOR_ROLE"


def test_no_grace_blocks_at_once(
    api: Api, at: datetime, enforced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "mfa_grace_days", 0)
    c = _client(_login(FAISAL)["access_token"])
    assert c.get("/api/v1/projects").json()["detail"]["code"] == "MFA_ENROLMENT_REQUIRED"
    assert c.post("/api/v1/auth/logout").status_code == 204


def test_admin_emails_count_as_required(
    api: Api, at: datetime, enforced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "project_delete_emails", NOURA)
    assert _login(NOURA)["user"]["mfa_required"] is True
    monkeypatch.setattr(get_settings(), "mfa_required_roles", "hse_manager")
    assert _login(NOURA)["user"]["mfa_required"] is False


def test_pending_session_expires(api: Api, at: datetime) -> None:
    _c, secret, _codes = _enrol(api, NOURA)
    pending = _client(_login(NOURA)["access_token"])
    clock.advance(timedelta(minutes=11))
    res = pending.post("/api/v1/auth/mfa/verify", json={"code": mfa.current_code(secret)})
    assert res.status_code == 401  # the short-lived token has run out


def test_wrong_codes_lock_the_account(api: Api, db: Session, at: datetime) -> None:
    _enrol(api, NOURA)
    pending = _client(_login(NOURA)["access_token"])
    for _ in range(get_settings().lockout_threshold):
        pending.post("/api/v1/auth/mfa/verify", json={"code": "000000"})
    user = db.scalar(select(User).where(User.email == NOURA))
    assert user is not None
    db.refresh(user)
    assert user.status == UserStatus.locked


def test_manager_resets_lost_phone(api: Api, db: Session, at: datetime) -> None:
    noura, _secret, _codes = _enrol(api, NOURA)
    uid = noura.get("/api/v1/auth/me").json()["id"]
    faisal = api.as_(FAISAL)
    res = faisal.post(f"/api/v1/users/{uid}/mfa/reset")
    assert res.status_code == 200 and res.json()["mfa_enabled"] is False
    assert noura.get("/api/v1/auth/me").status_code == 401  # sessions revoked
    assert _login(NOURA)["mfa_pending"] is False
    again = faisal.post(f"/api/v1/users/{uid}/mfa/reset")
    assert again.status_code == 409
    me = faisal.get("/api/v1/auth/me").json()["id"]
    assert faisal.post(f"/api/v1/users/{me}/mfa/reset").status_code == 403
    officer = api.as_(NOURA)
    fid = db.scalar(select(User.id).where(User.email == FAISAL))
    assert officer.post(f"/api/v1/users/{fid}/mfa/reset").status_code in (403, 404)
    revoked = db.scalars(select(UserSession).where(UserSession.revoked_reason == "mfa_reset")).all()
    assert revoked
