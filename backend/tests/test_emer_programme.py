"""6c-emergency-drills §9 ACs 30-35 (drill programme, DP-1…DP-6)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.emergency_enums import (
    AnnouncementRequirement,
    DrillShift,
    DrillStatus,
    DrillType,
    LineSource,
    ProgrammeScope,
    ShiftRequirement,
)
from app.models import Drill
from app.services.emergency import programme as pg
from tests.emer_helpers import notified, project, site, team, tick

pytestmark = pytest.mark.usefixtures("emergency_seed", "clock")
SR, AR = ShiftRequirement, AnnouncementRequirement


def lines(db: Session, pcode: str, as_of: date) -> list[pg.Line]:
    return pg.lines(db, project(db, pcode).id, as_of)


def evac(ls: list[pg.Line], sid: uuid.UUID, sr: SR = SR.any, ar: AR = AR.any,
         src: LineSource = LineSource.minimum) -> pg.Line:  # fmt: skip
    (ln,) = [x for x in ls if x.drill_type == DrillType.evacuation_full and x.site_id == sid
             and x.shift_req == sr and x.ann_req == ar and x.source == src]  # fmt: skip
    return ln


def test_AC30_ed5_s_land(db: Session) -> None:
    land = site(db, "S-LAND").id
    ls = lines(db, "ANIA-EXP", date(2026, 10, 6))
    ln = evac(ls, land)
    sept = [i for i in ln.items if i.due == date(2026, 9, 17)]
    assert sept and sept[0].met and sept[0].drill is not None
    assert sept[0].drill.drill_no == "DRL-ANIA-EXP-2026-031"
    assert ln.due_by == date(2027, 3, 16)
    rep = evac(ls, land, src=LineSource.repeat)
    assert rep.due_by == date(2026, 10, 17) and rep.src is not None
    assert rep.src.drill_no == "DRL-ANIA-EXP-2026-031"


def test_AC31_ed4_night_late(db: Session) -> None:
    ln = evac(lines(db, "ANIA-EXP", date(2026, 10, 6)), site(db, "S-AIR").id, sr=SR.night)
    (item,) = [i for i in ln.items if i.due == date(2026, 9, 20)]
    assert not item.met and item.drill is not None
    assert item.drill.drill_no == "DRL-ANIA-EXP-2026-034"
    assert ln.due_by == date(2027, 9, 23)


def test_AC32_satisfies() -> None:
    sid = uuid.uuid4()
    x = Drill(drill_type=DrillType.evacuation_full, site_id=sid, shift=DrillShift.night,
              announced=False, status=DrillStatus.evaluated)  # fmt: skip
    mk = lambda sr, ar: pg.Line(DrillType.evacuation_full, ProgrammeScope.site, sid, None, sr, ar,  # noqa: E731
                                6, LineSource.minimum)  # fmt: skip
    for sr, ar in ((SR.any, AR.any), (SR.night, AR.any), (SR.any, AR.unannounced)):
        assert pg.satisfies(x, mk(sr, ar))
    x.drill_type = DrillType.evacuation_partial
    assert not any(pg.satisfies(x, mk(sr, ar)) for sr in SR for ar in AR)


def test_AC33_new_site_first_due() -> None:
    ln = pg.Line(DrillType.evacuation_full, ProgrammeScope.site, uuid.uuid4(), None, SR.any,
                 AR.any, 6, LineSource.minimum, start=date(2026, 10, 10))  # fmt: skip
    pg._schedule(ln, [], date(2026, 10, 10), timedelta(days=30))
    assert ln.due_by == date(2026, 11, 9)


def test_AC34_due_alerts(db: Session) -> None:
    """RT-ANIA-CSE-01's cse_rescue line is due 2026-10-19 (ED7): steps 09-19, 10-05, 10-12,
    10-19 to Noura, the site engineers and the lead's Contractor HSE Rep; overdue from 10-20."""
    pid = project(db, "ANIA-EXP").id
    tm = team(db, "RT-ANIA-CSE-01")
    (ln,) = [x for x in lines(db, "ANIA-EXP", date(2026, 10, 6)) if x.team_id == tm.id]
    assert ln.due_by == date(2026, 10, 19)
    from app.services.cert.alerts import scheduled_steps

    assert scheduled_steps(ln.due_by, (30, 14, 7, 0)) == [
        date(2026, 9, 19), date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19)]  # fmt: skip
    t = tick(2026, 10, 12, 7, 5)
    assert pg.due_alerts(db, pid, date(2026, 10, 12)) > 0
    db.commit()
    got = notified(db, "emergency_drill_due", t)
    assert {"noura.qahtani", "fahad.mutairi", "ahmed.zahrani"} <= set(got), got
    assert any("RT-ANIA-CSE-01" in x for x in got["noura.qahtani"])
    (late,) = [x for x in lines(db, "ANIA-EXP", date(2026, 10, 20)) if x.team_id == tm.id]
    assert late.status.value == "overdue"


def test_AC35_events_satisfy_nothing(db: Session) -> None:
    """DP-6: lines are built from drills only; the seeded S-LAND event EMV-003 changes nothing."""
    from app.models import EmergencyEvent

    before = [(x.key, x.due_by) for x in lines(db, "ANIA-EXP", date(2026, 10, 6))]
    for ev in db.query(EmergencyEvent).all():
        db.delete(ev)
    db.flush()
    assert [(x.key, x.due_by) for x in lines(db, "ANIA-EXP", date(2026, 10, 6))] == before
