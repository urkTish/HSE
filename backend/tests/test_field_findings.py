"""6d-field-assurance §9 ACs 21-29 (findings, CAs, repeats, critical alerts, stop-work)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.models import (
    ChecklistResponse,
    CorrectiveAction,
    FieldFinding,
    Inspection,
    PermitSuspension,
    StopWorkOrder,
)
from tests.field_helpers import (
    PNG,
    P,
    answers,
    body,
    expect,
    local,
    notified,
    project,
    stop_fields,
    submit,
    uid,
)
from tests.ptw_helpers import permit, resume, world

pytestmark = pytest.mark.usefixtures("field_seed", "clock")


def fd1(db: Session, nc: set[str], zone_code: str = "Z-LAY1", **kw: Any) -> dict[str, Any]:
    vals = kw.pop("vals", {})
    a = answers(db, "GSI", nc, GSI_21={"answer": "na"}, **vals)
    return body(db, zone_code=zone_code, answer_list=a, **kw)


def cas(db: Session, ins_id: Any) -> list[CorrectiveAction]:
    return list(db.scalars(select(CorrectiveAction).where(CorrectiveAction.source_id == ins_id)))


def test_AC21_cas_by_severity(db: Session) -> None:
    r = submit(db, "noura.qahtani", fd1(db, {"GSI-05", "GSI-12", "GSI-19"}, stop=stop_fields()))
    got = cas(db, r.inspection_id)
    assert len(got) == 1
    ca = got[0]
    assert (ca.priority.value, ca.source_type.value) == ("critical", "inspection")
    assert ca.due_date == ca.created_date + timedelta(days=1)
    assert ca.owner_id == uid(db, "ahmed.zahrani")
    assert ca.control_level.value == "engineering"
    db.rollback()
    r2 = submit(db, "noura.qahtani", fd1(db, {"GSI-12"}, vals={"GSI_12": {
        "answer": "non_compliant", "note": "Access route blocked by pallets", "ca_required": True}}))  # fmt: skip
    got2 = cas(db, r2.inspection_id)
    assert [c.priority.value for c in got2] == ["medium"]


def test_AC22_fix_on_spot_and_severity(db: Session) -> None:
    r = submit(db, "noura.qahtani", fd1(db, {"GSI-12"}, vals={"GSI_12": {
        "answer": "non_compliant", "note": "Access route blocked by pallets", "fixed_on_spot": True}}))  # fmt: skip
    assert cas(db, r.inspection_id) == []
    a = next(x for x in r.answers if x.item_code == "GSI-12")
    assert a.compliant is False and r.compliant_count == 20
    crit = {
        "answer": "non_compliant",
        "note": "Guardrail removed at slab edge",
        "photos": [{"file_name": "a.png", "content_base64": PNG}],
        "fixed_on_spot": True,
    }
    expect("FIX_ON_SPOT_NOT_ALLOWED", lambda: submit(db, "noura.qahtani", fd1(
        db, {"GSI-17"}, vals={"GSI_17": crit})))  # fmt: skip
    db.rollback()
    low = {**crit, "fixed_on_spot": False, "severity": "minor"}
    expect("SEVERITY_LOWERED", lambda: submit(db, "noura.qahtani", fd1(
        db, {"GSI-17"}, vals={"GSI_17": low})))  # fmt: skip


def test_AC23_fd3_repeats(db: Session) -> None:
    from app.schemas.field import InspectionVoid
    from app.services.field import execution

    f2 = db.scalar(select(FieldFinding).where(FieldFinding.item_code == "GSI-12",
                                              FieldFinding.project_id == project(db, "ANIA-EXP").id,
                                              FieldFinding.repeat_of_id.is_not(None)))  # fmt: skip
    assert f2 is not None and f2.severity.value == "major"
    f1 = db.get(FieldFinding, f2.repeat_of_id)
    assert f1 is not None
    second = _ins_of(db, f2)
    first = _ins_of(db, f1)
    ca = db.get(CorrectiveAction, f2.ca_id)
    assert ca is not None and ca.priority.value == "high"
    assert second.completed_date and first.completed_date
    # 18 days after the second → repeat
    set_now(local(*(second.completed_date + timedelta(days=18)).timetuple()[:3], 10))
    r = submit(db, "noura.qahtani", fd1(db, {"GSI-12"}, zone_code="Z-MSCP"))
    f3 = next(f for f in r.findings if f.item_code == "GSI-12")
    assert f3.repeat_of is not None and f3.severity.value == "major"
    db.rollback()
    # had the second been compliant: 32 days after the first → not a repeat
    set_now(local(2026, 10, 6, 10))
    execution.void_inspection(db, P(db, "noura.qahtani"), second.id,
                              InspectionVoid(reason="Voided for the FD3 variant check (TEST)"))  # fmt: skip
    set_now(local(*(first.completed_date + timedelta(days=32)).timetuple()[:3], 10))
    r = submit(db, "noura.qahtani", fd1(db, {"GSI-12"}, zone_code="Z-MSCP"))
    f4 = next(f for f in r.findings if f.item_code == "GSI-12")
    assert f4.repeat_of is None and f4.severity.value == "minor" and f4.ca_id is None


def _ins_of(db: Session, f: FieldFinding) -> Inspection:
    r = db.get(ChecklistResponse, f.response_id)
    assert r is not None and r.inspection_id is not None
    i = db.get(Inspection, r.inspection_id)
    assert i is not None
    return i


def test_AC24_critical_without_stop_rule(db: Session) -> None:
    t0 = now()
    crit = {
        "answer": "non_compliant",
        "note": "Escape route blocked by materials",
        "photos": [{"file_name": "a.png", "content_base64": PNG}],
    }
    a = answers(db, "HSK", {"HSK-04"}, HSK_04=crit)
    r = submit(db, "noura.qahtani", body(db, "HSK", zone_code="Z-LAY1", answer_list=a))
    assert r.result.value == "fail" and r.stop_work_order_id is None
    got = notified(db, "critical_item_failure", t0)
    assert {"fahad.mutairi", "noura.qahtani", "ahmed.zahrani"} <= set(got)


def test_AC25_AC26_AC27_stop_work_order(db: Session) -> None:
    from app.schemas.field import StopWorkRelease
    from app.services.field import stopwork

    t0 = now()
    pm = permit(db, "PTW-ANIA-EXP-2026-0412")
    r = submit(db, "noura.qahtani", fd1(db, {"GSI-05"}, zone_code="Z-PIERB",
                                        stop=stop_fields(permits=[str(pm.id)])))  # fmt: skip
    o = db.get(StopWorkOrder, r.stop_work_order_id)
    assert o is not None and o.status.value == "active"
    got = notified(db, "stop_work_order", t0)
    assert {"faisal.harbi", "noura.qahtani", "fahad.mutairi", "ahmed.zahrani", "khalid.otaibi",
            "ramesh.kumar"} <= set(got)  # fmt: skip
    db.refresh(pm)
    assert (pm.status.value, pm.status_reason.value if pm.status_reason else None) == (
        "suspended",
        "stop_work",
    )
    sp = db.scalar(select(PermitSuspension).where(PermitSuspension.permit_id == pm.id)
                   .order_by(PermitSuspension.suspended_at.desc()))  # fmt: skip
    assert sp is not None and sp.auto_source_ref == o.order_no
    db.commit()
    # AC26: the issuer cannot resume while the order is Active
    n = world(db)
    t = now() + timedelta(minutes=10)
    expect("STOP_WORK_ACTIVE", lambda: resume(n, pm, "khalid.otaibi", "ramesh.kumar", t), 422)
    db.rollback()
    set_now(t)
    rel = StopWorkRelease.model_validate({
        "release_note": "Guardrail refitted along the slab edge and checked (TEST).",
        "photos": [{"file_name": "fixed.png", "content_base64": PNG}]})  # fmt: skip
    # AC27: CA still Open → refused; Ahmed → 403; CA In Progress → Released
    expect("STOP_RELEASE_CA_REQUIRED",
           lambda: stopwork.release_order(db, P(db, "fahad.mutairi"), o.id, rel), 422)  # fmt: skip
    db.rollback()
    expect("FORBIDDEN", lambda: stopwork.release_order(db, P(db, "ahmed.zahrani"), o.id, rel), 403)
    db.rollback()
    ca = db.get(CorrectiveAction, o.ca_id)
    assert ca is not None
    ca.status = ca.status.__class__("in_progress")
    db.flush()
    out = stopwork.release_order(db, P(db, "fahad.mutairi"), o.id, rel)
    assert out.status.value == "released"
    db.commit()
    db.refresh(pm)
    resume(n, pm, "khalid.otaibi", "ramesh.kumar", t + timedelta(minutes=5))
    assert pm.status.value == "active"


def test_AC28_offline_stop_alert_label(db: Session) -> None:
    done = local(2026, 10, 6, 9, 35)
    set_now(local(2026, 10, 6, 11, 10))
    t0 = now()
    r = submit(db, "noura.qahtani", fd1(db, {"GSI-05"}, completed=done,
                                        stop=stop_fields(at=done)))  # fmt: skip
    o = db.get(StopWorkOrder, r.stop_work_order_id)
    assert o is not None and o.instructed_at == done
    titles = [x for v in notified(db, "stop_work_order", t0).values() for x in v]
    assert titles and all("recorded offline at 09:35" in x for x in titles)


def test_AC29_phase1_read_model_findings(db: Session) -> None:
    r = submit(db, "noura.qahtani", fd1(db, {"GSI-05", "GSI-12"}, stop=stop_fields()))
    i = db.get(Inspection, r.inspection_id)
    assert i is not None
    sev = sorted((f["severity"], f["ca_required"]) for f in i.findings)
    assert sev == [("critical", True), ("medium", False)]
    resp = db.scalar(select(ChecklistResponse).where(ChecklistResponse.id == r.id))
    assert resp is not None and resp.inspection_id == i.id
