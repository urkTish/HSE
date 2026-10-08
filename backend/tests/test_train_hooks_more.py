"""5-training §9 hook / alert / audit ACs not covered elsewhere: 87, 95, 100, 101, 103, 104,
124, 136, 138, 146, 147, and the two §8.3 action-panel items (block soon, holders)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, HookSubjectType, RequirementStatus
from app.core.clock import set_now
from app.main import app
from app.models import AuditEntry, HookPolicyState, Notification, Permit
from tests.cert_helpers import upload_pdf
from tests.conftest import Api
from tests.train_helpers import API, project, provider, record, riyadh, worker

pytestmark = pytest.mark.usefixtures("train_seed", "clock")

RS = RequirementStatus
TC = HookKind.training_course


def hook(db: Session, sid: uuid.UUID, code: str, at: datetime, pcode: str = "ANIA-EXP") -> Any:
    from app.services.access import common as acommon
    from app.services.access import eligibility as elig
    from app.services.access.hooks import HookContext
    from app.services.cert import policy
    from app.services.train import hook as thook

    pid = project(db, pcode).id
    policy.clear_cache(db)
    thook.clear_cache(db)
    return elig.hook_item(db, HookSubjectType.worker, sid, TC, code, at,
                          acommon.settings(db, pid), HookContext(project_id=pid))  # fmt: skip


def reason(it: Any) -> str | None:
    return it.to_schema().model_dump(mode="json").get("hook_reason_code")


def notes(db: Session, entity_id: uuid.UUID, kind: str | None = None) -> int:
    q = select(Notification).where(Notification.entity_id == entity_id)
    if kind:
        q = q.where(Notification.kind == kind)
    return len(db.scalars(q).all())


def panel(api: Api, db: Session, who: str = "faisal.harbi") -> dict[str, dict[str, Any]]:
    pid = project(db, "ANIA-EXP").id
    res = api.as_(who).get(f"{API}/dashboard/action-panel", params={"project_id": str(pid)})
    assert res.status_code == 200, res.text
    return {i["key"]: i for i in res.json()["items"]}


def test_P5AC87_booked_holder_alerts(db: Session) -> None:
    """Ahmed Raza's FIRE-WATCH runs to 2026-10-10 and he is booked in time on 00058."""
    from app.train_jobs import training_alerts

    r = record(db, "WKR-000015", "FIRE-WATCH")
    assert r.valid_until == date(2026, 10, 10)
    n0 = notes(db, r.id, "training_record_expiry")
    training_alerts(db, riyadh(2026, 9, 26, 7))  # the 14-day step: booked in time → skipped
    assert notes(db, r.id, "training_record_expiry") == n0
    training_alerts(db, riyadh(2026, 10, 3, 7))  # the 7-day step: sent
    assert notes(db, r.id, "training_record_expiry") > n0
    it = hook(db, worker(db, "WKR-000015").id, "FIRE-WATCH", riyadh(2026, 10, 6, 10))
    assert it.status == RS.expiring and it.valid_until == date(2026, 10, 10)


def test_P5AC95_receiver_warn_then_ineligible(db: Session) -> None:
    sanjay = worker(db, "WKR-000028").id
    it = hook(db, sanjay, "PTW-RECEIVER", riyadh(2026, 10, 6, 23))
    assert it.status == RS.warn and it.reason is not None
    assert it.reason.value == "HOOK_NOT_MET_WARN", it.reason
    it = hook(db, sanjay, "PTW-RECEIVER", riyadh(2026, 10, 31, 9))
    assert it.status == RS.not_met
    # Phase 3 maps the not_met receiver hook to KEY_ROLE_INELIGIBLE
    from app.services.ptw import evaluation

    p = db.scalar(select(Permit).where(Permit.permit_no == "PTW-ANIA-EXP-2026-0408"))
    assert p is not None
    set_now(riyadh(2026, 10, 6, 23))
    evaluation.refresh(db, p, run_simops=False)
    assert "HOOK_NOT_MET_WARN" in str(p.warnings), p.warnings
    set_now(riyadh(2026, 10, 31, 0, 1))
    from app import cert_jobs

    cert_jobs.cert_switch(db)
    evaluation.refresh(db, p, run_simops=False)
    assert "KEY_ROLE_INELIGIBLE" in str(p.blockers), p.blockers


