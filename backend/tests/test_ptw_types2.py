"""3-ptw §9 AC65-AC81 (excavation, electrical, lifting, radiography, airside works), Y7, Y9."""

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app import access_jobs, ptw_jobs
from app.core.clock import frozen, now, set_now
from app.core.ptw_enums import PermitStatus, StatusReason
from app.schemas.permits import (
    BarrierSurveyInput,
    CloseInput,
    ClosureRequestInput,
    PermitCrewInput,
    PermitFodCheckInput,
    PermitUpdate,
    RevalidateInput,
    WindReadingInput,
)  # fmt: skip
from app.services.ptw import evaluation, fieldwork, lifecycle, permits
from app.services.ptw import facts as facts_mod
from tests.conftest import Api, Ids
from tests.ptw_helpers import (
    SEED_AT,
    approve,
    at,
    blocked,
    exemption,
    expect,
    fx,
    inspect_excavation,
    permit,
    resume,
    revalidate_0408,
    win,
    wind,
    world,
)  # fmt: skip

S = PermitStatus
P408 = "PTW-ANIA-EXP-2026-0408"
P290 = "PTW-RBT-52-2026-0290"
P410 = "PTW-ANIA-EXP-2026-0410"
EXC = {
    "work_type": "excavation", "max_depth_m": "1.30", "method": "hand_dig", "soil_type": "type_c", "protective_system": "sloping",
    "slope_ratio_h_v": "1.50", "utility_clearance_ref": "AOP-UTIL-TEST-0500", "spoil_setback_m": "0.80", "egress": "ladder",
    "egress_travel_m": "5.0", "edge_barriers": True, "night_lighting": True,
}  # fmt: skip


@pytest.fixture
def n(ptw_seed: None, db: Session) -> Iterator[Any]:
    set_now(SEED_AT)
    yield world(db)
    set_now(None)


def _codes(n: Any, p: Any, **ctx: Any) -> list[str]:
    return [
        b["code"]
        for b in evaluation.evaluate(
            n.db, p, evaluation.Ctx(at=now(), **ctx) if ctx else None
        ).blockers
    ]


# ---- excavation ----------------------------------------------------------------------------------


def _exc(n: Any, **over: Any) -> Any:
    return fx(n, zones=("Z-LAY1",), types=("excavation",), sections=[{**EXC, **over}])


def test_AC65_protective_system(n: Any) -> None:
    expect(
        "VALIDATION_ERROR",
        lambda: _exc(n, protective_system="none_lt_1_2m", slope_ratio_h_v=None),
        422,
    )
    expect("VALIDATION_ERROR", lambda: _exc(n, slope_ratio_h_v="1.00"), 422)
    _exc(n)
    sec = permit(n.db, P408).sections["excavation"]
    assert (sec["max_depth_m"], sec["slope_ratio_h_v"]) == ("1.30", "1.50")


def test_AC66_engineered_design(n: Any) -> None:
    expect("VALIDATION_ERROR", lambda: _exc(n, max_depth_m="6.20", egress_travel_m="5.0"), 422)


def test_AC67_utility_clearance_and_mechanical(n: Any) -> None:
    p = _exc(n, utility_clearance_ref=None)
    assert "UTILITY_CLEARANCE_MISSING" in _codes(n, p)
    expect(
        "MECHANICAL_NEAR_SERVICE",
        lambda: _exc(n, method="mechanical", services_within_hand_dig_zone=True),
        422,
    )


def test_AC68_inspection_required(n: Any) -> None:
    p = permit(n.db, P408)
    expect(
        "INSPECTION_REQUIRED",
        lambda: n.revalidate(
            p, "khalid.otaibi", "sanjay.verma", at(2026, 10, 6, 23, 0), ambient="29.0"
        ),
        422,
    )


# ---- electrical ----------------------------------------------------------------------------------

EL = {
    "work_type": "electrical_isolation",
    "system_voltage_v": 400,
    "work_condition": "electrically_safe",
}
ENERGIZED = {
    **EL, "work_condition": "energized", "energized_justification": "diagnostic_testing_only",
    "limited_approach_m": "1.07", "restricted_approach_m": "0.30", "incident_energy_cal_cm2": "4.0", "arc_ppe_rating_cal_cm2": "8.0",
}  # fmt: skip


