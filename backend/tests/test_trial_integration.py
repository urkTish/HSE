"""Trial readiness A + B + C working together (D-307).

- B's read-only mode leaves C's sign-in steps (two-step code, recovery code, set-up), a manager's
  two-step reset and the first-time setup of an empty install open, and A's email sender (a
  background job, not an HTTP write) keeps delivering.
- C's two-step enforcement leaves B's licence status readable (the banner), even when the set-up
  is overdue.
- `attachments.store` scans the upload as received (C), then shrinks a photo (A), then checks the
  licence storage cap on the size actually stored (B)."""

from __future__ import annotations

import socketserver
import threading
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.enums import EmailStatus, Language
from app.core.errors import ApiError
from app.core.hse_enums import AttachmentOwner, ScanStatus
from app.jobs import JOBS
from app.main import app
from app.models import EmailMessage, Project, User
from app.services import attachments, licence, mfa
from tests.conftest import PASSWORD, Api
from tests.smtp_fake import smtp_server
from tests.test_first_setup import _body as setup_body
from tests.test_first_setup import _empty_install
from tests.test_licence import TODAY, expire, install, key
from tests.test_licence import vendor as vendor  # noqa: PLC0414 (fixture re-export)
from tests.test_scanner import EICAR, _Clamd
from tests.test_trial_a_photos import no_metadata, opened, photo

API = "/api/v1"
NOURA = "noura.qahtani@example.com"  # HSE officer: two-step verification optional
FAISAL = "faisal.harbi@example.com"  # HSE Manager: two-step verification required when enforced
PROJECT = {
    "code": "TRIAL-X",
    "name_en": "Another project",
    "name_ar": "مشروع آخر",
    "project_type": "other",
    "client_name_en": "Client",
    "client_name_ar": "العميل",
    "city": "Riyadh",
    "start_date": "2026-10-01",
}


def _bearer(token: str) -> TestClient:
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def _login(email: str) -> dict[str, Any]:
    res = TestClient(app).post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


def _enrol(c: TestClient) -> tuple[str, list[str]]:
    start = c.post(f"{API}/auth/mfa/setup")
    assert start.status_code == 200, start.text
    secret = start.json()["secret"]
    done = c.post(f"{API}/auth/mfa/confirm", json={"code": mfa.current_code(secret)})
    assert done.status_code == 200, done.text
    clock.advance(timedelta(seconds=30))  # the confirm code's step cannot be used again
    return secret, done.json()["codes"]


def _read_only_code(res: Any) -> str:
    assert res.status_code == 403, res.text
    code: str = res.json()["detail"]["code"]
    return code


@pytest.fixture
def enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "mfa_required_roles", "hse_manager,admin")


@pytest.fixture
def clamd(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[bytes]]:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Clamd)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(get_settings(), "clamav_host", "127.0.0.1")
    monkeypatch.setattr(get_settings(), "clamav_port", server.server_address[1])
    _Clamd.seen = []
    try:
        yield _Clamd.seen
    finally:
        server.shutdown()
        server.server_close()


# ---- B read-only × C sign-in, set-up and reset -------------------------------------------------


def test_read_only_keeps_two_step_sign_in_and_recovery_codes(
    api: Api, vendor: Ed25519PrivateKey
) -> None:
    assert install(api, key(vendor)).status_code == 200
    secret, codes = _enrol(api.as_(NOURA))
    expire()
    # read-only is on: an ordinary write is refused
    mgr = api.as_(FAISAL)
    assert _read_only_code(mgr.post(f"{API}/projects", json=PROJECT)) == "LICENCE_READ_ONLY"
    # sign-in with the authenticator code
    pending = _bearer(_login(NOURA)["access_token"])
    ok = pending.post(f"{API}/auth/mfa/verify", json={"code": mfa.current_code(secret)})
    assert ok.status_code == 200, ok.text
    assert _bearer(ok.json()["access_token"]).get(f"{API}/auth/me").status_code == 200
    # sign-in with a recovery code, then new recovery codes
    pending = _bearer(_login(NOURA)["access_token"])
    rec = pending.post(f"{API}/auth/mfa/verify", json={"recovery_code": codes[0]})
    assert rec.status_code == 200, rec.text
    full = _bearer(rec.json()["access_token"])
    clock.advance(timedelta(seconds=30))
    new = full.post(f"{API}/auth/mfa/recovery-codes", json={"code": mfa.current_code(secret)})
    assert new.status_code == 200, new.text