def test_P5AC100_switch_all_codes_early(api: Api, db: Session) -> None:
    set_now(riyadh(2026, 10, 10, 9))
    pid = project(db, "ANIA-EXP").id
    st = db.scalar(select(HookPolicyState).where(HookPolicyState.project_id == pid,
                                                 HookPolicyState.kind == TC))  # fmt: skip
    assert st is not None
    n0 = notes(db, st.id)
    res = api.as_("faisal.harbi").post(
        f"{API}/projects/{pid}/hook-policy/training_course/switch", json={"all_codes": True}
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    assert st.stage.value == "block" and st.all_switched_at is not None
    assert notes(db, st.id) > n0
    users = {n.user_id for n in db.scalars(select(Notification).where(
        Notification.entity_id == st.id))}  # fmt: skip
    from app.core.enums import Role
    from app.models import RoleAssignment

    roles = set(db.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id.in_(users))))
    assert {Role.hse_officer, Role.contractor_hse_rep} <= roles, roles
    assert db.scalar(select(AuditEntry.id).where(AuditEntry.entity_id == st.id)) is not None
    # HEAT-AWR (general, normally 10-31) now blocks
    it = hook(db, worker(db, "WKR-000017").id, "WAH", riyadh(2026, 10, 10, 10))
    assert it.status == RS.not_met


def test_P5AC101_unknown_code(db: Session) -> None:
    biju = worker(db, "WKR-000017").id
    it = hook(db, biju, "SCAFF-USER", riyadh(2026, 10, 6, 10))
    assert it.status == RS.warn, (it.status, reason(it))
    assert reason(it) == "UNKNOWN_CODE", reason(it)
    it = hook(db, biju, "SCAFF-USER", riyadh(2026, 11, 1, 10))
    assert it.status == RS.not_met, (it.status, reason(it))


def test_P5AC103_holder_not_linked_and_panel(api: Api, db: Session) -> None:
    from app.core.ptw_enums import AppointmentStatus
    from app.models import PtwAppointment, User

    it = hook(db, uuid.uuid4(), "PTW-ISSUER", riyadh(2026, 10, 6, 10))
    assert reason(it) == "HOLDER_NOT_LINKED", reason(it)
    assert it.status in (RS.warn, RS.not_met) and not it.hard_stop
    before = panel(api, db)["training_holders_not_linked"]["count"]
    # an active issuer appointment whose holder has no worker record
    pid = project(db, "ANIA-EXP").id
    a = db.scalars(select(PtwAppointment).where(
        PtwAppointment.project_id == pid, PtwAppointment.status == AppointmentStatus.active,
        PtwAppointment.function == "issuer")).first()  # fmt: skip
    assert a is not None
    sarah = db.scalar(select(User.id).where(User.email == "sarah.mitchell@example.com"))
    a.holder_user_id, a.holder_worker_id = sarah, None
    db.commit()
    item = panel(api, db)["training_holders_not_linked"]
    assert item["count"] == before + 1, item
    assert item["link"]["path"].endswith("/ptw-appointments"), item


def test_P5AC_panel_hook_block_soon_not_ready(api: Api, db: Session) -> None:
    """§8.3: the critical block date 2026-10-08 is ≤ 7 days from the clock and CSE-ATTENDANT
    (Biju, standby on PTW-0413) is < 100 % ready."""
    item = panel(api, db)["training_hook_block_soon_not_ready"]
    assert item["count"] >= 1, item
    assert item["link"]["query"] == {"kind": "training_course"}, item
    pid = project(db, "ANIA-EXP").id
    res = api.as_("faisal.harbi").get(f"{API}/projects/{pid}/hook-readiness",
                                      params={"kind": "training_course"})  # fmt: skip
    crit = [
        c for c in res.json()["codes"]
        if c["block_from"] == "2026-10-08" and c["in_force"] < c["required"]
    ]  # fmt: skip
    assert item["count"] == len(crit), (item, crit)
    set_now(riyadh(2026, 10, 20, 9))  # 10-31 is 11 days away; 10-08 already switched
    assert panel(api, db)["training_hook_block_soon_not_ready"]["count"] == 0