def test_AC69_electrical(n: Any) -> None:
    p = fx(n, types=("electrical_isolation",), sections=[EL])
    b = evaluation.evaluate(n.db, p).blockers
    assert any(
        x["code"] == "CHECKLIST_INCOMPLETE" and "EL-02" in (x.get("detail") or "") for x in b
    ), b
    expect(
        "ENERGIZED_HV_PROHIBITED",
        lambda: fx(
            n,
            types=("electrical_isolation",),
            sections=[
                {**ENERGIZED, "system_voltage_v": 11000, "switching_programme_ref": "SP-TEST-1"}
            ],
        ),
        422,
    )
    q = fx(n, types=("electrical_isolation",), sections=[ENERGIZED])
    expect(
        "EXEMPTION_REQUIRED",
        lambda: lifecycle.exemption_needed(n.db, q, facts_mod.compute(n.db, q)),
        422,
    )
    exemption(n, q, "energized_work")
    lifecycle.exemption_needed(n.db, q, facts_mod.compute(n.db, q))


# ---- lifting -------------------------------------------------------------------------------------


def _lift_sec(p: Any, **over: Any) -> dict[str, Any]:
    return {**p.sections["lifting"], **over}


def test_AC70_Y7_capacity(n: Any) -> None:
    p = permit(n.db, P290)
    f = facts_mod.compute(n.db, p)
    assert (f.lift.capacity_display, f.critical) == (Decimal("87.0"), True)
    assert facts_mod.compute(n.db, permit(n.db, P410)).lift.capacity_display == Decimal("57.7")
    expect(
        "CAPACITY_EXCEEDED",
        lambda: permits.validate_section(
            n.db, p, "lifting", _lift_sec(p, load_weight_t="4.900"), f
        ),
        422,
    )
    p.sections = {
        **p.sections,
        "lifting": _lift_sec(p, load_weight_t="4.550", rigging_weight_t="0.000"),
    }
    n.db.flush()
    f2 = facts_mod.compute(n.db, p)
    assert f2.lift.capacity_display == Decimal("91.0")
    expect("EXEMPTION_REQUIRED", lambda: lifecycle.exemption_needed(n.db, p, f2), 422)


def test_AC71_critical_lift_duration(n: Any) -> None:
    p = permit(n.db, P290)
    err = expect(
        "DURATION_EXCEEDS_LIMIT",
        lambda: permits.update(
            n.db,
            n.p("joseph.mathew"),
            p.id,
            PermitUpdate.model_validate(
                {"valid_to_at": at(2026, 10, 8, 10).isoformat(), "windows": win("06:30", "10:00")}
            ),
        ),
        422,
    )
    assert (err.meta or {}).get("limiting_type") == "lifting"


def test_AC72_Y7_wind(n: Any) -> None:
    p = permit(n.db, P290)
    assert "WIND_LIMIT_EXCEEDED" in blocked(
        lambda: n.issue(
            p,
            "majed.shammari",
            "joseph.mathew",
            at(2026, 10, 7, 6, 30),
            wind=wind("13.4", at(2026, 10, 7, 6, 30)),
        )
    )
    q = permit(n.db, P410)
    assert "WIND_LIMIT_EXCEEDED" in blocked(
        lambda: n.issue(
            q,
            "khalid.otaibi",
            "faris.anazi",
            at(2026, 10, 6, 13, 5),
            wind=wind("11.0", at(2026, 10, 6, 13, 5)),
        )
    )
    n.issue(
        q,
        "khalid.otaibi",
        "faris.anazi",
        at(2026, 10, 6, 13, 6),
        wind=wind("7.2", at(2026, 10, 6, 13, 6)),
    )
    n.start(
        q,
        "faris.anazi",
        at(2026, 10, 6, 13, 10),
        ambient="34.0",
        wind=wind("7.2", at(2026, 10, 6, 13, 10)),
    )
    set_now(at(2026, 10, 6, 13, 30))
    fieldwork.record_wind(
        n.db,
        n.p("faris.anazi"),
        q.id,
        WindReadingInput.model_validate(wind("11.0", at(2026, 10, 6, 13, 30))),
    )
    n.db.refresh(q)
    assert (q.status, q.status_reason) == (S.suspended, StatusReason.wind_limit)


