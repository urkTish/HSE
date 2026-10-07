"""API builders shared by Phase 2 tests."""

import struct
from typing import Any

from fastapi.testclient import TestClient

from tests.access_helpers import API


def png(w: int = 400, h: int = 400) -> bytes:
    """A PNG header with the given IHDR size (enough for the photo checks)."""
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", w, h)
        + (b"\x08\x02\x00\x00\x00" + b"\x00" * 64)
    )


PDF = b"%PDF-1.4\n% test id copy\n"


def upload(c: TestClient, owner_type: str, owner_id: Any, name: str, content: bytes) -> Any:
    return c.post(
        f"{API}/attachments",
        data={"owner_type": owner_type, "owner_id": str(owner_id)},
        files={"file": (name, content)},
    )


def transition(c: TestClient, app_id: Any, to: str, **extra: Any) -> Any:
    return c.post(f"{API}/pass-applications/{app_id}/transitions", json={"to_status": to, **extra})