def test_read_only_keeps_two_step_set_up_and_manager_reset(
    api: Api, db: Session, vendor: Ed25519PrivateKey, enforced: None, monkeypatch: Any
) -> None:
    assert install(api, key(vendor)).status_code == 200
    _enrol(api.as_(NOURA))
    expire()
    monkeypatch.setattr(get_settings(), "mfa_grace_days", 0)
    # the HSE Manager, set-up overdue, can still read the licence and enrol in read-only mode
    mgr = _bearer(_login(FAISAL)["access_token"])
    assert mgr.get(f"{API}/projects").json()["detail"]["code"] == "MFA_ENROLMENT_REQUIRED"
    _enrol(mgr)
    # ... and reset a user's lost phone: a locked-out user must be able to sign in again
    uid = db.scalar(select(User.id).where(User.email == NOURA))
    res = mgr.post(f"{API}/users/{uid}/mfa/reset")
    assert res.status_code == 200, res.text
    assert res.json()["mfa_enabled"] is False
    assert _login(NOURA)["mfa_pending"] is False
    # other writes stay refused
    assert _read_only_code(mgr.post(f"{API}/projects", json=PROJECT)) == "LICENCE_READ_ONLY"


def test_first_time_setup_works_under_an_ended_environment_key(
    db: Session, vendor: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    ended = key(vendor, issued_on=TODAY - timedelta(days=30), valid_until=TODAY - timedelta(days=1))
    monkeypatch.setattr(get_settings(), "licence_key", ended)
    _empty_install()
    licence.invalidate()
    c = TestClient(app)
    assert c.get(f"{API}/setup").json()["needed"] is True
    res = c.post(f"{API}/setup", json=setup_body())
    assert res.status_code == 201, res.text
    admin = _bearer(res.json()["access_token"])
    st = admin.get(f"{API}/licence").json()
    assert st["state"] == "expired" and st["read_only"] is True
    # the install is set up, but read-only until a key is entered
    assert _read_only_code(admin.post(f"{API}/projects", json=PROJECT)) == "LICENCE_READ_ONLY"
    assert c.post(f"{API}/setup", json=setup_body()).status_code == 409  # locked by itself


# ---- C enforcement × B licence page ---------------------------------------------------------


def test_licence_status_is_readable_while_two_step_set_up_is_overdue(
    api: Api, vendor: Ed25519PrivateKey, enforced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert install(api, key(vendor)).status_code == 200
    monkeypatch.setattr(get_settings(), "mfa_grace_days", 0)
    mgr = _bearer(_login(FAISAL)["access_token"])
    assert mgr.get(f"{API}/projects").json()["detail"]["code"] == "MFA_ENROLMENT_REQUIRED"
    st = mgr.get(f"{API}/licence")
    assert st.status_code == 200, st.text
    assert st.json()["state"] == "active" and st.json()["is_trial"] is True
    # entering a key is a manager action: only after the set-up
    put = mgr.put(f"{API}/licence", json={"key": key(vendor)})
    assert put.json()["detail"]["code"] == "MFA_ENROLMENT_REQUIRED"
    # a session still waiting for its code reads nothing
    _enrol(api.as_(NOURA))
    pending = _bearer(_login(NOURA)["access_token"])
    assert pending.get(f"{API}/licence").json()["detail"]["code"] == "MFA_REQUIRED"


# ---- B read-only × A sender ----------------------------------------------------------------------


def test_email_sender_keeps_delivering_in_read_only_mode(
    api: Api, db: Session, vendor: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert install(api, key(vendor)).status_code == 200
    expire()
    assert licence.current(db).read_only is True
    db.execute(delete(EmailMessage))
    row = EmailMessage(
        to_email="pm@client.sa",
        language=Language.en,
        template="generic",
        subject="Read-only notice",
        body="Hello",
    )
    db.add(row)
    db.commit()
    s = get_settings()
    with smtp_server() as (port, inbox):
        for k, v in {
            "smtp_host": "127.0.0.1",
            "smtp_port": port,
            "smtp_user": "hse-mailer",
            "smtp_password": "secret",
            "smtp_from": "HSE Platform <hse@client.sa>",
            "smtp_security": "none",
            "smtp_timeout_seconds": 5.0,
        }.items():
            monkeypatch.setattr(s, k, v)
        out = JOBS["email_send"](db)
    assert out["sent"] == 1, out
    db.refresh(row)
    assert row.status == EmailStatus.sent and len(inbox.messages) == 1


# ---- attachments.store: scan (C) → shrink (A) → storage cap (B) ----------------------------------


def _project_user(db: Session) -> tuple[uuid.UUID, uuid.UUID]:
    pid = db.scalars(select(Project.id).where(Project.code == "ANIA-EXP")).one()
    uid = db.scalars(select(User.id).where(User.email == NOURA)).one()
    return pid, uid


def test_store_scans_the_original_then_shrinks(db: Session, clamd: list[bytes]) -> None:
    pid, uid = _project_user(db)
    raw = photo()
    a = attachments.store(
        db, AttachmentOwner.field_photo, uuid.uuid4(), pid, "IMG_1.jpg", raw, "image/jpeg", uid
    )
    assert clamd == [raw]  # the scanner saw the upload as received, metadata and all
    assert a.scan_status == ScanStatus.clean
    stored = attachments.read_content(a)
    assert a.size_bytes == len(stored) < len(raw) // 5 and no_metadata(stored)
    # an infected "photo" is refused before any image work
    with pytest.raises(ApiError) as e:
        attachments.store(
            db, AttachmentOwner.field_photo, uuid.uuid4(), pid, "x.jpg", EICAR, "image/jpeg", uid
        )
    assert e.value.code == "FILE_INFECTED"


def test_generated_files_are_neither_scanned_nor_shrunk(db: Session, clamd: list[bytes]) -> None:
    pid, uid = _project_user(db)
    raw = photo(2400, 1800)
    a = attachments.store(
        db,
        AttachmentOwner.field_photo,
        uuid.uuid4(),
        pid,
        "chart.jpg",
        raw,
        "image/jpeg",
        uid,
        generated=True,
    )
    assert clamd == [] and a.scan_status == ScanStatus.skipped
    assert attachments.read_content(a) == raw and opened(raw).size == (2400, 1800)


def test_storage_cap_counts_the_shrunk_size(
    api: Api, db: Session, vendor: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert install(api, key(vendor, max_storage_gb=10)).status_code == 200
    room = 1024 * 1024  # 1 MB left under the cap
    monkeypatch.setattr(
        licence, "storage_used", lambda _db: licence.Storage(10 * licence.GB - room, 0)
    )
    pid, uid = _project_user(db)
    raw = photo()
    assert len(raw) > room
    a = attachments.store(
        db, AttachmentOwner.field_photo, uuid.uuid4(), pid, "IMG_2.jpg", raw, "image/jpeg", uid
    )
    assert a.size_bytes < room  # accepted: the shrunk photo fits
    with pytest.raises(ApiError) as e:  # the same bytes kept as they are do not
        attachments.store(
            db,
            AttachmentOwner.field_photo,
            uuid.uuid4(),
            pid,
            "IMG_3.jpg",
            raw,
            "image/jpeg",
            uid,
            shrink=False,
        )
    assert e.value.code == "LICENCE_LIMIT_REACHED"