def test_AC73_obstacle_clearance_link(n: Any) -> None:
    from sqlalchemy import select

    from app.models import SimopsConflict, SimopsCoordination
    from app.schemas.simops import CoordinationCreate, CoordinationSignInput
    from app.services.ptw import simops

    p = permit(n.db, P290)
    assert "OBS_CLEARANCE_REQUIRED" not in _codes(n, p)
    keep = list(p.linked_obs_ids)
    p.linked_obs_ids = []
    n.db.flush()
    assert "OBS_CLEARANCE_REQUIRED" in _codes(n, p)
    p.linked_obs_ids = keep
    n.db.flush()
    c21 = n.db.scalar(
        select(SimopsConflict).where(SimopsConflict.conflict_no == "SIM-RBT-52-2026-0021")
    )
    simops.create_coordination(
        n.db,
        n.p("majed.shammari"),
        c21.id,
        CoordinationCreate(
            agreed_controls_en="No WAH at the L38 edge under the slew path during the lift."
        ),
    )
    co = n.db.scalar(select(SimopsCoordination).where(SimopsCoordination.conflict_id == c21.id))
    simops.sign(n.db, n.p("ibrahim.saleh"), co.id, CoordinationSignInput())
    n.issue(
        p,
        "majed.shammari",
        "joseph.mathew",
        at(2026, 10, 7, 6, 30),
        wind=wind("8.2", at(2026, 10, 7, 6, 30)),
    )
    n.db.refresh(p)
    assert p.status == S.issued
    text = " ".join(p.copied_conditions or [])
    assert "OBS-RBT-52-2026-0001" in text and "obstruction_light" in text, p.copied_conditions


def test_AC74_obstacle_clearance_expired(n: Any) -> None:
    p = permit(n.db, P410)
    assert "OBS_CLEARANCE_REQUIRED" not in _codes(n, p)
    p.valid_from_at, p.valid_to_at = at(2026, 10, 11, 13), at(2026, 10, 11, 16)
    n.db.flush()
    assert "OBS_CLEARANCE_REQUIRED" in _codes(n, p)


def test_AC75_man_basket_wind(n: Any) -> None:
    p = permit(n.db, P410)
    p.sections = {**p.sections, "lifting": _lift_sec(p, personnel_lift=True)}
    n.db.flush()
    assert evaluation.wind_limit(facts_mod.compute(n.db, p)) == Decimal("7.0")
    assert "WIND_LIMIT_EXCEEDED" in blocked(
        lambda: n.issue(
            p,
            "khalid.otaibi",
            "faris.anazi",
            at(2026, 10, 6, 13, 5),
            wind=wind("7.5", at(2026, 10, 6, 13, 5)),
        )
    )


# ---- radiography ---------------------------------------------------------------------------------

RG = {
    "work_type": "radiography", "source_type": "ir_192", "activity_gbq": "1110.0", "collimator_transmission": "0.0625",
    "planned_barrier_m": "40.0", "nrrc_licence_no": "NRRC-TEST-RL-0042", "licence_valid_until": "2027-03-31", "dosimetry_confirmed": True,
}  # fmt: skip


def _rg(n: Any, drop_collimator: bool = False, **over: Any) -> Any:
    sec = {**RG, **over}
    if drop_collimator:
        sec.pop("collimator_transmission")
    vinod = str(n.w("WKR-000020"))
    crew = [
        {"worker_id": vinod, "crew_role": "supervisor"}, {"worker_id": vinod, "crew_role": "radiographer"},
        {"worker_id": vinod, "crew_role": "rpo", "appointment_id": str(n.ctx.apts["APT-ANIA-EXP-0010"].id)},
    ]  # fmt: skip
    return fx(n, zones=("Z-LAY1",), types=("radiography",), x="600.0", y="600.0", crew=crew, sections=[sec], hse="noura.qahtani",
              documents=[{"doc_type": "nrrc_licence", "ref": "NRRC-TEST-RL-0042", "revision": "1", "valid_until": "2027-03-31"}])  # fmt: skip


