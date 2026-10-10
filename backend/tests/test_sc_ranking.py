"""Phase 6g ranking, visibility, watch list, commendation and E25 (6g §9 AC 22-30)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.hse_enums import CaSourceType, ControlLevel
from app.core.scorecard_enums import (
    ScCardStatus,
    ScGrade,
    ScRemarkStatus,
    ScResolution,
    ScWatchAction,
    ScWatchDecision,
    ScWatchLevel,
    ScWatchProposal,
)
from app.models import Contractor, CorrectiveAction, ScRemark, ScWatchEntry
from app.schemas.scorecard import ScRemarkResolve, ScWatchCreate, ScWatchTransition
from app.services.scorecard import cards, remarks, watch
from app.services.scorecard import common as cm
from tests.conftest import Api
from tests.sc_helpers import API, SEP, P, card, eng, expect, notified, project, tick

pytestmark = pytest.mark.usefixtures("sc_seed", "sc_clock")
WL = "WL-ANIA-EXP-2026-002"


def _entry(db: Session) -> ScWatchEntry:
    w = db.scalar(select(ScWatchEntry).where(ScWatchEntry.entry_no == WL))
    assert w is not None
    return w


def _resolve_seeded(db: Session) -> None:
    r = db.scalar(select(ScRemark).where(ScRemark.status == ScRemarkStatus.open))
    assert r is not None
    remarks.resolve(
        db,
        P(db, "noura.qahtani"),
        r.id,
        ScRemarkResolve(
            resolution=ScResolution.rejected,
            resolution_text="The audit is attributed correctly to NAJD.",
        ),
    )


def test_ranking_sg3_ac22(db: Session, api: Api) -> None:
    pid = project(db, "ANIA-EXP").id
    rk = cards.ranking(db, P(db, "faisal.harbi"), pid, "2026-09")
    ranks = {r.engagement_code.split("-")[-1]: r.rank for r in rk.rows}
    assert [k for k, v in sorted(((k, v) for k, v in ranks.items() if v), key=lambda x: x[1])] == [
        "RAWABI",
        "GULFPAVE",
        "NAJD",
        "SAHARA",
    ]
    assert rk.median_display == "82.5"
    r = api.as_("faisal.harbi").get(
        f"{API}/kpi/scorecards",
        params={
            "project_id": str(pid),
            "period": "custom",
            "start": "2026-09-01",
            "end": "2026-09-30",
        },
    )
    assert r.status_code == 200, r.text
    k132 = next(m for m in r.json()["metrics"] if m["metric"] in ("K132", "K-132"))
    assert k132["display"] == "84.2"


def test_visibility_ac23_24(db: Session) -> None:
    tariq = P(db, "tariq.mutairi")
    najd, sahara = card(db, "ANIA-EXP", "NAJD"), card(db, "ANIA-EXP", "SAHARA")
    for c, n in ((najd, 3), (sahara, 4)):
        info = cards.read(db, tariq, c.id).ranking
        assert (info.rank, info.rank_of, info.median_display) == (n, 4, "82.5")
    for short in ("RAWABI", "GULFPAVE"):
        cid = card(db, "ANIA-EXP", short).id
        expect("NOT_FOUND", lambda cid=cid: cards.read(db, tariq, cid))  # type: ignore[misc]
    rows = cards.ranking(db, tariq, project(db, "ANIA-EXP").id, "2026-09").rows
    assert {r.engagement_code.split("-")[-1] for r in rows} == {"NAJD", "SAHARA"}
    sarah = P(db, "sarah.mitchell")
    expect("NOT_FOUND", lambda: cards.read(db, sarah, najd.id))  # Issued September
    aug = card(db, "ANIA-EXP", "SAHARA", "2026-08")
    assert cards.read(db, sarah, aug.id).watch_level == ScWatchLevel.watch
    expect(
        "FORBIDDEN",
        lambda: remarks.list_remarks(
            db, sarah, project(db, "ANIA-EXP").id, None, None, None, None, 1, 50
        ),
    )
    expect("NOT_FOUND", lambda: cards.read(db, P(db, "yousef.ghamdi"), aug.id))


def test_watch_sg4_ac25(db: Session) -> None:
    w = _entry(db)
    assert w.engagement_id == eng(db, "ANIA-EXP", "SAHARA").id
    assert w.level == ScWatchLevel.watch and w.baseline_score == Decimal("71.5")
    assert cm.local_day(w.opened_at) == date(2026, 9, 15)
    ca = db.get(CorrectiveAction, w.review_ca_id)
    assert (
        ca is not None
        and ca.source_type == CaSourceType.scorecard
        and ca.due_date == date(2026, 9, 22)
    )
    assert ca.priority.value == "high"
    assert {"tariq.mutairi", "ahmed.zahrani", "noura.qahtani", "faisal.harbi"} <= set(
        _audience(db, w)
    )


def _audience(db: Session, w: ScWatchEntry) -> list[str]:
    from app.models import User

    return [
        u.email.split("@")[0]
        for u in db.scalars(
            select(User).where(User.id.in_(watch.audience(db, w.project_id, w.engagement_id)))
        )
    ]


def _pip_ca(db: Session, w: ScWatchEntry, level: ControlLevel, days: int = 20) -> CorrectiveAction:
    pr = project(db, "ANIA-EXP")
    ca = cm.make_ca(
        db,
        pr,
        CaSourceType.scorecard,
        w.id,
        watch._site(db, pr.id),
        None,
        w.engagement_id,
        "major",
        "PIP action",
        "Improvement plan action for the engagement.",
        level,
        None,
        None,
    )
    ca.due_date = ca.original_due_date = ca.created_date + timedelta(days=days)
    db.flush()
    return ca


def test_watch_escalation_ac26_27_28(db: Session) -> None:
    pr = project(db, "ANIA-EXP")
    sahara = card(db, "ANIA-EXP", "SAHARA")
    sahara.score, sahara.grade, sahara.status = Decimal("70.0"), ScGrade.C, ScCardStatus.final
    db.flush()
    t = tick(2026, 10, 15, 10)
    watch.evaluate_month(db, pr, SEP, t)
    w = _entry(db)
    assert w.proposal == ScWatchProposal.improvement_plan
    faisal, tariq = P(db, "faisal.harbi"), P(db, "tariq.mutairi")
    watch.transition(db, faisal, w.id, ScWatchTransition(action=ScWatchAction.confirm_escalation))
    assert w.level == ScWatchLevel.improvement_plan and w.pip_due_on is not None
    two = [_pip_ca(db, w, ControlLevel.administrative).id for _ in range(2)]
    expect(
        "PIP_INCOMPLETE",
        lambda: watch.transition(
            db, tariq, w.id, ScWatchTransition(action=ScWatchAction.submit_pip, pip_ca_ids=two)
        ),
    )
    three = [*two, _pip_ca(db, w, ControlLevel.engineering).id]
    watch.transition(
        db, tariq, w.id, ScWatchTransition(action=ScWatchAction.submit_pip, pip_ca_ids=three)
    )
    watch.transition(db, faisal, w.id, ScWatchTransition(action=ScWatchAction.accept_pip))
    late = db.get(CorrectiveAction, two[0])
    assert late is not None
    late.due_date = date(2026, 10, 1)
    t = tick(2026, 10, 16, 0, 20)
    watch.daily(db, t)
    assert w.proposal == ScWatchProposal.suspension_review
    watch.transition(db, faisal, w.id, ScWatchTransition(action=ScWatchAction.confirm_escalation))
    watch.transition(
        db,
        faisal,
        w.id,
        ScWatchTransition(
            action=ScWatchAction.decide,
            decision=ScWatchDecision.suspend,
            reason="PIP actions overdue; suspension recommended.",
        ),
    )
    con = db.get(Contractor, eng(db, "ANIA-EXP", "SAHARA").contractor_id)
    assert con is not None
    before = con.status
    form = watch.suspension_form(db, faisal, w.id)
    assert form.status_reason == f"HSE performance — {WL}" and "every project" in form.warning_en
    assert con.status == before  # never suspended by the platform
    expect(
        "WATCH_ENTRY_OPEN",
        lambda: watch.open_manual(
            db,
            faisal,
            pr.id,
            ScWatchCreate(
                engagement_id=w.engagement_id, reason="Client instruction to watch this contractor."
            ),
        ),
    )


def test_commended_and_e25_ac29_30(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    for m in ("2026-07", "2026-08", "2026-09"):
        c = card(db, "ANIA-EXP", "RAWABI", m)
        c.grade, c.caps_applied = ScGrade.A, []
    gp = card(db, "ANIA-EXP", "GULFPAVE")
    gp.grade = ScGrade.D
    db.flush()
    tick(2026, 10, 15, 10)
    _resolve_seeded(db)
    out = cards.finalise(db, P(db, "faisal.harbi"), pid, "2026-09")
    assert card(db, "ANIA-EXP", "RAWABI").commended
    assert any(w.startswith("E25 ") and "GULFPAVE" in w and "grade_d" in w for w in out.warnings)
    assert not any("tariq" in w.lower() for w in out.warnings)
    assert any(
        x.startswith("E25") for x in notified(db, "scorecard_finalise_due").get("faisal.harbi", [])
    )
