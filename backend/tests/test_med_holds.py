"""6a-occupational-health §9 ACs 59-76, 79-80 (holds, referrals, return to work)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.core.ptw_enums import PermitStatus
from app.models import (
    Deployment,
    FitnessHold,
    FitnessReferral,
    Incident,
    Notification,
    Permit,
    PersonnelCertificate,
    User,
)
from tests.conftest import Api, Ids
from tests.hse_helpers import add_case, create_incident, transition
from tests.med_helpers import (
    API,
    CLOCK,
    body,
    err,
    fit,
    hold,
    hook,
    ok,
    post,
    project,
    reason,
    riyadh,
    worker,
)

pytestmark = pytest.mark.usefixtures("med_seed", "clock")


def _case(c: Any, ids: Ids, inc_id: str, wno: str, db: Session, **over: Any) -> dict[str, Any]:
    w = worker(db, wno)
    kw: dict[str, Any] = {
        "worker_id": str(w.id),
        "person_name": w.full_name_en,
        "id_type": None,
        "id_number": None,
        "trade": "labourer",
        "employer_engagement_id": ids.engagement("RAWABI"),
    }
    kw.update(over)
    return add_case(c, ids, inc_id, **kw)  # type: ignore[no-any-return]


def _holds(db: Session, wno: str) -> list[FitnessHold]:
    db.expire_all()
    return list(
        db.scalars(
            select(FitnessHold)
            .where(FitnessHold.worker_id == worker(db, wno).id)
            .order_by(FitnessHold.started_at)
        )
    )


def _user(db: Session, name: str) -> Any:
    return db.scalar(select(User).where(User.email == f"{name}@example.com"))


def _notified(db: Session, name: str, kind: str) -> int:
    u = _user(db, name)
    return len(
        list(
            db.scalars(
                select(Notification).where(Notification.user_id == u.id, Notification.kind == kind)
            )
        )
    )


# ---- holds from injury cases (FH-1a, FH-2, FH-4, FH-5) ------------------------------------------


def test_AC59_AC62_AC64_lti_hold_blocks_permit_then_reclassified(
    api: Api, ids: Ids, db: Session
) -> None:
    noura = api.as_("noura.qahtani")
    inc = create_incident(noura, ids, occurred_at="2026-10-03T06:40:00Z")  # entered 10-06
    case = _case(noura, ids, inc["id"], "WKR-000016", db, away_start_date="2026-10-04")
    assert _holds(db, "WKR-000016") == []  # draft incident: no hold yet
    assert transition(noura, inc["id"], "reported").status_code == 200
    (h,) = _holds(db, "WKR-000016")
    assert h.reason.value == "rtw_after_injury" and h.status.value == "active"
    assert h.started_at == CLOCK  # FH-5: creation time, not the event date
    it = hook(db, "WKR-000016", "CSE-ENTRY-FIT")
    assert it.status.value == "not_met" and it.hard_stop and reason(it) == "MEDICAL_HOLD"
    p = db.scalar(select(Permit).where(Permit.permit_no == "PTW-ANIA-EXP-2026-0413"))
    assert p is not None and p.status == PermitStatus.suspended, (p.status, p.blockers)
    # AC62: reclassified to FAC (no absence) before release → Cancelled source_reclassified
    res = noura.patch(f"{API}/injury-cases/{case['id']}", json={"away_start_date": None})
    assert res.status_code == 200, res.text
    (h,) = _holds(db, "WKR-000016")
    assert h.status.value == "cancelled" and h.cancel_code is not None
    assert h.cancel_code.value == "source_reclassified"


def test_AC60_AC61_AC63_heat_hold_mtc_no_hold_and_void(api: Api, ids: Ids, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    inc = create_incident(noura, ids, occurred_at="2026-10-05T10:40:00Z")
    _case(noura, ids, inc["id"], "WKR-000016", db, nature="heat_exhaustion",
          treatments=["fluids_oral_heat"], body_part="whole_body")  # fmt: skip
    _case(noura, ids, inc["id"], "WKR-000034", db, treatments=["sutures_staples_glue"])
    assert transition(noura, inc["id"], "reported").status_code == 200
    (h,) = _holds(db, "WKR-000016")
    assert h.reason.value == "heat_illness"
    assert [x.reason.value for x in _holds(db, "WKR-000034")] == ["referral"]  # seeded only
    res = transition(api.as_("faisal.harbi"), inc["id"], "voided", reason="duplicate report (test)")
    assert res.status_code == 200, res.text
    (h,) = _holds(db, "WKR-000016")
    assert h.status.value == "cancelled" and h.cancel_code is not None
    assert h.cancel_code.value == "source_voided"


# ---- release, manual holds, deployment unchanged (FH-3, FH-6, FH-7, FA-5) -----------------------


def test_AC65_AC69_release_only_by_assessment(api: Api, db: Session) -> None:
    h = hold(db, "MFH-ANIA-EXP-2026-00027")
    res = api.as_("faisal.harbi").post(f"{API}/fitness-holds/{h.id}/release")
    assert res.status_code == 422 and err(res) == "HOLD_RELEASE_REQUIRES_ASSESSMENT", res.text
    dep = db.scalar(select(Deployment).where(Deployment.worker_id == h.worker_id))
    assert dep is not None and dep.status.value == "mobilised"
    assert worker(db, "WKR-000034").status.value == "active"


def test_AC66_AC80_rtw_reference_and_restricted_days_prompt(
    api: Api, ids: Ids, db: Session
) -> None:
    noura = api.as_("noura.qahtani")
    inc = create_incident(noura, ids, occurred_at="2026-10-02T06:40:00Z")
    _case(noura, ids, inc["id"], "WKR-000016", db, away_start_date="2026-10-03")
    assert transition(noura, inc["id"], "reported").status_code == 200
    (h,) = _holds(db, "WKR-000016")
    huda = api.as_("huda.mansour")
    rtw: dict[str, Any] = {"typ": "return_to_work", "related_hold_id": str(h.id)}
    res = post(huda, db, body(db, "WKR-000016", [fit("WAH-FIT")], **rtw))
    assert err(res) == "HOLD_REFERENCE_INVALID", res.text
    line = fit(
        "GEN-FIT",
        "fit_with_restrictions",
        restrictions=[{"code": "no_heavy_lifting", "value": "15"}],
        restriction_review_date="2026-11-05",
    )
    ok(post(huda, db, body(db, "WKR-000016", [line], **rtw)))
    (h,) = _holds(db, "WKR-000016")
    assert h.status.value == "released"
    assert _notified(db, "noura.qahtani", "fitness_restricted_days_prompt") == 1
    db.expire_all()
    inc_row = db.get(Incident, inc["id"])
    assert inc_row is not None and inc_row.status.value == "reported"  # case unchanged (RW-3)


def test_AC67_AC68_manual_hold_then_unfit_rtw(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    w = worker(db, "WKR-000014")
    url = f"{API}/projects/{pid}/fitness-holds"
    res = noura.post(url, json={"worker_id": str(w.id), "reason_text": "dizzy spel"})
    assert res.status_code == 422, res.text
    text = "Reported dizziness on the platform; keep off duty until assessed"
    h = ok(noura.post(url, json={"worker_id": str(w.id), "reason_text": text}))
    assert h["status"] == "active"
    res = noura.post(f"{API}/fitness-holds/{h['id']}/cancel", json={"reason": "x" * 30})
    assert res.status_code == 403, res.text
    line = fit("GEN-FIT", "temporarily_unfit", unfit_review_date="2026-11-05")
    rtw: dict[str, Any] = {"typ": "return_to_work", "related_hold_id": h["id"]}
    ok(post(api.as_("huda.mansour"), db, body(db, "WKR-000014", [line], **rtw)))
    assert _holds(db, "WKR-000014")[-1].status.value == "released"
    for code in ("GEN-FIT", "NOISE-SURV"):
        it = hook(db, "WKR-000014", code)
        assert it.status.value == "not_met" and it.hard_stop and reason(it) == "MEDICAL_UNFIT"


# ---- work during hold (FH-8a, FH-8c) -------------------------------------------------------------


def test_AC70_admitted_despite_denial_logged(db: Session) -> None:
    h = hold(db, "MFH-ANIA-EXP-2026-00016")  # MF3c seed: gate entry during the hold
    assert h.status.value == "released" and h.work_during_hold
    assert [x["event_type"] for x in h.work_during_hold] == ["gate_entry"]


def test_AC79_rtw_before_clearance(api: Api, db: Session) -> None:
    h = hold(db, "MFH-ANIA-EXP-2026-00015")
    assert h.source_id is not None and h.released_at is not None
    res = api.as_("noura.qahtani").patch(
        f"{API}/injury-cases/{h.source_id}", json={"rtw_date": "2026-09-27"}
    )
    assert res.status_code == 200, res.text
    assert "RTW_BEFORE_CLEARANCE" in [w["code"] for w in res.json().get("warnings", [])]
    db.expire_all()
    h = hold(db, "MFH-ANIA-EXP-2026-00015")
    assert [x["event_type"] for x in h.work_during_hold][-1] == "rtw_before_clearance"
    assert _notified(db, "faisal.harbi", "fitness_rtw_before_clearance") == 1
    assert _notified(db, "huda.mansour", "fitness_rtw_before_clearance") == 1


# ---- referrals (RF-2 … RF-7, §7) -----------------------------------------------------------------


def _refer(c: Any, db: Session, wno: str, **kw: Any) -> Any:
    b = {"worker_id": str(worker(db, wno).id), "reason": "observed_unwell",
         "remove_from_work": False, **kw}  # fmt: skip
    return c.post(f"{API}/projects/{project(db, 'ANIA-EXP').id}/fitness-referrals", json=b)


def test_AC71_AC72_AC73_referral_scope_hold_and_cancel(api: Api, db: Session) -> None:
    faris = api.as_("faris.anazi")
    assert _refer(faris, db, "WKR-000014").status_code == 403  # NAJD worker
    ok(_refer(faris, db, "WKR-000016"))  # RAWABI worker
    fahad = api.as_("fahad.mutairi")
    before = _notified(db, "grace.villanueva", "fitness_referral_raised")
    r = ok(_refer(fahad, db, "WKR-000014", remove_from_work=True))
    assert r["hold_no"] and r["due_at"].startswith("2026-10-07T07:00")
    assert _notified(db, "grace.villanueva", "fitness_referral_raised") == before + 1
    assert _notified(db, "huda.mansour", "fitness_referral_raised") >= 1
    url = f"{API}/fitness-referrals/{r['id']}/cancel"
    assert fahad.post(url, json={"reason": "raised against the wrong worker"}).status_code == 403
    r2 = ok(_refer(fahad, db, "WKR-000013"))
    url = f"{API}/fitness-referrals/{r2['id']}/cancel"
    assert fahad.post(url, json={"reason": "short"}).status_code == 422
    ok(fahad.post(url, json={"reason": "raised against the wrong worker"}))


def test_AC74_overdue_alerts(db: Session) -> None:
    from app import med_jobs

    r = db.scalar(
        select(FitnessReferral).where(FitnessReferral.referral_no == "MFR-ANIA-EXP-2026-00031")
    )
    assert r is not None and r.due_at == riyadh(2026, 10, 7, 8, 40)
    set_now(r.due_at)
    assert med_jobs.medical_minute(db)["referrals_overdue"] == 1
    assert med_jobs.medical_minute(db)["referrals_overdue"] == 0  # once
    for name in ("huda.mansour", "grace.villanueva", "noura.qahtani"):
        assert _notified(db, name, "fitness_referral_overdue") == 1, name
    assert _notified(db, "faisal.harbi", "fitness_referral_overdue") == 0
    set_now(r.due_at + timedelta(hours=24))
    med_jobs.medical_minute(db)
    assert _notified(db, "faisal.harbi", "fitness_referral_overdue") == 1


def test_AC75_heat_referral_warns_incident_expected(api: Api, db: Session) -> None:
    n = len(list(db.scalars(select(Incident.id))))
    r = ok(_refer(api.as_("fahad.mutairi"), db, "WKR-000014", reason="heat_illness_episode"))
    assert "INCIDENT_RECORD_EXPECTED" in [w["code"] for w in r["warnings"]]
    assert r["incident_draft_link"]
    assert len(list(db.scalars(select(Incident.id)))) == n


def test_AC76_rf7_card_restriction_referral(db: Session) -> None:
    from app.services.med import config

    pid = project(db, "ANIA-EXP").id
    pc = db.scalar(
        select(PersonnelCertificate).where(
            PersonnelCertificate.project_id == pid, PersonnelCertificate.worker_id.is_not(None)
        )
    )
    assert pc is not None
    pc.medical_restriction_on_card = True
    pc.restriction_reviewed_at = None
    db.flush()
    assert config.rf7_referrals(db, pid, None) >= 1
    r = db.scalar(select(FitnessReferral).where(FitnessReferral.source_cert_id == pc.id))
    assert r is not None and r.reason.value == "certificate_restriction"
    assert r.remove_from_work is False and r.hold_id is None
