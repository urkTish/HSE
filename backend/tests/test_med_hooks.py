"""6a-occupational-health §9 ACs 83-100 (medical hooks, warn → block, gates and permits)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind
from app.core.clock import set_now
from app.core.med_enums import MedicalProviderStatus
from app.core.ptw_enums import PermitStatus
from app.models import (
    AccessSettings,
    AuditEntry,
    FitnessLine,
    HookPolicyState,
    MedicalProvider,
    Permit,
    Zone,
    ZoneAccessProfile,
)
from app.services.access import common as acommon
from tests.cert_helpers import gate
from tests.conftest import Api
from tests.med_helpers import API, err, hook, project, reason, riyadh, worker

pytestmark = pytest.mark.usefixtures("med_seed", "clock")
MF = HookKind.medical_fitness


def _kinds(items: list[dict[str, Any]] | None) -> set[tuple[str, str]]:
    return {(x["kind"], x["code"]) for x in items or []}


# ---- enable and policy (HK6-1, HK6-2, §6.8) ------------------------------------------------------


def test_AC83_enable_preconditions(api: Api, db: Session) -> None:
    from app.services.med import common

    pid = project(db, "ANIA-EXP").id
    faisal = api.as_("faisal.harbi")
    url = f"{API}/projects/{pid}/medical-hooks/enable"
    s = common.settings(db, pid)
    s.medical_register_from = None
    db.commit()
    assert err(faisal.post(url, json={})) == "MEDICAL_REGISTER_NOT_LIVE"
    s = common.settings(db, pid)
    s.medical_register_from = date(2026, 8, 1)
    for pv in db.scalars(select(MedicalProvider)):
        pv.status = MedicalProviderStatus.suspended
    db.commit()
    assert err(faisal.post(url, json={})) == "NO_MEDICAL_PROVIDER"


def test_AC84_AC85_policy_state_and_attach_points(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    st = db.scalar(
        select(HookPolicyState).where(HookPolicyState.project_id == pid, HookPolicyState.kind == MF)
    )
    assert st is not None and st.stage.value == "transition"
    assert st.critical_block_from == date(2026, 10, 8)
    assert st.general_block_from == date(2026, 10, 31)
    acc = db.get(AccessSettings, pid)
    assert acc is not None
    assert ("medical_fitness", "GEN-FIT") in _kinds(acc.project_hook_requirements)
    adp = acc.hook_requirements_by_adp_category or {}
    for cat in ("apron", "manoeuvring"):
        assert ("medical_fitness", "DRIVER-FIT") in _kinds(adp.get(cat)), cat
    rbt = project(db, "RBT-52").id
    z = db.scalar(select(Zone).where(Zone.project_id == rbt, Zone.code == "Z-TC01"))
    assert z is not None
    zp = db.get(ZoneAccessProfile, z.id)
    assert zp is not None
    assert ("medical_fitness", "CRANE-OPERATOR-FIT") in _kinds(zp.hook_requirements)
    rows = db.scalars(select(AuditEntry).where(AuditEntry.entity_id == pid))
    assert any("attach_points_seeded" in (r.details or {}) for r in rows)
    # Phase 2 now answers medical codes (no HOOK_NOT_AVAILABLE)
    assert reason(hook(db, "WKR-000016", "GEN-FIT")) != "HOOK_NOT_AVAILABLE"


def test_AC93_deferral_rules(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    faisal = api.as_("faisal.harbi")
    base = f"{API}/projects/{pid}/hook-policy/medical_fitness"
    why = "Clinic capacity for the remaining periodic medicals (test)"
    res = faisal.post(f"{base}/deferral", json={"new_date": "2026-11-30", "reason": why,
                                               "codes": ["CSE-ENTRY-FIT"]})  # fmt: skip
    assert err(res) == "CRITICAL_CODE_NO_DEFERRAL", res.text
    res = faisal.post(f"{base}/deferral", json={"new_date": "2026-11-30", "reason": why})
    assert res.status_code == 200, res.text
    res = faisal.post(f"{base}/deferral", json={"new_date": "2026-11-30", "reason": why})
    assert err(res) == "DEFERRAL_USED", res.text
    set_now(riyadh(2026, 10, 8, 1))
    res = api.as_("faisal.harbi").post(
        f"{base}/switch", json={"codes": ["CSE-ENTRY-FIT"], "policy": "warn"}
    )
    assert err(res) == "HOOK_POLICY_LOOSENING", res.text


# ---- results per worker (MF2, HK6-3, HK6-10) ----------------------------------------------------


def test_AC86_AC87_AC99_kamal_met_zaheer_expiring_then_blocked(db: Session) -> None:
    it = hook(db, "WKR-000016", "CSE-ENTRY-FIT")
    assert it.status.value == "met", reason(it)
    it = hook(db, "WKR-000019", "CRANE-OPERATOR-FIT", riyadh(2026, 10, 6, 13))
    assert it.status.value == "expiring" and it.reason.value == "EXPIRING_7D", it.reason
    it = hook(db, "WKR-000019", "CRANE-OPERATOR-FIT", riyadh(2026, 10, 9, 19))
    assert it.status.value in ("met", "expiring"), reason(it)  # HK6-10 shift date
    it = hook(db, "WKR-000019", "CRANE-OPERATOR-FIT", riyadh(2026, 10, 10, 8))
    assert it.status.value == "not_met", reason(it)


def test_AC88_restriction_conflict_hard_stop(db: Session) -> None:
    it = hook(db, "WKR-000009", "WAH-FIT")
    assert it.status.value == "not_met" and it.hard_stop
    assert reason(it) == "RESTRICTION_CONFLICT"


def test_AC90_AC94_AC100_warn_then_block_unknown_code(db: Session) -> None:
    from app.core.access_enums import HookSubjectType
    from app.services.access import eligibility as elig
    from app.services.access.hooks import HookContext

    pid = project(db, "ANIA-EXP").id
    has_gen = select(FitnessLine.worker_id).where(FitnessLine.code == "GEN-FIT")
    from app.models import Deployment, Worker

    w = db.scalar(
        select(Worker)
        .join(Deployment, Deployment.worker_id == Worker.id)
        .where(Deployment.project_id == pid, Deployment.status == "mobilised")
        .where(Worker.id.not_in(has_gen))
        .order_by(Worker.worker_no)
    )
    assert w is not None
    it = hook(db, w.worker_no, "GEN-FIT")
    assert it.status.value == "warn" and it.reason.value == "HOOK_NOT_MET_WARN", reason(it)
    it = hook(db, w.worker_no, "GEN-FIT", riyadh(2026, 10, 31, 0, 1))
    assert it.status.value == "not_met" and it.reason.value == "HOOK_NOT_MET"
    it = hook(db, w.worker_no, "SCBA-FIT")
    assert it.status.value == "warn" and reason(it) == "UNKNOWN_CODE", reason(it)
    it = hook(db, w.worker_no, "SCBA-FIT", riyadh(2026, 11, 1))
    assert it.status.value == "not_met", reason(it)
    s = acommon.settings(db, pid)
    v = elig.hook_item(db, HookSubjectType.vehicle, w.id, MF, "GEN-FIT", riyadh(2026, 10, 6), s,
                       HookContext(project_id=pid))  # fmt: skip
    assert v.to_schema().model_dump(mode="json").get("hook_reason_code") == "UNKNOWN_CODE"


def test_AC91_AC92_conditions_and_review(api: Api, db: Session) -> None:
    it = hook(db, "WKR-000033", "GEN-FIT", riyadh(2026, 10, 8, 10))
    assert it.status.value == "warn" and reason(it) == "MEDICAL_REVIEW_DUE", reason(it)
    it = hook(db, "WKR-000033", "GEN-FIT")
    assert it.status.value == "expiring" and it.reason.value == "EXPIRING_7D", it.reason
    it = hook(db, "WKR-000003", "DRIVER-FIT")
    assert it.status.value == "met", reason(it)
    conds = it.to_schema().model_dump(mode="json")["conditions"]
    assert [c["code"] for c in conds] == ["requires_corrective_lenses"]
    assert conds[0]["text_en"] and conds[0]["text_ar"]
    w = worker(db, "WKR-000003")
    pid = project(db, "ANIA-EXP").id
    for who, visible in (("khalid.otaibi", False), ("noura.qahtani", True)):
        res = api.as_(who).get(f"{API}/workers/{w.id}/fitness", params={"project_id": str(pid)})
        assert res.status_code == 200, (who, res.text)
        assert ("requires_corrective_lenses" in res.text) is visible, (who, res.text)


# ---- gates and permits (HK6-7, HK6-8) ------------------------------------------------------------


def test_AC89_held_worker_denied_at_gate(api: Api, db: Session) -> None:
    from app.models import Deployment, GateCheck

    w = worker(db, "WKR-000034")
    dep = db.scalar(select(Deployment).where(Deployment.worker_id == w.id))
    assert dep is not None
    t = acommon.active_qr(db, dep.id)
    assert t is not None
    res = api.as_("noura.qahtani").post(
        f"{API}/gate-checks",
        json={"gate_id": str(gate(db, "G-ANIA-01").id), "payload": acommon.payload(t)},
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["result"] == "DENIED", out
    rs = [x for x in out["reasons"] if x["code"] == "HOOK_NOT_MET"]
    assert rs and "Not eligible" in rs[0]["message_en"], out
    assert "MEDICAL_HOLD" not in res.text
    row = db.get(GateCheck, out["check_id"])
    assert row is not None and "MEDICAL_HOLD" not in str(row.reasons)


def test_AC95_permit_suspended_when_line_ends(db: Session) -> None:
    from app import cert_jobs, med_jobs
    from app.services.ptw import evaluation

    set_now(riyadh(2026, 11, 1, 0, 7))
    med_jobs.medical_daily(db)
    cert_jobs.cert_switch(db)
    p = db.scalar(select(Permit).where(Permit.permit_no == "PTW-ANIA-EXP-2026-0413"))
    assert p is not None
    evaluation.refresh(db, p, run_simops=False)
    assert p.status == PermitStatus.suspended, p.blockers


def test_AC97_readiness_report(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    url = f"{API}/projects/{pid}/hook-readiness"
    rep = api.as_("noura.qahtani").get(url, params={"kind": "medical_fitness"})
    assert rep.status_code == 200, rep.text
    body = rep.json()
    codes = {c["code"]: c for c in body["codes"]}
    assert codes["GEN-FIT"]["required"] > 0 and codes["GEN-FIT"]["not_met"]
    ahmed = api.as_("ahmed.zahrani").get(url, params={"kind": "medical_fitness"})
    assert ahmed.status_code == 200, ahmed.text
    mine = {c["code"]: c for c in ahmed.json()["codes"]}
    assert mine["GEN-FIT"]["required"] < codes["GEN-FIT"]["required"]
