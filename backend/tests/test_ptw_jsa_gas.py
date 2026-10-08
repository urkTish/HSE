"""3-ptw §9 AC26-AC37 (JSA and gas testing), Y1, Y2, Y3, Y11."""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ptw_jobs
from app.core.clock import set_now
from app.core.enums import NotificationKind
from app.core.ptw_enums import PermitStatus, StatusReason
from app.models import Notification
from app.schemas.jsa import JsaInstanceCreate, JsaTransition, ResidualAcceptanceInput
from app.services.ptw import gas, jsa, lifecycle
from tests.ptw_helpers import (
    SEED_AT,
    at,
    blocked,
    expect,
    fx,
    gas_test,
    hz,
    jsa_fill,
    jsa_of,
    permit,
    rd,
    resume,
    world,
)  # fmt: skip

S = PermitStatus
ALARP = "Edge protection, netting and SRL reduce the risk as low as reasonably practicable."
RBT = {
    "key": "joseph.mathew",
    "project": "RBT-52",
    "site": "S-TWR",
    "zones": ("Z-CORE",),
    "con": "QIMMA",
    "receiver": "joseph.mathew",
    "area": "ibrahim.saleh",
    "issuer": "majed.shammari",
    "hse": "lina.haddad",
}
Y1 = [
    hz("fall_from_height", 4, 5, 2, 5, "engineering", "administrative", "ppe"),
    hz("falling_objects", 3, 4, 1, 4, "engineering", "administrative"),
]


@pytest.fixture
def n(ptw_seed: None, db: Session) -> Iterator[Any]:
    set_now(SEED_AT)
    yield world(db)
    set_now(None)


def _review(n: Any, p: Any) -> None:
    from app.schemas.permits import AreaReviewInput, HseReviewInput, RequestInput

    n.ensure_docs(p, "joseph.mathew")
    lifecycle.request(n.db, n.p("joseph.mathew"), p.id, RequestInput())
    lifecycle.area_review(
        n.db,
        n.p("ibrahim.saleh"),
        p.id,
        AreaReviewInput(area_conditions_known=True, simops_reviewed=True),
    )
    n.db.refresh(p)
    if p.high_risk:
        lifecycle.hse_review(n.db, n.p("lina.haddad"), p.id, HseReviewInput(decision="accepted"))
    n.checklist(p, "joseph.mathew")


def _approve(n: Any, p: Any) -> None:
    from app.schemas.permits import ApproveInput

    lifecycle.approve(n.db, n.p("majed.shammari"), p.id, ApproveInput())


# ---- JSA -----------------------------------------------------------------------------------------


def test_AC26_Y1_high_residual_needs_issuer_and_hse(n: Any) -> None:
    p = fx(n, **RBT)
    j = jsa_fill(n, p, "joseph.mathew", Y1)
    rows = [jsa.line_facts(h) for h in Y1]
    assert [(r["initial_score"], r["residual_score"]) for r in rows] == [(20, 10), (12, 4)]
    assert jsa.governing_band(j).value == "high"
    jsa.accept(
        n.db, n.p("majed.shammari"), j.id, ResidualAcceptanceInput(alarp_justification=ALARP)
    )
    _review(n, p)
    expect("RESIDUAL_ACCEPTANCE_MISSING", lambda: _approve(n, p), 422)
    j.created_by_user_id = n.ctx.uid("lina.haddad")  # variant: Lina as the JSA author
    expect(
        "SOD_CONFLICT",
        lambda: jsa.accept(
            n.db, n.p("lina.haddad"), j.id, ResidualAcceptanceInput(alarp_justification=ALARP)
        ),
        422,
    )
    j.created_by_user_id = n.ctx.uid("joseph.mathew")
    jsa.accept(n.db, n.p("lina.haddad"), j.id, ResidualAcceptanceInput(alarp_justification=ALARP))
    _approve(n, p)
    n.db.refresh(p)
    assert p.status == S.approved


def test_AC27_residual_extreme(n: Any) -> None:
    p = fx(n, **RBT)
    jsa_fill(
        n, p, "joseph.mathew", [hz("fall_from_height", 4, 5, 3, 5, "engineering", "administrative")]
    )
    _review(n, p)
    expect("JSA_RESIDUAL_EXTREME", lambda: _approve(n, p), 422)


