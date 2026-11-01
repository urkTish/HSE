"""Helpers of the Q3 tests: look-ups on the RUH-CCH set-up, CSV builders and API shortcuts."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project, Zone
from app.models.quality import QCustomer, QMteItem
from app.models.quality.q3 import QMonitoringPoint, QProduct
from app.services.quality.q3.checklists import TEMPLATES

API = "/api/v1"
RIYADH = ZoneInfo("Asia/Riyadh")
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def ok(res: Any, code: int = 200) -> Any:
    assert res.status_code == code, res.text
    return res.json()


def err(res: Any, status: int, code: str) -> dict[str, Any]:
    assert res.status_code == status, res.text
    d = res.json()["detail"]
    assert d["code"] == code, d
    return d


def L(d: date, hh: int = 0, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), RIYADH).astimezone(UTC)


class R:
    """RUH-CCH look-ups."""

    def __init__(self, db: Session) -> None:
        self.db = db
        p = db.scalar(select(Project).where(Project.code == "RUH-CCH"))
        assert p is not None
        self.project = p
        self.pid = str(p.id)

    def point(self, code: str) -> str:
        return str(self.db.scalar(select(QMonitoringPoint.id).where(QMonitoringPoint.code == code)))

    def zone(self, code: str) -> str:
        return str(self.db.scalar(select(Zone.id).where(Zone.code == code)))

    def product(self, sku: str) -> str:
        return str(self.db.scalar(select(QProduct.id).where(QProduct.sku == sku)))

    def customer(self, code: str) -> str:
        return str(
            self.db.scalar(
                select(QCustomer.id).where(
                    QCustomer.project_id == self.project.id, QCustomer.code == code
                )
            )
        )

    def mte(self, no: str) -> str:
        return str(
            self.db.scalar(
                select(QMteItem.id).where(
                    QMteItem.project_id == self.project.id, QMteItem.mte_no == no
                )
            )
        )


def readings_csv(
    rows: list[tuple[datetime, float]],
    tz: Any = RIYADH,
    fmt: str = "%Y-%m-%d %H:%M",
    channel: str | None = None,
) -> bytes:
    head = "time,temperature" + (",channel" if channel else "")
    out = [head]
    for t, v in rows:
        line = f"{t.astimezone(tz).strftime(fmt)},{v}"
        if channel:
            line += f",{channel}"
        out.append(line)
    return ("\n".join(out) + "\n").encode()


def import_readings(
    c: TestClient,
    pid: str,
    target_type: str,
    target_id: str,
    content: bytes,
    profile: str | None = None,
    name: str = "logger.csv",
) -> Any:
    data = {"kind": "readings", "target_type": target_type, "target_id": target_id}
    if profile:
        data["profile"] = profile
    return c.post(
        f"{API}/projects/{pid}/quality/imports",
        data=data,
        files={"file": (name, content, "text/csv")},
    )


def import_kind(
    c: TestClient,
    pid: str,
    kind: str,
    target_id: str,
    content: bytes,
    as_of: datetime | None = None,
) -> Any:
    data = {"kind": kind, "target_type": "site", "target_id": target_id}
    if as_of:
        data["as_of"] = as_of.isoformat()
    return c.post(
        f"{API}/projects/{pid}/quality/imports",
        data=data,
        files={"file": ("data.csv", content, "text/csv")},
    )


def series(start: datetime, values: list[float], step: int = 15) -> list[tuple[datetime, float]]:
    return [(start + timedelta(minutes=step * i), v) for i, v in enumerate(values)]


def answers(code: str, fail: tuple[int, ...] = ()) -> list[dict[str, Any]]:
    rows = TEMPLATES[code][3]
    out = []
    for n, _ in enumerate(rows, start=1):
        a: dict[str, Any] = {
            "item_code": f"{code}-{n:02d}",
            "answer": "non_compliant" if n in fail else "compliant",
        }
        if n in fail:
            a["note"] = "Found during the check, recorded for action."
        out.append(a)
    return out


def attach(c: TestClient, owner_type: str, owner_id: str, name: str = "evidence.pdf") -> str:
    res = c.post(
        f"{API}/attachments",
        data={"owner_type": owner_type, "owner_id": owner_id},
        files={"file": (name, PDF, "application/pdf")},
    )
    return str(ok(res, 201)["id"])
