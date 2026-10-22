"""Virus scanning of uploads before they are accepted (D-302, D-303).

The scanner is clamd (the `clamav` service in docker-compose) spoken to over TCP with the
INSTREAM command, so no file ever touches a shared disk. Every user upload passes `ensure_clean`:
through `attachments.store` (all stored files, whether multipart or base64 in JSON) and, for
imports that are parsed rather than stored, through `check_upload` in the router.

- Not configured (`CLAMAV_HOST` empty, the default in dev and tests): nothing is scanned and
  stored files keep `scan_status = skipped`, as before.
- Malware found: 422 FILE_INFECTED, nothing is stored, an `access_denied` audit entry is kept.
- Scanner down or erroring: 503 SCANNER_UNAVAILABLE (fail closed), or with `CLAMAV_FAIL_OPEN`
  the file is accepted unscanned (`skipped`) and a warning is logged."""

from __future__ import annotations

import hashlib
import logging
import socket
import struct
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import AuditAction, AuditResult
from app.core.errors import ApiError, ErrorCode
from app.core.hse_enums import ScanStatus

log = logging.getLogger("hse.scanner")
CHUNK = 64 * 1024


class ScannerError(Exception):
    """clamd could not be reached or did not give a verdict."""


@dataclass(frozen=True)
class Verdict:
    infected: bool
    signature: str | None = None


def enabled() -> bool:
    return bool(get_settings().clamav_host.strip())


def _recv_reply(sock: socket.socket) -> str:
    buf = b""
    while not buf.endswith(b"\0"):
        part = sock.recv(4096)
        if not part:
            break
        buf += part
    return buf.rstrip(b"\0").decode("utf-8", "replace").strip()


def scan_bytes(data: bytes) -> Verdict:
    """One INSTREAM round trip. Raises ScannerError when there is no clear verdict."""
    s = get_settings()
    try:
        with socket.create_connection(
            (s.clamav_host.strip(), s.clamav_port), timeout=s.clamav_timeout_seconds
        ) as sock:
            sock.sendall(b"zINSTREAM\0")
            for i in range(0, len(data), CHUNK):
                part = data[i : i + CHUNK]
                sock.sendall(struct.pack(">I", len(part)) + part)
            sock.sendall(struct.pack(">I", 0))
            reply = _recv_reply(sock)
    except OSError as exc:
        raise ScannerError(f"clamd unreachable: {exc}") from exc
    # "stream: OK" | "stream: <Signature> FOUND" | "<message> ERROR"
    body = reply.split(":", 1)[1].strip() if ":" in reply else reply
    if body == "OK":
        return Verdict(False)
    if body.endswith(" FOUND"):
        return Verdict(True, body[: -len(" FOUND")].strip())
    raise ScannerError(f"clamd answered {reply!r}")


def unavailable() -> ApiError:
    return ApiError(
        503,
        ErrorCode.SCANNER_UNAVAILABLE,
        "The file could not be checked for viruses right now, so it was not saved. "
        "Try again in a few minutes.",
        "تعذّر فحص الملف من الفيروسات الآن، لذا لم يُحفظ. حاول مرة أخرى بعد بضع دقائق.",
    )


def infected(file_name: str) -> ApiError:
    return ApiError(
        422,
        ErrorCode.FILE_INFECTED,
        f"The file {file_name} was rejected: the virus scanner found a threat in it.",
        f"رُفض الملف {file_name}: وجد فاحص الفيروسات فيه تهديدًا.",
    )


def ensure_clean(
    data: bytes,
    file_name: str,
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> ScanStatus:
    """`clean` or `skipped` (scanning off, or fail-open while the scanner is down); raises
    FILE_INFECTED / SCANNER_UNAVAILABLE otherwise."""
    if not enabled():
        return ScanStatus.skipped
    name = (file_name or "file").rsplit("/", 1)[-1][:120]
    try:
        verdict = scan_bytes(data)
    except ScannerError as exc:
        if get_settings().clamav_fail_open:
            log.warning("upload accepted unscanned (fail-open): %s; %s", name, exc)
            return ScanStatus.skipped
        log.error("upload refused, scanner unavailable: %s; %s", name, exc)
        raise unavailable() from exc
    if not verdict.infected:
        return ScanStatus.clean
    digest = hashlib.sha256(data).hexdigest()
    log.warning(
        "infected upload refused: %s sha256=%s signature=%s", name, digest, verdict.signature
    )
    if db is not None:
        from app.services import audit  # noqa: PLC0415

        details: dict[str, Any] = {"reason": "file_infected", "file_name": name,
                                   "sha256": digest, "signature": verdict.signature}  # fmt: skip
        audit.record(db, AuditAction.access_denied, audit.AuditActor(user_id),
                     project_id=project_id, result=AuditResult.failed, details=details,
                     defer=True)  # fmt: skip
    raise infected(name)


def check_upload(
    upload: Any,
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> None:
    """Scan a FastAPI UploadFile (imports parsed in place) and rewind it for the caller."""
    if upload is None or not enabled():
        return
    f = upload.file
    f.seek(0)
    data = f.read()
    f.seek(0)
    ensure_clean(data, getattr(upload, "filename", None) or "upload", db, user_id, project_id)
