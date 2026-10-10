"""Phase 6g monthly cycle, disputes, finalisation and restatement (6g §9 AC 10, 11, 13-21)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.scorecard_enums import (
    RpType,
    ScCardStatus,
    ScDisputeReason,
    ScLineStatus,
    ScRemarkKind,
    ScRemarkStatus,
    ScResolution,
    ScScope,
)
from app.models import CorrectiveAction, Incident, InjuryCase, RpPack, ScCard, ScRemark
from app.schemas.scorecard import ScRemarkCreate, ScRemarkResolve
from app.services.scorecard import cards, remarks
from app.services.scorecard import common as cm
from tests.sc_helpers import SEP, P, card, expect, line, notified, project, tick

pytestmark = pytest.mark.usefixtures("sc_seed", "sc_clock")


def _dispute(
    code: str = "SM-OBS", text: str = "The observation count is attributed to the wrong contractor."
) -> ScRemarkCreate:
    return ScRemarkCreate(
        kind=ScRemarkKind.dispute,
        target_code=code,
        reason_code=ScDisputeReason.wrong_attribution,
        text=text,
    )


def _seeded(db: Session) -> ScRemark:
    r = db.scalar(
        select(ScRemark).where(
            ScRemark.kind == ScRemarkKind.dispute, ScRemark.status == ScRemarkStatus.open
        )
    )
    assert r is not None
    return r


def test_cards_issued_ac10_11_13(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    own = cards.current(db, pid, SEP, ScScope.own)
    shorts = sorted(cm.eng(db, c.engagement_id).contractor.short_code for c in own)
    assert len(own) == 4 and "DLIFT" not in shorts  # AC10: no hours -> no card
    tree = cards.current(db, pid, SEP, ScScope.tree)
    assert sorted(cm.eng(db, c.engagement_id).contractor.short_code for c in tree) == [
        "NAJD",
        "RAWABI",
    ]
    for c in own + tree:
        assert c.status == ScCardStatus.issued
        assert (
            c.comment_until is not None
            and cm.to_local(c.comment_until).strftime("%Y-%m-%d %H:%M") == "2026-10-14 23:59"
        )
    rawabi_tree = next(
        c for c in tree if cm.eng(db, c.engagement_id).contractor.short_code == "RAWABI"
    )
    assert rawabi_tree.rank is None  # AC11: tree cards are not ranked
    assert all(c.rank is not None or c.rank_status.value != "ranked" for c in own)


def test_month_not_locked_ac14(db: Session) -> None:
    t = tick(2026, 11, 12, 6)
    out = cards.run_monthly(db, t)
    assert out["issued"] == 0 and out["alerts"] >= 1
    assert not cards.current(db, project(db, "ANIA-EXP").id, date(2026, 10, 1), None)
    assert any(
        "not Locked" in x
        for x in notified(db, "scorecard_month_not_locked").get("faisal.harbi", [])
    )
    assert cards.run_monthly(db, t)["alerts"] == 0  # once per day
    assert cards.run_monthly(db, tick(2026, 11, 13, 6))["alerts"] >= 1  # and daily after


def test_dispute_create_ac15_16_21(db: Session) -> None:
    c = card(db, "ANIA-EXP", "NAJD")
    t = P(db, "tariq.mutairi")
    r = remarks.create(db, t, c.id, _dispute())
    assert r.status == ScRemarkStatus.open and r.due_at is not None
    assert cm.to_local(r.due_at).strftime("%Y-%m-%d %H:%M") == "2026-10-15 23:59"
    alerted = notified(db, "scorecard_dispute")
    assert "noura.qahtani" in alerted and "faisal.harbi" in alerted
    expect("FORBIDDEN", lambda: remarks.create(db, P(db, "ramesh.kumar"), c.id, _dispute()))
    w = remarks.create(
        db, t, c.id, _dispute(text="Worker ID 2123456789 should not count here, please check.")
    )
    assert any(x.code == "POSSIBLE_ID_NUMBER" for x in w.warnings)
    case = db.scalar(
        select(InjuryCase)
        .join(Incident, Incident.id == InjuryCase.incident_id)
        .where(
            Incident.responsible_engagement_id == c.engagement_id,
            InjuryCase.person_name.is_not(None),
        )
    )
    if case is not None:
        expect(
            "IDENTITY_IN_TEXT",
            lambda: remarks.create(
                db, t, c.id, _dispute(text=f"The case of {case.person_name} was not ours at all.")
            ),
        )
    tick(2026, 10, 15, 10)
    expect("COMMENT_WINDOW_CLOSED", lambda: remarks.create(db, t, c.id, _dispute()))


def test_dispute_resolve_ac17_18(db: Session) -> None:
    r = _seeded(db)
    noura, faisal = P(db, "noura.qahtani"), P(db, "faisal.harbi")
    ca = db.scalar(
        select(CorrectiveAction)
        .where(CorrectiveAction.project_id == r.project_id)
        .order_by(CorrectiveAction.ref)
    )
    assert ca is not None
    body = ScRemarkResolve(
        resolution=ScResolution.upheld_data_corrected,
        resolution_text="The record was corrected in Phase 3.",
        corrected_record_ref=ca.ref,
    )
    expect("CORRECTION_NOT_FOUND", lambda: remarks.resolve(db, noura, r.id, body))
    ca.updated_at = tick(2026, 10, 13, 9)
    db.flush()
    out = remarks.resolve(db, noura, r.id, body)
    assert (
        out.status == ScRemarkStatus.resolved
        and out.old_score is not None
        and out.new_score is not None
    )
    c = card(db, "ANIA-EXP", "NAJD")
    a = remarks.create(db, P(db, "tariq.mutairi"), c.id, _dispute("SM-PTW-AUDIT"))
    excl = ScRemarkResolve(
        resolution=ScResolution.upheld_metric_excluded,
        resolution_text="The metric is excluded for this month.",
    )
    expect("FORBIDDEN", lambda: remarks.resolve(db, noura, a.id, excl))
    remarks.resolve(db, faisal, a.id, excl)
    assert line(db, c, "SM-PTW-AUDIT").line_status == ScLineStatus.excluded_by_manager
    b = remarks.create(db, P(db, "tariq.mutairi"), c.id, _dispute("CP-2"))
    expect("CAP_NOT_EXCLUDABLE", lambda: remarks.resolve(db, faisal, b.id, excl))


def test_finalise_ac19(db: Session) -> None:
    faisal = P(db, "faisal.harbi")
    pid = project(db, "ANIA-EXP").id
    tick(2026, 10, 13, 10)
    expect("COMMENT_WINDOW_OPEN", lambda: cards.finalise(db, faisal, pid, "2026-09"))
    tick(2026, 10, 15, 10)
    expect("DISPUTES_OPEN", lambda: cards.finalise(db, faisal, pid, "2026-09"))
    remarks.resolve(
        db,
        P(db, "noura.qahtani"),
        _seeded(db).id,
        ScRemarkResolve(
            resolution=ScResolution.rejected,
            resolution_text="The audit is attributed correctly to NAJD.",
        ),
    )
    out = cards.finalise(db, faisal, pid, "2026-09")
    assert out.finalised == 6 and out.scp_issued == 4
    assert all(c.status == ScCardStatus.final for c in cards.current(db, pid, SEP, None))
    scps = db.scalars(
        select(RpPack).where(
            RpPack.report_type == RpType.SCP, RpPack.period_start == SEP, RpPack.project_id == pid
        )
    ).all()
    assert len(scps) == 4 and "tariq.mutairi" in notified(
        db, "report_pack_issued", datetime(2026, 10, 15, 6, 0, tzinfo=UTC)
    )


def test_restatement_reissue_ac20(db: Session) -> None:
    aug = card(db, "ANIA-EXP", "NAJD", "2026-08")
    assert aug.status == ScCardStatus.final
    aug.inputs_hash = "changed-by-a-later-edit"
    db.flush()
    t = tick(2026, 10, 13, 0, 20)
    assert cards.restatement(db, t) >= 1
    assert aug.revised_since_final and aug.recomputed_score is not None
    assert cards.restatement(db, t) == 0  # alerts once per revision
    faisal = P(db, "faisal.harbi")
    expect("VALIDATION_ERROR", lambda: cards.reissue(db, faisal, aug.id, ""))
    new = cards.reissue(db, faisal, aug.id, "Phase 6d response corrected after Final.")
    assert new.revision == 1 and new.status == ScCardStatus.issued
    assert db.get(ScCard, aug.id).status == ScCardStatus.superseded  # type: ignore[union-attr]