def test_AC28_mandatory_hazards(n: Any) -> None:
    p = fx(n, types=("work_at_height",), zones=("Z-LAY1",))
    expect(
        "JSA_MANDATORY_HAZARD_MISSING",
        lambda: jsa_fill(
            n,
            p,
            "ramesh.kumar",
            [hz("fall_from_height", 3, 5, 1, 5, "engineering")],
            mandatory=False,
        ),
        422,
    )
    set_now(at(2026, 7, 13, 10))
    q = fx(n, zones=("Z-LAY1",), vf=at(2026, 7, 14, 6), vt=at(2026, 7, 14, 11), windows=None)
    err = expect(
        "JSA_MANDATORY_HAZARD_MISSING",
        lambda: jsa_fill(
            n,
            q,
            "ramesh.kumar",
            [hz("manual_handling", 3, 3, 1, 3, "engineering")],
            mandatory=False,
        ),
        422,
    )
    assert "heat_stress" in (err.meta or {}).get("missing", [])


def test_AC29_ppe_only_controls(n: Any) -> None:
    p = fx(n, **RBT)
    expect(
        "PPE_ONLY_CONTROLS",
        lambda: jsa_fill(
            n, p, "joseph.mathew", [hz("manual_handling", 3, 3, 1, 3, "ppe")], submit=False
        ),
        422,
    )
    j = jsa_fill(n, p, "joseph.mathew", [hz("manual_handling", 3, 3, 2, 3, "ppe")], submit=False)
    assert j.steps[0]["hazards"][0]["residual_l"] == 2


def test_AC30_template_review_due(n: Any) -> None:
    p = fx(n, **{**RBT, "template": None})
    expect(
        "TEMPLATE_REVIEW_DUE",
        lambda: jsa.create_instance(
            n.db,
            n.p("joseph.mathew"),
            p.id,
            JsaInstanceCreate(template_id=n.ctx.templates["JSA-T-RBT-52-0009"].id),
        ),
        422,
    )
    _ = JsaTransition, jsa_of


# ---- gas -----------------------------------------------------------------------------------------

P413 = "PTW-ANIA-EXP-2026-0413"
GOOD = [
    rd("top", "20.9", "0", "0", "3"),
    rd("middle", "20.8", "0", "0", "4"),
    rd("bottom", "20.6", "2", "0", "6"),
]


def test_AC31_Y2_gas_results(n: Any) -> None:
    p = permit(n.db, P413)
    first = gas.tests_of(n.db, p.id)[0]
    assert (first.test_type.value, first.result.value, first.fail_codes) == (
        "pre_entry",
        "pass",
        [],
    )
    bad = gas_test(n, p, SEED_AT, "periodic", [rd("at_work_point", "19.4", "2", "0", "6")])
    assert bad.result.value == "fail" and [
        c.value if hasattr(c, "value") else c for c in bad.fail_codes
    ] == ["O2_OUT_OF_RANGE"]
    n.db.refresh(p)
    assert p.status_reason == StatusReason.gas_test_failed


def test_AC32_Y3_gas_timing(n: Any) -> None:
    p = permit(n.db, P413)
    rows = gas.tests_of(n.db, p.id)
    local = [(r.tested_at, r.valid_for_start_until, r.next_due_at) for r in rows]
    assert local[0] == (at(2026, 10, 6, 7, 40), at(2026, 10, 6, 8, 10), at(2026, 10, 6, 8, 40))
    assert [x[2] for x in local[1:]] == [at(2026, 10, 6, 9, 38), at(2026, 10, 6, 10, 48)]
    shift = lifecycle.current_shift(n.db, p)
    from app.services.ptw import common

    st = common.settings(n.db, p.project_id)
    ok = gas.shift_compliant(
        n.db,
        p,
        shift,
        60,
        st.gas_pre_start_validity_minutes,
        st.gas_break_retest_minutes,
        at(2026, 10, 6, 10, 47),
        False,
    )
    assert ok is True
    ptw_jobs.ptw_minute(n.db, at(2026, 10, 6, 10, 47))
    n.db.refresh(p)
    assert p.status == S.active
    ptw_jobs.ptw_minute(n.db, at(2026, 10, 6, 10, 48))
    n.db.refresh(p)
    assert (p.status, p.status_reason) == (S.suspended, StatusReason.gas_retest_overdue)
    rows[1].superseded = True  # variant without the 08:38 test
    n.db.flush()
    assert (
        gas.shift_compliant(
            n.db,
            p,
            shift,
            60,
            st.gas_pre_start_validity_minutes,
            st.gas_break_retest_minutes,
            at(2026, 10, 6, 10, 47),
            False,
        )
        is False
    )


