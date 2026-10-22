"""SMTP sender for the email outbox (D-279, D-280, D-281).

Requests only write `email_outbox` rows (`notify.send_email`, 6g distribution); the scheduler's
`email_send` job delivers them here, so a slow or broken mail server never blocks a request.

- Provider-neutral SMTP: SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM and
  SMTP_SECURITY (`starttls`, `ssl` or `none`). No host or from address = rows stay queued.
- One row at a time, locked with SKIP LOCKED and committed after each send, so two schedulers
  never send the same row and a crash re-sends at most the message in flight.
- Server or login trouble (cannot connect, TLS, authentication) ends the run without touching
  rows: they are tried again next minute. A message-level temporary error (4xx, dropped
  connection while sending) is retried with backoff (EMAIL_RETRY_BASE_SECONDS × 2ⁿ, at most one
  hour) up to EMAIL_MAX_ATTEMPTS; a permanent one (5xx, missing attachment file) fails at once.
- Rows older than EMAIL_MAX_AGE_HOURS are marked failed instead of sent (invite and reset links
  would have expired), so switching SMTP on later does not flush a stale backlog.
- RFC 2606 / 6761 reserved domains (example.com, *.test, *.invalid, …) are marked failed
  without contacting the server (demo data).
"""

from __future__ import annotations

import html
import logging
import re
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from datetime import timedelta
from email.message import EmailMessage as Mime
from email.utils import formatdate, make_msgid, parseaddr
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import Settings, get_settings
from app.core.enums import EmailStatus, Language
from app.models import Attachment, EmailMessage

log = logging.getLogger("hse.mailer")

RESERVED_DOMAINS = frozenset({"example.com", "example.net", "example.org"})
RESERVED_TLDS = frozenset({"test", "example", "invalid", "localhost"})
MAX_BACKOFF_SECONDS = 3600
_URL = re.compile(r"https?://[^\s<>\"]+")


class SmtpUnavailableError(Exception):
    """The server cannot be reached or refuses our login: no row is charged an attempt."""


class SendError(Exception):
    def __init__(self, message: str, permanent: bool) -> None:
        super().__init__(message)
        self.permanent = permanent


def configured(s: Settings | None = None) -> bool:
    s = s or get_settings()
    return bool(s.smtp_host.strip() and s.smtp_from.strip())


def reserved_address(addr: str) -> bool:
    domain = addr.rsplit("@", 1)[-1].strip().lower().rstrip(".")
    if not domain or "@" not in addr:
        return True
    return (
        domain in RESERVED_DOMAINS
        or domain.rsplit(".", 1)[-1] in RESERVED_TLDS
        or any(domain.endswith("." + d) for d in RESERVED_DOMAINS)
    )


# ---- message ------------------------------------------------------------------------------------


@dataclass
class File:
    name: str
    content_type: str
    data: bytes


def _html(body: str, lang: Language) -> str:
    """The plain body as HTML with links and the reading direction (Arabic right-to-left)."""
    out: list[str] = []
    pos = 0
    for m in _URL.finditer(body):
        out.append(html.escape(body[pos : m.start()]))
        url = html.escape(m.group(0), quote=True)
        out.append(f'<a href="{url}">{url}</a>')
        pos = m.end()
    out.append(html.escape(body[pos:]))
    text = "".join(out).replace("\n", "<br>\n")
    d = "rtl" if lang == Language.ar else "ltr"
    font = "Tahoma, Arial, sans-serif" if lang == Language.ar else "Arial, sans-serif"
    return (
        f'<!doctype html>\n<html lang="{lang.value}" dir="{d}"><body>'
        f'<div dir="{d}" style="font-family: {font}; font-size: 15px; line-height: 1.6;">'
        f"{text}</div></body></html>\n"
    )


def build(row: EmailMessage, files: list[File], s: Settings | None = None) -> Mime:
    s = s or get_settings()
    msg = Mime()
    msg["From"] = s.smtp_from
    msg["To"] = row.to_email
    msg["Subject"] = row.subject
    msg["Date"] = formatdate(localtime=False)
    domain = parseaddr(s.smtp_from)[1].rsplit("@", 1)[-1] or "hse.local"
    msg["Message-ID"] = make_msgid(idstring=row.id.hex[:12], domain=domain)
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(row.body)
    msg.add_alternative(_html(row.body, row.language), subtype="html")
    msg["Content-Language"] = row.language.value  # after set_content, which clears Content-*
    for f in files:
        main, _, sub = f.content_type.partition("/")
        msg.add_attachment(
            f.data, maintype=main or "application", subtype=sub or "octet-stream", filename=f.name
        )
    return msg


