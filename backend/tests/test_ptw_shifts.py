"""3-ptw §9 AC82-AC87 (midday ban, shifts, handover, suspension, closure, expiry), Y5, Y6."""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app import ptw_jobs
from app.core.clock import set_now
from app.core.ptw_enums import PermitStatus, StatusReason
from app.schemas.permits import (
    ExemptionDecision,
    HandoverAcceptInput,
    HandoverCreate,
    StartInput,
    SuspendInput,
)
from app.services.ptw import fieldwork, lifecycle
from tests.conftest import Api, Ids
from tests.ptw_helpers import (
    SEED_AT,
    activate,
    approve,
    at,
    exemption,
    expect,
    fx,
    permit,
    resume,
    win,
    world,
)  # fmt: skip

S = PermitStatus
DAYS = win("06:00", "12:00")[0]["weekdays"]
SPLIT = [
    {"start_local": "06:00", "end_local": "12:00", "weekdays": DAYS},
    {"start_local": "15:00", "end_local": "18:00", "weekdays": DAYS},
]
HEAT = "Shaded rest area, 15-minute breaks each hour, chilled water and buddy checks."


@pytest.fixture
def n(ptw_seed: None, db: Session) -> Iterator[Any]:
    set_now(SEED_AT)
    yield world(db)
    set_now(None)


def _panel(api: Api, ids: Ids, who: str = "faisal.harbi") -> dict[str, int]:
    res = api.as_(who).get(
        "/api/v1/dashboard/action-panel", params={"project_id": ids.project("ANIA-EXP")}
    )
    assert res.status_code == 200, res.text
    return {e["key"]: e["count"] for e in res.json()["items"]}


def _day(n: Any, d: int, m: int = 9, **kw: Any) -> Any:
    return fx(n, zones=("Z-LAY1",), vf=at(2026, m, d, 6), vt=at(2026, m, d, 18), **kw)


def test_AC82_Y5_midday_ban(n: Any) -> None:
    set_now(at(2026, 9, 9, 10))
    expect("MIDDAY_BAN_WINDOW", lambda: _day(n, 10, windows=win("06:00", "18:00")), 422)
    p = _day(n, 10, windows=SPLIT)
    set_now(at(2026, 6, 14, 10))
    expect("MIDDAY_BAN_WINDOW", lambda: _day(n, 15, m=6, windows=win("06:00", "18:00")), 422)
    set_now(at(2026, 9, 15, 10))
    _day(n, 16, windows=win("06:00", "18:00"))
    set_now(at(2026, 9, 10, 6, 0))
    activate(n, p, hse=None)
    assert p.status == S.active
    ptw_jobs.ptw_minute(n.db, at(2026, 9, 10, 11, 45))
    n.db.refresh(p)
    assert p.status == S.active
    ptw_jobs.ptw_minute(n.db, at(2026, 9, 10, 12, 0))
    n.db.refresh(p)
    assert (p.status, p.status_reason) == (S.suspended, StatusReason.midday_ban)
    expect(
        "MIDDAY_BAN",
        lambda: resume(n, p, "khalid.otaibi", "ramesh.kumar", at(2026, 9, 10, 14, 59), cause=None),
        422,
    )
    shifts = len(lifecycle.shifts_of(n.db, p.id))
    resume(n, p, "khalid.otaibi", "ramesh.kumar", at(2026, 9, 10, 15, 0), cause=None)
    assert p.status == S.active and len(lifecycle.shifts_of(n.db, p.id)) == shifts + 1


def test_AC83_midday_exemption(n: Any, api: Api, ids: Ids) -> None:
    set_now(at(2026, 9, 9, 10))
    p = _day(n, 10, windows=SPLIT)
    e = exemption(
        n,
        p,
        "midday_ban",
        who="ramesh.kumar",
        midday_reason="emergency_repair",
        heat_controls_text=HEAT,
        valid_from="2026-09-10",
        valid_to="2026-09-10",
    )
    expect(
        "FORBIDDEN",
        lambda: fieldwork.decide_exemption(
            n.db, n.p("noura.qahtani"), e.id, ExemptionDecision(decision="granted")
        ),
        403,
    )
    fieldwork.decide_exemption(
        n.db, n.p("faisal.harbi"), e.id, ExemptionDecision(decision="granted")
    )
    from app.schemas.permits import PermitUpdate
    from app.services.ptw import permits

    permits.update(
        n.db,
        n.p("ramesh.kumar"),
        p.id,
        PermitUpdate.model_validate({"windows": win("06:00", "18:00")}),
    )
    set_now(at(2026, 9, 10, 6, 0))
    activate(n, p, hse=None)
    ptw_jobs.ptw_minute(n.db, at(2026, 9, 10, 12, 0))
    n.db.refresh(p)
    assert p.status == S.active
    n.db.commit()
    set_now(at(2026, 9, 10, 12, 5))
    assert _panel(api, ids).get("midday_exemptions_active", 0) >= 1


def test_AC84_Y6_shift_planned_end_and_lapse(n: Any) -> None:
    p412 = permit(n.db, "PTW-ANIA-EXP-2026-0412")
    assert lifecycle.current_shift(n.db, p412).planned_end_at == at(2026, 10, 6, 19, 0)
    p408 = permit(n.db, "PTW-ANIA-EXP-2026-0408")
    first = lifecycle.shifts_of(n.db, p408.id)[-1]
    assert (first.started_at, first.planned_end_at) == (
        at(2026, 10, 5, 23, 5),
        at(2026, 10, 6, 5, 0),
    )
    expect(
        "OUTSIDE_WINDOW",
        lambda: n.revalidate(
            p408, "khalid.otaibi", "sanjay.verma", at(2026, 10, 6, 22, 40), ambient="29.0"
        ),
    )
    ptw_jobs.ptw_minute(n.db, at(2026, 10, 6, 19, 0))
    n.db.refresh(p412)
    assert (p412.status, p412.status_reason) == (S.suspended, StatusReason.shift_lapsed)


