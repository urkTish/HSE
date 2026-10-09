"""Helpers for Phase 6e tests (6e-environmental Appendix A world, clock 2026-10-06 10:00 Riyadh).
Tests use the ``env_seed`` fixture (Phase 0-6d template + the 6e seed, cloned per test) and
``clock``. Service calls take a Principal from ``P(db, "noura.qahtani")``."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EmergencyAsset,
    EnvExceedance,
    EnvPermit,
    EnvPoint,
    EnvProvider,
    WasteConsignment,
    WasteStorageArea,
)
from app.schemas.env import ConsignmentCreate
from app.services.env import common as ec
from tests.cert_helpers import API, P, expect, project
from tests.heat_helpers import eng, err, local, notified, tick, uid, zone
from tests.train_helpers import kpi

__all__ = [
    "API",
    "D",
    "P",
    "area",
    "con",
    "con_body",
    "eng",
    "err",
    "exd",
    "expect",
    "kit",
    "kpi",
    "kpis",
    "local",
    "notified",
    "permit",
    "point",
    "project",
    "prov",
    "tick",
    "uid",
    "zone",
]

D = Decimal


def prov(db: Session, code: str) -> EnvProvider:
    x = db.scalar(select(EnvProvider).where(EnvProvider.provider_code == code))
    assert x is not None, code
    return x


def permit(db: Session, ref: str) -> EnvPermit:
    x = db.scalar(select(EnvPermit).where(EnvPermit.reference_no == ref))
    assert x is not None, ref
    return x


def area(db: Session, code: str) -> WasteStorageArea:
    x = db.scalar(select(WasteStorageArea).where(WasteStorageArea.area_code == code))
    assert x is not None, code
    return x


def point(db: Session, code: str) -> EnvPoint:
    x = db.scalar(select(EnvPoint).where(EnvPoint.point_code == code))
    assert x is not None, code
    return x


def con(db: Session, no: str) -> WasteConsignment:
    x = db.scalar(select(WasteConsignment).where(WasteConsignment.consignment_no == no))
    assert x is not None, no
    return x


def exd(db: Session, no: str) -> EnvExceedance:
    x = db.scalar(select(EnvExceedance).where(EnvExceedance.exceedance_no == no))
    assert x is not None, no
    return x


def kit(db: Session, tag: str) -> EmergencyAsset:
    x = db.scalar(select(EmergencyAsset).where(EmergencyAsset.asset_tag == tag))
    assert x is not None, tag
    return x


def con_body(db: Session, stream: str = "inert_cd", **kw: Any) -> ConsignmentCreate:
    """A valid ANIA-EXP consignment from WSA-SLAND-01 (RAWABI → GREENHAUL → RECYCON)."""
    data: dict[str, Any] = {
        "stream_code": stream,
        "storage_area_id": area(db, "WSA-SLAND-01").id,
        "generator_engagement_id": eng(db, "ANIA-EXP", "RAWABI").id,
        "quantity": D("10.0"),
        "unit": "t",
        "transporter_id": prov(db, "GREENHAUL").id,
        "facility_provider_id": prov(db, "RECYCON").id,
        "facility_code": "RECYCON-1",
        "vehicle_plate": "7781 KSA",
        "driver_name": "Driver TEST",
        "dispatched_at": local(2026, 10, 6, 9, 30),
    }
    data.update(kw)
    return ConsignmentCreate.model_validate(data)


def kpis(
    c: TestClient, pid: Any, start: str = "2026-09-01", end: str = "2026-09-30", **params: Any
) -> dict[str, Any]:
    r = c.get(
        f"{API}/kpi/environmental",
        params={"project_id": str(pid), "period": "custom", "start": start, "end": end, **params},
    )
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def fresh(db: Session) -> None:
    """Drop the per-session 6e caches after direct row changes."""
    ec.clear_cache(db)
    for k in ("env_rseq", "env_ops"):
        db.info.pop(k, None)


def uuid4() -> uuid.UUID:
    return uuid.uuid4()


def day(y: int, m: int, d: int) -> date:
    return date(y, m, d)


def ts(y: int, m: int, d: int, h: int = 10, mi: int = 0) -> datetime:
    return local(y, m, d, h, mi)
