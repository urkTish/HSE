"""3-ptw §9 AC38-AC50 (isolations / LOTO and SIMOPS), Y8, Y9."""

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.core.enums import NotificationKind
from app.core.ptw_enums import PermitStatus, SimopsCheckTrigger, StatusReason
from app.models import (
    AuditEntry,
    IsolationCertificate,
    Notification,
    SimopsConflict,
    SimopsCoordination,
)
from app.schemas.isolations import (
    IsolationCreate,
    IsolationTransition,
    LockCutInput,
    LongTermReviewInput,
    PersonalLockApply,
    PersonalLockRemove,
    PointApplyInput,
    PointVerifyInput,
)  # fmt: skip
from app.schemas.permits import PermitUpdate
from app.schemas.simops import CoordinationCreate, CoordinationSignInput
from app.services.ptw import isolations, permits, simops
from app.services.ptw.rules import q1
from tests.conftest import Api, Ids
from tests.ptw_helpers import (
    SEED_AT,
    approve,
    at,
    blocked,
    cse_fx,
    cse_ready,
    expect,
    fx,
    permit,
    wind,
    world,
)  # fmt: skip

S = PermitStatus
P405 = "PTW-ANIA-EXP-2026-0405"
CONTROLS = "Debris netting at the edge; no work above the bay except behind netting."


@pytest.fixture
def n(ptw_seed: None, db: Session) -> Iterator[Any]:
    set_now(SEED_AT)
    yield world(db)
    set_now(None)


def iso61(n: Any) -> IsolationCertificate:
    c = n.db.scalar(
        select(IsolationCertificate).where(IsolationCertificate.iso_no == "ISO-ANIA-EXP-2026-0061")
    )
    assert c is not None
    return c


# ---- isolations ----------------------------------------------------------------------------------


def _new_cert(
    n: Any, hv: bool = False, project: str = "ANIA-EXP", authority: str = "nasser.shahrani"
) -> Any:
    from app.schemas.isolations import LockCreate

    box = isolations.create_lock(
        n.db, n.p(authority), n.ctx.pid(project), LockCreate(lock_type="lockbox")
    )
    return isolations.create(n.db, n.p(authority), n.ctx.pid(project), IsolationCreate.model_validate({
        "equipment_desc": "Fixture DB-9", "energy_types": ["electrical"], "hv": hv, "lockbox_id": str(box.id),
        "isolation_authority_user_id": str(n.ctx.uid(authority)),
        "points": [{"energy_type": "electrical", "device_tag": "Q99", "location": "Fixture board", "method": "breaker_racked_out"}],
    }))  # fmt: skip


def test_AC38_verifier_is_applier(n: Any) -> None:
    iso = _new_cert(n)
    cert = n.db.get(IsolationCertificate, iso.id)
    cert.engagement_id = n.ctx.eng("ANIA-EXP", "RAWABI").id  # RAWABI equipment: visible to Faris
    pt = isolations.points(n.db, cert)[0]
    isolations.apply_point(
        n.db,
        n.p("nasser.shahrani"),
        cert.id,
        pt.id,
        PointApplyInput.model_validate(
            {
                "isolation_lock_id": str(n.ctx.locks["L-ANIA-0233"].id),
                "tag_no": "DT-0233",
                "applied_at": now().isoformat(),
            }
        ),
    )
    isolations.transition(
        n.db, n.p("nasser.shahrani"), cert.id, IsolationTransition(to_status="isolated")
    )
    body = PointVerifyInput.model_validate(
        {"verified_at": now().isoformat(), "verification_method": "test_for_dead"}
    )
    expect(
        "VERIFIER_IS_APPLIER",
        lambda: isolations.verify_point(n.db, n.p("nasser.shahrani"), cert.id, pt.id, body),
        422,
    )
    isolations.verify_point(n.db, n.p("faris.anazi"), cert.id, pt.id, body)


def _events(n: Any) -> list[Any]:
    return isolations.active_personal_locks(n.db, iso61(n).lockbox_id)


