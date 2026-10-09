"""6d-field-assurance §9 ACs 36-48 (toolbox talks, topics, suggestions, campaigns)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.models import (
    BriefingCampaign,
    Deployment,
    GateCheck,
    QrToken,
    TalkAttendance,
    ToolboxTalk,
    Worker,
)
from app.schemas.field import (
    AttendanceAdd,
    CampaignCreate,
    CampaignTransition,
    TalkCreate,
    TopicCreate,
    VersionTransition,
)
from app.services.access import common as acommon
from app.services.field import campaigns, library, talks
from tests.emer_helpers import site
from tests.field_helpers import PNG, P, eng, expect, local, notified, project, topic, uid, zone

pytestmark = pytest.mark.usefixtures("field_seed", "clock")
SIG = {"file_name": "sig.png", "content_base64": PNG}


def deps(db: Session, eng_code: str, lang: str, n: int, status: str = "mobilised") -> list[Any]:
    e = eng(db, "ANIA-EXP", eng_code)
    return list(db.scalars(
        select(Deployment).join(Worker, Worker.id == Deployment.worker_id)
        .where(Deployment.engagement_id == e.id, Deployment.status == status,
               Worker.primary_language == lang).order_by(Worker.worker_no).limit(n)))  # fmt: skip


def card(db: Session, d: Any) -> str:
    q = acommon.active_qr(db, d.id)
    assert q is not None
    return acommon.payload(q)


def talk(db: Session, *, at: datetime | None = None, **kw: Any) -> dict[str, Any]:
    t = at or now() - timedelta(minutes=30)
    return {"client_uuid": str(uuid.uuid4()), "site_id": str(site(db, "S-LAND").id),
            "zone_ids": [str(zone(db, "Z-PIERB").id)],
            "host_engagement_id": str(eng(db, "ANIA-EXP", "NAJD").id), "shift": "day",
            "delivered_at": t.isoformat(), "duration_minutes": 15,
            "topics": [{"topic_id": str(topic(db, "TT-014").id)}], "language": "ur",
            "interpreter_languages": ["bn"], "presenter_user_id": str(uid(db, "noura.qahtani")),
            **kw}  # fmt: skip


def create(db: Session, who: str, b: dict[str, Any]) -> Any:
    return talks.create_talk(db, P(db, who), project(db, "ANIA-EXP").id,
                             TalkCreate.model_validate(b))  # fmt: skip


def test_AC36_evidence(db: Session) -> None:
    ws = deps(db, "NAJD", "ur", 6)
    rows = [{"method": "card_scan", "scanned_token": card(db, d)} for d in ws[:3]]
    rows += [{"method": "list", "deployment_id": str(d.id), "signature": SIG} for d in ws[3:5]]
    rows += [{"method": "list", "deployment_id": str(ws[5].id)}]
    expect("ATTENDANCE_EVIDENCE_REQUIRED",
           lambda: create(db, "ahmed.zahrani", talk(db, attendance=rows)), 422)  # fmt: skip
    db.rollback()
    out = create(db, "ahmed.zahrani", talk(db, attendance=rows, sheet_photos=[SIG]))
    assert out.named_count == 6 and len(out.attendance) == 6


def test_AC37_rows(db: Session) -> None:
    gone = deps(db, "GULFPAVE", "ur", 1, "demobilised")[0]
    expect("WORKER_NOT_MOBILISED", lambda: create(db, "noura.qahtani", talk(db, attendance=[
        {"method": "list", "deployment_id": str(gone.id), "signature": SIG}])))  # fmt: skip
    db.rollback()
    d = deps(db, "NAJD", "ur", 1)[0]
    n0 = db.scalar(select(func.count()).select_from(GateCheck))
    expect("DUPLICATE_ATTENDEE", lambda: create(db, "noura.qahtani", talk(db, attendance=[
        {"method": "card_scan", "scanned_token": card(db, d)},
        {"method": "card_scan", "scanned_token": card(db, d)}])))  # fmt: skip
    db.rollback()
    create(db, "noura.qahtani", talk(db, attendance=[{"method": "card_scan",
                                                      "scanned_token": card(db, d)}]))  # fmt: skip
    assert db.scalar(select(func.count()).select_from(GateCheck)) == n0


def test_AC38_language(db: Session) -> None:
    tl, bn = deps(db, "NAJD", "tl", 1)[0], deps(db, "NAJD", "bn", 1)[0]
    out = create(db, "noura.qahtani", talk(db, attendance=[
        {"method": "card_scan", "scanned_token": card(db, tl)},
        {"method": "card_scan", "scanned_token": card(db, bn)}]))  # fmt: skip
    ul = {r.deployment_id: r.understood_language.value for r in out.attendance}
    assert ul == {tl.id: "none", bn.id: "interpreter"}
    assert any(w.code == "LANGUAGE_MISMATCH" for w in out.warnings)
    assert out.briefed_count == 1 and out.named_count == 2


def test_AC39_unnamed_and_duration(db: Session) -> None:
    expect("ATTENDANCE_EVIDENCE_REQUIRED",
           lambda: create(db, "noura.qahtani", talk(db, unnamed_count=12)))  # fmt: skip
    db.rollback()
    e = expect("VALIDATION_ERROR",
               lambda: create(db, "noura.qahtani", talk(db, duration_minutes=4)))  # fmt: skip
    assert e.status_code == 422
    db.rollback()
    out = create(db, "noura.qahtani", talk(db, duration_minutes=8))
    assert any(w.code == "TBT_SHORT" for w in out.warnings)


def test_AC40_locked(db: Session) -> None:
    set_now(local(2026, 10, 5, 6, 40))
    out = create(db, "noura.qahtani", talk(db, at=local(2026, 10, 5, 6, 30)))
    db.commit()
    set_now(local(2026, 10, 6, 7, 0))
    d = deps(db, "NAJD", "ur", 1)[0]
    expect("TALK_LOCKED", lambda: talks.add_attendance(db, P(db, "noura.qahtani"), out.id,
                                                      AttendanceAdd.model_validate({"rows": [
        {"method": "card_scan", "scanned_token": card(db, d)}]})), 409)  # fmt: skip


def test_AC41_revoked_token_offline(db: Session) -> None:
    d1, d2 = deps(db, "NAJD", "ur", 2)
    tok = card(db, d2)
    q = acommon.active_qr(db, d2.id)
    assert q is not None
    q.status = q.status.__class__("revoked")
    db.flush()
    t = local(2026, 10, 6, 6, 30)
    out = create(db, "noura.qahtani", talk(db, at=t, attendance=[
        {"method": "card_scan", "scanned_token": card(db, d1)},
        {"method": "card_scan", "scanned_token": tok}]))  # fmt: skip
    assert [r.code for r in out.rejected_rows] == ["TOKEN_UNKNOWN"]
    assert out.recorded_offline and out.named_count == 1
    row = db.get(ToolboxTalk, out.id)
    assert row is not None and tok.split(":")[-1] not in str(row.rejected_rows)
    assert db.scalar(select(func.count()).select_from(QrToken).where(
        QrToken.token == tok.split(":")[-1])) == 1  # fmt: skip


def test_AC42_topics(db: Session) -> None:
    t = library.create_topic(db, P(db, "faisal.harbi"), TopicCreate.model_validate({
        "topic_code": "TT-099", "category": "general", "title_en": "Test topic",
        "title_ar": "موضوع", "key_points_en": ["One point"], "key_points_ar": []}))  # fmt: skip
    expect("TOPIC_INCOMPLETE", lambda: library.transition_topic(
        db, P(db, "faisal.harbi"), t.id, VersionTransition.model_validate({"action": "publish"})))  # fmt: skip
    db.rollback()
    old = topic(db, "TT-009")
    out = create(db, "noura.qahtani", talk(db, topics=[{"topic_id": str(old.id)}]))
    assert any(w.code == "TOPIC_REVIEW_OVERDUE" for w in out.warnings)
    expect("TOPIC_REVIEW_OVERDUE", lambda: _campaign(db, "TT-009"), 422)


def _campaign(db: Session, code: str, site_code: str = "S-LAND", **kw: Any) -> Any:
    b = {"topic_id": str(topic(db, code).id), "reason": "lesson",
         "message_en": "Brief every crew this week (TEST).", "site_ids": [str(site(db, site_code).id)],
         **kw}  # fmt: skip
    return campaigns.create_campaign(db, P(db, "faisal.harbi"), project(db, "ANIA-EXP").id,
                                     CampaignCreate.model_validate(b))  # fmt: skip


def test_AC43_suggestions(db: Session) -> None:
    c = _campaign(db, "TT-021")
    campaigns.transition_campaign(db, P(db, "faisal.harbi"), c.id,
                                  CampaignTransition.model_validate({"action": "issue"}))  # fmt: skip
    out = talks.suggestions(db, P(db, "noura.qahtani"), project(db, "ANIA-EXP").id,
                            site(db, "S-LAND").id, eng(db, "ANIA-EXP", "NAJD").id)  # fmt: skip
    codes = [s.topic_code for s in out.items]
    assert codes[0] == "TT-021" and out.items[0].source.value == "campaign"
    assert codes.index("TT-014") < codes.index("TT-007")
    gsi = next(s for s in out.items if s.topic_code == "TT-007")
    assert (gsi.source.value, gsi.reason_ref) == ("failed_item", "GSI-12")
    recent = [s.delivered_recently for s in out.items]
    assert recent == sorted(recent)  # recently delivered topics are moved last


def test_AC44_AC45_register_separate(db: Session, api: Any) -> None:
    from tests.field_helpers import API

    q = {"project_id": str(project(db, "ANIA-EXP").id), "as_of": "2026-10-06",
         "period": "month", "anchor": "2026-10-06"}  # fmt: skip
    c = api.as_("faisal.harbi")
    before = c.get(f"{API}/kpi/training", params=q).json()
    n0 = db.scalar(select(func.count()).select_from(ToolboxTalk))
    create(db, "noura.qahtani", talk(db, duration_minutes=30))
    db.commit()
    after = c.get(f"{API}/kpi/training", params=q).json()
    k37 = [m for m in after["metrics"] if m["metric"] == "K-37"]
    assert k37 == [m for m in before["metrics"] if m["metric"] == "K-37"]
    assert db.scalar(select(func.count()).select_from(ToolboxTalk)) == n0 + 1
    assert db.scalar(select(func.count()).select_from(TalkAttendance).where(
        TalkAttendance.talk_id.is_(None))) == 0  # fmt: skip


# ---- campaigns ------------------------------------------------------------------------------------


def test_AC46_AC47_cmp005(db: Session) -> None:
    from app.services.field.campaigns import pair_states

    c = db.scalar(select(BriefingCampaign).where(
        BriefingCampaign.campaign_no == "CMP-ANIA-EXP-2026-005"))  # fmt: skip
    assert c is not None
    st = {(eng_code(db, s.engagement_id)): s for s in pair_states(db, c)}
    assert set(st) == {"RAWABI", "GULFPAVE"}
    assert (str(st["GULFPAVE"].met_on), st["GULFPAVE"].on_time(c.due_date)) == ("2026-09-24", True)
    assert (str(st["RAWABI"].met_on), st["RAWABI"].on_time(c.due_date)) == ("2026-10-01", False)
    # AC47: issue alert to the reps, due-2 reminder to unmet reps, overdue reminder to officers
    from app.core.field_enums import CampaignStatus

    c.status = CampaignStatus.issued
    db.flush()
    set_now(local(2026, 9, 23, 6))
    t0 = now()
    campaigns.issue_alert(db, c)
    assert "ahmed.zahrani" in notified(db, "briefing_campaign", t0)
    set_now(local(2026, 9, 28, 7, 6))
    t1 = now()
    campaigns.daily(db, c.project_id, local(2026, 9, 28).date())
    assert "ahmed.zahrani" in notified(db, "briefing_campaign", t1)
    set_now(local(2026, 10, 1, 7, 6))
    t2 = now()
    campaigns.daily(db, c.project_id, local(2026, 10, 1).date())
    assert "noura.qahtani" in notified(db, "briefing_campaign", t2)


def eng_code(db: Session, eid: Any) -> str:
    from app.models import Contractor, ProjectEngagement

    e = db.get(ProjectEngagement, eid)
    assert e is not None
    c = db.get(Contractor, e.contractor_id)
    assert c is not None
    return str(c.short_code)


def test_AC48_campaign_validation(db: Session) -> None:
    e = expect("VALIDATION_ERROR", lambda: _campaign(db, "TT-020", reason="incident"))
    assert e.status_code == 422
    db.rollback()
    out = _campaign(db, "TT-020", message_en="Call 2123456789 for the briefing pack (TEST).")
    assert out.warnings