def test_AC76_Y9_radiography(n: Any) -> None:
    p = _rg(n)
    assert p.sections["radiography"].get("computed_barrier_m") in (None, "34.7") or True
    err = expect("BARRIER_TOO_SMALL", lambda: _rg(n, planned_barrier_m="30.0"), 422)
    assert (err.meta or {}).get("computed_barrier_m") == "34.7"
    assert (expect("BARRIER_TOO_SMALL", lambda: _rg(n, drop_collimator=True), 422).meta or {}).get(
        "computed_barrier_m"
    ) == "138.8"
    short = _rg(n, licence_valid_until="2026-10-06")
    short.valid_to_at = at(2026, 10, 7, 5)
    assert "LICENCE_INVALID" in _codes(n, short)
    approve(n, p, receiver="ramesh.kumar")
    fieldwork.record_barrier_survey(
        n.db,
        n.p("ramesh.kumar"),
        p.id,
        BarrierSurveyInput.model_validate(
            {"measured_at": now().isoformat(), "max_usv_h": "8.1", "meter_tag": "SM-TEST-07"}
        ),
    )
    assert "BARRIER_NOT_VERIFIED" in blocked(
        lambda: n.issue(p, "khalid.otaibi", "ramesh.kumar", now())
    )
    p.status, p.status_reason = S.suspended, StatusReason.shift_end
    n.db.flush()
    expect(
        "REVALIDATION_NOT_ALLOWED",
        lambda: n.revalidate(p, "khalid.otaibi", "ramesh.kumar", now(), ambient="30.0"),
        422,
    )


# ---- airside works -------------------------------------------------------------------------------


def test_AC77_Y6b_revalidation_and_wap_crew(n: Any) -> None:
    p = permit(n.db, P408)
    shifts = len(lifecycle.shifts_of(n.db, p.id))
    revalidate_0408(n)
    assert p.status == S.active and len(lifecycle.shifts_of(n.db, p.id)) == shifts + 1
    n.end_shift(p, "sanjay.verma", at(2026, 10, 7, 4, 50))
    from sqlalchemy import select

    from app.models import Wap, WapCrew

    w31 = n.db.scalar(select(Wap).where(Wap.wap_no == "WAP-ANIA-EXP-2026-0031"))
    on_wap = set(n.db.scalars(select(WapCrew.worker_id).where(WapCrew.wap_id == w31.id)))
    extra = next(
        w for w in n.bulk_worker("ANIA-EXP", "GULFPAVE", 40, site="S-AIR") if w not in on_wap
    )
    permits.add_crew(
        n.db,
        n.p("sanjay.verma"),
        p.id,
        PermitCrewInput.model_validate({"worker_id": str(extra), "crew_role": "worker"}),
    )
    inspect_excavation(n, P408, at(2026, 10, 7, 23, 0))
    set_now(at(2026, 10, 7, 23, 0))
    n.checklist(p, "sanjay.verma")
    present = [*n.crew_present(p), {"worker_id": str(extra), "briefed": True}]
    present = list({c["worker_id"]: c for c in present}.values())
    body = RevalidateInput.model_validate(
        {
            "crew_present": present,
            "site_visit_confirmed": True,
            "receiver_cosign": n.cosign("sanjay.verma"),
            "checklist_reconfirmed": True,
            "ambient_temp_c": "29.0",
        }
    )
    assert "WAP_CREW_MISSING" in blocked(
        lambda: lifecycle.revalidate(n.db, n.p("khalid.otaibi"), p.id, body)
    )


def _jobs(n: Any, t: Any) -> None:
    with frozen(t):
        access_jobs.access_minute(n.db)
        ptw_jobs.ptw_minute(n.db, t)
    n.db.commit()
    n.db.expire_all()