def _files(db: Session, row: EmailMessage) -> list[File]:
    from app.services import attachments  # noqa: PLC0415

    out: list[File] = []
    for raw in row.attachment_ids or []:
        a = db.get(Attachment, uuid.UUID(str(raw)))
        if a is None:
            raise SendError("Attachment no longer exists.", permanent=True)
        try:
            data = attachments.read_content(a)
        except OSError as e:
            raise SendError(f"Attachment file missing: {a.file_name}", permanent=True) from e
        out.append(File(a.file_name, a.content_type, data))
    return out


def _message(db: Session, row: EmailMessage, s: Settings) -> Mime:
    files = _files(db, row)
    try:
        return build(row, files, s)
    except (ValueError, TypeError) as e:  # e.g. a header with a line break
        raise SendError(f"Cannot build the message: {e}"[:500], permanent=True) from e


# ---- SMTP ----------------------------------------------------------------------------------------


def connect(s: Settings | None = None) -> smtplib.SMTP:
    """Open and log in. Raises SmtpUnavailableError on any connection, TLS or login problem."""
    s = s or get_settings()
    ctx = ssl.create_default_context()
    try:
        conn: smtplib.SMTP
        if s.smtp_security == "ssl":
            conn = smtplib.SMTP_SSL(
                s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds, context=ctx
            )
        else:
            conn = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
        try:
            conn.ehlo()
            if s.smtp_security == "starttls":
                conn.starttls(context=ctx)
                conn.ehlo()
            if s.smtp_user:
                conn.login(s.smtp_user, s.smtp_password)
        except BaseException:
            _quit(conn)
            raise
    except (smtplib.SMTPException, OSError) as e:
        raise SmtpUnavailableError(f"{type(e).__name__}: {e}"[:500]) from e
    return conn


def _quit(conn: smtplib.SMTP | None) -> None:
    if conn is None:
        return
    try:
        conn.quit()
    except (smtplib.SMTPException, OSError):
        conn.close()


def _code_error(code: int, text: Any) -> SendError:
    detail = text.decode(errors="replace") if isinstance(text, bytes) else str(text)
    return SendError(f"{code} {detail}"[:500], permanent=code >= 500)


def deliver(conn: smtplib.SMTP, msg: Mime) -> None:
    """Send one message. Raises SendError (permanent or temporary)."""
    try:
        refused = conn.send_message(msg)
    except smtplib.SMTPRecipientsRefused as e:
        code, text = next(iter(e.recipients.values()), (550, b"recipient refused"))
        raise _code_error(code, text) from e
    except smtplib.SMTPResponseException as e:  # sender refused, data error, …
        raise _code_error(e.smtp_code, e.smtp_error) from e
    except (smtplib.SMTPException, OSError) as e:  # dropped connection, timeout
        raise SendError(f"{type(e).__name__}: {e}"[:500], permanent=False) from e
    if refused:  # only one recipient per message, so this is unusual
        code, text = next(iter(refused.values()))
        raise _code_error(code, text)


# ---- the job ------------------------------------------------------------------------------------


def _fail(db: Session, row: EmailMessage, error: str) -> None:
    row.status, row.last_error, row.next_attempt_at = EmailStatus.failed, error[:500], None
    if row.delivery_id is not None:
        from app.services.scorecard import distribution  # noqa: PLC0415

        distribution.delivery_failed(db, row.delivery_id, error)


def _sent(db: Session, row: EmailMessage) -> None:
    at = now()
    row.status, row.sent_at, row.last_error, row.next_attempt_at = EmailStatus.sent, at, None, None
    if row.delivery_id is not None:
        from app.services.scorecard import distribution  # noqa: PLC0415

        distribution.delivery_sent(db, row.delivery_id, at)


