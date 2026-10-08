"""3-ptw §9 AC10-AC25 (permit core)."""

import re
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ptw_jobs
from app.core.access_enums import HookKind, HookProviderStatus
from app.core.clock import now, set_now
from app.core.ptw_enums import PermitStatus, StatusReason
from app.models import Permit, Worker
from app.schemas.permits import (
    ApproveInput,
    IssueInput,
    PermitCrewInput,
    PermitUpdate,
    RequestInput,
)
from app.services.access import hooks
from app.services.ptw import board, evaluation, lifecycle, permits
from tests.conftest import Api, Ids
from tests.ptw_helpers import (
    SEED_AT,
    activate,
    approve,
    at,
    blocked,
    expect,
    fx,
    permit,
    revalidate_0408,
    win,
    wind,
    world,
)

S = PermitStatus


@pytest.fixture
def n(ptw_seed: None, db: Session) -> Iterator[Any]:
    set_now(SEED_AT)
    yield world(db)
    set_now(None)


def wid(db: Session, name: str) -> str:
    return str(db.scalar(select(Worker.id).where(Worker.full_name_en == name)))


def test_AC10_duration_exceeds_limit(n: Any) -> None:
    set_now(at(2026, 10, 6, 6, 50))
    err = expect(
        "DURATION_EXCEEDS_LIMIT",
        lambda: fx(
            n, types=("hot_work",), vf=at(2026, 10, 6, 7), vt=at(2026, 10, 7, 9), sections=[_hw()]
        ),
        422,
    )
    assert (err.meta or {}).get("limiting_type") == "hot_work"


AIR = {
    "work_type": "airside_works",
    "fod_control_plan": True,
    "aircraft_proximity": "no_stand_in_zone",
}


def _hw(**over: Any) -> dict[str, Any]:
    return {
        "work_type": "hot_work", "hot_work_kind": ["arc_welding"], "combustibles_cleared_radius_m": "11.0",
        "fire_extinguishers": [{"type": "dcp_abc_6kg", "count": 2, "distance_m": "5.0"}],
        "fire_blanket": True, "work_height_above_floor_m": "0.00", "cylinders": "none", **over,
    }  # fmt: skip


def test_AC11_zones_not_same_site(n: Any) -> None:
    expect("ZONES_NOT_SAME_SITE", lambda: fx(n, zones=("Z-PIERB", "Z-APR-21")), 422)


def test_AC12_contractor_suspended(n: Any) -> None:
    expect(
        "CONTRACTOR_SUSPENDED",
        lambda: fx(
            n,
            key="ibrahim.saleh",
            project="RBT-52",
            site="S-TWR",
            zones=("Z-CORE",),
            con="DLIFT",
            receiver="joseph.mathew",
            area="ibrahim.saleh",
            issuer="majed.shammari",
            supervisor=False,
        ),
        422,
    )


def test_AC13_contractor_suspension_cascades(n: Any, api: Api, ids: Ids) -> None:
    p = revalidate_0408(n)
    assert p.status == S.active
    n.db.commit()
    mgr = api.as_("faisal.harbi")
    url = f"/api/v1/contractors/{ids.contractor('GULFPAVE')}/transitions"
    assert (
        mgr.post(
            url, json={"to_status": "suspended", "reason": "Safety stand-down TEST"}
        ).status_code
        == 200
    )
    n.db.expire_all()
    assert (p.status, p.status_reason) == (S.suspended, StatusReason.contractor_suspended)
    assert (
        mgr.post(url, json={"to_status": "approved", "reason": "Reinstated TEST"}).status_code
        == 200
    )
    ptw_jobs.ptw_minute(n.db, now() + timedelta(minutes=1))
    n.db.expire_all()
    assert p.status == S.suspended


def test_AC14_crew_not_in_tree(n: Any) -> None:
    p = fx(
        n,
        key="ibrahim.saleh",
        project="RBT-52",
        site="S-TWR",
        zones=("Z-CORE",),
        con="QIMMA",
        receiver="joseph.mathew",
        area="ibrahim.saleh",
        issuer="majed.shammari",
    )
    expect(
        "CREW_NOT_IN_TREE",
        lambda: permits.add_crew(
            n.db,
            n.p("joseph.mathew"),
            p.id,
            PermitCrewInput.model_validate(
                {"worker_id": wid(n.db, "Bikash Rai"), "crew_role": "worker"}
            ),
        ),
        422,
    )


