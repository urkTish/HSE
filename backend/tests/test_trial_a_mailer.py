"""Trial A: SMTP sender for the email outbox (D-279, D-280, D-281)."""

from __future__ import annotations

import email
import smtplib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import Message
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.core.config import get_settings
from app.core.enums import EmailStatus, Language
from app.jobs import JOBS
from app.models import EmailMessage, User
from app.services import mailer, notify
from tests.smtp_fake import smtp_server

T0 = datetime(2026, 10, 22, 6, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> Iterator[None]:
    set_now(T0)
    yield
    set_now(None)


@pytest.fixture(autouse=True)
def _empty_outbox(db: Session) -> None:
    """Seeds may leave queued rows (demo invites); each test starts from an empty outbox."""
    db.execute(delete(EmailMessage))
    db.commit()


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """SMTP settings pointing at the in-process fake server (no TLS, with a login)."""
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
        yield inbox


def outbox_row(db: Session, to: str = "pm@client.sa", **kw: Any) -> EmailMessage:
    row = EmailMessage(
        to_email=to,
        language=kw.pop("language", Language.en),
        template=kw.pop("template", "generic"),
        subject=kw.pop("subject", "Test subject"),
        body=kw.pop("body", "Hello,\nopen https://hse.client.sa/en/x?token=abc\n"),
        **kw,
    )
    db.add(row)
    db.commit()
    return row


def parsed(raw: bytes) -> Message:
    return email.message_from_bytes(raw)


def test_not_configured_rows_stay_queued(db: Session, clock: None) -> None:
    row = outbox_row(db)
    assert not mailer.configured()
    out = JOBS["email_send"](db)
    assert out == {"smtp": "not_configured", "waiting": 1}
    db.refresh(row)
    assert row.status == EmailStatus.queued and row.sent_at is None and row.attempts == 0


def test_sends_template_email_en_ar(db: Session, clock: None, smtp: Any) -> None:
    user = db.scalars(select(User).where(User.email == "noura.qahtani@example.com")).one()
    user.email, user.preferred_language = "noura@client.sa", Language.ar
    msg = notify.send_email(db, user, "password_reset", link="https://hse.client.sa/ar/reset?t=1")
    en = outbox_row(db, "omar@client.sa")
    db.commit()
    out = mailer.send_due(db)
    assert out["sent"] == 2 and out["failed"] == 0
    db.refresh(msg)
    db.refresh(en)
    assert msg.status == en.status == EmailStatus.sent and msg.sent_at == T0
    assert len(smtp.logins) == 1  # one connection, one login for the batch
    by_to = {rcpts[0]: parsed(raw) for _, rcpts, raw in smtp.messages}
    ar = by_to["noura@client.sa"]
    assert str(email.header.make_header(email.header.decode_header(ar["Subject"]))) == (
        "إعادة تعيين كلمة المرور"
    )
    assert ar["From"] == "HSE Platform <hse@client.sa>" and ar["Content-Language"] == "ar"
    assert ar["Auto-Submitted"] == "auto-generated" and ar["Message-ID"].endswith("@client.sa>")
    parts = {p.get_content_type(): p for p in ar.walk() if not p.is_multipart()}
    plain = parts["text/plain"].get_payload(decode=True).decode()
    html = parts["text/html"].get_payload(decode=True).decode()
    assert "https://hse.client.sa/ar/reset?t=1" in plain
    assert 'dir="rtl"' in html and '<a href="https://hse.client.sa/ar/reset?t=1">' in html
    en_html = next(p for p in by_to["omar@client.sa"].walk() if p.get_content_type() == "text/html")
    assert 'dir="ltr"' in en_html.get_payload(decode=True).decode()
    # sent rows are not sent again
    assert mailer.send_due(db) == {"sent": 0, "failed": 0, "retry": 0, "expired": 0}
    assert len(smtp.messages) == 2


def test_permanent_refusal_fails_at_once(db: Session, clock: None, smtp: Any) -> None:
    smtp.refuse["gone@client.sa"] = "550 5.1.1 no such user"
    bad = outbox_row(db, "gone@client.sa")
    good = outbox_row(db, "pm@client.sa")
    out = mailer.send_due(db)
    assert out["failed"] == 1 and out["sent"] == 1
    db.refresh(bad)
    assert bad.status == EmailStatus.failed and bad.last_error is not None
    assert bad.last_error.startswith("550")
    db.refresh(good)
    assert good.status == EmailStatus.sent


def test_temporary_refusal_retries_with_backoff(
    db: Session, clock: None, smtp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "email_max_attempts", 3)
    smtp.refuse["busy@client.sa"] = "451 4.3.0 try again later"
    row = outbox_row(db, "busy@client.sa")
    assert mailer.send_due(db)["retry"] == 1
    db.refresh(row)
    assert row.status == EmailStatus.queued and row.attempts == 1
    assert row.next_attempt_at == T0 + timedelta(seconds=60)
    assert mailer.send_due(db)["retry"] == 0  # not due yet: nothing happens
    set_now(T0 + timedelta(seconds=61))
    mailer.send_due(db)
    db.refresh(row)
    assert row.attempts == 2 and row.next_attempt_at == T0 + timedelta(seconds=61 + 120)
    del smtp.refuse["busy@client.sa"]
    set_now(T0 + timedelta(seconds=200))
    assert mailer.send_due(db)["sent"] == 1
    db.refresh(row)
    assert row.status == EmailStatus.sent and row.last_error is None


def test_gives_up_after_max_attempts(
    db: Session, clock: None, smtp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "email_max_attempts", 2)
    smtp.refuse["busy@client.sa"] = "452 4.2.2 mailbox full"
    row = outbox_row(db, "busy@client.sa")
    mailer.send_due(db)
    set_now(T0 + timedelta(minutes=5))
    mailer.send_due(db)
    db.refresh(row)
    assert row.status == EmailStatus.failed and row.attempts == 2
    assert "Gave up after 2 attempts" in (row.last_error or "")


def test_server_down_leaves_rows_untouched(
    db: Session, clock: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = get_settings()
    with smtp_server() as (port, _):
        pass  # the port is now closed: connection refused
    monkeypatch.setattr(s, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(s, "smtp_port", port)
    monkeypatch.setattr(s, "smtp_from", "hse@client.sa")
    monkeypatch.setattr(s, "smtp_security", "none")
    row = outbox_row(db)
    out = mailer.send_due(db)
    assert out["smtp"] == "unavailable"
    db.refresh(row)
    assert row.status == EmailStatus.queued and row.attempts == 0 and row.next_attempt_at is None


class _AuthFails(smtplib.SMTP):
    def login(self, user: str, password: str, *, initial_response_ok: bool = True) -> Any:
        raise smtplib.SMTPAuthenticationError(535, b"5.7.8 bad credentials")


def test_login_failure_leaves_rows_untouched(
    db: Session, clock: None, smtp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mailer.smtplib, "SMTP", _AuthFails)
    row = outbox_row(db)
    out = mailer.send_due(db)
    assert out["smtp"] == "unavailable" and "535" in out["error"]
    db.refresh(row)
    assert row.status == EmailStatus.queued and row.attempts == 0
    assert smtp.messages == []


def test_stale_and_reserved_rows_are_not_sent(db: Session, clock: None, smtp: Any) -> None:
    set_now(T0 - timedelta(hours=73))
    old = outbox_row(db, "pm@client.sa")
    set_now(T0)
    demo = outbox_row(db, "ahmed.zahrani@example.com")
    out = mailer.send_due(db)
    assert out["expired"] == 1 and out["failed"] == 1 and out["sent"] == 0
    db.refresh(old)
    db.refresh(demo)
    assert old.status == demo.status == EmailStatus.failed
    assert "72 hours" in (old.last_error or "") and "Reserved" in (demo.last_error or "")
    assert smtp.messages == []


def test_reserved_address_rules() -> None:
    for a in ("x@example.com", "x@mail.example.org", "x@host.test", "x@a.invalid", "nobody"):
        assert mailer.reserved_address(a), a
    for a in ("x@client.sa", "x@examples.com", "x@gmail.com"):
        assert not mailer.reserved_address(a), a


def test_row_locked_by_another_sender_is_skipped(db: Session, clock: None, smtp: Any) -> None:
    from app.db.session import get_sessionmaker

    row = outbox_row(db)
    with get_sessionmaker()() as other:
        other.scalars(select(EmailMessage).where(EmailMessage.id == row.id).with_for_update()).one()
        assert mailer.send_due(db)["sent"] == 0
        other.rollback()
    assert smtp.messages == []
    assert mailer.send_due(db)["sent"] == 1


def test_missing_attachment_fails_permanently(db: Session, clock: None, smtp: Any) -> None:
    row = outbox_row(db, attachment_ids=[str(uuid.uuid4())])
    assert mailer.send_due(db)["failed"] == 1
    db.refresh(row)
    assert row.status == EmailStatus.failed and "Attachment" in (row.last_error or "")


def test_send_test_cli(smtp: Any) -> None:
    assert mailer.main(["test", "turki@client.sa"]) == 0
    (_, rcpts, raw) = smtp.messages[0]
    plain = next(p for p in parsed(raw).walk() if p.get_content_type() == "text/plain")
    assert rcpts == ["turki@client.sa"]
    assert "SMTP sending works" in plain.get_payload(decode=True).decode()


def test_send_test_cli_not_configured(capsys: pytest.CaptureFixture[str]) -> None:
    assert mailer.main(["test", "turki@client.sa"]) == 1
    assert "not configured" in capsys.readouterr().out
    assert mailer.main([]) == 2