def _day24(n: Any) -> Any:
    set_now(at(2026, 10, 7, 5, 55))
    p = fx(
        n,
        zones=("Z-LAY1",),
        x="20.0",
        y="20.0",
        vf=at(2026, 10, 7, 6),
        vt=at(2026, 10, 8, 6),
        windows=win("06:00", "06:00"),
    )
    set_now(at(2026, 10, 7, 6, 0))
    activate(n, p, hse=None)
    return p


def _handover(n: Any, p: Any, t: Any) -> Any:
    set_now(t)
    return fieldwork.create_handover(
        n.db,
        n.p("ramesh.kumar"),
        p.id,
        HandoverCreate.model_validate(
            {
                "to_receiver_user_id": str(n.ctx.uid("ramesh.kumar")),
                "to_issuer_user_id": str(n.ctx.uid("khalid.otaibi")),
                "notes_en": "Night shift continues the same scope.",
            }
        ),
    )


def test_AC84_Y6c_handover(n: Any) -> None:
    p = _day24(n)
    assert lifecycle.current_shift(n.db, p).planned_end_at == at(2026, 10, 7, 18, 0)
    h = _handover(n, p, at(2026, 10, 7, 17, 30))
    set_now(at(2026, 10, 7, 17, 50))
    body = HandoverAcceptInput.model_validate(
        {
            "crew_present": n.crew_present(p),
            "ambient_temp_c": "33.0",
            "cosign": n.cosign("khalid.otaibi"),
        }
    )
    fieldwork.accept_handover(n.db, n.p("ramesh.kumar"), h.id, body)
    sh = lifecycle.current_shift(n.db, p)
    assert (sh.started_at, sh.planned_end_at) == (at(2026, 10, 7, 17, 50), at(2026, 10, 8, 5, 50))


def test_AC84_Y6c_handover_lapses(n: Any) -> None:
    p = _day24(n)
    _handover(n, p, at(2026, 10, 7, 17, 30))
    ptw_jobs.ptw_minute(n.db, at(2026, 10, 7, 18, 0))
    n.db.refresh(p)
    assert (p.status, p.status_reason) == (S.suspended, StatusReason.shift_lapsed)


def test_AC85_crew_not_briefed(n: Any) -> None:
    p = fx(n, zones=("Z-LAY1",), x="30.0", y="30.0")
    activate(n, p, hse=None, start=False)
    crew = [{**c, "briefed": False} for c in n.crew_present(p)]
    expect(
        "CREW_NOT_BRIEFED",
        lambda: lifecycle.start(
            n.db,
            n.p("ramesh.kumar"),
            p.id,
            StartInput.model_validate({"crew_present": crew, "ambient_temp_c": "30.0"}),
        ),
        422,
    )


def test_AC86_stop_work(n: Any) -> None:
    p = permit(n.db, "PTW-ANIA-EXP-2026-0412")
    lifecycle.suspend(
        n.db,
        n.p("ahmed.zahrani"),
        p.id,
        SuspendInput(reason="stop_work", detail="Unsafe scaffold access at gridline B4"),
    )
    n.db.refresh(p)
    assert (p.status, p.status_reason) == (S.suspended, StatusReason.stop_work)
    expect(
        "FORBIDDEN",
        lambda: resume(n, p, "ahmed.zahrani", "ramesh.kumar", at(2026, 10, 6, 10, 20)),
        403,
    )
    resume(
        n,
        p,
        "khalid.otaibi",
        "ramesh.kumar",
        at(2026, 10, 6, 10, 30),
        cause="Scaffold access corrected and inspected by the supervisor.",
    )
    assert p.status == S.active


def test_AC87_expiry_and_post_expiry_check(n: Any, api: Api, ids: Ids) -> None:
    p = fx(n, zones=("Z-LAY1",), x="40.0", y="40.0", vt=at(2026, 10, 6, 12, 0))
    activate(n, p, hse=None)
    before = _panel_count(n, api, ids)
    k_before = _k69(api, ids)
    ptw_jobs.ptw_minute(n.db, at(2026, 10, 6, 12, 1))
    n.db.refresh(p)
    assert p.status == S.expired and p.post_expiry_check is None
    n.db.commit()
    set_now(at(2026, 10, 6, 12, 5))
    assert _panel(api, ids).get("post_expiry_checks_pending", 0) == before + 1
    k_after = _k69(api, ids)
    assert (k_after[0], k_after[1]) == (k_before[0], k_before[1] + 1), (k_before, k_after)
    _ = approve


def _k69(api: Api, ids: Ids) -> tuple[float, float]:
    res = api.as_("faisal.harbi").get(
        "/api/v1/kpi/metrics/K-69",
        params={
            "project_id": ids.project("ANIA-EXP"),
            "period": "month",
            "anchor": "2026-10-01",
            "as_of": "2026-10-31",
        },
    )
    assert res.status_code == 200, res.text
    k = res.json()["kpi"]
    return float(k.get("numerator") or 0), float(k.get("denominator") or 0)


def _panel_count(n: Any, api: Api, ids: Ids) -> int:
    n.db.commit()
    return _panel(api, ids).get("post_expiry_checks_pending", 0)