def test_AC15_induction_expired_excluded(n: Any) -> None:
    suman = wid(n.db, "Suman Tamang")
    p = fx(
        n,
        site="S-AIR",
        zones=("Z-APR-21",),
        con="RAWABI",
        receiver="faris.anazi",
        area="omar.siddiqui",
        crew=[{"worker_id": suman, "crew_role": "worker"}],
        vt=at(2026, 10, 6, 12),
        sections=[AIR],
        wap="WAP-ANIA-EXP-2026-0033",
    )
    approve(n, p, receiver="faris.anazi", area="omar.siddiqui", wap_no="WAP-ANIA-EXP-2026-0033")
    line = next(c for c in evaluation.crew_lines(n.db, p.id) if str(c.worker_id) == suman)
    assert (line.status.value, line.excluded_reason) == ("excluded", "INDUCTION_EXPIRED")
    q = fx(
        n,
        site="S-AIR",
        zones=("Z-APR-21",),
        con="RAWABI",
        receiver="faris.anazi",
        area="omar.siddiqui",
        crew=[{"worker_id": suman, "crew_role": "supervisor"}],
        vt=at(2026, 10, 6, 12),
        sections=[AIR],
        wap="WAP-ANIA-EXP-2026-0033",
    )
    approve(n, q, receiver="faris.anazi", area="omar.siddiqui", wap_no="WAP-ANIA-EXP-2026-0033")
    assert "KEY_ROLE_INELIGIBLE" in [b["code"] for b in q.blockers]


def test_AC21_backdated_request(n: Any) -> None:
    p = fx(n, vf=now() - timedelta(minutes=30))
    expect(
        "BACKDATED_PERMIT",
        lambda: lifecycle.request(n.db, n.p("ramesh.kumar"), p.id, RequestInput()),
        422,
    )


def test_AC22_change_after_approve_returns_to_requested(n: Any) -> None:
    p = fx(n)
    approve(n, p, hse=None)
    assert p.status == S.approved
    permits.update(
        n.db,
        n.p("ramesh.kumar"),
        p.id,
        PermitUpdate.model_validate({"zone_ids": [str(n.ctx.zones["Z-LAY1"].id)]}),
    )
    n.db.refresh(p)
    assert p.status == S.requested
    assert not (p.area_review or {}).get("signed_at")


def test_AC23_issue_lists_every_blocker(n: Any, api: Api) -> None:
    p = permit(n.db, "PTW-RBT-52-2026-0290")
    p.checklists = {}
    n.db.flush()
    set_now(at(2026, 10, 7, 6, 30))
    codes = blocked(lambda: n.issue(p, "majed.shammari", "joseph.mathew", now(), wind=wind("5.0")))
    assert {"SIMOPS_COORDINATION_REQUIRED", "CHECKLIST_INCOMPLETE"} <= set(codes), codes
    paths = api.anon.get("/api/v1/openapi.json").json()["paths"]
    assert not any("override" in k for k in paths)


def test_AC24_issue_lapses_to_approved(n: Any) -> None:
    set_now(at(2026, 10, 6, 10, 0))
    p = fx(n)
    approve(n, p, hse=None)
    n.issue(p, "khalid.otaibi", "ramesh.kumar", at(2026, 10, 6, 10, 0))
    assert p.status == S.issued
    ptw_jobs.ptw_minute(n.db, at(2026, 10, 6, 10, 59))
    n.db.refresh(p)
    assert p.status == S.issued
    ptw_jobs.ptw_minute(n.db, at(2026, 10, 6, 11, 1))
    n.db.refresh(p)
    assert p.status == S.approved


def test_AC25_print_token_and_no_id_numbers(n: Any) -> None:
    rx = re.compile(r"^HSE2:PT:[A-Za-z0-9_-]{22}$")
    for no in ("PTW-ANIA-EXP-2026-0412", "PTW-ANIA-EXP-2026-0413", "PTW-RBT-52-2026-0288"):
        pr = board.print_view(
            n.db, n.p("khalid.otaibi" if "ANIA" in no else "majed.shammari"), permit(n.db, no).id
        )
        assert rx.match(pr.qr_payload), pr.qr_payload
        dump = pr.model_dump_json()
        assert not re.search(r"[12]0{5}\d{4}", dump)
        assert "nationality" not in dump and '"NP"' not in dump and '"PK"' not in dump


def test_AC20_receiver_limit(n: Any) -> None:
    p410 = permit(n.db, "PTW-ANIA-EXP-2026-0410")
    n.issue(p410, "khalid.otaibi", "faris.anazi", at(2026, 10, 6, 13, 5), wind=wind("7.2"))
    p = fx(n, con="RAWABI", receiver="faris.anazi")
    approve(n, p, receiver="faris.anazi", hse=None)
    expect("RECEIVER_LIMIT", lambda: n.issue(p, "khalid.otaibi", "faris.anazi", now()), 422)


