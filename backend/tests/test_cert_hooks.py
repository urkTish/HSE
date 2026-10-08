"""4-third-party-cert §9 hook ACs (3, 21, 33-35, 37, 42-44, 50, 56-59, 61, 73, 85-93) and one test
per hook stage (transition warn, block not_met, hard stop in every stage).

Provider-level checks call the Phase 2 HK-3 entry point (`eligibility.hook_item`) with the HK4-8
context, exactly as Phase 2 gates / WAPs and Phase 3 permits do; permit-level checks re-evaluate
seeded permits (`evaluation.refresh`)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, HookSubjectType, RequirementStatus
from app.core.cert_enums import (
    HookStage,
    ScaffoldStatus,
    ScaffoldTagStatus,
)
from app.core.clock import set_now
from app.core.ptw_enums import EquipmentCategory, EquipmentUse, PermitStatus
from app.models import (
    EquipmentCertLine,
    HookPolicyState,
    Permit,
    PermitEquipment,
)
from app.services.access import common as acommon
from app.services.access import eligibility as elig
from app.services.access.hooks import HookContext
from app.services.cert import policy
from app.services.ptw import evaluation
from tests.cert_helpers import (
    API,
    dep,
    ecert,
    item,
    pcert,
    project,
    riyadh,
    scaffold,
    worker,
)
from tests.conftest import Api

pytestmark = pytest.mark.usefixtures("cert_seed", "clock")

PC = HookKind.personnel_certificate
EC = HookKind.equipment_certificate
RS = RequirementStatus


def hook(
    db: Session,
    pcode: str,
    kind: HookKind,
    code: str,
    *,
    worker_no: str | None = None,
    tag: str | None = None,
    vehicle_id: uuid.UUID | None = None,
    when: datetime | None = None,
    **ctx: Any,
) -> elig.Item:
    pid = project(db, pcode).id
    s = acommon.settings(db, pid)
    at = when or riyadh(2026, 10, 6)
    policy.clear_cache(db)
    if worker_no:
        st, sid = HookSubjectType.worker, worker(db, worker_no).id
    elif vehicle_id:
        st, sid = HookSubjectType.vehicle, vehicle_id
    else:
        st, sid = HookSubjectType.equipment_tag, uuid.uuid4()
    hc = HookContext(project_id=pid, equipment_tag=tag, vehicle_id=vehicle_id, **ctx)
    return elig.hook_item(db, st, sid, kind, code, at, s, hc)


def reason(it: elig.Item) -> str | None:
    return it.to_schema().model_dump(mode="json").get("hook_reason_code")


def permit(db: Session, no: str) -> Permit:
    p = db.scalar(select(Permit).where(Permit.permit_no == no))
    assert p is not None, no
    return p


def codes(items: list[dict[str, Any]] | None) -> list[str]:
    return [x["code"] for x in items or []]


# ---- stages (HK4-3 / HK4-4) --------------------------------------------------------------------


def test_stage_transition_not_met_is_warn(db: Session) -> None:
    it = hook(db, "ANIA-EXP", EC, "LIFTING-ACCESSORY-TPI", tag="FX-ACC-0219",
              equipment_category="lifting_accessory")  # fmt: skip
    assert it.status == RS.warn
    assert it.reason is not None and it.reason.value == "HOOK_NOT_MET_WARN"
    assert reason(it) == "CERT_EXPIRED"


def test_stage_block_not_met_blocks(db: Session) -> None:
    it = hook(db, "ANIA-EXP", EC, "LIFTING-ACCESSORY-TPI", tag="FX-ACC-0219",
              equipment_category="lifting_accessory", when=riyadh(2026, 10, 8))  # fmt: skip
    assert it.status == RS.not_met
    assert it.reason is not None and it.reason.value == "HOOK_NOT_MET"


def test_stage_hard_stop_blocks_in_every_stage(db: Session) -> None:
    for when in (riyadh(2026, 10, 6), riyadh(2026, 11, 1)):
        it = hook(db, "ANIA-EXP", EC, "MEWP-TPI", tag="RW-MEWP-07", equipment_category="mewp",
                  when=when)  # fmt: skip
        assert it.status == RS.not_met and it.hard_stop, when
        assert reason(it) == "EQUIPMENT_OUT_OF_SERVICE"


def test_stage_before_registration_is_hook_not_available(db: Session) -> None:
    """Before HK4-1 registration the Phase 2 HK-4 behaviour applies (HOOK_NOT_AVAILABLE)."""
    it = hook(db, "ANIA-EXP", EC, "CRANE-TPI", tag="RW-MC-03", when=riyadh(2026, 9, 30))
    assert it.reason is not None and it.reason.value == "HOOK_NOT_AVAILABLE"


# ---- AC3 boundary BD-4 --------------------------------------------------------------------------


def test_P4AC3_gas_tester_certificate_and_training_course_separately(db: Session) -> None:
    pc = hook(db, "ANIA-EXP", PC, "GAS-TESTER", worker_no="WKR-000018")
    assert pc.status == RS.met and pc.valid_until == date(2028, 4, 19)
    tc = hook(db, "ANIA-EXP", HookKind.training_course, "GAS-TEST", worker_no="WKR-000018")
    assert tc.reason is not None and tc.reason.value == "HOOK_NOT_AVAILABLE"


# ---- AC21 arrival inspection ----------------------------------------------------------------------


def test_P4AC21_arrival_inspection_missing_is_warn_in_transition(db: Session) -> None:
    d = dep(db, "RW-MC-03")
    d.arrival_inspection_passed = False
    db.flush()
    it = hook(db, "ANIA-EXP", EC, "CRANE-TPI", tag="RW-MC-03", equipment_category="mobile_crane")
    assert it.status == RS.warn and reason(it) == "ARRIVAL_INSPECTION_MISSING"


# ---- AC33 / AC34 / AC35 context checks -------------------------------------------------------------


def test_P4AC33_lifting_duty_not_certified(db: Session) -> None:
    it_ = item(db, "GP-EX-05")
    it_.lifting_duty = True
    db.flush()
    it = hook(db, "ANIA-EXP", EC, "PLANT-TPI", tag="GP-EX-05", use="lifting_appliance")
    assert it.status == RS.warn and reason(it) == "LIFTING_DUTY_NOT_CERTIFIED"


def test_P4AC34_no_personnel_lifting_limitation(db: Session) -> None:
    c = ecert(db, "AICC-EQ-TEST-25-1106")
    line = db.scalar(select(EquipmentCertLine).where(EquipmentCertLine.certificate_id == c.id))
    assert line is not None
    line.limitations = [{"code": "no_personnel_lifting", "value": None, "text": None}]
    db.flush()
    it = hook(db, "ANIA-EXP", EC, "CRANE-TPI", tag="RW-MC-03", use="personnel_lift")
    assert reason(it) == "LIMITATION_CONFLICT"
    assert it.status in (RS.warn, RS.not_met)
    ok = hook(db, "ANIA-EXP", EC, "CRANE-TPI", tag="RW-MC-03", use="lifting_appliance")
    assert ok.status in (RS.met, RS.expiring)


def test_P4AC35_newer_failed_line_hard_stop(db: Session) -> None:
    it = hook(db, "ANIA-EXP", EC, "TELEHANDLER-TPI", tag="FX-TH-04")
    assert it.status == RS.not_met and it.hard_stop


# ---- AC37 configuration change on a lifting permit -------------------------------------------------


def test_P4AC37_climb_suspends_line_quarantines_item_and_blocks_permit(
    api: Api, db: Session
) -> None:
    tc = item(db, "TC-01")
    p = permit(db, "PTW-RBT-52-2026-0290")
    res = api.as_("lina.haddad").post(
        f"{API}/equipment/{tc.id}/configuration-events",
        json={
            "project_id": str(project(db, "RBT-52").id),
            "event_type": "climb_jacking",
            "occurred_at": "2026-10-06T06:30:00Z",
            "new_configuration": "HUH 248.00 m, jib 60 m, 10 tie-ins",
        },
    )
    assert res.status_code in (200, 201), res.text
    db.expire_all()
    assert item(db, "TC-01").service_status.value == "quarantined"
    it = hook(db, "RBT-52", EC, "CRANE-TPI", tag="TC-01")
    assert it.status == RS.not_met and it.hard_stop
    assert reason(it) == "CONFIGURATION_CHANGED"
    evaluation.refresh(db, p, run_simops=False)
    assert "HOOK_NOT_MET" in [b["code"] for b in p.blockers or []]


# ---- scaffolds AC42-AC44 --------------------------------------------------------------------------------


def test_P4AC42_scaffold_tag_validity(db: Session) -> None:
    sc = scaffold(db, "SC-0142")
    assert sc.tag_valid_until == date(2026, 10, 7)
    ok = hook(db, "ANIA-EXP", EC, "SCAFFOLD-TAG", tag="SC-0142")
    assert ok.status == RS.met
    late = hook(db, "ANIA-EXP", EC, "SCAFFOLD-TAG", tag="SC-0142", when=riyadh(2026, 10, 8))
    assert late.status == RS.warn and reason(late) == "SCAFFOLD_INSPECTION_OVERDUE"
    blocked = hook(db, "ANIA-EXP", EC, "SCAFFOLD-TAG", tag="SC-0142", when=riyadh(2026, 10, 31))
    assert blocked.status == RS.not_met


def _wah_on_scaffold(db: Session, tag: str) -> Permit:
    p = permit(db, "PTW-RBT-52-2026-0287")
    sections = dict(p.sections or {})
    wah = dict(sections["work_at_height"])
    wah["scaffold_tag_ref"] = tag
    access = list(wah.get("access_method") or [])
    if "scaffold" not in access:
        access.append("scaffold")
    wah["access_method"] = access
    sections["work_at_height"] = wah
    p.sections = sections
    db.flush()
    return p


def test_P4AC43_red_scaffold_hard_stop_suspends_live_permit(db: Session) -> None:
    it = hook(db, "ANIA-EXP", EC, "SCAFFOLD-TAG", tag="SC-0150")
    assert it.status == RS.not_met and it.hard_stop and reason(it) == "SCAFFOLD_TAG_RED"
    sc = scaffold(db, "SC-0001")
    sc.status, sc.tag_status = ScaffoldStatus.closed_red, ScaffoldTagStatus.red
    p = _wah_on_scaffold(db, "SC-0001")
    assert p.status == PermitStatus.active
    evaluation.refresh(db, p, run_simops=False)
    assert "HOOK_NOT_MET" in [b["code"] for b in p.blockers or []]
    assert p.status == PermitStatus.suspended
    assert p.status_reason is not None and p.status_reason.value == "hook_not_met"


def test_P4AC44_yellow_tag_met_with_restriction_as_permit_condition(db: Session) -> None:
    it = hook(db, "ANIA-EXP", EC, "SCAFFOLD-TAG", tag="SC-0151")
    assert it.status == RS.met and reason(it) == "SCAFFOLD_YELLOW_TAG"
    assert "Harness and lanyard" in it.conditions[0]["text_en"]
    sc = scaffold(db, "SC-0002")
    sc.tag_status = ScaffoldTagStatus.yellow
    sc.restrictions_en = "Guardrail removed at the hoist gate; harness required."
    p = _wah_on_scaffold(db, "SC-0002")
    evaluation.refresh(db, p, run_simops=False)
    assert p.status == PermitStatus.active
    assert any("Guardrail removed" in c["text_en"] for c in p.hook_conditions or [])


# ---- personnel AC50, AC56-AC59 -------------------------------------------------------------------------


def test_P4AC50_Z2a_joel_rigger_dates(db: Session) -> None:
    met = hook(db, "RBT-52", PC, "RIGGER", worker_no="WKR-000108", when=riyadh(2026, 10, 7))
    assert met.status == RS.met and met.valid_until == date(2026, 10, 20)
    exp = hook(db, "RBT-52", PC, "RIGGER", worker_no="WKR-000108", when=riyadh(2026, 10, 14))
    assert exp.status == RS.expiring
    gone = hook(db, "RBT-52", PC, "RIGGER", worker_no="WKR-000108", when=riyadh(2026, 10, 21))
    assert gone.status == RS.not_met and reason(gone) == "CERT_EXPIRED"


def _op(db: Session, pcode: str, wno: str, tag: str, **kw: Any) -> elig.Item:
    return hook(db, pcode, PC, "CRANE-OPERATOR", worker_no=wno,
                equipment_item_id=item(db, tag).id, crew_role="crane_operator", **kw)  # fmt: skip


def test_P4AC56_Z7_zaheer_scope(db: Session) -> None:
    assert _op(db, "ANIA-EXP", "WKR-000019", "RW-MC-03").status == RS.met
    tc = _op(db, "ANIA-EXP", "WKR-000019", "TC-01")
    assert reason(tc) == "CERT_SCOPE_MISMATCH"
    dl = _op(db, "ANIA-EXP", "WKR-000019", "DL-MC-01")
    assert dl.status == RS.met  # 60 ≤ 60: scope met; the equipment check is the crane's own
    crane = hook(db, "RBT-52", EC, "CRANE-TPI", tag="DL-MC-01")
    assert crane.status != RS.met
    big = _op(db, "ANIA-EXP", "WKR-000019", "RW-MC-03", rated_capacity_t=Decimal("70.000"))
    assert reason(big) == "CERT_SCOPE_MISMATCH"


def test_P4AC57_ali_hassan_tower_crane(db: Session) -> None:
    assert _op(db, "RBT-52", "WKR-000102", "TC-01").status == RS.met


def test_P4AC58_osman_rigger_level_on_critical_lift(db: Session) -> None:
    kw = {"worker_no": "WKR-000009", "crew_role": "rigger"}
    crit = hook(db, "ANIA-EXP", PC, "RIGGER", critical=True, when=riyadh(2026, 10, 7), **kw)
    assert crit.status == RS.warn and reason(crit) == "CERT_SCOPE_MISMATCH"
    blk = hook(db, "ANIA-EXP", PC, "RIGGER", critical=True, when=riyadh(2026, 10, 8), **kw)
    assert blk.status == RS.not_met
    assert hook(db, "ANIA-EXP", PC, "RIGGER", **kw).status == RS.met


def test_P4AC59_signaller_trainee_logbook(db: Session) -> None:
    pc = pcert(db, "AICC-SG-TEST-25-0303")
    pc.limitations = [{"code": "trainee_logbook", "text": None}]
    db.flush()
    kw = {"worker_no": "WKR-000108", "crew_role": "signaller"}
    crit = hook(db, "RBT-52", PC, "SIGNALLER", critical=True, **kw)
    assert reason(crit) == "CERT_LIMITATION"
    routine = hook(db, "RBT-52", PC, "SIGNALLER", **kw)
    assert routine.status == RS.met and routine.conditions


# ---- AC61 HSE suspension of an operator card ------------------------------------------------------------


def test_P4AC61_suspended_operator_card_is_hard_stop_on_permit(api: Api, db: Session) -> None:
    pc = pcert(db, "AICC-OP-TEST-24-0412")
    res = api.as_("faisal.harbi").post(
        f"{API}/personnel-certificates/{pc.id}/transitions",
        json={"to_status": "suspended", "reason": "Unsafe operation observed on site (test)."},
    )
    assert res.status_code == 200, res.text
    body = res.text
    assert "capability 49" in body or "ban" in body.lower()
    db.expire_all()
    assert worker(db, "WKR-000019").status.value != "banned"
    it = hook(db, "ANIA-EXP", PC, "CRANE-OPERATOR", worker_no="WKR-000019")
    assert it.status == RS.not_met and it.hard_stop
    db.expire_all()
    p = permit(db, "PTW-ANIA-EXP-2026-0410")
    evaluation.refresh(db, p, run_simops=False)
    assert "HOOK_NOT_MET" in [b["code"] for b in p.blockers or []]


# ---- AC73 RW-MEWP-07 on a WAH permit ---------------------------------------------------------------------


def test_P4AC73_out_of_service_mewp_hard_stop_on_permit(db: Session) -> None:
    p = permit(db, "PTW-ANIA-EXP-2026-0410")
    db.add(PermitEquipment(id=uuid.uuid4(), permit_id=p.id, category=EquipmentCategory.mewp,
                           tag="RW-MEWP-07", use=EquipmentUse.access_equipment, hooks=[],
                           operator_hooks=[], conditions=[]))  # fmt: skip
    db.flush()
    evaluation.refresh(db, p, run_simops=False)
    assert "HOOK_NOT_MET" in [b["code"] for b in p.blockers or []]


# ---- AC85-AC93 --------------------------------------------------------------------------------------------


def test_P4AC85_Z4_block_dates(api: Api, db: Session) -> None:
    for st in db.scalars(
        select(HookPolicyState).where(HookPolicyState.project_id == project(db, "ANIA-EXP").id)
    ):
        assert st.provider_registered_on == date(2026, 10, 1)
        assert st.critical_block_from == date(2026, 10, 8)
        assert st.general_block_from == date(2026, 10, 31)
        assert st.stage == HookStage.transition
    res = api.as_("faisal.harbi").get(f"{API}/projects/{project(db, 'ANIA-EXP').id}/hook-policy")
    assert res.status_code == 200, res.text
    assert res.json()["enabled"] is True


def test_P4AC86_Z4a_chain_sling_warn_then_block_and_suspend(db: Session) -> None:
    from app import cert_jobs

    p = permit(db, "PTW-ANIA-EXP-2026-0410")
    db.add(PermitEquipment(id=uuid.uuid4(), permit_id=p.id,
                           category=EquipmentCategory.lifting_accessory, tag="FX-ACC-0219",
                           use=EquipmentUse.lifting_accessory, hooks=[], operator_hooks=[],
                           conditions=[]))  # fmt: skip
    db.flush()
    evaluation.refresh(db, p, run_simops=False)
    warn = [w for w in p.warnings or [] if w["code"] == "HOOK_NOT_MET_WARN"]
    assert any("CERT_EXPIRED" in (w.get("detail") or "") for w in warn), p.warnings
    assert "HOOK_NOT_MET" not in [b["code"] for b in p.blockers or []]
    p.status = PermitStatus.active  # issued and active (Issue was allowed)
    db.flush()
    set_now(riyadh(2026, 10, 8, 0).replace(minute=0, second=30))
    cert_jobs.cert_switch(db)
    evaluation.refresh(db, p, run_simops=False)
    assert "HOOK_NOT_MET" in [b["code"] for b in p.blockers or []]
    assert p.status == PermitStatus.suspended
    assert p.status_reason is not None and p.status_reason.value == "hook_not_met"


def test_P4AC87_Z4b_expired_plant_line_on_vehicle(db: Session) -> None:
    it_ = item(db, "GP-EX-05")
    assert it_.vehicle_id is not None
    c = ecert(db, "AICC-EQ-TEST-26-0210")
    for ln in db.scalars(select(EquipmentCertLine).where(EquipmentCertLine.certificate_id == c.id)):
        ln.valid_until = date(2026, 10, 3)
    db.flush()
    w = hook(db, "ANIA-EXP", EC, "PLANT-TPI", vehicle_id=it_.vehicle_id, when=riyadh(2026, 10, 30))
    assert w.status == RS.warn and reason(w) == "CERT_EXPIRED"
    b = hook(db, "ANIA-EXP", EC, "PLANT-TPI", vehicle_id=it_.vehicle_id, when=riyadh(2026, 10, 31))
    assert b.status == RS.not_met


def test_P4AC88_Z4d_deferral_rules(api: Api, db: Session) -> None:
    c = api.as_("faisal.harbi")
    pid = project(db, "ANIA-EXP").id
    url = f"{API}/projects/{pid}/hook-policy/personnel_certificate/deferral"
    why = "Contractors need more time to collect cards (test reason)."
    too_long = c.post(url, json={"new_date": "2026-12-01", "reason": why})
    assert too_long.status_code == 422, too_long.text
    crit = c.post(url, json={"new_date": "2026-11-15", "reason": why, "codes": ["CRANE-OPERATOR"]})
    assert crit.status_code == 422 and "CRITICAL_CODE_NO_DEFERRAL" in crit.text
    ok = c.post(url, json={"new_date": "2026-11-30", "reason": why})
    assert ok.status_code == 200, ok.text
    again = c.post(url, json={"new_date": "2026-11-29", "reason": why})
    assert again.status_code in (409, 422) and "DEFERRAL_USED" in again.text
    sw = f"{API}/projects/{pid}/hook-policy/personnel_certificate/switch"
    assert c.post(sw, json={"codes": ["RIGGER"], "policy": "block"}).status_code == 200
    back = c.post(sw, json={"codes": ["RIGGER"], "policy": "warn"})
    assert back.status_code == 422 and "HOOK_POLICY_LOOSENING" in back.text


def test_P4AC89_early_switch_all_codes_rbt(api: Api, db: Session) -> None:
    from app.models import AuditEntry, Notification, User

    pid = project(db, "RBT-52").id
    res = api.as_("faisal.harbi").post(
        f"{API}/projects/{pid}/hook-policy/equipment_certificate/switch",
        json={"all_codes": True, "policy": "block"},
    )
    assert res.status_code == 200, res.text
    it = hook(db, "RBT-52", EC, "CRANE-TPI", tag="DL-MC-01")
    assert it.status == RS.not_met
    db.expire_all()
    assert (
        db.scalar(select(AuditEntry.id).where(AuditEntry.entity_type == "hook_policy_state"))
        is not None
    )
    who = {
        u.email.split("@")[0]
        for u in db.scalars(
            select(User)
            .join(Notification, Notification.user_id == User.id)
            .where(Notification.kind == "hook_policy_changed")
        )
    }
    assert {"lina.haddad", "yousef.ghamdi"} <= who, who


def test_P4AC90_equipment_tag_without_project_is_caller_error(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.cert import providers

    seen: list[str] = []
    monkeypatch.setattr(providers.log, "warning", lambda msg, *a: seen.append(msg % a))
    if True:
        res = providers.check(db, HookSubjectType.equipment_tag, uuid.uuid4(), EC, "CRANE-TPI",
                              riyadh(2026, 10, 6), HookContext(equipment_tag="RW-MC-03"), None)  # fmt: skip
    assert res.reason_code == "EQUIPMENT_NOT_REGISTERED"
    assert any("caller error" in x for x in seen)


def test_P4AC91_status_event_reevaluates_permits(api: Api, db: Session) -> None:
    pc = pcert(db, "AICC-OP-TEST-25-0815")  # Ali Hassan, TC-01 operator on PTW-RBT-52-0290
    res = api.as_("faisal.harbi").post(
        f"{API}/personnel-certificates/{pc.id}/transitions",
        json={"to_status": "suspended", "reason": "Card under investigation by the TPI (test)."},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    p = permit(db, "PTW-RBT-52-2026-0290")
    line = db.scalar(
        select(PermitEquipment).where(
            PermitEquipment.permit_id == p.id, PermitEquipment.tag == "TC-01"
        )
    )
    assert line is not None
    assert [h["status"] for h in line.operator_hooks] == ["not_met"]
    assert "HOOK_NOT_MET" in [b["code"] for b in p.blockers or []]


def test_P4AC92_Z10_avp_equipment_certificate_limit(db: Session) -> None:
    from app.models import Avp
    from app.services.access import lifecycle

    a = db.scalar(select(Avp).where(Avp.avp_no == "AVP-OEXX-26-0120"))
    assert a is not None
    assert a.effective_valid_until == date(2026, 11, 5)
    assert a.limiting_factor is not None and a.limiting_factor.value == "equipment_certificate"
    set_now(riyadh(2026, 11, 6))
    lifecycle.evaluate_avp(db, a)
    assert a.validity_status.value == "suspended"
    c = ecert(db, "AICC-EQ-TEST-25-1106")
    for ln in db.scalars(select(EquipmentCertLine).where(EquipmentCertLine.certificate_id == c.id)):
        ln.valid_until = date(2027, 11, 5)
    db.flush()
    lifecycle.evaluate_avp(db, a)
    assert a.validity_status.value == "active"


def test_P4AC93_readiness_report(api: Api, db: Session) -> None:
    res = api.as_("faisal.harbi").get(
        f"{API}/projects/{project(db, 'ANIA-EXP').id}/hook-readiness",
        params={"kind": "personnel_certificate"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    rig = next(c for c in body["codes"] if c["code"] == "RIGGER")
    assert rig["required"] >= rig["in_force"] >= 0
    assert rig["not_met"]
    assert body["affected"] and body["affected"][0]["on_date"] == "2026-10-08"


def test_operator_required_and_line_binding(api: Api, db: Session) -> None:
    """3-ptw v1.1 §11.4 / HK4-9: a crane line without an operator → 422 OPERATOR_REQUIRED; with
    Zaheer → the line carries the item, the operator hook and the certified SWL."""
    from tests.ptw_helpers import permit as ptw_permit

    p = ptw_permit(db, "PTW-ANIA-EXP-2026-0410")
    c = api.as_("ahmed.zahrani")
    url = f"{API}/permits/{p.id}/equipment"
    body = {
        "equipment_tag": {"category": "mobile_crane", "tag": "NJ-MC-02"},
        "use": "lifting_appliance",
    }
    res = c.post(url, json=body)
    assert res.status_code == 422 and "OPERATOR_REQUIRED" in res.text, res.text
    res = c.post(url, json={**body, "operator_worker_id": str(worker(db, "WKR-000019").id)})
    assert res.status_code in (200, 201), res.text
    line = res.json()
    assert line["equipment_item"]["equipment_no"]
    assert codes(line["operator_hooks"]) == ["CRANE-OPERATOR"]
    assert line["swl_t"] == "40.000"


def test_scaffold_ref_resolved_in_permit_read(api: Api, db: Session) -> None:
    p = _wah_on_scaffold(db, "SC-0003")
    db.commit()
    res = api.as_("faisal.harbi").get(f"{API}/permits/{p.id}")
    assert res.status_code == 200, res.text
    wah = next(s for s in res.json()["sections"] if "scaffold_tag_ref" in s)
    assert wah["scaffold"]["tag"] == "SC-0003"
