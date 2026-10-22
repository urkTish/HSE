"""Trial readiness, package B: signed licence, read-only on expiry, caps (D-289…D-298)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import licence_cli
from app.core import clock
from app.core import licence_key as lk
from app.core.config import get_settings
from app.core.enums import EntityType
from app.core.errors import ApiError
from app.core.hse_enums import AttachmentOwner, GroundingResult
from app.models import AiLog, AuditEntry, LicenceKey, User
from app.services import licence
from tests.conftest import Api, Ids

API = "/api/v1"
TODAY = date(2026, 10, 22)  # Riyadh date of the pinned clock below
PROJECT = {
    "code": "TRIAL-2",
    "name_en": "Second project",
    "name_ar": "المشروع الثاني",
    "project_type": "other",
    "client_name_en": "Client",
    "client_name_ar": "العميل",
    "city": "Riyadh",
    "start_date": "2026-10-01",
}


@pytest.fixture
def vendor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Ed25519PrivateKey]:
    """A throw-away vendor key pair: the public half is configured as the shipped key."""
    private = Ed25519PrivateKey.generate()
    monkeypatch.setattr(lk, "PUBLIC_KEY_FILE", tmp_path / "absent.pem")
    monkeypatch.setattr(get_settings(), "licence_public_key", lk.public_pem(private.public_key()))
    clock.set_now(datetime(2026, 10, 22, 7, 0, tzinfo=UTC))
    licence.invalidate()
    yield private
    clock.set_now(None)
    licence.invalidate()


def terms(**over: Any) -> lk.LicenceTerms:
    base: dict[str, Any] = {
        "licence_id": "LIC-TEST-1",
        "customer": "ACME Airports",
        "bundle": "trial",
        "issued_on": TODAY,
        "valid_until": TODAY + timedelta(days=29),
        "max_projects": None,
        "max_users": None,
        "max_storage_gb": None,
        "ai_questions_per_month": None,
    }
    return lk.LicenceTerms(**{**base, **over})


def key(private: Ed25519PrivateKey, **over: Any) -> str:
    return lk.sign(terms(**over), private)


def install(api: Api, k: str) -> Any:
    return api.as_("faisal.harbi").put(f"{API}/licence", json={"key": k})


def expire(days_after: int = 1) -> None:
    """Move the clock past a key installed with the default 30-day window."""
    clock.set_now(datetime(2026, 10, 22, 7, 0, tzinfo=UTC) + timedelta(days=29 + days_after))


# ---- no key = unlimited -------------------------------------------------------------------------


def test_no_key_is_unlimited(api: Api) -> None:
    mgr = api.as_("faisal.harbi")
    st = mgr.get(f"{API}/licence").json()
    assert st["state"] == "none" and st["read_only"] is False and st["source"] is None
    assert st["projects"]["limit"] is None and st["users"]["limit"] is None
    assert st["storage"]["limit_gb"] is None and st["storage"]["warning"] is False
    assert st["storage"]["used_bytes"] > 0  # the database itself
    assert st["can_manage"] is True
    assert mgr.post(f"{API}/projects", json=PROJECT).status_code == 201


# ---- key format and CLI -------------------------------------------------------------------------


def test_sign_verify_and_tamper() -> None:
    private = Ed25519PrivateKey.generate()
    pub = private.public_key()
    k = key(private, max_users=50, extra={"extra_field": "kept"})
    t = lk.verify(k, pub)
    assert t.customer == "ACME Airports" and t.max_users == 50 and t.is_trial
    assert t.extra == {"extra_field": "kept"}  # readable later for bundle gating
    # line breaks from an e-mail do not matter
    assert lk.verify(k[:20] + "\n  " + k[20:], pub) == t
    prefix, _payload, sig = k.split(".")
    other = lk.sign(terms(max_users=5000), private).split(".")[1]
    with pytest.raises(lk.LicenceKeyError) as e:
        lk.verify(f"{prefix}.{other}.{sig}", pub)
    assert e.value.reason == "bad_signature"
    with pytest.raises(lk.LicenceKeyError) as e:
        lk.verify(k, Ed25519PrivateKey.generate().public_key())
    assert e.value.reason == "bad_signature"
    with pytest.raises(lk.LicenceKeyError) as e:
        lk.verify("not-a-key", pub)
    assert e.value.reason == "malformed"
    with pytest.raises(lk.LicenceKeyError) as e:
        lk.verify(k, None)
    assert e.value.reason == "no_public_key"


def test_cli_keygen_issue_show(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    priv, pub = tmp_path / "secret" / "p.pem", tmp_path / "pub.pem"
    assert licence_cli.main(["keygen", "--private-out", str(priv), "--public-out", str(pub)]) == 0
    assert priv.stat().st_mode & 0o077 == 0  # only the owner can read the private key
    assert licence_cli.main(["keygen", "--private-out", str(priv), "--public-out", str(pub)]) == 1
    capsys.readouterr()
    args = ["issue", "--private-key", str(priv), "--customer", "ACME", "--bundle", "trial"]
    assert licence_cli.main([*args, "--issued-on", "2026-10-22", "--max-users", "60"]) == 0
    issued = capsys.readouterr().out.strip()
    t = lk.verify(issued, lk.load_public_key(pub.read_text()))
    assert (t.bundle, t.valid_until, t.max_projects, t.max_users) == (
        "trial",
        date(2026, 11, 20),  # 30 days, the issue day included
        1,
        60,
    )
    assert (t.max_storage_gb, t.ai_questions_per_month) == (10, 100)
    assert licence_cli.main(["show", issued, "--public-key", str(pub)]) == 0
    assert '"customer": "ACME"' in capsys.readouterr().out
    # a paid bundle needs an end date; "unlimited" clears a cap
    assert licence_cli.main([*args[:-1], "basic"]) == 2
    paid = [*args[:-1], "basic", "--valid-until", "2027-10-31", "--max-projects", "unlimited"]
    assert licence_cli.main(paid) == 0
    t = lk.verify(capsys.readouterr().out.strip(), lk.load_public_key(pub.read_text()))
    assert (t.max_projects, t.ai_questions_per_month, t.max_storage_gb) == (None, 0, 50)


# ---- installing a key ---------------------------------------------------------------------------


def test_install_trial_key(api: Api, db: Session, vendor: Ed25519PrivateKey) -> None:
    res = install(api, key(vendor))
    assert res.status_code == 200, res.text
    st = res.json()
    assert st["state"] == "active" and st["source"] == "database"
    assert st["bundle"] == "trial" and st["is_trial"] is True and st["days_left"] == 29
    assert st["data_deletion_after"] == "2026-12-20"  # 30 days after the last day
    assert st["customer"] == "ACME Airports"
    # every user sees the state (banner); only the HSE Manager may change it
    officer = api.as_("noura.qahtani")
    seen = officer.get(f"{API}/licence").json()
    assert seen["state"] == "active" and seen["can_manage"] is False
    assert officer.put(f"{API}/licence", json={"key": key(vendor)}).status_code == 403
    entry = db.scalar(select(AuditEntry).where(AuditEntry.entity_type == EntityType.licence))
    assert entry is not None and entry.after is not None and entry.after["bundle"] == "trial"
    assert db.scalar(select(func.count()).select_from(LicenceKey)) == 1


@pytest.mark.parametrize(
    ("make", "reason"),
    [
        (lambda v: "HSE1.only-two-parts", "malformed"),
        (lambda v: key(Ed25519PrivateKey.generate()), "bad_signature"),
        (
            lambda v: key(
                v, valid_until=TODAY - timedelta(days=1), issued_on=TODAY - timedelta(30)
            ),
            "expired",
        ),
    ],
)
def test_install_rejects_bad_keys(
    api: Api, vendor: Ed25519PrivateKey, make: Any, reason: str
) -> None:
    res = install(api, make(vendor))
    assert res.status_code == 422
    d = res.json()["detail"]
    assert d["code"] == "LICENCE_KEY_INVALID" and d["meta"]["reason"] == reason
    assert d["message_ar"]
    assert api.as_("faisal.harbi").get(f"{API}/licence").json()["state"] == "none"


def test_install_without_public_key(
    api: Api, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(lk, "PUBLIC_KEY_FILE", tmp_path / "absent.pem")
    res = install(api, key(Ed25519PrivateKey.generate()))
    assert res.status_code == 422
    assert res.json()["detail"]["meta"]["reason"] == "no_public_key"


def test_renewal_without_restart(
    api: Api, vendor: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "licence_cache_seconds", 3600)
    assert install(api, key(vendor)).status_code == 200
    expire()
    mgr = api.as_("faisal.harbi")  # sessions do not survive the 30-day jump
    assert mgr.get(f"{API}/licence").json()["state"] == "expired"
    assert mgr.post(f"{API}/projects", json=PROJECT).status_code == 403
    renewed = key(vendor, licence_id="LIC-2", bundle="basic", valid_until=TODAY + timedelta(400))
    res = install(api, renewed)
    assert res.status_code == 200 and res.json()["state"] == "active"
    # the long cache was dropped by the install: writes work at once
    assert mgr.get(f"{API}/licence").json()["bundle"] == "basic"
    assert mgr.post(f"{API}/projects", json=PROJECT).status_code == 201


# ---- read-only ----------------------------------------------------------------------------------


def test_expired_is_read_only(api: Api, ids: Ids, vendor: Ed25519PrivateKey) -> None:
    assert install(api, key(vendor)).status_code == 200
    assert api.as_("faisal.harbi").get(f"{API}/licence").json()["days_left"] == 29
    expire()
    mgr = api.as_("faisal.harbi")  # sessions do not survive the 30-day jump
    st = mgr.get(f"{API}/licence").json()
    assert st["state"] == "expired" and st["read_only"] is True and st["days_left"] == -1
    # writes refused with a clear EN / AR error
    res = mgr.post(f"{API}/projects", json=PROJECT)
    assert res.status_code == 403
    d = res.json()["detail"]
    assert d["code"] == "LICENCE_READ_ONLY" and d["meta"] == {"state": "expired"}
    assert "read-only" in d["message"] and "للقراءة فقط" in d["message_ar"]
    pid = ids.project("ANIA-EXP")
    patch = mgr.patch(f"{API}/projects/{pid}", json={"city": "Jeddah"})
    assert patch.status_code == 403
    # reads, exports, sign-in and sign-out keep working
    assert mgr.get(f"{API}/projects").status_code == 200
    assert mgr.get(f"{API}/exports/projects").status_code in (200, 404, 422)
    assert api.login("noura.qahtani@example.com").status_code == 200
    assert api.as_("noura.qahtani").post(f"{API}/auth/logout").status_code == 204
    reset = api.anon.post(f"{API}/auth/password-reset", json={"email": "x@example.com"})
    assert reset.status_code == 202
    # the last day itself is still fine
    clock.set_now(datetime(2026, 11, 20, 20, 59, tzinfo=UTC))  # 23:59 Riyadh, last day
    mgr = api.as_("faisal.harbi")
    assert mgr.post(f"{API}/projects", json=PROJECT).status_code == 201


def test_invalid_environment_key_is_read_only(
    api: Api, vendor: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "licence_key", key(Ed25519PrivateKey.generate()))
    mgr = api.as_("faisal.harbi")
    st = mgr.get(f"{API}/licence").json()
    assert st["state"] == "invalid" and st["read_only"] and st["source"] == "environment"
    assert "signature" in st["problem"]
    res = mgr.post(f"{API}/projects", json=PROJECT)
    assert res.status_code == 403 and res.json()["detail"]["meta"] == {"state": "invalid"}
    # a valid environment key works; a pasted key wins over it
    monkeypatch.setattr(get_settings(), "licence_key", key(vendor, customer="From env"))
    assert mgr.get(f"{API}/licence").json()["customer"] == "From env"
    assert install(api, key(vendor, customer="Pasted")).status_code == 200
    assert mgr.get(f"{API}/licence").json()["customer"] == "Pasted"


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("GET", "/api/v1/incidents", True),
        ("POST", "/api/v1/auth/login", True),
        ("POST", "/api/v1/auth/password-reset/confirm", True),
        ("PUT", "/api/v1/licence", True),
        ("POST", "/api/v1/exports", True),
        ("POST", f"/api/v1/attachments/{uuid.uuid4()}/signed-url", True),
        ("POST", "/api/v1/gate-checks", True),
        ("POST", "/api/v1/emergency/muster-scan", True),
        ("POST", f"/api/v1/projects/{uuid.uuid4()}/emergency-events", True),
        ("POST", f"/api/v1/notifications/{uuid.uuid4()}/read", True),
        ("POST", "/api/v1/projects", False),
        ("POST", "/api/v1/ai/ask", False),
        ("POST", f"/api/v1/projects/{uuid.uuid4()}/incidents", False),
        ("DELETE", "/api/v1/export-subscriptions/x", False),
        ("POST", "/api/v1/gate-checks/pairings/x/cancel", False),
    ],
)
def test_read_only_allow_list(method: str, path: str, allowed: bool) -> None:
    assert licence.write_allowed(method, path) is allowed


# ---- caps ---------------------------------------------------------------------------------------


def test_project_cap(api: Api, db: Session, vendor: Ed25519PrivateKey) -> None:
    open_now = licence.open_projects(db)
    assert install(api, key(vendor, max_projects=open_now + 1)).status_code == 200
    mgr = api.as_("faisal.harbi")
    first = mgr.post(f"{API}/projects", json=PROJECT)
    assert first.status_code == 201
    res = mgr.post(f"{API}/projects", json={**PROJECT, "code": "TRIAL-3"})
    assert res.status_code == 409
    d = res.json()["detail"]
    assert d["code"] == "LICENCE_LIMIT_REACHED" and d["message_ar"]
    assert d["meta"] == {"limit": "projects", "max": open_now + 1, "used": open_now + 1}
    st = mgr.get(f"{API}/licence").json()["projects"]
    assert st == {"used": open_now + 1, "limit": open_now + 1, "percent": 100}


def test_user_cap_blocks_invite_and_reactivation(
    api: Api, db: Session, ids: Ids, vendor: Ed25519PrivateKey
) -> None:
    used = licence.counted_users(db)
    assert install(api, key(vendor, max_users=used + 1)).status_code == 200
    mgr = api.as_("faisal.harbi")
    pid = ids.project("ANIA-EXP")

    def invite(email: str) -> Any:
        return mgr.post(
            f"{API}/users",
            json={
                "email": email,
                "full_name_en": "New Person",
                "employer_type": "client",
                "role_assignments": [{"role": "viewer_client", "project_id": pid}],
            },
        )

    assert invite("user.fits@example.com").status_code == 201
    res = invite("user.too.many@example.com")
    assert res.status_code == 409
    assert res.json()["detail"]["meta"]["limit"] == "users"
    # freeing a seat by deactivating lets one in; reactivating the old one is then refused
    old = ids.user("user.fits")
    off = mgr.post(
        f"{API}/users/{old}/transitions", json={"to_status": "deactivated", "reason": "Left site"}
    )
    assert off.status_code == 200, off.text
    assert invite("user.next@example.com").status_code == 201
    back = mgr.post(
        f"{API}/users/{old}/transitions", json={"to_status": "active", "reason": "Back"}
    )
    assert back.status_code == 409 and back.json()["detail"]["code"] == "LICENCE_LIMIT_REACHED"


def test_ai_questions_per_month(api: Api, db: Session, ids: Ids, vendor: Ed25519PrivateKey) -> None:
    assert install(api, key(vendor, ai_questions_per_month=2)).status_code == 200
    noura = db.scalar(select(User).where(User.email == "noura.qahtani@example.com"))
    assert noura is not None

    def log(at: datetime, **over: Any) -> None:
        db.add(
            AiLog(
                user_id=noura.id,
                kind=over.get("kind", "ask"),
                grounding=GroundingResult.passed,
                model="m",
                cached=over.get("cached", False),
                error_code=over.get("error_code"),
                created_at=at,
            )
        )

    log(datetime(2026, 9, 30, 20, 0, tzinfo=UTC))  # 23:00 Riyadh on 30 Sep: last month
    log(datetime(2026, 10, 2, 8, 0, tzinfo=UTC))
    log(datetime(2026, 10, 3, 8, 0, tzinfo=UTC), cached=True)  # cached: not counted
    log(datetime(2026, 10, 3, 9, 0, tzinfo=UTC), error_code="AI_UNAVAILABLE")  # failed
    log(datetime(2026, 10, 4, 9, 0, tzinfo=UTC), kind="insights")  # not a question
    db.commit()
    c = api.as_("noura.qahtani")
    pid = ids.project("ANIA-EXP")
    body = {"project_id": pid, "question": "TRIR?", "language": "en"}
    headers = {"Accept": "application/json"}
    # one question left: the ask passes the licence check (then: no AI key in tests → 503)
    assert c.post(f"{API}/ai/ask", json=body, headers=headers).status_code == 503
    assert c.get(f"{API}/licence").json()["ai_questions_month"]["used"] == 1
    log(datetime(2026, 10, 21, 9, 0, tzinfo=UTC))
    db.commit()
    res = c.post(f"{API}/ai/ask", json=body, headers=headers)
    assert res.status_code == 429
    d = res.json()["detail"]
    assert d["code"] == "LICENCE_LIMIT_REACHED" and d["meta"]["limit"] == "ai_questions"
    # renews on the 1st of next month, Riyadh time (Nov 1 00:00 = Oct 31 21:00 UTC)
    assert int(res.headers["Retry-After"]) == int(
        (datetime(2026, 10, 31, 21, 0, tzinfo=UTC) - clock.now()).total_seconds()
    )


def test_storage_cap_and_warning(api: Api, db: Session, vendor: Ed25519PrivateKey) -> None:
    assert install(api, key(vendor, max_storage_gb=0)).status_code == 200
    st = api.as_("faisal.harbi").get(f"{API}/licence").json()["storage"]
    assert st["limit_gb"] == 0 and st["percent"] == 100 and st["warning"] is True
    with pytest.raises(ApiError) as e:
        licence.ensure_storage(db, AttachmentOwner.incident, 10)
    assert e.value.code == "LICENCE_LIMIT_REACHED" and e.value.meta == {
        "limit": "storage",
        "max": 0,
        "used": 0,
    }
    licence.ensure_storage(db, AttachmentOwner.xp_export_file, 10)  # exports are never refused


def test_storage_warning_threshold(
    api: Api, db: Session, vendor: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert install(api, key(vendor, max_storage_gb=10)).status_code == 200

    def fake(used_gb: float) -> None:
        monkeypatch.setattr(
            licence, "storage_used", lambda _db: licence.Storage(int(used_gb * licence.GB), 0)
        )

    mgr = api.as_("faisal.harbi")
    fake(7.9)
    assert mgr.get(f"{API}/licence").json()["storage"]["warning"] is False
    fake(8.0)
    s = mgr.get(f"{API}/licence").json()["storage"]
    assert s["warning"] is True and s["percent"] == 80
    licence.ensure_storage(db, AttachmentOwner.incident, 1024)  # below the cap: accepted
    fake(10.0)
    with pytest.raises(ApiError):
        licence.ensure_storage(db, AttachmentOwner.incident, 1)
