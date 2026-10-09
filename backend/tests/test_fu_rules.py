# ruff: noqa: E501
"""Phase 6f rules, requirements and submissions (6f §9 AC 1-10, 18-24)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.followup_enums import FuChannel, FuFiler, FuWaiverReason
from app.models import AuditEntry, ExternalNotification, FuRequirement, FuRule
from app.schemas.followup import (
    FuRuleUpdate,
    FuSubmissionCreate,
    FuSubmissionUpdate,
    FuSubmissionVoid,
    FuWaiverRequest,
)
from app.schemas.incidents import ExternalNotificationRecord
from app.services import incidents as inc_svc
from app.services.followup import config, submissions
from app.services.followup import requirements as rq
from tests.conftest import Api
from tests.fu_helpers import (
    P, due, eng, expect, f64, fu2, inc, kpi, kpis, local, make_inc, notified, project, reqs,
    rules_from, set_case, status, tick,
)  # fmt: skip

pytestmark = pytest.mark.usefixtures("fu_seed", "clock")


def fu1(db: Session, cat: str = "MTC"):  # type: ignore[no-untyped-def]
    tick(2026, 10, 3, 15, 0)
    return make_inc(db, "ANIA-EXP", "S-LAND", local(2026, 10, 3, 14, 20), "NAJD", [{"cat": cat, "emp": "NAJD"}])


def due_l(t):  # type: ignore[no-untyped-def]
    from app.services.followup import common as fc

    return fc.to_local(t).strftime("%m-%d %H:%M")


def rule(db: Session, pcode: str, code: str) -> FuRule:
    r = db.scalar(select(FuRule).where(FuRule.project_id == project(db, pcode).id, FuRule.rule_code == code))
    assert r is not None
    return r


def test_ac1_phase1_unchanged_before_switch(db: Session) -> None:
    """AC 1: RBT-52 (null) and ANIA-EXP September incidents keep the Phase 1 I-20 items."""
    tick(2026, 10, 6, 9, 0)
    i = make_inc(db, "RBT-52", "S-TWR", local(2026, 10, 6, 8, 0), "QIMMA", [{"cat": "LTI", "emp": "QIMMA"}])
    assert reqs(db, i) == {}
    assert rq.phase1_required(i) is None
    from app.models import InjuryCase

    cases = list(db.scalars(select(InjuryCase).where(InjuryCase.incident_id == i.id)))
    got = {r.body.value: due_l(r.due_at) for r in inc_svc.required_notifications(i, cases)}
    assert got == {"gosi": "10-09 08:00", "client": "10-07 08:00"}  # I-20: 3 days / 24 h, stage written
    sept = inc(db, "INC-ANIA-EXP-2026-0147")
    assert rq.phase1_required(sept) is None and reqs(db, sept) == {}


def test_ac2_ac3_fu1_gosi_and_reclassification(db: Session) -> None:
    i = fu1(db)
    rs = reqs(db, i)
    assert list(rs) == ["GOSI-W:P1"]
    g = rs["GOSI-W:P1"]
    assert due(g) == "10-06 14:20" and g.filer_engagement_id == eng(db, "ANIA-EXP", "NAJD").id
    who = notified(db, "followup_requirement")
    assert {"ahmed.zahrani", "noura.qahtani"} <= set(who)
    pid = project(db, "ANIA-EXP").id
    t0 = tick(2026, 10, 5, 14, 19)
    rq.run_alerts(db, pid, t0)
    assert not notified(db, "followup_requirement", since=t0)
    t1 = tick(2026, 10, 5, 14, 20)
    rq.run_alerts(db, pid, t1)
    assert "ahmed.zahrani" in notified(db, "followup_requirement", since=t1)
    # AC 3: LTI at 10-07 09:00 → client rows from that time; GOSI-W unchanged
    tick(2026, 10, 7, 9, 0)
    set_case(db, i, 1, "LTI")
    rq.derive(db, i)
    rs = reqs(db, i)
    assert {k: due(r) for k, r in rs.items()} == {
        "GOSI-W:P1": "10-06 14:20", "CL-V": "10-07 10:00", "CL-F": "10-08 09:00",
        "CL-I": "10-10 09:00", "CL-FIN": "10-17 23:59",
    }
    tick(2026, 10, 7, 15, 0)
    rq.derive(db, i)
    assert due(reqs(db, i)["CL-V"]) == "10-07 10:00"


def test_ac2_no_pre_due_once_submitted(db: Session) -> None:
    i = fu1(db)
    g = reqs(db, i)["GOSI-W:P1"]
    tick(2026, 10, 5, 11, 5)
    submissions.record(db, P(db, "ahmed.zahrani"), g.id, FuSubmissionCreate(
        channel=FuChannel.portal, submitted_at=local(2026, 10, 5, 11, 0), reference_no="GOSI-TEST-0412",
        external_document=f64("gosi.pdf.txt"), evidence_files=[f64("screenshot.txt")]))  # fmt: skip
    t = tick(2026, 10, 5, 14, 30)
    rq.run_alerts(db, project(db, "ANIA-EXP").id, t)
    assert not notified(db, "followup_requirement", since=t)
    # AC 21: SB-4 Phase 1 read fields
    row = db.get(ExternalNotification, (i.id, "gosi"))
    assert row is not None and row.reference_no == "GOSI-TEST-0412"
    assert row.notified_at == local(2026, 10, 5, 11, 0)
    expect("EVIDENCE_REQUIRED", lambda: inc_svc.record_notification(
        db, P(db, "noura.qahtani"), i.id, row.body,
        ExternalNotificationRecord(notified_at=local(2026, 10, 5, 12, 0), reference_no="X")))  # fmt: skip


def test_ac4_fu3_fatality(db: Session) -> None:
    rules_from(db, "RBT-52", date(2026, 10, 1))
    tick(2026, 10, 10, 8, 5)
    i = make_inc(db, "RBT-52", "S-TWR", local(2026, 10, 10, 8, 0), "QIMMA",
                 [{"cat": "FAT", "emp": "QIMMA", "trade": "steel_erector"}], potential_severity=5)  # fmt: skip
    got = {k.split(":")[0]: due(r) for k, r in reqs(db, i).items()}
    assert got == {"POL-V": "10-10 09:00", "MHRSD-F": "10-11 08:00", "GOSI-W": "10-13 08:00",
                   "CL-V": "10-10 09:00", "CL-F": "10-11 08:00", "CL-I": "10-13 08:00",
                   "CL-FIN": "10-24 23:59"}  # fmt: skip
    who = notified(db, "followup_requirement")
    assert {"lina.haddad", "faisal.harbi"} <= set(who)


def test_ac5_two_employers_two_gosi(db: Session) -> None:
    tick(2026, 10, 6, 9, 0)
    i = make_inc(db, "ANIA-EXP", "S-LAND", local(2026, 10, 6, 8, 0), "NAJD",
                 [{"no": 1, "cat": "LTI", "emp": "NAJD"}, {"no": 2, "cat": "LTI", "emp": "SAHARA", "name": "Imran Qadir"}])  # fmt: skip
    g = {k: r.filer_engagement_id for k, r in reqs(db, i).items() if k.startswith("GOSI")}
    assert g == {"GOSI-W:P1": eng(db, "ANIA-EXP", "NAJD").id, "GOSI-W:P2": eng(db, "ANIA-EXP", "SAHARA").id}


def test_ac6_ac7_rule_edits(db: Session) -> None:
    faisal = P(db, "faisal.harbi")
    gosi = rule(db, "ANIA-EXP", "GOSI-W")
    expect("RULE_LOOSENING", lambda: config.update_rule(db, faisal, gosi.id, FuRuleUpdate(deadline_hours=96)))
    expect("RULE_LOOSENING", lambda: config.update_rule(db, faisal, rule(db, "ANIA-EXP", "POL-V").id, FuRuleUpdate(active=False)))
    config.update_rule(db, faisal, gosi.id, FuRuleUpdate(deadline_hours=48))
    assert db.scalar(select(AuditEntry.id).where(AuditEntry.entity_id == gosi.id)) is not None
    tick(2026, 10, 6, 9, 0)
    i = make_inc(db, "ANIA-EXP", "S-LAND", local(2026, 10, 6, 8, 0), "NAJD", [{"cat": "MTC"}])
    assert due(reqs(db, i)["GOSI-W:P1"]) == "10-08 08:00"
    assert config.update_rule(db, faisal, rule(db, "ANIA-EXP", "CL-F").id, FuRuleUpdate(deadline_hours=12)).deadline_hours == 12
    expect("FORBIDDEN", lambda: config.update_rule(db, P(db, "noura.qahtani"), rule(db, "ANIA-EXP", "CL-F").id, FuRuleUpdate(deadline_hours=10)))
    clv = rule(db, "RBT-52", "CL-V")
    clv.active = False
    from app.services.followup import common as fc

    fc.settings_row(db, project(db, "RBT-52").id).client_recipients = []
    fc.clear_cache(db)
    expect("CLIENT_RECIPIENT_REQUIRED", lambda: config.update_rule(db, faisal, clv.id, FuRuleUpdate(active=True)))


def test_ac8_downgrade_releases_client_rows(db: Session) -> None:
    i = fu1(db, "LTI")
    rs = reqs(db, i)
    tick(2026, 10, 3, 16, 0)
    submissions.record(db, P(db, "noura.qahtani"), rs["CL-V"].id, FuSubmissionCreate(
        channel=FuChannel.phone_radio, submitted_at=local(2026, 10, 3, 15, 0),
        contacted_desk_en="PMC duty engineer", reference_no="PMC-TEST-1"))  # fmt: skip
    set_case(db, i, 1, "MTC")
    rq.derive(db, i)
    db.expire_all()
    rs = reqs(db, i)
    assert {k: status(db, r) for k, r in rs.items() if k.startswith("CL")} == {
        "CL-V": "submitted", "CL-F": "not_required", "CL-I": "not_required", "CL-FIN": "not_required"}
    assert rs["CL-V"].trigger_note and "no longer" in rs["CL-V"].trigger_note


def test_ac9_waiver(db: Session) -> None:
    g = reqs(db, fu2(db))["GACA-W"]
    faisal = P(db, "faisal.harbi")
    text = "GACA occurrence report filed by the airport operator (TEST)."
    expect("WAIVER_EVIDENCE_REQUIRED", lambda: rq.waive(db, faisal, g.id, FuWaiverRequest(
        reason_code=FuWaiverReason.reported_by_other_party, text=text)))  # fmt: skip
    rq.waive(db, faisal, g.id, FuWaiverRequest(reason_code=FuWaiverReason.reported_by_other_party,
                                               text=text, reference="GACA-TEST-77", evidence_file=f64()))  # fmt: skip
    assert status(db, g) == "waived"
    expect("FORBIDDEN", lambda: rq.waive(db, P(db, "noura.qahtani"), reqs(db, fu2(db))["CL-I"].id, FuWaiverRequest(
        reason_code=FuWaiverReason.reported_by_other_party, text=text, reference="X", evidence_file=f64())))  # fmt: skip


def test_ac10_ncec_environmental(db: Session) -> None:
    from app.core.hse_enums import EnvCategory, EnvReached

    tick(2026, 10, 6, 9, 0)
    i = make_inc(db, "ANIA-EXP", "S-LAND", local(2026, 10, 6, 8, 0), "RAWABI", None, inv_days=None,
                 incident_types=["environmental"], env_category=EnvCategory.spill, env_reached=EnvReached.drain)  # fmt: skip
    assert due(reqs(db, i)["NCEC-W"]) == "10-07 08:00"


def test_ac18_fu2_table_and_kpis(api: Api, db: Session) -> None:
    rs = reqs(db, fu2(db))
    assert {k: (due(r), status(db, r)) for k, r in rs.items()} == {
        "AO-V": ("10-05 00:30", "submitted"), "AO-W": ("10-05 23:30", "acknowledged"),
        "CL-V": ("10-05 00:30", "submitted"), "CL-F": ("10-05 23:30", "submitted"),
        "GACA-W": ("10-07 23:30", "due"), "CL-I": ("10-07 23:30", "due"), "CL-FIN": ("10-18 23:59", "due"),
    }
    body = kpis(api.as_("faisal.harbi"), project(db, "ANIA-EXP").id, end="2026-10-06")
    assert kpi(body, "K127")["display"] == "100.0 %" and kpi(body, "K128")["display"] == "0"


def test_ac19_ac20_submission_rules(db: Session) -> None:
    i = fu2(db)
    g = reqs(db, i)["GACA-W"]
    noura = P(db, "noura.qahtani")

    def sub(**kw):  # type: ignore[no-untyped-def]
        data = {"channel": FuChannel.email, "submitted_at": local(2026, 10, 6, 9, 0), "reference_no": "GACA-TEST-1", **kw}
        return lambda: submissions.record(db, noura, g.id, FuSubmissionCreate(**data))

    expect("PACK_NOT_APPROVED", sub())
    expect("CHANNEL_NOT_ALLOWED", sub(channel=FuChannel.phone_radio))
    expect("EVIDENCE_REQUIRED", sub(channel=FuChannel.hand_delivered, external_document=f64()))
    expect("SUBMITTED_AT_INVALID", sub(submitted_at=local(2026, 10, 4, 23, 0), external_document=f64()))
    expect("SUBMITTED_AT_INVALID", sub(submitted_at=local(2026, 10, 6, 10, 10), external_document=f64()))


def test_ac22_lock_and_void(db: Session) -> None:
    g = reqs(db, fu2(db))["GACA-W"]
    noura = P(db, "noura.qahtani")
    tick(2026, 10, 6, 10, 0)
    s = submissions.record(db, noura, g.id, FuSubmissionCreate(
        channel=FuChannel.email, submitted_at=local(2026, 10, 6, 9, 0), reference_no="GACA-TEST-2",
        external_document=f64()))  # fmt: skip
    tick(2026, 10, 7, 11, 0)
    expect("SUBMISSION_LOCKED", lambda: submissions.update(db, noura, s.id, FuSubmissionUpdate(reference_no="GACA-TEST-3")))
    submissions.void(db, noura, s.id, FuSubmissionVoid(reason="Wrong requirement selected by mistake (TEST)."))
    assert status(db, g) == "due"
    tick(2026, 10, 8, 0, 0)
    assert status(db, g) == "overdue"


def test_ac23_operator_filer(db: Session) -> None:
    g = reqs(db, fu2(db))["GACA-W"]
    config.update_rule(db, P(db, "faisal.harbi"), db.scalar(select(FuRule.id).where(
        FuRule.project_id == g.project_id, FuRule.rule_code == "GACA-W")), FuRuleUpdate(filer=FuFiler.airport_operator))  # fmt: skip
    g.filer = FuFiler.airport_operator
    submissions.record(db, P(db, "noura.qahtani"), g.id, FuSubmissionCreate(
        channel=FuChannel.email, submitted_at=local(2026, 10, 6, 9, 0), reference_no="AOP-GACA-TEST-9",
        evidence_files=[f64("operator-confirmation.txt")]))  # fmt: skip
    assert status(db, g) == "submitted"


def test_ac24_overdue_alerts(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    t = tick(2026, 10, 7, 23, 30)
    rq.run_alerts(db, pid, t)
    assert "faisal.harbi" in notified(db, "followup_requirement", since=t)
    t2 = tick(2026, 10, 8, 7, 10)
    rq.daily_overdue(db, pid, t2)
    assert "faisal.harbi" in notified(db, "followup_requirement", since=t2)
    assert db.scalar(select(FuRequirement.id).where(FuRequirement.rule_code == "GACA-W")) is not None