def test_P5AC104_record_changed_on_expiry(db: Session) -> None:
    from app.services.cert import events
    from app.services.train import records as rsvc

    r = record(db, "WKR-000015", "FIRE-WATCH")  # valid until 2026-10-10
    it = hook(db, worker(db, "WKR-000015").id, "FIRE-WATCH", riyadh(2026, 10, 10, 12))
    assert it.status in (RS.met, RS.expiring)
    n = rsvc.expiry_job(db, date(2026, 10, 11))
    assert n >= 1
    assert "training.record_changed" in events.published(db)
    db.refresh(r)
    assert r.status.value == "expired"
    from app.services.access import common as acommon
    from app.services.access import eligibility as elig
    from app.services.access.hooks import HookContext

    pid = project(db, "ANIA-EXP").id  # no cache clear here: the event already cleared it
    it = elig.hook_item(db, HookSubjectType.worker, worker(db, "WKR-000015").id, TC,
                        "FIRE-WATCH", riyadh(2026, 10, 11, 0, 7), acommon.settings(db, pid),
                        HookContext(project_id=pid))  # fmt: skip
    assert it.status != RS.met and reason(it) == "TRAINING_EXPIRED", (it.status, reason(it))


def test_P5AC136_renewal_cancels_steps(db: Session) -> None:
    """Majed's PTW-ISSUER runs to 2026-10-25: renewed in force on 10-15 (before the 7-day
    step), the 7- and 0-day alerts are not sent."""
    from app.core.cert_enums import VerificationStatus
    from app.core.train_enums import TrainingRecordStatus
    from app.models import TrainingRecord
    from app.train_jobs import training_alerts

    old = record(db, "WKR-000025", "PTW-ISSUER")
    training_alerts(db, riyadh(2026, 10, 11, 7))
    n1 = notes(db, old.id, "training_record_expiry")
    assert n1 >= 1
    new = TrainingRecord(
        id=uuid.uuid4(), seq=999001, record_no="TRR-999001", worker_id=old.worker_id,
        project_id=old.project_id, course_code="PTW-ISSUER", source=old.source,
        provider_id=old.provider_id, certificate_no="REN-PTW-ISSUER-1",
        completed_on=date(2026, 10, 15), valid_until=date(2028, 10, 14),
        status=TrainingRecordStatus.accepted, verification_status=VerificationStatus.verified,
        name_as_printed=old.name_as_printed, name_match=old.name_match,
        id_match_result=old.id_match_result, engagement_id=old.engagement_id,
        limiting_factor=old.limiting_factor, in_force_from=riyadh(2026, 10, 15, 9),
        verified_at=riyadh(2026, 10, 15, 9),
    )  # fmt: skip
    db.add(new)
    db.flush()
    for d in (18, 25):
        training_alerts(db, riyadh(2026, 10, d, 7))
    assert notes(db, old.id, "training_record_expiry") == n1


def test_P5AC138_hook_block_alerts(db: Session) -> None:
    from app import cert_jobs

    pid = project(db, "ANIA-EXP").id
    st = db.scalar(select(HookPolicyState).where(HookPolicyState.project_id == pid,
                                                 HookPolicyState.kind == TC))  # fmt: skip
    assert st is not None and st.critical_block_from == date(2026, 10, 8)
    seen = []
    for d in (date(2026, 10, 1), date(2026, 10, 6), date(2026, 10, 7)):
        before = notes(db, st.id)
        cert_jobs._hook_block(db, d)
        db.flush()
        seen.append(notes(db, st.id) > before)
    assert seen == [True, False, True], seen
    before = notes(db, st.id)
    cert_jobs.cert_switch(db, riyadh(2026, 10, 8, 0, 0).replace(second=30))
    db.flush()
    assert notes(db, st.id) > before


