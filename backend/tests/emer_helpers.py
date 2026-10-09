"""Helpers for Phase 6c tests (6c-emergency-drills Appendix A world, clock 2026-10-06 10:00 Riyadh).
Tests use the ``emergency_seed`` fixture (Phase 0-6b template + the 6c seed, cloned per test) and
``clock``. Service calls take a Principal from ``P(db, "noura.qahtani")``."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AssemblyPoint,
    Drill,
    EmergencyAsset,
    EmergencyEvent,
    Erp,
    Muster,
    RescueTeam,
    Site,
)
from app.services.emergency import common as ec
from tests.cert_helpers import API, P, expect, project, worker
from tests.heat_helpers import eng, err, local, notified, tick, uid, zone
from tests.train_helpers import kpi

__all__ = [
    "API",
    "P",
    "ap",
    "asset",
    "drill",
    "eng",
    "erp",
    "err",
    "event",
    "expect",
    "kpi",
    "local",
    "muster_of",
    "notified",
    "project",
    "set_cfg",
    "site",
    "team",
    "tick",
    "uid",
    "worker",
    "zone",
]


def _one(db: Session, model: Any, col: Any, key: str) -> Any:
    x = db.scalar(select(model).where(col == key))
    assert x is not None, key
    return x


def site(db: Session, code: str) -> Site:
    return _one(db, Site, Site.code, code)  # type: ignore[no-any-return]


def ap(db: Session, code: str) -> AssemblyPoint:
    return _one(db, AssemblyPoint, AssemblyPoint.ap_code, code)  # type: ignore[no-any-return]


def asset(db: Session, tag: str) -> EmergencyAsset:
    return _one(db, EmergencyAsset, EmergencyAsset.asset_tag, tag)  # type: ignore[no-any-return]


def drill(db: Session, no: str) -> Drill:
    return _one(db, Drill, Drill.drill_no, no)  # type: ignore[no-any-return]


def event(db: Session, no: str) -> EmergencyEvent:
    return _one(db, EmergencyEvent, EmergencyEvent.event_no, no)  # type: ignore[no-any-return]


def team(db: Session, code: str) -> RescueTeam:
    return _one(db, RescueTeam, RescueTeam.team_code, code)  # type: ignore[no-any-return]


def erp(db: Session, no: str) -> Erp:
    return _one(db, Erp, Erp.erp_no, no)  # type: ignore[no-any-return]


def muster_of(db: Session, d: Drill | EmergencyEvent) -> Muster:
    assert d.muster_id is not None
    m = db.get(Muster, d.muster_id)
    assert m is not None
    return m


def set_cfg(db: Session, pcode: str, **values: Any) -> None:
    """Write 6c settings directly (bypassing ER-9) and clear the settings cache."""
    row = ec.settings_row(db, project(db, pcode).id)
    row.values = {**(row.values or {}), **values}
    db.commit()
    ec.clear_cache(db)
