"""3-ptw §9 AC51-AC64 (hot work, confined space, work at height), Y4, Y10."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app import ptw_jobs
from app.core.clock import now, set_now
from app.core.ptw_enums import HazardousAreaClass, PermitStatus, StatusReason
from app.schemas.permits import (
    CloseInput,
    ClosureRequestInput,
    EndShiftInput,
    EntryLogInput,
    HandoverCreate,
    HotWorkEndInput,
    RequestInput,
    SectionsInput,
    StartInput,
    WindReadingInput,
)  # fmt: skip
from app.services.ptw import common, fieldwork, lifecycle
from app.services.ptw import facts as facts_mod
from tests.ptw_helpers import (
    GOOD_GAS,
    SEED_AT,
    activate,
    approve,
    at,
    blocked,
    cse_fx,
    cse_ready,
    exemption,
    expect,
    fx,
    gas_test,
    hw_fx,
    hw_section,
    permit,
    rd,
    wind,
    world,
)  # fmt: skip

S = PermitStatus
P412 = "PTW-ANIA-EXP-2026-0412"
P413 = "PTW-ANIA-EXP-2026-0413"
AIR = {
    "work_type": "airside_works",
    "fod_control_plan": True,
    "aircraft_proximity": "no_stand_in_zone",
}


@pytest.fixture
def n(ptw_seed: None, db: Session) -> Iterator[Any]:
    set_now(SEED_AT)
    yield world(db)
    set_now(None)


def _hw_end(n: Any, p: Any, t: Any) -> None:
    set_now(t)
    fieldwork.record_hot_work_end(n.db, n.p("ramesh.kumar"), p.id, HotWorkEndInput(ended_at=t))
    n.db.refresh(p)


def _close(n: Any, p: Any, receiver: str, issuer: str, t: Any) -> None:
    set_now(t)
    lifecycle.close(n.db, n.p(issuer), p.id, CloseInput(site_visit_confirmed=True))
    n.db.refresh(p)


# ---- hot work ------------------------------------------------------------------------------------


def test_AC51_Y4_fire_watch(n: Any) -> None:
    p = permit(n.db, P412)
    _hw_end(n, p, at(2026, 10, 6, 15, 20))
    assert lifecycle.fire_watch_until(p) == at(2026, 10, 6, 16, 20)
    set_now(at(2026, 10, 6, 16, 0))
    n.checklist(p, "ramesh.kumar", "closure")
    lifecycle.request_closure(
        n.db,
        n.p("ramesh.kumar"),
        p.id,
        ClosureRequestInput(work_status="complete", crew_withdrawn=True),
    )
    expect(
        "FIRE_WATCH_RUNNING",
        lambda: _close(n, p, "ramesh.kumar", "khalid.otaibi", at(2026, 10, 6, 16, 5)),
        422,
    )
    _close(n, p, "ramesh.kumar", "khalid.otaibi", at(2026, 10, 6, 16, 21))
    assert p.status == S.closed


def test_AC51_Y4_late_end_delays_expiry(n: Any) -> None:
    p = permit(n.db, P412)
    _hw_end(n, p, at(2026, 10, 6, 18, 30))
    assert lifecycle.fire_watch_until(p) == at(2026, 10, 6, 19, 30)
    assert "HOT_WORK_LATE" in [w["code"] for w in p.warnings]
    ptw_jobs.ptw_minute(n.db, at(2026, 10, 6, 19, 5))
    n.db.refresh(p)
    assert p.status != S.expired
    ptw_jobs.ptw_minute(n.db, at(2026, 10, 6, 19, 31))
    n.db.refresh(p)
    assert p.status == S.expired


def test_AC52_fire_impairment(n: Any) -> None:
    p = hw_fx(
        n,
        section=hw_section(
            fire_system_impairment=True, impairment_hours_24h="6.0", impairment_ref="IMP-TEST-01"
        ),
    )
    assert "FIRE_IMPAIRMENT_NOT_APPROVED" in blocked(lambda: approve(n, p, hse="noura.qahtani"))
    exemption(n, p, "fire_impairment")
    assert "FIRE_IMPAIRMENT_NOT_APPROVED" in blocked(
        lambda: n.approve_now(
            p, "ramesh.kumar", "fahad.mutairi", "khalid.otaibi", "noura.qahtani", now()
        )
    )
    n.sections(
        p,
        "ramesh.kumar",
        [
            hw_section(
                fire_system_impairment=True,
                impairment_hours_24h="6.0",
                impairment_ref="IMP-TEST-01",
                civil_defense_notified_at=(now() - timedelta(minutes=30)).isoformat(),
            )
        ],
    )
    n.approve_now(p, "ramesh.kumar", "fahad.mutairi", "khalid.otaibi", "noura.qahtani", now())
    n.issue(p, "khalid.otaibi", "ramesh.kumar", now())
    assert p.status == S.issued


def test_AC53_combustibles_and_extinguisher(n: Any) -> None:
    expect(
        "VALIDATION_ERROR",
        lambda: hw_fx(n, section=hw_section(combustibles_cleared_radius_m="8.0")),
        422,
    )
    expect(
        "VALIDATION_ERROR",
        lambda: hw_fx(
            n,
            section=hw_section(
                fire_extinguishers=[{"type": "co2_5kg", "count": 1, "distance_m": "12.0"}]
            ),
        ),
        422,
    )
    hw_fx(
        n,
        section=hw_section(
            combustibles_cleared_radius_m="8.0",
            combustibles_protected_method="Fire blankets over timber formwork",
        ),
    )


def test_AC54_hazardous_areas(n: Any) -> None:
    prof = common.profile(n.db, n.ctx.zones["Z-LAY1"])
    prof.hazardous_area_class = HazardousAreaClass.zone_1
    prof.hazardous_area_note = "Fixture fuel farm"
    n.db.flush()
    expect("HAZARDOUS_AREA_PROHIBITED", lambda: hw_fx(n), 422)
    p = hw_fx(
        n,
        zone="Z-APR-21",
        x=None,
        y=None,
        site="S-AIR",
        con="RAWABI",
        receiver="faris.anazi",
        area="omar.siddiqui",
        types=("hot_work", "airside_works"),
        extra_sections=[AIR],
        wap="WAP-ANIA-EXP-2026-0033",
        vt=at(2026, 10, 6, 12),
    )
    f = facts_mod.compute(n.db, p)
    assert p.high_risk and f.gas_required
    assert f.limits.lel_below == 1


def test_AC55_aircraft_proximity(n: Any) -> None:
    live = {**AIR, "aircraft_proximity": "live_stand_adjacent"}
    expect(
        "AIRCRAFT_PROXIMITY",
        lambda: hw_fx(
            n,
            zone="Z-APR-21",
            x=None,
            y=None,
            site="S-AIR",
            con="RAWABI",
            receiver="faris.anazi",
            area="omar.siddiqui",
            types=("hot_work", "airside_works"),
            extra_sections=[live],
            wap="WAP-ANIA-EXP-2026-0033",
            vt=at(2026, 10, 6, 12),
        ),
        422,
    )


def test_AC56_fire_watch_must_be_present(n: Any) -> None:
    p = hw_fx(n)
    activate(n, p, hse="noura.qahtani", start=False)
    crew = [
        c
        for c in n.crew_present(p)
        if c["worker_id"]
        != str(
            next(
                x.worker_id
                for x in lifecycle.evaluation.crew_lines(n.db, p.id)
                if x.crew_role.value == "fire_watch"
            )
        )
    ]
    body = StartInput.model_validate({"crew_present": crew, "ambient_temp_c": "30.0"})
    assert "ROLE_MISSING" in blocked(lambda: lifecycle.start(n.db, n.p("ramesh.kumar"), p.id, body))


# ---- confined space ------------------------------------------------------------------------------


def test_AC57_cse_rescue_plan_and_standby(n: Any) -> None:
    p = cse_fx(n)
    n.jsa(p, "faris.anazi", "khalid.otaibi", "noura.qahtani")
    err = expect(
        "DOCUMENT_MISSING",
        lambda: lifecycle.request(n.db, n.p("faris.anazi"), p.id, RequestInput()),
    )
    assert "rescue_plan" in str(err.meta) + err.message
    q = cse_fx(n, crew=[c for c in _cse_crew(n) if c["crew_role"] != "standby_person"])
    n.jsa(q, "faris.anazi", "khalid.otaibi", "noura.qahtani")
    n.ensure_docs(q, "faris.anazi")
    err = expect(
        "ROLE_MISSING", lambda: lifecycle.request(n.db, n.p("faris.anazi"), q.id, RequestInput())
    )
    assert "standby_person" in str(err.meta) + err.message


def _cse_crew(n: Any) -> list[dict[str, Any]]:
    bulk = n.bulk_worker("ANIA-EXP", "RAWABI", 2, site="S-LAND", zone="Z-PIERB")
    return [
        {
            "worker_id": str(n.w("WKR-000021")),
            "crew_role": "rescue_lead",
            "appointment_id": str(n.ctx.apts["APT-ANIA-EXP-0012"].id),
        },
        {"worker_id": str(bulk[0]), "crew_role": "standby_person"},
        {"worker_id": str(bulk[1]), "crew_role": "entrant"},
        {
            "worker_id": str(n.w("WKR-000018")),
            "crew_role": "gas_tester",
            "appointment_id": str(n.ctx.apts["APT-ANIA-EXP-0011"].id),
        },
    ]


def test_AC58_cse_points_required(n: Any) -> None:
    p = cse_fx(n)
    approve(n, p, receiver="faris.anazi")
    expect("CSE_POINTS_REQUIRED", lambda: gas_test(n, p, now(), "pre_entry", GOOD_GAS[:2]), 422)


def test_AC59_entrants_inside(n: Any) -> None:
    p = permit(n.db, P413)
    n.checklist(p, "faris.anazi", "closure")
    expect(
        "ENTRANTS_INSIDE",
        lambda: lifecycle.request_closure(
            n.db,
            n.p("faris.anazi"),
            p.id,
            ClosureRequestInput(work_status="complete", crew_withdrawn=True),
        ),
        422,
    )
    expect(
        "ENTRANTS_INSIDE",
        lambda: lifecycle.end_shift(n.db, n.p("faris.anazi"), p.id, EndShiftInput()),
        422,
    )
    set_now(at(2026, 10, 6, 18, 10))
    expect(
        "ENTRANTS_INSIDE",
        lambda: fieldwork.create_handover(
            n.db,
            n.p("faris.anazi"),
            p.id,
            HandoverCreate.model_validate(
                {
                    "to_receiver_user_id": str(n.ctx.uid("faris.anazi")),
                    "to_issuer_user_id": str(n.ctx.uid("khalid.otaibi")),
                    "notes_en": "Fixture handover notes for the night shift.",
                }
            ),
        ),
        422,
    )


def test_AC60_heat_controls(n: Any) -> None:
    p = cse_fx(n, x="10.0", y="300.0")
    approve(n, p, receiver="faris.anazi")
    gas_test(n, p, now(), "pre_entry", GOOD_GAS, temp="36.0")
    n.issue(p, "khalid.otaibi", "faris.anazi", now())
    expect("HEAT_CONTROLS_REQUIRED", lambda: n.start(p, "faris.anazi", now(), ambient="34.0"), 422)


def test_AC61_handover_limit(n: Any) -> None:
    from app.core.ptw_enums import HandoverStatus
    from app.models import PermitHandover

    p = permit(n.db, P413)
    sh = lifecycle.current_shift(n.db, p)
    n.db.add(
        PermitHandover(
            permit_id=p.id,
            from_shift_id=sh.id,
            from_receiver_user_id=p.receiver_user_id,
            to_receiver_user_id=p.receiver_user_id,
            to_issuer_user_id=p.issuer_user_id,
            deadline_at=sh.planned_end_at,
            status=HandoverStatus.accepted,
            notes_en="Earlier handover (fixture)",
            initiated_at=at(2026, 10, 6, 7, 0),
        )
    )
    n.db.flush()
    set_now(at(2026, 10, 6, 18, 10))
    expect(
        "HANDOVER_LIMIT",
        lambda: fieldwork.create_handover(
            n.db,
            n.p("faris.anazi"),
            p.id,
            HandoverCreate.model_validate(
                {
                    "to_receiver_user_id": str(n.ctx.uid("faris.anazi")),
                    "to_issuer_user_id": str(n.ctx.uid("khalid.otaibi")),
                    "notes_en": "Second handover attempt.",
                }
            ),
        ),
        422,
    )
    _ = EntryLogInput


# ---- work at height ------------------------------------------------------------------------------

WAH = {
    "work_type": "work_at_height", "max_fall_height_m": "8.00", "access_method": ["mewp"], "fall_protection": "arrest_lanyard",
    "anchor_rating_kn": "22.2", "lanyard_length_m": "1.80", "available_clearance_m": "4.00", "drop_zone_controlled": True, "tool_tethering": True,
}  # fmt: skip


def test_AC62_Y10_fall_clearance(n: Any) -> None:
    p = fx(n, zones=("Z-LAY1",), types=("work_at_height",), sections=[WAH])
    assert "FALL_CLEARANCE_INSUFFICIENT" in [
        b["code"] for b in lifecycle.evaluation.evaluate(n.db, p).blockers
    ]
    n.sections(
        p,
        "ramesh.kumar",
        [
            {
                **WAH,
                "fall_protection": "arrest_srl",
                "lanyard_length_m": None,
                "srl_required_clearance_m": "2.40",
            }
        ],
    )
    assert "FALL_CLEARANCE_INSUFFICIENT" not in [
        b["code"] for b in lifecycle.evaluation.evaluate(n.db, p).blockers
    ]


def test_AC63_srl_needs_rescue_plan(n: Any) -> None:
    p = fx(
        n,
        zones=("Z-LAY1",),
        types=("work_at_height",),
        sections=[
            {
                **WAH,
                "fall_protection": "arrest_srl",
                "lanyard_length_m": None,
                "srl_required_clearance_m": "2.40",
            }
        ],
    )
    assert p.high_risk
    n.jsa(p, "ramesh.kumar", "khalid.otaibi", "noura.qahtani")
    err = expect(
        "DOCUMENT_MISSING",
        lambda: lifecycle.request(n.db, n.p("ramesh.kumar"), p.id, RequestInput()),
        422,
    )
    assert "rescue_plan" in str(err.meta) + err.message


def test_AC64_outdoor_wah_wind(n: Any) -> None:
    sec = {
        **WAH,
        "fall_protection": "collective_only",
        "lanyard_length_m": None,
        "available_clearance_m": None,
        "access_method": ["mewp"],
    }
    p = fx(n, zones=("Z-LAY1",), types=("work_at_height",), sections=[sec])
    activate(n, p, hse="noura.qahtani", wind=wind("6.0"))
    assert p.status == S.active
    fieldwork.record_wind(
        n.db, n.p("ramesh.kumar"), p.id, WindReadingInput.model_validate(wind("11.2"))
    )
    n.db.refresh(p)
    assert (p.status, p.status_reason) == (S.suspended, StatusReason.weather)
    _ = SectionsInput, cse_ready, rd