def test_P5AC124_ac_card_competence_mode(api: Api, db: Session) -> None:
    from app.core.enums import AuditAction
    from app.models import Deployment, QrToken
    from app.services.access import common as acommon

    pid = project(db, "ANIA-EXP").id
    biju = worker(db, "WKR-000017")
    d = db.scalar(select(Deployment).where(Deployment.worker_id == biju.id,
                                           Deployment.project_id == pid))  # fmt: skip
    assert d is not None
    t = db.scalar(select(QrToken).where(QrToken.subject_id == d.id)
                  .order_by(QrToken.created_at.desc()))  # fmt: skip
    assert t is not None
    n0 = len(db.scalars(select(AuditEntry.id).where(
        AuditEntry.action == AuditAction.cert_check_view)).all())  # fmt: skip
    res = api.as_("fahad.mutairi").post(
        f"{API}/certification-checks", json={"payload": acommon.payload(t), "project_id": str(pid)}
    )
    assert res.status_code == 200, res.text
    training = res.json()["person"]["training"]
    assert training, res.json()["person"]
    row = training[0]
    for k in ("in_force", "valid_until"):
        assert k in row, row
    txt = res.text
    for k in ("id_number", "theory_score", "scan"):
        assert k not in txt, k
    db.expire_all()
    n1 = len(db.scalars(select(AuditEntry.id).where(
        AuditEntry.action == AuditAction.cert_check_view)).all())  # fmt: skip
    assert n1 == n0 + 1


def test_P5AC146_gate_device_has_no_phase5_access(api: Api, db: Session) -> None:
    from tests.cert_helpers import gate

    g = gate(db, "G-ANIA-01")
    res = api.as_("noura.qahtani").post(
        f"{API}/gates/{g.id}/devices", json={"device_id": "GATE-TAB-T5", "label": "Test tab"}
    )
    assert res.status_code == 201, res.text
    login = TestClient(app).post(f"{API}/gate-device/login",
                                 json={"device_token": res.json()["device_token"]})  # fmt: skip
    assert login.status_code == 200, login.text
    dev = TestClient(app)
    dev.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    pid = project(db, "ANIA-EXP").id
    for path in (
        "/training-courses",
        f"/projects/{pid}/training-sessions",
        f"/projects/{pid}/training-records",
        f"/projects/{pid}/training-gaps",
        f"/projects/{pid}/training-matrix",
    ):
        r = dev.get(f"{API}{path}")
        assert r.status_code in (401, 403), (path, r.status_code)
    r = dev.post(f"{API}/projects/{pid}/training-sessions", json={})
    assert r.status_code in (401, 403, 422), r.status_code


def test_P5AC147_audit_without_ids_or_scores(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    body = {
        "worker_id": str(worker(db, "WKR-000017").id), "project_id": str(pid),
        "course_code": "FIRST-AID", "provider_id": str(provider(db, "HAYAT").id),
        "certificate_no": "HY-FA-AUD-1", "completed_on": "2026-09-01",
        "name_as_printed": "Biju Thomas", "theory_score_pct": "91.50",
        "id_on_card": {"shown": True, "id_type": "iqama", "id_number": "2000001017"},
    }  # fmt: skip
    res = noura.post(f"{API}/projects/{pid}/training-records", json=body)
    assert res.status_code == 201, res.text
    rid = res.json()["id"]
    upload_pdf(noura, "training_record_scan", rid)
    db.expire_all()
    rows = db.scalars(select(AuditEntry).where(AuditEntry.entity_id == uuid.UUID(rid))).all()
    assert rows and any(r.after for r in rows), "create audited with after"
    blob = str([(r.before, r.after, r.details) for r in rows])
    assert "2000001017" not in blob
    hist = api.as_("ahmed.zahrani").get(f"{API}/history/training_record/{rid}")
    assert hist.status_code == 200, hist.text
    assert "91.5" not in hist.text and "2000001017" not in hist.text