def _retry(db: Session, row: EmailMessage, error: str, s: Settings) -> None:
    row.attempts += 1
    if row.attempts >= s.email_max_attempts:
        _fail(db, row, f"Gave up after {row.attempts} attempts: {error}")
        return
    wait = min(s.email_retry_base_seconds * 2 ** (row.attempts - 1), MAX_BACKOFF_SECONDS)
    row.last_error, row.next_attempt_at = error[:500], now() + timedelta(seconds=wait)


def waiting(db: Session) -> int:
    q = select(func.count()).select_from(EmailMessage)
    return int(db.scalar(q.where(EmailMessage.status == EmailStatus.queued)) or 0)


_warned_unconfigured = False


def send_due(db: Session) -> dict[str, Any]:
    """`email_send` job: deliver the due queued rows (at most EMAIL_BATCH_SIZE per run)."""
    global _warned_unconfigured  # noqa: PLW0603
    s = get_settings()
    if not configured(s):
        n = waiting(db)
        if n and not _warned_unconfigured:
            log.warning("SMTP is not configured (SMTP_HOST / SMTP_FROM): %d emails wait", n)
            _warned_unconfigured = True
        return {"smtp": "not_configured", "waiting": n}
    t = now()
    due = list(
        db.scalars(
            select(EmailMessage.id)
            .where(
                EmailMessage.status == EmailStatus.queued,
                or_(EmailMessage.next_attempt_at.is_(None), EmailMessage.next_attempt_at <= t),
            )
            .order_by(EmailMessage.created_at, EmailMessage.id)
            .limit(s.email_batch_size)
        )
    )
    out = {"sent": 0, "failed": 0, "retry": 0, "expired": 0}
    conn: smtplib.SMTP | None = None
    try:
        for mid in due:
            row = db.scalars(
                select(EmailMessage)
                .where(EmailMessage.id == mid, EmailMessage.status == EmailStatus.queued)
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:  # taken by another sender or already handled
                db.rollback()
                continue
            if row.created_at < t - timedelta(hours=s.email_max_age_hours):
                _fail(db, row, f"Not sent within {s.email_max_age_hours} hours; dropped.")
                out["expired"] += 1
                db.commit()
                continue
            if reserved_address(row.to_email):
                _fail(db, row, "Reserved or invalid address (demo data); not sent.")
                out["failed"] += 1
                db.commit()
                continue
            try:
                msg = _message(db, row, s)
                if conn is None:
                    conn = connect(s)
                deliver(conn, msg)
            except SendError as e:
                if e.permanent:
                    _fail(db, row, str(e))
                    out["failed"] += 1
                else:
                    _retry(db, row, str(e), s)
                    out["retry"] += 1
                    _quit(conn)  # start the next message on a fresh connection
                    conn = None
                db.commit()
                continue
            _sent(db, row)
            out["sent"] += 1
            db.commit()
    except SmtpUnavailableError as e:
        db.rollback()
        log.error("SMTP server unavailable, emails stay queued: %s", e)
        return {**out, "smtp": "unavailable", "error": str(e)}
    finally:
        _quit(conn)
    return out


def send_test(to_email: str) -> str:
    """Send one test message straight away (CLI: `python -m app.services.mailer test <to>`)."""
    s = get_settings()
    if not configured(s):
        return "SMTP is not configured: set SMTP_HOST and SMTP_FROM (see .env.example)."
    row = EmailMessage(
        id=uuid.uuid4(),
        to_email=to_email,
        language=Language.en,
        template="smtp_test",
        subject="HSE platform: test email / رسالة تجريبية",
        body=(
            "This is a test email from the HSE platform. SMTP sending works.\n\n"
            "هذه رسالة تجريبية من منصة الصحة والسلامة والبيئة. إرسال البريد يعمل.\n"
        ),
    )
    try:
        conn = connect(s)
    except SmtpUnavailableError as e:
        return f"Cannot connect or log in: {e}"
    try:
        deliver(conn, build(row, [], s))
    except SendError as e:
        return f"The server refused the message: {e}"
    finally:
        _quit(conn)
    return f"Sent a test email to {to_email} via {s.smtp_host}:{s.smtp_port}."


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "test":
        print("usage: python -m app.services.mailer test <to-address>")
        return 2
    result = send_test(argv[1])
    print(result)
    return 0 if result.startswith("Sent") else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