def test_AC39_personal_locks_missing(n: Any) -> None:
    p = permit(n.db, P405)
    for ev in _events(n):
        set_now(at(2026, 10, 6, 16, 50))
        isolations.remove_personal(
            n.db,
            n.p("faris.anazi"),
            ev.id,
            PersonalLockRemove.model_validate({"removed_at": now().isoformat()}),
        )
    workers = [ev.worker_id for ev in sorted(_events(n) or [], key=str)]
    assert workers == []
    n.end_shift(p, "faris.anazi", at(2026, 10, 6, 16, 55))
    crew = [c["worker_id"] for c in n.crew_present(p)]
    assert len(crew) == 3
    # each personal lock has one holder (one holder, one key): pair locks with their holders
    # first so the test does not depend on the crew's uuid order
    locks = ("P-ANIA-1101", "P-ANIA-1102")
    held = {lk: str(n.ctx.locks[lk].holder_worker_id or "") for lk in locks}
    free = [w for w in crew if w not in held.values()]
    pairs = [(held[lk] or free.pop(0), lk) for lk in locks]
    for wid, lk in pairs:
        set_now(at(2026, 10, 7, 7, 0))
        isolations.apply_personal(
            n.db,
            n.p("faris.anazi"),
            iso61(n).id,
            PersonalLockApply.model_validate(
                {
                    "lock_id": str(n.ctx.locks[lk].id),
                    "worker_id": wid,
                    "applied_at": now().isoformat(),
                    "permit_id": str(p.id),
                }
            ),
        )
    assert "PERSONAL_LOCKS_MISSING" in blocked(
        lambda: n.revalidate(
            p, "khalid.otaibi", "faris.anazi", at(2026, 10, 7, 7, 5), ambient="29.0"
        )
    )


def test_AC40_deisolation_blocked(n: Any) -> None:
    err = expect(
        "DEISOLATION_BLOCKED",
        lambda: isolations.transition(
            n.db,
            n.p("nasser.shahrani"),
            iso61(n).id,
            IsolationTransition(to_status="deisolation_requested"),
        ),
    )
    meta = str(err.meta)
    assert P405 in meta and all(f"P-ANIA-110{i}" in meta for i in (1, 2, 3)), meta


def test_AC41_lock_cut_needs_manager(n: Any) -> None:
    ev = _events(n)[0]
    body = LockCutInput.model_validate({
        "supervisor_user_id": str(n.ctx.uid("faris.anazi")), "supervisor_confirmed_absent_at": now().isoformat(),
        "contact_attempts": "Called the worker's mobile twice and the camp office at 09:40 and 09:50.",
    })  # fmt: skip
    expect("FORBIDDEN", lambda: isolations.cut(n.db, n.p("noura.qahtani"), ev.id, body), 403)
    res = isolations.cut(n.db, n.p("faisal.harbi"), ev.id, body)
    assert res.removed_by.value == "cut"
    assert (
        n.db.scalar(select(Notification).where(Notification.kind == NotificationKind.lock_cut))
        is not None
    )


def test_AC42_hv_needs_hv_authority(n: Any) -> None:
    expect(
        "APPOINTMENT_INVALID",
        lambda: _new_cert(n, hv=True, project="RBT-52", authority="ibrahim.saleh"),
        422,
    )


def test_AC43_long_term_review_breach(n: Any) -> None:
    c = iso61(n)
    c.verified_at = now() - timedelta(days=40)
    n.db.flush()
    assert isolations.long_term(n.db, c)
    isolations.review(
        n.db, n.p("nasser.shahrani"), c.id, LongTermReviewInput(lock_tag_in_place=False)
    )
    p = permit(n.db, P405)
    n.db.refresh(p)
    assert (p.status, p.status_reason) == (S.suspended, StatusReason.isolation_breach)


# ---- SIMOPS --------------------------------------------------------------------------------------


def _conflicts(n: Any, p: Any) -> list[SimopsConflict]:
    return simops.conflicts_of(n.db, p.id, include_closed=True)


