"""Upload virus scanning with clamd INSTREAM (D-302, D-303). A fake clamd on a local socket stands
in for the ClamAV container, so the suite needs no scanner."""

import socketserver
import struct
import threading
from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import AuditAction
from app.core.hse_enums import ScanStatus
from app.models import Attachment, AuditEntry
from app.services import scanner
from tests.conftest import Api, Ids
from tests.hse_helpers import reported_incident

API = "/api/v1"
PDF = b"%PDF-1.4\n" + b"0" * 64
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class _Clamd(socketserver.BaseRequestHandler):
    seen: list[bytes] = []  # noqa: RUF012

    def handle(self) -> None:
        sock = self.request
        cmd = b""
        while not cmd.endswith(b"\0"):
            cmd += sock.recv(1)
        assert cmd == b"zINSTREAM\0"
        data = b""
        while True:
            head = b""
            while len(head) < 4:
                head += sock.recv(4 - len(head))
            (n,) = struct.unpack(">I", head)
            if n == 0:
                break
            chunk = b""
            while len(chunk) < n:
                chunk += sock.recv(n - len(chunk))
            data += chunk
        _Clamd.seen.append(data)
        if b"EICAR-STANDARD" in data:
            sock.sendall(b"stream: Eicar-Test-Signature FOUND\0")
        elif b"BROKEN" in data:
            sock.sendall(b"INSTREAM size limit exceeded. ERROR\0")
        else:
            sock.sendall(b"stream: OK\0")


@pytest.fixture
def clamd(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[bytes]]:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Clamd)
    server.daemon_threads = True
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    monkeypatch.setattr(get_settings(), "clamav_host", "127.0.0.1")
    monkeypatch.setattr(get_settings(), "clamav_port", server.server_address[1])
    _Clamd.seen = []
    try:
        yield _Clamd.seen
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def scanner_down(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler)
    port = probe.server_address[1]
    probe.server_close()  # nothing listens on this port any more
    monkeypatch.setattr(get_settings(), "clamav_host", "127.0.0.1")
    monkeypatch.setattr(get_settings(), "clamav_port", port)
    monkeypatch.setattr(get_settings(), "clamav_timeout_seconds", 2.0)


def _upload(api: Api, ids: Ids, content: bytes, name: str = "evidence.pdf") -> object:
    n = api.as_("noura.qahtani")
    inc = reported_incident(n, ids)
    return n.post(
        f"{API}/attachments",
        data={"owner_type": "incident", "owner_id": inc["id"]},
        files={"file": (name, content, "application/pdf")},
    )


def test_scanning_off_by_default_stores_skipped(api: Api, ids: Ids, db: Session) -> None:
    assert scanner.enabled() is False
    res = _upload(api, ids, PDF)
    assert res.status_code == 201, res.text  # type: ignore[attr-defined]
    assert res.json()["scan_status"] == "skipped"  # type: ignore[attr-defined]


def test_clean_file_is_marked_clean(api: Api, ids: Ids, clamd: list[bytes]) -> None:
    res = _upload(api, ids, PDF + b"x" * 200_000)  # several INSTREAM chunks
    assert res.status_code == 201, res.text  # type: ignore[attr-defined]
    assert res.json()["scan_status"] == ScanStatus.clean  # type: ignore[attr-defined]
    assert clamd[-1] == PDF + b"x" * 200_000


def test_infected_file_is_refused_and_audited(
    api: Api, ids: Ids, db: Session, clamd: list[bytes]
) -> None:
    res = _upload(api, ids, PDF + EICAR)
    assert res.status_code == 422  # type: ignore[attr-defined]
    detail = res.json()["detail"]  # type: ignore[attr-defined]
    assert detail["code"] == "FILE_INFECTED" and detail["message_ar"]
    assert db.scalars(select(Attachment)).all() == []
    entry = db.scalars(
        select(AuditEntry).where(AuditEntry.action == AuditAction.access_denied)
    ).all()
    assert any((e.details or {}).get("signature") == "Eicar-Test-Signature" for e in entry)


def test_scanner_down_fails_closed(api: Api, ids: Ids, db: Session, scanner_down: None) -> None:
    res = _upload(api, ids, PDF)
    assert res.status_code == 503  # type: ignore[attr-defined]
    assert res.json()["detail"]["code"] == "SCANNER_UNAVAILABLE"  # type: ignore[attr-defined]
    assert db.scalars(select(Attachment)).all() == []


def test_scanner_down_fail_open_stores_unscanned(
    api: Api, ids: Ids, scanner_down: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "clamav_fail_open", True)
    res = _upload(api, ids, PDF)
    assert res.status_code == 201  # type: ignore[attr-defined]
    assert res.json()["scan_status"] == "skipped"  # type: ignore[attr-defined]


def test_scanner_error_reply_counts_as_unavailable(api: Api, ids: Ids, clamd: list[bytes]) -> None:
    res = _upload(api, ids, PDF + b"BROKEN")
    assert res.status_code == 503  # type: ignore[attr-defined]


def test_import_files_are_scanned_before_parsing(api: Api, ids: Ids, clamd: list[bytes]) -> None:
    c = api.as_("noura.qahtani")
    pid = ids.project("ANIA-EXP")
    bad = b"work_date,contractor\n" + EICAR
    res = c.post(f"{API}/projects/{pid}/workforce-imports", files={"file": ("r.csv", bad)})
    assert res.status_code == 422 and res.json()["detail"]["code"] == "FILE_INFECTED"
    heat = c.post(f"{API}/projects/{pid}/wbgt-imports", files={"file": ("w.csv", bad, "text/csv")})
    assert heat.status_code in (403, 404, 422)
    if heat.status_code == 422:
        assert heat.json()["detail"]["code"] == "FILE_INFECTED"


def test_base64_signature_uploads_are_scanned(clamd: list[bytes]) -> None:
    assert scanner.ensure_clean(PDF, "sig.png") == ScanStatus.clean
    with pytest.raises(Exception) as exc:
        scanner.ensure_clean(EICAR, "sig.png")
    assert getattr(exc.value, "code", None) == "FILE_INFECTED"