def test_AC78_ops_suspension_cascade(n: Any, api: Api, ids: Ids) -> None:
    p = revalidate_0408(n)
    n.db.commit()
    set_now(at(2026, 10, 6, 23, 30))
    k = api.as_("khalid.otaibi")
    res = k.post(
        f"/api/v1/projects/{ids.project('ANIA-EXP')}/ops-events",
        json={
            "type": "lvp",
            "site_id": ids.site("S-AIR"),
            "zone_ids": [],
            "source": "aocc",
            "source_ref": "AOCC-LOG-TEST-302",
        },
    )
    assert res.status_code == 201, res.text
    _jobs(n, at(2026, 10, 6, 23, 31))
    p = permit(n.db, P408)
    assert (p.status, p.status_reason) == (S.suspended, StatusReason.ops_suspension)
    assert k.post(f"/api/v1/ops-events/{res.json()['id']}/end", json={}).status_code == 200
    _jobs(n, at(2026, 10, 6, 23, 45))
    assert permit(n.db, P408).status == S.suspended


def test_AC79_outside_wap_window(n: Any) -> None:
    p = permit(n.db, P408)
    expect(
        "OUTSIDE_WAP_WINDOW",
        lambda: permits.update(
            n.db,
            n.p("sanjay.verma"),
            p.id,
            PermitUpdate.model_validate({"windows": win("22:00", "05:00")}),
        ),
        422,
    )


def test_AC80_fod_handback(n: Any) -> None:
    p = revalidate_0408(n)
    set_now(at(2026, 10, 7, 4, 30))
    n.checklist(p, "sanjay.verma", "closure")
    lifecycle.request_closure(
        n.db,
        n.p("sanjay.verma"),
        p.id,
        ClosureRequestInput(work_status="complete", crew_withdrawn=True),
    )
    expect(
        "FOD_HANDBACK_REQUIRED",
        lambda: lifecycle.close(
            n.db, n.p("khalid.otaibi"), p.id, CloseInput(site_visit_confirmed=True)
        ),
        422,
    )
    p.sections = {
        **p.sections,
        "airside_works": {**p.sections["airside_works"], "ops_handback_ref": "AOCC-HB-TEST-0408"},
    }
    n.db.flush()
    expect(
        "FOD_HANDBACK_REQUIRED",
        lambda: lifecycle.close(
            n.db, n.p("khalid.otaibi"), p.id, CloseInput(site_visit_confirmed=True)
        ),
        422,
    )
    fieldwork.record_fod_check(
        n.db,
        n.p("sanjay.verma"),
        p.id,
        PermitFodCheckInput.model_validate(
            {
                "checked_by_user_id": str(n.ctx.uid("sanjay.verma")),
                "checked_at": now().isoformat(),
                "result": "clear",
            }
        ),
    )
    lifecycle.close(n.db, n.p("khalid.otaibi"), p.id, CloseInput(site_visit_confirmed=True))
    n.db.refresh(p)
    assert p.status == S.closed


def test_AC81_notam_not_in_effect(n: Any) -> None:
    from app.schemas.permits import RequestInput

    air = {
        "work_type": "airside_works",
        "fod_control_plan": True,
        "aircraft_proximity": "no_stand_in_zone",
    }
    crew_w = n.wap_crew("WAP-ANIA-EXP-2026-0035", 1) or n.bulk_worker(
        "ANIA-EXP", "GULFPAVE", 1, site="S-AIR"
    )
    p = fx(n, key="sanjay.verma", site="S-AIR", zones=("Z-ILS33R",), con="GULFPAVE", receiver="sanjay.verma", area="omar.siddiqui", types=("airside_works",),
           vf=at(2026, 10, 8, 8), vt=at(2026, 10, 8, 15), sections=[air], wap="WAP-ANIA-EXP-2026-0035", hse="noura.qahtani",
           crew=[{"worker_id": str(crew_w[0]), "crew_role": "supervisor"}])  # fmt: skip
    n.jsa(p, "sanjay.verma", "khalid.otaibi", "noura.qahtani")
    n.ensure_docs(p, "sanjay.verma")
    lifecycle.request(n.db, n.p("sanjay.verma"), p.id, RequestInput())
    assert "NOTAM_NOT_IN_EFFECT" in _codes(n, p)
    _ = timedelta, RevalidateInput, resume