def test_AC44_Y8a_prohibited_then_resolved_by_change(n: Any) -> None:
    p = fx(n, x="126.0", y="53.0", flammables_in_use=True)
    expect("SIMOPS_PROHIBITED", lambda: approve(n, p, hse=None), 422)
    c = next(c for c in _conflicts(n, p) if c.rule_code == "SM-R03")
    assert (c.result.value, q1(c.distance_m)) == ("prohibited", Decimal("10.0"))
    permits.update(
        n.db,
        n.p("ramesh.kumar"),
        p.id,
        PermitUpdate.model_validate({"grid_x_m": "130.0", "grid_y_m": "52.5"}),
    )
    n.db.refresh(c)
    assert c.status.value == "resolved_by_change"


def test_AC45_Y8b_coordination_required(n: Any) -> None:
    p = cse_fx(n, x="128.0", y="51.0")
    cse_ready(n, p)
    c = next(c for c in _conflicts(n, p) if c.rule_code == "SM-R02")
    assert (c.result.value, q1(c.distance_m)) == ("conditional", Decimal("10.0"))
    assert "SIMOPS_COORDINATION_REQUIRED" in blocked(
        lambda: n.issue(p, "khalid.otaibi", "faris.anazi", now())
    )
    simops.create_coordination(
        n.db, n.p("khalid.otaibi"), c.id, CoordinationCreate(agreed_controls_en=CONTROLS)
    )
    assert "SIMOPS_COORDINATION_REQUIRED" in blocked(
        lambda: n.issue(p, "khalid.otaibi", "faris.anazi", now())
    )
    co = n.db.scalar(select(SimopsCoordination).where(SimopsCoordination.conflict_id == c.id))
    simops.sign(n.db, n.p("fahad.mutairi"), co.id, CoordinationSignInput())
    n.issue(p, "khalid.otaibi", "faris.anazi", now())
    assert p.status == S.issued


def test_AC46_seeded_coordination(n: Any) -> None:
    c19 = n.db.scalar(
        select(SimopsConflict).where(SimopsConflict.conflict_no == "SIM-RBT-52-2026-0019")
    )
    assert (c19.rule_code, c19.status.value, q1(c19.distance_m)) == (
        "SM-R06",
        "coordinated",
        Decimal("2.8"),
    )
    assert permit(n.db, "PTW-RBT-52-2026-0288").status == S.active
    c21 = n.db.scalar(
        select(SimopsConflict).where(SimopsConflict.conflict_no == "SIM-RBT-52-2026-0021")
    )
    assert (c21.rule_code, c21.status.value, q1(c21.distance_m)) == (
        "SM-R05b",
        "open",
        Decimal("23.3"),
    )
    p = permit(n.db, "PTW-RBT-52-2026-0290")
    assert "SIMOPS_COORDINATION_REQUIRED" in [b["code"] for b in p.blockers]
    simops.create_coordination(
        n.db, n.p("majed.shammari"), c21.id, CoordinationCreate(agreed_controls_en=CONTROLS)
    )
    co = n.db.scalar(select(SimopsCoordination).where(SimopsCoordination.conflict_id == c21.id))
    simops.sign(n.db, n.p("ibrahim.saleh"), co.id, CoordinationSignInput())
    n.db.refresh(p)
    assert "SIMOPS_COORDINATION_REQUIRED" not in [b["code"] for b in p.blockers]


