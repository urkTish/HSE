"""Helpers for Phase 3 PTW tests (3-ptw Appendix A world, seed clock 2026-10-06 10:00 Riyadh).

Most tests drive the services directly through ``N`` (the same helper the seed uses), with the
clock pinned per step; API-level checks use ``tests.conftest.Api``.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.core.errors import ApiError
from app.core.ptw_enums import CrewLineStatus, PermitStatus
from app.models import (
    GasDetector,
    Jsa,
    Lock,
    Permit,
    PermitCrew,
    PtwAppointment,
)
from app.seed_ptw import SEED_AT, _load, at
from app.seed_ptw_named import EMERGENCY, N, rd, win
from tests.conftest import PASSWORD

__all__ = ["EMERGENCY", "SEED_AT", "at", "rd", "win"]


def world(db: Session) -> N:
    """The seeded Appendix A context (users, workers, appointments, detectors, locks, permits)."""
    ctx = _load(db)
    ctx.password = PASSWORD
    ctx.apts = {a.appointment_no: a for a in db.scalars(select(PtwAppointment))}
    ctx.detectors = {d.detector_no: d for d in db.scalars(select(GasDetector))}
    ctx.locks = {lk.lock_no: lk for lk in db.scalars(select(Lock))}
    ctx.templates = {j.jsa_no: j for j in db.scalars(select(Jsa).where(Jsa.is_template.is_(True)))}
    ctx.permits = {
        p.permit_no: p for p in db.scalars(select(Permit).where(Permit.seed_fake.is_(False)))
    }
    live = [
        p.id
        for p in ctx.permits.values()
        if p.status not in (PermitStatus.closed, PermitStatus.cancelled, PermitStatus.expired)
    ]
    ctx.bulk_used = set(
        db.scalars(
            select(PermitCrew.worker_id).where(
                PermitCrew.permit_id.in_(live), PermitCrew.status == CrewLineStatus.listed
            )
        )
    )
    return N(ctx, PASSWORD)


def permit(db: Session, no: str) -> Permit:
    p = db.scalar(select(Permit).where(Permit.permit_no == no))
    assert p is not None, no
    return p


def expect(code: str, fn: Callable[[], Any], status: int | None = None) -> ApiError:
    """Run `fn` and assert it raises ApiError with `code` (and `status` when given)."""
    with pytest.raises(ApiError) as ei:
        fn()
    err = ei.value
    assert err.code.value == code, (err.code.value, err.message, err.meta)
    if status is not None:
        assert err.status_code == status, (err.status_code, err.message)
    return err


def blocker_codes(err: ApiError) -> list[str]:
    return [b["code"] for b in (err.meta or {}).get("blockers", [])]


def codes(rows: list[dict[str, Any]] | None) -> list[str]:
    return [r["code"] for r in rows or []]


def utc(y: int, m: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=UTC)


def seed_clock() -> None:
    set_now(SEED_AT)


def uid(n: N, key: str) -> uuid.UUID:
    return n.ctx.uid(key)


TEMPLATES = {
    ("ANIA-EXP", ("general",)): "JSA-T-ANIA-EXP-0001",
    ("ANIA-EXP", ("hot_work",)): "JSA-T-ANIA-EXP-0002",
    ("ANIA-EXP", ("confined_space",)): "JSA-T-ANIA-EXP-0003",
    ("ANIA-EXP", ("work_at_height",)): "JSA-T-ANIA-EXP-0004",
    ("ANIA-EXP", ("excavation",)): "JSA-T-ANIA-EXP-0005",
    ("ANIA-EXP", ("electrical",)): "JSA-T-ANIA-EXP-0006",
    ("ANIA-EXP", ("lifting",)): "JSA-T-ANIA-EXP-0007",
    ("ANIA-EXP", ("radiography",)): "JSA-T-ANIA-EXP-0008",
    ("ANIA-EXP", ("airside_works",)): "JSA-T-ANIA-EXP-0009",
    ("ANIA-EXP", ("airside_works", "excavation")): "JSA-T-ANIA-EXP-0010",
    ("ANIA-EXP", ("airside_works", "lifting")): "JSA-T-ANIA-EXP-0011",
    ("ANIA-EXP", ("airside_works", "hot_work")): "JSA-T-ANIA-EXP-0012",
    ("ANIA-EXP", ("airside_works", "general")): "JSA-T-ANIA-EXP-0013",
    ("ANIA-EXP", ("airside_works", "work_at_height")): "JSA-T-ANIA-EXP-0014",
    ("RBT-52", ("general",)): "JSA-T-RBT-52-0001",
    ("RBT-52", ("hot_work",)): "JSA-T-RBT-52-0002",
    ("RBT-52", ("work_at_height",)): "JSA-T-RBT-52-0003",
    ("RBT-52", ("excavation",)): "JSA-T-RBT-52-0004",
    ("RBT-52", ("electrical",)): "JSA-T-RBT-52-0005",
    ("RBT-52", ("lifting",)): "JSA-T-RBT-52-0006",
    ("RBT-52", ("hot_work", "work_at_height")): "JSA-T-RBT-52-0007",
    ("RBT-52", ("lifting", "work_at_height")): "JSA-T-RBT-52-0008",
}


def fx(
    n: N,
    *,
    key: str | None = None,
    project: str = "ANIA-EXP",
    site: str = "S-LAND",
    zones: tuple[str, ...] = ("Z-PIERB",),
    con: str = "NAJD",
    types: tuple[str, ...] = ("general",),
    primary: str | None = None,
    receiver: str = "ramesh.kumar",
    area: str = "fahad.mutairi",
    issuer: str = "khalid.otaibi",
    hse: str | None = None,
    vf: datetime | None = None,
    vt: datetime | None = None,
    windows: list[dict[str, Any]] | None = None,
    x: str | None = None,
    y: str | None = None,
    crew: list[dict[str, Any]] | None = None,
    sections: list[dict[str, Any]] | None = None,
    template: str | None = "auto",
    supervisor: bool = True,
    wap: str | None = None,
    **extra: Any,
) -> Permit:
    """A fixture permit (Draft) created through the service at the current clock."""
    from datetime import timedelta

    from app.core.clock import now
    from app.schemas.permits import PermitCreate
    from app.services.ptw import permits

    t0 = now()
    vf = vf or t0
    vt = vt or vf + timedelta(hours=6)
    body = n.base(
        project, site, list(zones), "Fixture work location", x, y, None, None, con,
        list(types), primary or types[0], "Fixture permit", vf, vt,
        windows or win("00:00", "23:59"), receiver, area, issuer, hse, None,
    )  # fmt: skip
    lines = list(crew or [])
    if supervisor and not any(c["crew_role"] == "supervisor" for c in lines):
        sup = n.bulk_worker(project, con, 1, site=site, zone=zones[0], until=vt)
        lines.insert(0, {"worker_id": str(sup[0]), "crew_role": "supervisor"})
    body["crew"] = lines
    if wap:
        from app.models import Wap

        w = n.db.scalar(select(Wap).where(Wap.wap_no == wap))
        assert w is not None
        body["linked_wap_ids"] = [str(w.id)]
        if windows is None:
            body["windows"] = w.windows
        sections = [
            ({**s, "wap_id": str(w.id)} if s["work_type"] == "airside_works" else s)
            for s in sections or []
        ]
    if sections:
        body["sections"] = sections
    if template == "auto":
        template = TEMPLATES.get((project, tuple(sorted(types))))
    if template:
        body["jsa_template_id"] = str(n.ctx.templates[template].id)
    body.update(extra)
    res = permits.create(
        n.db, n.p(key or receiver), n.ctx.pid(project), PermitCreate.model_validate(body)
    )
    p = n.db.get(Permit, res.id)
    assert p is not None
    return p


def approve(
    n: N, p: Permit, *, receiver: str = "ramesh.kumar", area: str = "fahad.mutairi",
    issuer: str = "khalid.otaibi", hse: str | None = "noura.qahtani", wap_no: str | None = None,
) -> None:  # fmt: skip
    """JSA → Request → reviews → Approve, all at the current clock."""
    from app.core.clock import now

    t = now()
    n.jsa(p, receiver, issuer, hse)
    n.to_approved(p, receiver, area, issuer, hse, t, t, t, t, wap_no)
    set_now(t)


def activate(
    n: N, p: Permit, *, receiver: str = "ramesh.kumar", area: str = "fahad.mutairi",
    issuer: str = "khalid.otaibi", hse: str | None = "noura.qahtani", wap_no: str | None = None,
    start: bool = True, wind: dict[str, Any] | None = None, ambient: str | None = "30.0",
) -> None:  # fmt: skip
    """Approve, issue and (optionally) start the fixture permit at the current clock."""
    from app.core.clock import now

    t = now()
    approve(n, p, receiver=receiver, area=area, issuer=issuer, hse=hse, wap_no=wap_no)
    n.issue(p, issuer, receiver, t, wind=wind)
    if start:
        n.start(p, receiver, t, ambient=ambient, wind=wind)
    set_now(t)
    n.db.refresh(p)


def blocked(fn: Callable[[], Any]) -> list[str]:
    """Run `fn`, assert a 422 blocked transition, return every blocker code (meta.blockers)."""
    with pytest.raises(ApiError) as ei:
        fn()
    err = ei.value
    assert err.status_code == 422 and (err.meta or {}).get("blockers"), (
        err.code.value,
        err.message,
        err.meta,
    )
    return blocker_codes(err)


def wind(speed: str, t: datetime | None = None, source: str = "anemometer") -> dict[str, Any]:
    from app.core.clock import now

    return {"measured_at": (t or now()).isoformat(), "speed_ms": speed, "source": source}


def inspect_excavation(
    n: N,
    permit_no: str,
    t: datetime,
    key: str = "sanjay.verma",
    apt: str = "APT-ANIA-EXP-0009",
    result: str = "safe",
) -> None:
    from app.schemas.permits import ExcavationInspectionInput
    from app.services.ptw import fieldwork

    set_now(t)
    p = permit(n.db, permit_no)
    fieldwork.record_excavation_inspection(
        n.db, n.p(key), p.id,
        ExcavationInspectionInput.model_validate({"inspected_at": t.isoformat(), "appointment_id": str(n.ctx.apts[apt].id), "result": result}),
    )  # fmt: skip


def revalidate_0408(n: N, t: datetime | None = None) -> Permit:
    """PTW-0408 (Suspended shift_end) → Active at 23:00 on 2026-10-06 (Y6, AC77)."""
    t = t or at(2026, 10, 6, 23, 0)
    inspect_excavation(n, "PTW-ANIA-EXP-2026-0408", t)
    p = permit(n.db, "PTW-ANIA-EXP-2026-0408")
    n.revalidate(p, "khalid.otaibi", "sanjay.verma", t, ambient="29.0")
    n.db.refresh(p)
    return p


def hz(
    code: str, il: int, is_: int, rl: int, rs: int, *levels: str, desc: str | None = None
) -> dict[str, Any]:
    """A JSA hazard line (controls named after their hierarchy level)."""
    return {
        "hazard_code": code, "description": desc or f"{code} line", "initial_l": il, "initial_s": is_,
        "residual_l": rl, "residual_s": rs, "controls": [{"text": f"{lv} control", "level": lv} for lv in levels],
    }  # fmt: skip


def jsa_of(n: N, p: Permit) -> Jsa:
    j = n.db.scalar(select(Jsa).where(Jsa.permit_id == p.id).order_by(Jsa.revision.desc()))
    assert j is not None
    return j


def jsa_fill(
    n: N,
    p: Permit,
    author: str,
    lines: list[dict[str, Any]],
    mandatory: bool = True,
    submit: bool = True,
) -> Jsa:
    """Replace the instance steps with `lines` (+ filler for missing mandatory hazards) and submit."""
    from app.schemas.jsa import JsaTransition, JsaUpdate
    from app.services.ptw import jsa

    j = jsa_of(n, p)
    j.steps = [{"step_no": 1, "description_en": "Task", "hazards": lines}]
    n.db.flush()
    add = []
    if mandatory:
        for h in jsa.missing_hazards(n.db, j):
            add.append(hz(h.value, 3, 3, 1, 3, "engineering", "administrative"))
    steps = [{"step_no": 1, "description_en": "Task", "hazards": lines}]
    if add:
        steps.append({"step_no": 2, "description_en": "Mandatory hazards", "hazards": add})
    jsa.update(n.db, n.p(author), j.id, JsaUpdate.model_validate({"steps": steps}))
    if submit:
        jsa.transition(n.db, n.p(author), j.id, JsaTransition(to_status="submitted"))
    n.db.refresh(j)
    return j


def resume(
    n: N, p: Permit, issuer: str, receiver: str, t: datetime, cause: str | None = "Cause cleared and verified on site by the issuer.",
    ambient: str | None = "30.0", wind_ms: str | None = None,
) -> None:  # fmt: skip
    from app.schemas.permits import ResumeInput
    from app.services.ptw import lifecycle

    set_now(t)
    body: dict[str, Any] = {
        "crew_present": n.crew_present(p),
        "site_visit_confirmed": True,
        "receiver_cosign": n.cosign(receiver),
    }
    if cause:
        body["cause_cleared_text"] = cause
    if ambient:
        body["ambient_temp_c"] = ambient
    if wind_ms:
        body["wind_reading"] = wind(wind_ms, t)
    lifecycle.resume(n.db, n.p(issuer), p.id, ResumeInput.model_validate(body))
    n.db.refresh(p)


def gas_test(
    n: N, p: Permit, tested: datetime, test_type: str, readings: list[dict[str, Any]], *, saved: datetime | None = None,
    recorder: str = "faris.anazi", detector: str = "GD-ANIA-003", apt: str = "APT-ANIA-EXP-0011", temp: str | None = "31.0",
    signature: bool = True,
) -> Any:  # fmt: skip
    """Record a gas test with tested_at `tested` saved at `saved` (default: the same time)."""
    from app.schemas.gas import GasTestCreate
    from app.seed_ptw_named import PNG
    from app.services.ptw import gas

    set_now(saved or tested)
    body: dict[str, Any] = {
        "test_type": test_type, "tested_at": tested.isoformat(), "tester_appointment_id": str(n.ctx.apts[apt].id),
        "detector_id": str(n.ctx.detectors[detector].id), "readings": readings,
    }  # fmt: skip
    if signature:
        body["tester_signature_png_base64"] = PNG
    if temp:
        body["internal_temp_c"] = temp
    return gas.record(n.db, n.p(recorder), p.id, GasTestCreate.model_validate(body))


CSE_SECTION = {
    "work_type": "confined_space", "space_id_desc": "Fixture chamber (sewer)", "space_hazards": ["toxic", "oxygen_deficiency"],
    "ventilation": "forced_supply", "rescue_method": "non_entry_tripod_winch", "rescue_response_minutes": 4,
    "rescue_equipment_checked": True, "communication_method": "voice_visual",
}  # fmt: skip
GOOD_GAS = [
    rd("top", "20.9", "0", "0", "3"),
    rd("middle", "20.8", "0", "0", "4"),
    rd("bottom", "20.6", "2", "0", "6"),
]


def cse_fx(
    n: N, zone: str = "Z-PIERB", x: str | None = None, y: str | None = None, **kw: Any
) -> Permit:
    """A RAWABI confined-space fixture (receiver Faris) with standby, entrant, rescue lead and gas tester."""
    bulk = n.bulk_worker("ANIA-EXP", "RAWABI", 2, site="S-LAND", zone=zone)
    crew = [
        {"worker_id": str(n.w("WKR-000021")), "crew_role": "rescue_lead", "appointment_id": str(n.ctx.apts["APT-ANIA-EXP-0012"].id)},
        {"worker_id": str(bulk[0]), "crew_role": "standby_person"},
        {"worker_id": str(bulk[1]), "crew_role": "entrant"},
        {"worker_id": str(n.w("WKR-000018")), "crew_role": "gas_tester", "appointment_id": str(n.ctx.apts["APT-ANIA-EXP-0011"].id)},
    ]  # fmt: skip
    sec = {**CSE_SECTION, "continuous_monitor_detector_id": str(n.ctx.detectors["GD-ANIA-003"].id)}
    kw.setdefault("crew", crew)
    kw.setdefault("sections", [sec])
    return fx(
        n,
        con="RAWABI",
        receiver="faris.anazi",
        zones=(zone,),
        types=("confined_space",),
        x=x,
        y=y,
        hse="noura.qahtani",
        **kw,
    )


def cse_ready(n: N, p: Permit) -> None:
    """Approve the CSE fixture and record a passing 3-point pre-entry test at the current clock."""
    from app.core.clock import now

    t = now()
    approve(n, p, receiver="faris.anazi")
    gas_test(n, p, t, "pre_entry", GOOD_GAS)
    set_now(t)


def hw_section(**over: Any) -> dict[str, Any]:
    return {
        "work_type": "hot_work", "hot_work_kind": ["arc_welding"], "combustibles_cleared_radius_m": "11.0",
        "fire_extinguishers": [{"type": "dcp_abc_6kg", "count": 2, "distance_m": "5.0"}],
        "fire_blanket": True, "work_height_above_floor_m": "0.00", "cylinders": "none", **over,
    }  # fmt: skip


def hw_fx(
    n: N,
    zone: str = "Z-LAY1",
    x: str | None = "10.0",
    y: str | None = "10.0",
    section: dict[str, Any] | None = None,
    **kw: Any,
) -> Permit:
    """A NAJD hot-work fixture (receiver Ramesh) with a bulk operative and fire watch."""
    con = kw.pop("con", "NAJD")
    project = kw.get("project", "ANIA-EXP")
    site = kw.get("site", "S-LAND")
    bulk = n.bulk_worker(project, con, 2, site=site, zone=zone)
    kw.setdefault(
        "crew",
        [
            {"worker_id": str(bulk[0]), "crew_role": "hot_work_operative"},
            {"worker_id": str(bulk[1]), "crew_role": "fire_watch"},
        ],
    )
    types = kw.pop("types", ("hot_work",))
    return fx(
        n,
        zones=(zone,),
        x=x,
        y=y,
        con=con,
        types=types,
        sections=[section or hw_section(), *kw.pop("extra_sections", [])],
        **kw,
    )


def exemption(n: N, p: Permit, kind: str, who: str = "faisal.harbi", **body: Any) -> Any:
    from app.schemas.permits import ExemptionCreate
    from app.services.ptw import fieldwork

    data = {
        "kind": kind,
        "reason_text": "Approved by the HSE Manager for this permit (test).",
        **body,
    }
    return fieldwork.request_exemption(n.db, n.p(who), p.id, ExemptionCreate.model_validate(data))
