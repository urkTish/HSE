# ruff: noqa: E501
"""Phase 6f KPIs, E24, scope, settings, seed and AR labels (6f §9 AC 41-42, 46-48). AC 43 (AI
tools T23 / T24) is parked (docs/PROGRESS.md)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.followup_enums import (
    FuChannel,
    FuFiler,
    FuRuleSource,
    FuStage,
    FuSubmissionStatus,
    FuWaiverReason,
)
from app.core.hse_enums import ExternalBody, LeadingWarningCode
from app.models import FuRequirement, FuSubmission
from app.schemas.followup import FuSettingsUpdate
from app.services import incidents as inc_svc
from app.services.followup import config
from app.services.followup import requirements as rq
from tests.conftest import Api
from tests.fu_helpers import (
    P,
    eng,
    expect,
    fu2,
    inc,
    kpi,
    kpis,
    local,
    make_inc,
    project,
    rules_from,
    tick,
    uid,
)

pytestmark = pytest.mark.usefixtures("fu_seed", "clock")


def fu4(db: Session) -> uuid.UUID:
    """21 RBT-52 requirements due in October: 17 on time, 2 late, 1 overdue (GOSI-W), 1 waived."""
    rules_from(db, "RBT-52", date(2026, 10, 1))
    tick(2026, 10, 1, 9)
    i = make_inc(db, "RBT-52", "S-TWR", local(2026, 10, 1, 8), "QIMMA", None)
    q = eng(db, "RBT-52", "QIMMA").id
    for n in range(21):
        due = local(2026, 10, 1 + n, 12)
        gosi = n == 19
        r = FuRequirement(
            id=uuid.uuid4(), project_id=i.project_id, incident_id=i.id, rule_code="GOSI-W" if gosi else "CL-F",
            case_key=str(n), body=ExternalBody.gosi if gosi else ExternalBody.client, stage=FuStage.written,
            source=FuRuleSource.statutory if gosi else FuRuleSource.client, filer=FuFiler.employer_engagement if gosi else FuFiler.main_contractor,
            trigger_met_at=due - timedelta(hours=24), due_at=due, filer_engagement_id=q, responsible_engagement_id=q,
            case_ids=[], required=True, alerts_sent=[],
        )  # fmt: skip
        if n == 20:
            r.waiver_reason_code, r.waived_at, r.waiver_text = (
                FuWaiverReason.reported_by_other_party,
                due,
                "Waived (TEST) by other party",
            )
        db.add(r)
        db.flush()
        if n < 19:
            at = due - timedelta(hours=1) if n < 17 else due + timedelta(hours=2)
            db.add(FuSubmission(
                id=uuid.uuid4(), project_id=i.project_id, year=2026, seq=100 + n, submission_no=f"NS-RBT-52-2026-{100 + n:04d}",
                requirement_id=r.id, channel=FuChannel.email, submitted_at=at, reference_no=f"T-{n}",
                evidence_file_ids=[], on_time=n < 17, status=FuSubmissionStatus.recorded, created_by_user_id=uid(db, "lina.haddad"),
            ))  # fmt: skip
    db.flush()
    return i.project_id


def test_ac41_fu4_and_e24(api: Api, db: Session) -> None:
    from app.hse_jobs import project_scope
    from app.kpi import warnings as kwarn
    from app.kpi.periods import Window

    pid = fu4(db)
    db.commit()
    tick(2026, 11, 2, 7)
    body = kpis(api.as_("faisal.harbi"), pid)
    assert kpi(body, "K127")["display"] == "85.0 %" and kpi(body, "K128")["display"] == "1"
    chips = {c["key"]: c["display"] for c in kpi(body, "K128").get("components") or []}
    assert chips.get("statutory") == "1"
    pr = project(db, "RBT-52")
    found = [w for w in kwarn.evaluate(project_scope(db, pr, date(2026, 11, 2)), [Window(date(2026, 10, 1), date(2026, 10, 31))])
             if w.code == LeadingWarningCode.E24]  # fmt: skip
    assert {w.engagement.code if w.engagement else None for w in found} >= {None, "QIMMA"}
    inputs = {x.key: x.value for x in found[0].inputs}
    assert inputs["k127_numerator"] == Decimal(17) and inputs["k127_denominator"] == Decimal(20)
    assert "Rashid" not in found[0].message_en


def test_ac42_rep_tree_scope(api: Api, db: Session) -> None:
    ania = project(db, "ANIA-EXP").id
    body = kpis(api.as_("ahmed.zahrani"), ania, end="2026-10-06")
    assert kpi(body, "K127")["display"] == "100.0 %" and kpi(body, "K130")["display"] == "75.0 %"
    body = kpis(
        api.as_("faisal.harbi"),
        ania,
        end="2026-10-06",
        engagement_id=str(eng(db, "ANIA-EXP", "NAJD").id),
    )
    assert kpi(body, "K130")["display"] == "50.0 %"  # NAJD (ack) + SAHARA (pending)
    assert kpi(body, "K127")["display"] == "—"  # FU2 belongs to GULFPAVE


def test_ac46_settings(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    faisal = P(db, "faisal.harbi")
    expect(
        "SETTING_LOOSENING",
        lambda: config.update_settings(db, faisal, pid, FuSettingsUpdate(lesson_ack_days=10)),
    )
    expect(
        "SETTING_LOOSENING",
        lambda: config.update_settings(
            db, faisal, pid, FuSettingsUpdate(followup_warning_pct=Decimal("90.0"))
        ),
    )
    assert (
        config.update_settings(db, faisal, pid, FuSettingsUpdate(lesson_ack_days=5)).lesson_ack_days
        == 5
    )
    expect(
        "FORBIDDEN",
        lambda: config.update_settings(
            db, P(db, "noura.qahtani"), pid, FuSettingsUpdate(lesson_ack_days=4)
        ),
    )


def test_ac47_phase1_views(db: Session) -> None:
    from app.services.hse_common import Refs

    sept = inc(db, "INC-ANIA-EXP-2026-0147")
    assert rq.phase1_required(sept) is None
    i = fu2(db)
    assert i.occurred_date.month == 10
    reads = inc_svc.notification_reads(i, [], [], Refs(db))
    assert {r.rule_code: (r.state.value if r.state else None) for r in reads} == {
        "AO-V": "done",
        "CL-V": "done",
        "AO-W": "done",
        "CL-F": "done",
        "GACA-W": "due",
        "CL-I": "due",
        "CL-FIN": "due",
    }
    assert {r.body.value for r in inc_svc.required_notifications(i, [])} == {
        "gaca",
        "airport_operator",
        "client",
    }


def test_ac48_ar_labels(db: Session) -> None:
    ref = config.reference(db, P(db, "noura.qahtani"))
    missing = [
        (k, x.code)
        for k, xs in ref.lists.items()
        for x in xs
        if not x.label_ar or x.label_ar == x.label_en
    ]
    assert not missing