class NotMet:
    def check(self, subject_type, subject_id, kind, code, at):  # type: ignore[no-untyped-def]
        return hooks.HookCheck(HookProviderStatus.not_met, reason_code="NOT_CERTIFIED")


def test_AC17_hook_not_available_warnings(n: Any) -> None:
    p = permit(n.db, "PTW-ANIA-EXP-2026-0410")
    n.issue(p, "khalid.otaibi", "faris.anazi", at(2026, 10, 6, 13, 5), wind=wind("7.2"))
    n.db.refresh(p)
    assert p.status == S.issued
    warns = [(w.get("code"), w.get("subject") or w.get("detail")) for w in p.warnings or []]
    hk = [w for w in warns if w[0] == "HOOK_NOT_AVAILABLE"]
    text = str(hk)
    assert "CRANE-OPERATOR" in text and "CRANE-TPI" in text, warns


def _policy(api: Api, ids: Ids, project: str, value: str) -> None:
    res = api.as_("faisal.harbi").patch(
        f"/api/v1/projects/{ids.project(project)}/access-settings",
        json={"hook_policy": {"personnel_certificate": value, "equipment_certificate": value}},
    )
    assert res.status_code == 200, res.text


def test_AC18_hook_not_met_blocks_and_suspends(n: Any, api: Api, ids: Ids) -> None:
    live = permit(n.db, "PTW-ANIA-EXP-2026-0410")
    n.issue(live, "khalid.otaibi", "faris.anazi", at(2026, 10, 6, 13, 5), wind=wind("7.2"))
    n.start(live, "faris.anazi", at(2026, 10, 6, 13, 10), ambient="34.0", wind=wind("7.2"))
    assert live.status == S.active
    n.db.commit()
    hooks.register_provider(HookKind.personnel_certificate, NotMet())
    hooks.register_provider(HookKind.equipment_certificate, NotMet())
    try:
        _policy(api, ids, "ANIA-EXP", "block")
        _policy(api, ids, "RBT-52", "block")
        n.db.expire_all()
        ptw_jobs.ptw_minute(n.db, at(2026, 10, 6, 13, 11))
        n.db.refresh(live)
        assert (live.status, live.status_reason) == (S.suspended, StatusReason.hook_not_met)
        p = permit(n.db, "PTW-RBT-52-2026-0290")
        assert "HOOK_NOT_MET" in blocked(
            lambda: n.issue(
                p, "majed.shammari", "joseph.mathew", at(2026, 10, 7, 6, 30), wind=wind("5.0")
            )
        )
    finally:
        hooks.unregister_provider(HookKind.personnel_certificate)
        hooks.unregister_provider(HookKind.equipment_certificate)


def test_AC19_viewer_sees_no_names(n: Any, api: Api) -> None:
    pid = permit(n.db, "PTW-ANIA-EXP-2026-0412").id
    res = api.as_("sarah.mitchell").get(f"/api/v1/permits/{pid}")
    assert res.status_code == 200, res.text
    body = res.text
    i = body.find("WKR-0000")
    assert i < 0, body[max(0, i - 300) : i + 50]
    for s in ("Prakash", "Ahmed Raza", "WKR-0000"):
        assert s not in body
    crew = res.json().get("crew") or []
    assert crew and all(c.get("worker_name") in (None, "") for c in crew)
    _ = ApproveInput, IssueInput, Permit


def test_AC16_id_expiry_warning_then_block(n: Any) -> None:
    osman = wid(n.db, "Osman Idris")
    set_now(at(2026, 10, 14, 6, 30))
    p = fx(
        n,
        vf=at(2026, 10, 14, 7),
        vt=at(2026, 10, 21, 6, 59),
        windows=win("06:00", "17:00"),
        crew=[{"worker_id": osman, "crew_role": "rigger"}],
    )
    set_now(at(2026, 10, 14, 7, 0))
    activate(n, p, hse=None)
    assert p.status == S.active
    assert any(w["code"] == "EXPIRING_7D" for w in p.warnings), p.warnings
    n.end_shift(p, "ramesh.kumar", at(2026, 10, 14, 16, 30))
    codes = blocked(
        lambda: n.revalidate(
            p, "khalid.otaibi", "ramesh.kumar", at(2026, 10, 21, 6, 5), ambient="30.0"
        )
    )
    assert "KEY_ROLE_INELIGIBLE" in codes
    p_bl = str(lifecycle.evaluation.evaluate(n.db, p).blockers)
    assert "ID_EXPIRED" in p_bl, p_bl