def test_AC33_detector_quarantined_and_bump(n: Any) -> None:
    p = permit(n.db, P413)
    expect(
        "DETECTOR_CALIBRATION_OVERDUE",
        lambda: gas_test(
            n,
            p,
            at(2026, 10, 6, 10, 0),
            "periodic",
            [rd("at_work_point", "20.8", "1", "0", "5")],
            detector="GD-ANIA-005",
        ),
        422,
    )
    expect(
        "BUMP_TEST_MISSING",
        lambda: gas_test(
            n,
            p,
            at(2026, 10, 6, 7, 25),
            "periodic",
            [rd("at_work_point", "20.8", "1", "0", "5")],
            saved=at(2026, 10, 6, 7, 35),
        ),
        422,
    )


def test_AC34_detector_sensor_missing(n: Any) -> None:
    p = permit(n.db, P413)
    n.ctx.detectors["GD-ANIA-003"].sensors = ["o2", "lel", "co"]
    n.db.flush()
    expect(
        "DETECTOR_SENSOR_MISSING",
        lambda: gas_test(n, p, SEED_AT, "periodic", [rd("at_work_point", "20.8", "1", "0", "5")]),
        422,
    )


def test_AC35_signature_and_appointment(n: Any) -> None:
    p = permit(n.db, P413)
    expect(
        "TESTER_SIGNATURE_REQUIRED",
        lambda: gas_test(
            n, p, SEED_AT, "periodic", [rd("at_work_point", "20.8", "1", "0", "5")], signature=False
        ),
        422,
    )
    expect(
        "APPOINTMENT_INVALID",
        lambda: gas_test(
            n,
            p,
            SEED_AT,
            "periodic",
            [rd("at_work_point", "20.8", "1", "0", "5")],
            apt="APT-ANIA-EXP-0012",
        ),
        422,
    )


def test_AC36_failed_test_suspends_and_needs_post_alarm(n: Any) -> None:
    p = permit(n.db, P413)
    gas_test(n, p, SEED_AT, "periodic", [rd("at_work_point", "20.8", "7", "0", "5")])
    n.db.refresh(p)
    assert (p.status, p.status_reason) == (S.suspended, StatusReason.gas_test_failed)
    faisal = n.ctx.uid("faisal.harbi")
    assert (
        n.db.scalar(
            select(Notification).where(
                Notification.user_id == faisal,
                Notification.kind == NotificationKind.gas_test_failed,
            )
        )
        is not None
    )
    assert "GAS_TEST_FAILED" in blocked(
        lambda: resume(n, p, "khalid.otaibi", "faris.anazi", at(2026, 10, 6, 10, 20))
    )
    gas_test(n, p, at(2026, 10, 6, 10, 22), "periodic", GOOD)
    assert "GAS_TEST_REQUIRED" in blocked(
        lambda: resume(n, p, "khalid.otaibi", "faris.anazi", at(2026, 10, 6, 10, 24))
    )
    gas_test(n, p, at(2026, 10, 6, 10, 25), "post_alarm", GOOD)
    resume(n, p, "khalid.otaibi", "faris.anazi", at(2026, 10, 6, 10, 27))
    assert p.status == S.active


def test_AC37_backdated_test(n: Any) -> None:
    p = permit(n.db, P413)
    expect(
        "BACKDATED_TEST",
        lambda: gas_test(
            n,
            p,
            at(2026, 10, 6, 8, 0),
            "periodic",
            [rd("at_work_point", "20.8", "1", "0", "5")],
            saved=SEED_AT,
        ),
        422,
    )
