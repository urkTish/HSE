"""5-training §9 ACs 3, 8, 85-106, 123, 135-138 (training hook, gaps, plan, alerts)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, HookSubjectType, RequirementStatus
from app.core.cert_enums import HookStage
from app.core.clock import set_now
from app.models import HookPolicyState, Notification, Permit, QrToken, TrainingRecord
from app.services.access import common as acommon
from app.services.access import eligibility as elig
from app.services.access.hooks import HookContext
from app.services.cert import policy
from tests.cert_helpers import scan
from tests.conftest import Api
from tests.train_helpers import API, project, record, riyadh, worker

pytestmark = pytest.mark.usefixtures("train_seed", "clock")

TC = HookKind.training_course
RS = RequirementStatus


def hook(
    db: Session, worker_no: str, code: str, when: datetime | None = None, pcode: str = "ANIA-EXP"
) -> elig.Item:
    from app.services.train import hook as thook

    pid = project(db, pcode).id
    s = acommon.settings(db, pid)
    policy.clear_cache(db)
    thook.clear_cache(db)
    hc = HookContext(project_id=pid)
    w = worker(db, worker_no)
    return elig.hook_item(db, HookSubjectType.worker, w.id, TC, code, when or riyadh(2026, 10, 6),
                          s, hc)  # fmt: skip


def reason(it: elig.Item) -> str | None:
    return it.to_schema().model_dump(mode="json").get("hook_reason_code")


def test_P5AC3_gas_test_answered_by_phase5(db: Session) -> None:
    it = hook(db, "WKR-000018", "GAS-TEST")
    assert it.status == RS.met, (it.status, reason(it))
    assert it.valid_until == date(2028, 4, 14), it.valid_until


def test_P5AC8_rescue_satisfies_attendant(db: Session) -> None:
    it = hook(db, "WKR-000021", "CSE-ATTENDANT")
    assert it.status in (RS.met, RS.expiring), (it.status, reason(it))


def test_P5AC93_P5AC94_biju_warn_then_block(db: Session) -> None:
    it = hook(db, "WKR-000017", "CSE-ATTENDANT")
    assert it.status == RS.warn and it.reason is not None
    assert it.reason.value == "HOOK_NOT_MET_WARN" and reason(it) == "TRAINING_MISSING"
    it = hook(db, "WKR-000017", "CSE-ATTENDANT", riyadh(2026, 10, 8, 0, 1))
    assert it.status == RS.not_met and it.reason is not None
    assert it.reason.value == "HOOK_NOT_MET"


def test_P5AC94_permit_suspended_at_switch(db: Session) -> None:
    from app import cert_jobs
    from app.core.ptw_enums import PermitStatus
    from app.services.ptw import evaluation

    p = db.scalar(select(Permit).where(Permit.permit_no == "PTW-ANIA-EXP-2026-0413"))
    assert p is not None
    assert p.status == PermitStatus.active
    set_now(riyadh(2026, 10, 8, 0).replace(minute=0, second=30))
    cert_jobs.cert_switch(db)
    evaluation.refresh(db, p, run_simops=False)
    assert "HOOK_NOT_MET" in [b["code"] for b in p.blockers or []], p.blockers
    assert p.status == PermitStatus.suspended


def test_P5AC96_P5AC97_rajesh_avsec(db: Session) -> None:
    it = hook(db, "WKR-000002", "AVSEC-AWR")
    assert it.status in (RS.met, RS.expiring) and it.valid_until == date(2026, 10, 12)
    it = hook(db, "WKR-000002", "AVSEC-AWR", riyadh(2026, 10, 13))
    assert it.status == RS.warn, (it.status, reason(it))
    it = hook(db, "WKR-000002", "AVSEC-AWR", riyadh(2026, 10, 31))
    assert it.status == RS.not_met


def test_P5AC106_fire_watch_shift_date(db: Session) -> None:
    it = hook(db, "WKR-000015", "FIRE-WATCH", riyadh(2026, 10, 10, 18))
    assert it.status in (RS.met, RS.expiring), (it.status, reason(it))
    it = hook(db, "WKR-000015", "FIRE-WATCH", riyadh(2026, 10, 11, 8))
    assert it.status in (RS.warn, RS.not_met) and reason(it) == "TRAINING_EXPIRED", reason(it)


def test_P5AC102_revoked_wah_hard_stop(api: Api, db: Session) -> None:
    r = record(db, "WKR-000001", "WAH")
    res = api.as_("faisal.harbi").post(
        f"{API}/training-records/{r.id}/transitions",
        json={"action": "revoke", "reason_code": "hse_revocation",
              "reason": "Card obtained without attending the course (test)"},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    db.expire_all()
    it = hook(db, "WKR-000001", "WAH")
    assert it.status == RS.not_met and it.hard_stop, (it.status, reason(it))
    assert reason(it) == "TRAINING_REVOKED"


def test_P5AC92_policy_state(db: Session) -> None:
    st = db.scalar(
        select(HookPolicyState).where(
            HookPolicyState.project_id == project(db, "ANIA-EXP").id,
            HookPolicyState.kind == TC,
        )
    )
    assert st is not None
    assert st.critical_block_from == date(2026, 10, 8)
    assert st.general_block_from == date(2026, 10, 31)
    assert st.stage == HookStage.transition


def test_P5AC98_P5AC99_deferral_and_switch(api: Api, db: Session) -> None:
    c = api.as_("faisal.harbi")
    pid = project(db, "ANIA-EXP").id
    url = f"{API}/projects/{pid}/hook-policy/training_course/deferral"
    why = "Contractors need more time to train their crews (test reason)."
    crit = c.post(url, json={"new_date": "2026-11-15", "reason": why, "codes": ["WAH"]})
    assert crit.status_code == 422 and "CRITICAL_CODE_NO_DEFERRAL" in crit.text, crit.text
    ok = c.post(url, json={"new_date": "2026-11-30", "reason": why})
    assert ok.status_code == 200, ok.text
    again = c.post(url, json={"new_date": "2026-11-29", "reason": why})
    assert again.status_code in (409, 422) and "DEFERRAL_USED" in again.text
    sw = f"{API}/projects/{pid}/hook-policy/training_course/switch"
    res = c.post(sw, json={"codes": ["CSE-ATTENDANT"], "policy": "block"})
    assert res.status_code == 200, res.text
    back = c.post(sw, json={"codes": ["CSE-ATTENDANT"], "policy": "warn"})
    assert back.status_code == 422 and "HOOK_POLICY_LOOSENING" in back.text


def test_P5AC105_readiness(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    for who in ("faisal.harbi", "ahmed.zahrani"):
        res = api.as_(who).get(f"{API}/projects/{pid}/hook-readiness",
                               params={"kind": "training_course"})  # fmt: skip
        assert res.status_code == 200, res.text
        assert res.json()["codes"], res.text


def test_P5AC91_register_not_live(api: Api, db: Session) -> None:
    from app.models import HseSettings

    pid = project(db, "RBT-52").id
    hs = db.scalar(select(HseSettings).where(HseSettings.project_id == pid))
    assert hs is not None
    hs.training_register_from = None
    for st in db.scalars(select(HookPolicyState).where(HookPolicyState.project_id == pid,
                                                         HookPolicyState.kind == TC)):  # fmt: skip
        db.delete(st)
    db.commit()
    res = api.as_("faisal.harbi").post(f"{API}/projects/{pid}/training-hooks/enable", json={})
    assert res.status_code == 422 and "TRAINING_REGISTER_NOT_LIVE" in res.text, res.text


def test_P5AC85_gap_register_scope(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    res = api.as_("ahmed.zahrani").get(f"{API}/projects/{pid}/training-gaps",
                                       params={"page_size": 200})  # fmt: skip
    assert res.status_code == 200, res.text
    engs = {g["engagement"]["short_code"] for g in res.json()["items"]}
    assert engs and "QIMMA" not in engs, engs
    res = api.as_("sarah.mitchell").get(f"{API}/projects/{pid}/training-gaps")
    assert res.status_code == 403, res.text
    res = api.as_("sarah.mitchell").get(f"{API}/projects/{pid}/training-gaps/summary")
    assert res.status_code == 200, res.text


def test_P5AC86_rajesh_booked_late(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    items: list[dict[str, Any]] = []
    for page in range(1, 20):
        res = api.as_("noura.qahtani").get(f"{API}/projects/{pid}/refresher-plan",
                                           params={"page_size": 200, "page": page})  # fmt: skip
        assert res.status_code == 200, res.text
        items += res.json()["items"]
        if len(res.json()["items"]) < 200:
            break
    raj = [i for i in items if i["worker"]["worker_no"] == "WKR-000002"]
    assert raj, len(items)
    assert raj[0]["state"] == "booked_late", raj[0]


def test_P5AC123_tr_qr_at_gate(api: Api, db: Session) -> None:
    r = db.scalars(select(TrainingRecord).where(TrainingRecord.session_id.is_not(None))).first()
    assert r is not None
    tok = db.scalar(select(QrToken).where(QrToken.subject_id == r.id))
    assert tok is not None
    out = scan(api.as_("noura.qahtani"), db, "G-ANIA-01", payload=f"HSE2:TR:{tok.token}")
    assert out["result"] == "DENIED", out
    assert "TOKEN_UNKNOWN" in [x["code"] for x in out["reasons"]], out


def _alerts(db: Session, rid: uuid.UUID) -> int:
    return int(
        db.scalar(select(func.count(Notification.id)).where(Notification.entity_id == rid)) or 0
    )


def test_P5AC135_P5AC137_long_schedule(db: Session) -> None:
    from app.train_jobs import training_alerts

    r = record(db, "WKR-000025", "PTW-ISSUER")
    assert r.valid_until == date(2026, 10, 25), r.valid_until
    n0 = _alerts(db, r.id)
    training_alerts(db, riyadh(2026, 10, 11, 7, 2))
    n1 = _alerts(db, r.id)
    assert n1 > n0
    training_alerts(db, riyadh(2026, 10, 11, 7, 30))
    assert _alerts(db, r.id) == n1  # AC137: no duplicate on re-run
    rows: Any = db.scalars(select(Notification).where(Notification.entity_id == r.id)).all()
    assert all("WKR-000025" in (n.title_en or "") for n in rows[-1:]), [n.title_en for n in rows]


def test_P5AC77_accepted_but_unverified_not_in_force(api: Api, db: Session) -> None:
    from tests.cert_helpers import upload_pdf
    from tests.train_helpers import provider

    noura = api.as_("noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    res = noura.post(
        f"{API}/projects/{pid}/training-records",
        json={"worker_id": str(worker(db, "WKR-000017").id), "project_id": str(pid),
              "course_code": "FIRST-AID", "provider_id": str(provider(db, "HAYAT").id),
              "certificate_no": "HY-FA-TEST-26-0977", "completed_on": "2026-09-01",
              "name_as_printed": "Biju Thomas", "id_on_card": {"shown": False}},
    )  # fmt: skip
    assert res.status_code == 201, res.text
    rid = res.json()["id"]
    scan_id = upload_pdf(noura, "training_record_scan", rid)
    noura.patch(f"{API}/training-records/{rid}", json={"scan_attachment_id": scan_id})
    res = noura.post(f"{API}/training-records/{rid}/transitions", json={"action": "submit"})
    assert res.status_code == 200, res.text
    res = api.as_("faisal.harbi").post(
        f"{API}/training-records/{rid}/transitions", json={"action": "accept"}
    )
    assert res.status_code == 200 and res.json()["status"] == "accepted", res.text
    assert res.json()["verification_status"] == "not_verified"
    db.expire_all()
    it = hook(db, "WKR-000017", "FIRST-AID")
    assert it.status != RS.met and reason(it) == "TRAINING_UNVERIFIED", (it.status, reason(it))


def test_P5AC133_viewer_sees_aggregates_only(api: Api, db: Session) -> None:
    sarah = api.as_("sarah.mitchell")
    pid = str(project(db, "ANIA-EXP").id)
    res = sarah.get(f"{API}/kpi/training", params={"project_id": pid, "as_of": "2026-09-30"})
    assert res.status_code == 200, res.text
    assert "WKR-" not in res.text
    assert sarah.get(f"{API}/projects/{pid}/training-gaps").status_code == 403