def test_AC47_Y8d_hot_work_under_landing(n: Any) -> None:
    from app.schemas.permits import RequestInput
    from app.services.ptw import lifecycle

    bulk = n.bulk_worker("RBT-52", "QIMMA", 2, site="S-TWR", zone="Z-CORE")
    hw = fx(n, key="joseph.mathew", project="RBT-52", site="S-TWR", zones=("Z-CORE",), con="QIMMA", receiver="joseph.mathew", area="ibrahim.saleh", issuer="majed.shammari",
            types=("hot_work",), x="42.0", y="20.0", vf=at(2026, 10, 7, 7), vt=at(2026, 10, 7, 16),
            crew=[{"worker_id": str(bulk[0]), "crew_role": "hot_work_operative"}, {"worker_id": str(bulk[1]), "crew_role": "fire_watch"}],
            sections=[{"work_type": "hot_work", "hot_work_kind": ["arc_welding"], "combustibles_cleared_radius_m": "11.0", "fire_extinguishers": [{"type": "dcp_abc_6kg", "count": 2, "distance_m": "5.0"}], "fire_blanket": True, "work_height_above_floor_m": "0.00", "cylinders": "none"}])  # fmt: skip
    n.ensure_docs(hw, "joseph.mathew")
    lifecycle.request(n.db, n.p("joseph.mathew"), hw.id, RequestInput())
    p = permit(n.db, "PTW-RBT-52-2026-0290")
    set_now(at(2026, 10, 7, 6, 30))
    codes = blocked(lambda: n.issue(p, "majed.shammari", "joseph.mathew", now(), wind=wind("8.2")))
    assert "SIMOPS_PROHIBITED" in codes, codes
    c = next(c for c in _conflicts(n, hw) if c.rule_code == "SM-R05a")
    assert q1(c.distance_m) == Decimal("3.6")


def test_AC48_Y9_radiography_exclusion(n: Any) -> None:
    rg = permit(n.db, "PTW-ANIA-EXP-2026-0399")
    rg.status = S.active
    n.db.flush()
    set_now(at(2026, 10, 4, 20, 0))
    near = fx(
        n, zones=("Z-LAY1",), x="320.0", y="180.0", vf=at(2026, 10, 4, 22), vt=at(2026, 10, 5, 5)
    )
    res = simops.check(n.db, near, SimopsCheckTrigger.manual)
    m = [(x.rule_code, x.result.value, x.distance_m) for x in res.matches]
    assert ("SM-R01", "prohibited", Decimal("28.3")) in m, m
    far = fx(
        n, zones=("Z-LAY1",), x="330.0", y="230.0", vf=at(2026, 10, 4, 22), vt=at(2026, 10, 5, 5)
    )
    assert [
        x
        for x in simops.check(n.db, far, SimopsCheckTrigger.manual).matches
        if x.rule_code == "SM-R01"
    ] == []


def test_AC49_zone_distance_and_adjacency(n: Any) -> None:
    flam = fx(n, flammables_in_use=True)
    m = simops.check(n.db, flam, SimopsCheckTrigger.manual).matches
    hit = next(x for x in m if x.rule_code == "SM-R03")
    assert hit.distance_m == Decimal("0.0") or hit.distance_m == Decimal(0)
    cse = cse_fx(n, zone="Z-MSCP")
    m2 = simops.check(n.db, cse, SimopsCheckTrigger.manual).matches
    assert not [
        x
        for x in m2
        if x.rule_code == "SM-R02" and x.other_permit.permit_no == "PTW-ANIA-EXP-2026-0412"
    ], m2


def test_AC50_default_rules_locked(n: Any, api: Api, ids: Ids, db: Session) -> None:
    n.db.commit()
    c = api.as_("faisal.harbi")
    rules = c.get(f"/api/v1/projects/{ids.project('ANIA-EXP')}/simops-rules").json()["items"]
    r01 = next(r for r in rules if r["rule_code"] == "SM-R01")
    r02 = next(r for r in rules if r["rule_code"] == "SM-R02")
    assert c.delete(f"/api/v1/simops-rules/{r01['id']}").status_code == 422
    res = c.patch(f"/api/v1/simops-rules/{r02['id']}", json={"threshold_m": "20.0"})
    assert res.status_code == 200, res.text
    assert Decimal(str(res.json()["threshold_m"])) == Decimal("20.0")
    db.expire_all()
    assert db.scalar(select(AuditEntry).where(AuditEntry.entity_id == r02["id"])) is not None
