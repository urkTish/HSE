"""6d-field-assurance §9 ACs 1-10 (template library, settings, inspection programme)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.models import ChecklistTemplate, Inspection, InspectionPlan
from app.schemas.field import (
    FieldSettingsUpdate,
    SubmissionCreate,
    TemplateCreate,
    TemplateUpdate,
    VersionTransition,
)
from app.services import inspections
from app.services.field import config, execution, library
from tests.emer_helpers import site
from tests.field_helpers import (
    P,
    body,
    eng,
    expect,
    local,
    notified,
    project,
    tpl,
    zone,
)

pytestmark = pytest.mark.usefixtures("field_seed", "clock")
PUBLISH = VersionTransition.model_validate({"action": "publish"})


def test_AC1_publish_supersedes_and_pins(db: Session) -> None:
    v3 = tpl(db, "GSI")
    draft = library.new_version(db, P(db, "noura.qahtani"), v3.id)
    assert draft.version == 4 and draft.status.value == "draft"
    db.commit()
    started = now() - timedelta(minutes=20)
    expect("FORBIDDEN", lambda: library.transition_template(db, P(db, "noura.qahtani"), draft.id,
                                                            PUBLISH), 403)  # fmt: skip
    db.rollback()
    out = library.transition_template(db, P(db, "faisal.harbi"), draft.id, PUBLISH)
    assert out.status.value == "published"
    db.refresh(v3)
    assert v3.status.value == "superseded"
    b = body(db, completed=now(), template_id=str(v3.id))
    b["started_at"] = started.isoformat()
    b.pop("template_code")
    r = execution.submit(db, P(db, "noura.qahtani"), project(db, "ANIA-EXP").id,
                         SubmissionCreate.model_validate(b))  # fmt: skip
    assert r.template_version == 3


def _item(code: str, **kw: Any) -> dict[str, Any]:
    return {"item_code": code, "section_code": "A", "text_en": f"Check {code}",
            "text_ar": f"تحقق {code}", "item_type": "yes_no", **kw}  # fmt: skip


def test_AC2_AC3_completeness_and_immutability(db: Session) -> None:
    body_ = TemplateCreate.model_validate({
        "template_code": "TSTX", "kind": "inspection", "inspection_type": "general_site",
        "title_en": "Test template", "title_ar": "نموذج اختبار",
        "sections": [{"code": "A", "title_en": "A", "title_ar": "أ"}],
        "items": [_item("TSTX-01", text_ar=""), _item("TSTX-02", stop_rule="stop_work"),
                  _item("TSTX-03", critical=True, weight=3, photo_required_on_fail=False)],
    })  # fmt: skip
    t = library.create_template(db, P(db, "faisal.harbi"), body_)
    crit = next(i for i in t.items if i.item_code == "TSTX-03")
    assert crit.photo_required_on_fail is True
    e = expect("TEMPLATE_INCOMPLETE",
               lambda: library.transition_template(db, P(db, "faisal.harbi"), t.id, PUBLISH))  # fmt: skip
    text = str(e.meta) + e.message + str(getattr(e, "errors", ""))
    assert "TSTX-01" in text and "TSTX-02" in text
    db.rollback()
    # AC3
    v3 = tpl(db, "GSI")
    expect("TEMPLATE_IMMUTABLE", lambda: library.update_template(
        db, P(db, "faisal.harbi"), v3.id, TemplateUpdate.model_validate({"title_en": "X"})), 409)  # fmt: skip
    db.rollback()
    retire = VersionTransition.model_validate({"action": "retire",
                                               "reason": "Replaced by a newer approach (TEST)"})  # fmt: skip
    expect("TEMPLATE_IN_USE",
           lambda: library.transition_template(db, P(db, "faisal.harbi"), v3.id, retire), 422)  # fmt: skip


def test_AC4_project_scope_and_zone_types(db: Session) -> None:
    rbt = project(db, "RBT-52")
    t = library.create_template(db, P(db, "faisal.harbi"), TemplateCreate.model_validate({
        "template_code": "RBTX", "kind": "inspection", "inspection_type": "general_site",
        "title_en": "RBT only", "title_ar": "خاص", "project_ids": [str(rbt.id)],
        "sections": [{"code": "A", "title_en": "A", "title_ar": "أ"}], "items": [_item("RBTX-01")],
    }))  # fmt: skip
    row = db.get(ChecklistTemplate, t.id)
    assert row is not None
    assert library.offered(row, rbt.id) and not library.offered(row, project(db, "ANIA-EXP").id)
    b = body(db, "FOD", zone_code="Z-PIERB")
    expect("TEMPLATE_NOT_APPLICABLE", lambda: execution.submit(
        db, P(db, "noura.qahtani"), project(db, "ANIA-EXP").id, SubmissionCreate.model_validate(b)))  # fmt: skip


def test_AC5_settings_loosening(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    for bad in ({"inspection_pass_mark_pct": "80.0"}, {"repeat_finding_days": 20},
                {"contractor_audit_months": 9}):  # fmt: skip
        expect("SETTING_LOOSENING", lambda b=bad: config.update_settings(
            db, P(db, "faisal.harbi"), pid, FieldSettingsUpdate.model_validate(b)), 422)  # fmt: skip
        db.rollback()
    out = config.update_settings(db, P(db, "faisal.harbi"), pid, FieldSettingsUpdate.model_validate(
        {"inspection_pass_mark_pct": "90.0", "repeat_finding_days": 45,
         "contractor_audit_months": 4}))  # fmt: skip
    assert (out.inspection_pass_mark_pct, out.repeat_finding_days) == ("90.0", 45)
    expect("FORBIDDEN", lambda: config.update_settings(
        db, P(db, "noura.qahtani"), pid, FieldSettingsUpdate.model_validate(
            {"repeat_finding_days": 60})), 403)  # fmt: skip


def _plan(db: Session, **kw: Any) -> Any:
    from app.schemas.inspections import InspectionPlanCreate

    b = {
        "name_en": "GSI rotation (TEST)",
        "name_ar": "جولة",
        "inspection_type": "general_site",
        "site_id": str(site(db, "S-LAND").id),
        "frequency": "weekly",
        "weekday": "tuesday",
        "start_date": "2026-10-06",
        "assignee_role": "hse_officer",
        "template_code": "GSI",
        **kw,
    }
    return inspections.create_plan(db, P(db, "noura.qahtani"), project(db, "ANIA-EXP").id,
                                   InspectionPlanCreate.model_validate(b))  # fmt: skip


def test_AC6_rotation(db: Session) -> None:
    from app.schemas.inspections import InspectionPlanUpdate

    zs = [zone(db, c).id for c in ("Z-PIERB", "Z-MSCP", "Z-LAY1")]
    pl = _plan(db, rotation="zones", rotation_list=[str(z) for z in zs])
    got = list(db.scalars(select(Inspection).where(Inspection.plan_id == pl.id)
                          .order_by(Inspection.planned_date)))  # fmt: skip
    assert [i.zone_id for i in got[:4]] == [zs[0], zs[1], zs[2], zs[0]]
    first = got[0]
    set_now(local(2026, 10, 7, 10))
    inspections.update_plan(db, P(db, "noura.qahtani"), pl.id, InspectionPlanUpdate.model_validate(
        {"rotation_list": [str(zs[2]), str(zs[1])]}))  # fmt: skip
    db.refresh(first)
    assert first.zone_id == zs[0]
    later = list(db.scalars(select(Inspection).where(Inspection.plan_id == pl.id,
                                                     Inspection.planned_date > date(2026, 10, 7))
                            .order_by(Inspection.planned_date)))  # fmt: skip
    assert later and {i.zone_id for i in later} <= {zs[1], zs[2]}


def test_AC7_template_required(db: Session) -> None:
    expect("TEMPLATE_REQUIRED", lambda: _plan(db, template_code=None))
    db.rollback()
    old = db.scalar(select(InspectionPlan).where(
        InspectionPlan.active.is_(True), InspectionPlan.template_code.is_not(None),
        InspectionPlan.project_id == project(db, "ANIA-EXP").id))  # fmt: skip
    assert old is not None
    old.template_code = None
    db.flush()
    inspections.generate(db, old, date(2026, 10, 6))
    db.commit()
    inst = db.scalar(select(Inspection).where(Inspection.plan_id == old.id,
                                              Inspection.status == "planned"))  # fmt: skip
    assert inst is not None
    from app.services.field import board

    panel = board.action_panel(db, P(db, "noura.qahtani"), old.project_id)
    assert any(i.kind.value == "plan_without_checklist" and old.name_en in i.refs
               for i in panel.items)  # fmt: skip
    from app.schemas.inspections import InspectionComplete

    done = InspectionComplete.model_validate({"completed_at": now().isoformat(),
                                              "items_checked": 10, "items_compliant": 9})  # fmt: skip
    set_now(local(*inst.planned_date.timetuple()[:3], 12) if inst.planned_date else now())
    expect("TEMPLATE_REQUIRED", lambda: inspections.complete(
        db, P(db, "noura.qahtani"), inst.id, done.model_copy(update={"completed_at": now()})))  # fmt: skip
    db.rollback()
    from app.services.field import common as fc

    row = fc.settings_row(db, old.project_id)
    row.inspection_template_required_from = None
    fc.clear_cache(db)
    db.flush()
    inst = db.get(Inspection, inst.id)
    assert inst is not None
    out = inspections.complete(db, P(db, "noura.qahtani"), inst.id,
                               done.model_copy(update={"completed_at": now()}))  # fmt: skip
    assert out.status.value == "completed"


def test_AC8_quarterly(db: Session) -> None:
    pl = InspectionPlan(frequency="quarterly", start_date=date(2026, 1, 31), end_date=None,
                        weekday=None)  # fmt: skip
    got = list(inspections.due_dates(pl, date(2026, 1, 1), date(2026, 12, 31)))
    assert got == [date(2026, 1, 31), date(2026, 4, 30), date(2026, 7, 31), date(2026, 10, 31)]


def test_AC10_isp4_alert_and_panel(db: Session) -> None:
    from app.field_jobs import field_alerts
    from app.services.field import board

    set_now(local(2026, 10, 9, 7, 6))
    t0 = now()
    field_alerts(db)
    got = notified(db, "inspection_coverage_gap", t0)
    assert "ahmed.zahrani" in got and "fahad.mutairi" in got
    field_alerts(db)
    assert len(notified(db, "inspection_coverage_gap", t0)["fahad.mutairi"]) == len(
        got["fahad.mutairi"]
    )
    panel = board.action_panel(db, P(db, "noura.qahtani"), project(db, "ANIA-EXP").id)
    item = next(i for i in panel.items if i.kind.value == "not_inspected_this_week")
    assert "NAJD@S-LAND" in item.refs
    assert eng(db, "ANIA-EXP", "NAJD")
