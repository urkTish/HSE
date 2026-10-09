"""6d-field-assurance §9 ACs 30-35 (audits: score, SoD, report, programme, closure)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.models import Attachment, ChecklistResponse, CorrectiveAction, FieldFinding, Inspection
from app.schemas.field import AuditAnswers, AuditCreate, AuditTransition, AuditUpdate
from app.services.field import audits
from app.services.field.reference import grade_for
from app.services.field.scoring import evaluate
from tests.emer_helpers import site
from tests.field_helpers import PNG, P, audit, eng, expect, local, notified, project, tpl, uid

pytestmark = pytest.mark.usefixtures("field_seed", "clock")
T = AuditTransition.model_validate


def test_AC30_fd2(db: Session) -> None:
    a = audit(db, "AUD-ANIA-EXP-2026-011")
    r = db.get(ChecklistResponse, a.response_id)
    assert r is not None
    assert (r.applicable_weight, r.earned_weight) == (Decimal(42), Decimal(34))
    assert (str(Decimal(r.score_pct).quantize(Decimal("0.1"))), r.grade.value) == ("81.0", "B")
    sev = [f.severity.value for f in db.scalars(select(FieldFinding).where(
        FieldFinding.response_id == r.id, FieldFinding.voided.is_(False)))]  # fmt: skip
    assert (sev.count("major_nc"), sev.count("minor_nc"), sev.count("observation")) == (2, 4, 10)
    cas = list(db.scalars(select(CorrectiveAction).where(CorrectiveAction.source_id == a.id)))
    assert {c.source_type.value for c in cas} == {"field_audit"}
    pr = sorted(c.priority.value for c in cas)
    assert (pr.count("high"), pr.count("medium")) == (2, 4)
    # variant: CHA-27 rated 1 → 32 / 42 = 76.2 % but major_nc on a critical item → C
    t = tpl(db, "CHA")
    ans = [{k: v for k, v in x.items() if k in ("item_code", "answer", "note")} for x in r.answers]
    for x in ans:
        if x["item_code"] == "CHA-27":
            x.update(
                answer="1",
                note="Evidence not available for the sample (TEST).",
                photos=[{"file_name": "e.png", "content_base64": PNG}],
            )
    sc = evaluate(t.items, ans, False, audit=True)
    assert sc.earned_weight.quantize(Decimal("0.001")) == Decimal("32.000")
    assert grade_for(Decimal("76.2"), False).value == "B"
    assert grade_for(Decimal("76.2"), True).value == "C"


def _plan(db: Session, who: str, eng_code: str, lead: str = "noura.qahtani", **kw: Any) -> Any:
    b = {"audit_type": "contractor_hse", "template_code": "CHA",
         "auditee_engagement_id": str(eng(db, "ANIA-EXP", eng_code).id),
         "site_ids": [str(site(db, "S-LAND").id)], "lead_auditor_id": str(uid(db, lead)),
         "planned_start": "2026-10-11", "planned_end": "2026-10-12", **kw}  # fmt: skip
    return audits.create_audit(db, P(db, who), project(db, "ANIA-EXP").id,
                               AuditCreate.model_validate(b))  # fmt: skip


def _fieldwork(db: Session, a: Any, lead: str, start: date, end: date) -> None:
    pl = P(db, lead)
    audits.update_audit(db, pl, a.id, AuditUpdate.model_validate({
        "opening_meeting_at": local(*start.timetuple()[:3], 8).isoformat(),
        "fieldwork_start": start.isoformat(),
        "auditee_attendee_roles": "Project manager, HSE manager"}))  # fmt: skip
    ans = [{"item_code": it["item_code"], "answer": "3"} for it in tpl(db, "CHA").items]
    audits.save_answers(db, pl, a.id, AuditAnswers.model_validate({"answers": ans}))
    audits.update_audit(db, pl, a.id, AuditUpdate.model_validate({
        "fieldwork_end": end.isoformat(),
        "closing_meeting_at": local(*end.timetuple()[:3], 14).isoformat(),
        "summary_en": "Arrangements effective; no nonconformities found (TEST)."}))  # fmt: skip
    audits.transition_audit(db, pl, a.id, T({"action": "complete_fieldwork"}))


def test_AC31_sod_and_report(db: Session) -> None:
    ok = _plan(db, "ahmed.zahrani", "NAJD", lead="ahmed.zahrani")
    assert ok.status.value == "planned"
    db.rollback()
    expect("SOD_CONFLICT", lambda: _plan(db, "ahmed.zahrani", "RAWABI", lead="ahmed.zahrani"))
    db.rollback()
    a = _plan(db, "noura.qahtani", "NAJD")
    set_now(local(2026, 10, 6, 8))
    _fieldwork(db, a, "noura.qahtani", date(2026, 10, 6), date(2026, 10, 6))
    set_now(local(2026, 10, 6, 16))
    db.commit()
    expect("SOD_CONFLICT", lambda: audits.transition_audit(
        db, P(db, "noura.qahtani"), a.id, T({"action": "issue"})))  # fmt: skip
    db.rollback()
    out = audits.transition_audit(db, P(db, "faisal.harbi"), a.id, T({"action": "issue"}))
    assert out.status.value == "issued" and out.report_en_id and out.report_ar_id
    from app.core.config import get_settings

    for rid in (out.report_en_id, out.report_ar_id):
        att = db.get(Attachment, rid)
        assert att is not None
        html = (Path(get_settings().storage_dir) / att.storage_key).read_bytes().decode()
        assert "WKR-" not in html and out.audit_no in html


def test_AC32_report_overdue_alerts(db: Session) -> None:
    from app.field_jobs import field_alerts

    set_now(local(2026, 9, 27, 8))
    a = _plan(db, "noura.qahtani", "NAJD", planned_start="2026-09-27", planned_end="2026-09-28",
              team_ids=[str(uid(db, "fahad.mutairi"))])  # fmt: skip
    _fieldwork(db, a, "noura.qahtani", date(2026, 9, 27), date(2026, 9, 28))
    db.commit()
    set_now(local(2026, 10, 4, 7, 6))
    t0 = now()
    field_alerts(db)
    assert "noura.qahtani" not in notified(db, "audit_report_overdue", t0)
    set_now(local(2026, 10, 5, 7, 6))
    field_alerts(db)
    got = notified(db, "audit_report_overdue", t0)
    assert "noura.qahtani" in got and "faisal.harbi" not in got
    set_now(local(2026, 10, 8, 7, 6))
    field_alerts(db)
    assert "faisal.harbi" in notified(db, "audit_report_overdue", t0)


def _line(db: Session, code: str) -> Any:
    e = eng(db, "ANIA-EXP", code)
    return next(ln for ln in audits.lines(db, project(db, "ANIA-EXP").id, date(2026, 10, 6))
                if ln.engagement_id == e.id)  # fmt: skip


def test_AC33_fd4_programme(db: Session) -> None:
    s = _line(db, "SAHARA")
    assert s.last is not None and s.last.audit_no == "AUD-ANIA-EXP-2026-011"
    assert s.due_by == date(2027, 3, 7)
    assert audits.met_on_time(s.items[-2]) is True
    g = _line(db, "GULFPAVE")
    assert g.due_by == date(2027, 3, 22) and audits.met_on_time(g.items[-2]) is False
    # an engagement mobilised 2026-10-10 → first due 2026-12-09
    e = eng(db, "ANIA-EXP", "NAJD")
    e.mobilisation_date = date(2026, 10, 10)
    for x in db.scalars(select(audits.FieldAudit).where(audits.FieldAudit.auditee_engagement_id
                                                        == e.id)):  # fmt: skip
        x.status = x.status.__class__("voided")
    db.flush()
    assert _line(db, "NAJD").due_by == date(2026, 12, 9)


def test_AC34_void_satisfies_nothing_and_not_inspection(db: Session) -> None:
    a = audit(db, "AUD-ANIA-EXP-2026-012")
    audits.transition_audit(db, P(db, "faisal.harbi"), a.id,
                            T({"action": "void", "reason": "Raised against the wrong contractor"}))  # fmt: skip
    g = _line(db, "GULFPAVE")
    assert g.last is None or g.last.audit_no != a.audit_no
    assert db.scalar(select(Inspection.id).where(Inspection.ref.like("AUD-%"))) is None
    assert db.scalar(select(ChecklistResponse.inspection_id).where(
        ChecklistResponse.audit_id == a.id)) is None  # fmt: skip


def test_AC35_auto_close(db: Session) -> None:
    a = audit(db, "AUD-ANIA-EXP-2026-011")
    for ca in db.scalars(select(CorrectiveAction).where(CorrectiveAction.source_id == a.id)):
        ca.status = ca.status.__class__("closed")
        ca.completed_date = ca.verified_date = date(2026, 10, 1)
    db.flush()
    from app.field_jobs import field_daily

    set_now(local(2026, 10, 7, 0, 9))
    field_daily(db)
    db.refresh(a)
    assert a.status.value == "closed"
    assert now() - timedelta(days=1) < a.closed_at  # type: ignore[operator]
