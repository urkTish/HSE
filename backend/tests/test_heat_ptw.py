"""6b-heat-stress §9 ACs 20 (suspension part), 22-25, 27 (Phase 3 integration, §11.4)."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.core.heat_enums import ReadingSource
from app.core.ptw_enums import Exposure, PermitStatus
from app.models import Permit
from app.schemas.heat import ReadingComponents
from app.services.heat import common as hc
from app.services.heat import ptw as heat_ptw
from app.services.heat import readings
from tests.heat_helpers import instrument, local, point, project, tick
from tests.ptw_helpers import activate, approve, blocked, fx, win, world

pytestmark = pytest.mark.usefixtures("heat_seed", "clock")


def manual(db: Session, at: datetime, w: str, pt: str = "P-SLAND-M1") -> None:
    set_now(at)
    readings.make(db, point(db, pt), instrument(db, "HSM-ANIA-EXP-02"),
                  ReadingComponents(wbgt_entered_c=w), at, ReadingSource.manual)  # fmt: skip
    db.commit()


def lay1(n: object, **kw: object) -> Permit:
    return fx(n, site="S-LAND", zones=("Z-LAY1",), con="NAJD", types=("general",), **kw)  # type: ignore[arg-type]


def test_AC22_AC20_reading_required_and_stop(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    row = hc.settings_row(db, pid)  # controls period stretched to 10-31 (summer rules on 10-07)
    row.values = {**(row.values or {}), "heat_controls_period": {"start_mmdd": "05-01",
                                                                 "end_mmdd": "10-31"}}  # fmt: skip
    db.commit()
    hc.clear_cache(db)
    tick(2026, 10, 7, 7)
    n = world(db)
    p = lay1(n, windows=win("06:00", "12:00"), vt=local(2026, 10, 7, 12))
    assert p.exposure == Exposure.outdoor_direct_sun
    approve(n, p)
    codes = blocked(lambda: n.issue(p, "khalid.otaibi", "ramesh.kumar", now()))
    assert "WBGT_READING_REQUIRED" in codes
    manual(db, local(2026, 10, 7, 7, 0), "27.0")
    n.issue(p, "khalid.otaibi", "ramesh.kumar", now())
    n.start(p, "ramesh.kumar", now(), ambient="30.0")
    db.refresh(p)
    assert p.status == PermitStatus.active
    # R4 for the permit's workload (general → moderate: > 31.5) → Suspended heat_stress_stop
    manual(db, local(2026, 10, 7, 7, 30), "32.5")
    tick(2026, 10, 7, 7, 31)
    heat_ptw.refresh_outdoor(db, p.project_id, now())
    db.commit()
    db.refresh(p)
    assert p.status == PermitStatus.suspended
    assert getattr(p.status_reason, "value", p.status_reason) == "heat_stress_stop"


def test_AC23_AC24_AC27_outside_controls(db: Session) -> None:
    n = world(db)
    p = lay1(n)
    activate(n, p)  # 2026-10-06 10:00: outside the controls period, no WBGT blocker
    db.refresh(p)
    assert p.status == PermitStatus.active
    manual(db, local(2026, 10, 6, 10, 0), "28.0")
    set_now(local(2026, 10, 6, 10, 1))
    q = lay1(n, heat_clothing="vapour_barrier_coveralls")
    assert heat_ptw.workload(q).value == "moderate"
    approve(n, q)
    codes = blocked(lambda: n.issue(q, "khalid.otaibi", "ramesh.kumar", now()))
    assert "HEAT_STOP" in codes
    indoor = db.scalar(select(Permit).where(Permit.exposure == Exposure.indoor))
    assert indoor is not None and not heat_ptw.applies(db, indoor, now())
