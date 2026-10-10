"""Phase 6g profiles, settings, sources and the no-typed-score rule (6g §9 AC 1, 2, 12, 53, 54)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.scorecard_enums import ScCardStatus, ScProfileStatus
from app.models import AuditEntry, ScCard, ScSettings
from app.schemas.scorecard import (
    ScCapConfig,
    ScMetricPatch,
    ScProfileCreate,
    ScProfileUpdate,
    ScSettingsUpdate,
)
from app.services.scorecard import cards, config
from tests.conftest import Api
from tests.sc_helpers import API, P, card, expect, notified, project, tick

pytestmark = pytest.mark.usefixtures("sc_seed", "sc_clock")


def _draft(db: Session) -> str:
    return str(config.create_profile(db, P(db, "faisal.harbi"), ScProfileCreate()).id)


def test_profile_validation_ac1(db: Session, api: Api) -> None:
    f = P(db, "faisal.harbi")
    pid = _draft(db)
    import uuid

    x = uuid.UUID(pid)
    config.update_profile(
        db, f, x, ScProfileUpdate(metrics=[ScMetricPatch(metric_code="SM-TRIR", weight="11.5")])
    )
    expect("WEIGHTS_NOT_100", lambda: config.activate_profile(db, f, x))
    config.update_profile(
        db, f, x, ScProfileUpdate(metrics=[ScMetricPatch(metric_code="SM-TRIR", weight="12")])
    )
    config.update_profile(
        db, f, x, ScProfileUpdate(metrics=[ScMetricPatch(metric_code="SM-TRIR", enabled=False)])
    )
    expect("LAGGING_WEIGHT_OUT_OF_RANGE", lambda: config.activate_profile(db, f, x))
    db.rollback()
    x = uuid.UUID(_draft(db))
    caps = [
        ScCapConfig(cap_code=c.cap_code, max_grade=c.max_grade, enabled=c.cap_code.value != "CP-1")
        for c in config.get_profile(db, f, x).caps
    ]
    config.update_profile(db, f, x, ScProfileUpdate(caps=caps))
    expect("CAP_REQUIRED", lambda: config.activate_profile(db, f, x))
    db.commit()
    res = api.as_("noura.qahtani").patch(
        f"{API}/scorecard-profiles/{x}", json={"effective_from_month": "2026-11"}
    )
    assert res.status_code == 403


def test_profile_backdated_ac2(db: Session) -> None:
    import uuid

    f = P(db, "faisal.harbi")
    x = uuid.UUID(_draft(db))
    config.update_profile(db, f, x, ScProfileUpdate(effective_from_month="2026-08"))
    expect("PROFILE_BACKDATED", lambda: config.activate_profile(db, f, x))
    config.update_profile(db, f, x, ScProfileUpdate(effective_from_month="2026-09"))
    out = config.activate_profile(db, f, x)
    assert out.status == ScProfileStatus.active and out.version == 2
    aug = card(db, "ANIA-EXP", "NAJD", "2026-08")
    assert (aug.profile_code, aug.profile_version) == ("ORG", 1)
    assert config.profile_for(db, project(db, "ANIA-EXP"), date(2026, 10, 1)).version == 2


def test_no_typed_scores_ac12(db: Session, api: Api) -> None:
    c = card(db, "ANIA-EXP", "NAJD")
    cl = api.as_("faisal.harbi")
    assert (
        cl.patch(f"{API}/scorecards/{c.id}/lines/SM-PTW-AUDIT", json={"points": "100"}).status_code
        == 405
    )
    assert cl.patch(f"{API}/scorecards/{c.id}", json={"score": "99"}).status_code == 405
    body = cl.get(f"{API}/scorecards/{c.id}/lines/SM-PTW-AUDIT").json()
    assert body["metric_code"] == "SM-PTW-AUDIT"


def test_settings_ac53(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    f = P(db, "faisal.harbi")
    expect(
        "SETTING_OUT_OF_RANGE",
        lambda: config.update_settings(
            db, f, pid, ScSettingsUpdate(scorecard_min_exposure_hours=20000)
        ),
    )
    expect(
        "SETTING_OUT_OF_RANGE",
        lambda: config.update_settings(db, f, pid, ScSettingsUpdate(client_report_due_day=5)),
    )
    out = config.update_settings(db, f, pid, ScSettingsUpdate(scorecard_comment_days=4))
    assert out.scorecard_comment_days == 4
    assert (
        db.scalar(
            select(AuditEntry.id).where(
                AuditEntry.project_id == pid, AuditEntry.entity_type == "scorecard_settings"
            )
        )
        is not None
    )
    with pytest.raises(Exception) as ei:
        config.update_settings(
            db, P(db, "noura.qahtani"), pid, ScSettingsUpdate(scorecard_comment_days=5)
        )
    assert getattr(ei.value, "status_code", None) == 403


def test_sources_not_confirmed_ac54(db: Session) -> None:
    rbt = project(db, "RBT-52")
    s = db.get(ScSettings, rbt.id)
    assert s is not None
    s.sources_confirmed_at = None
    for c in db.scalars(select(ScCard).where(ScCard.project_id == rbt.id)):
        db.delete(c)
    db.flush()
    t = tick(2026, 10, 12, 11)
    expect("SOURCES_NOT_CONFIRMED", lambda: cards.issue_month(db, rbt, date(2026, 9, 1), t))
    assert "faisal.harbi" in notified(db, "scorecard_sources")
    config.confirm_sources(db, P(db, "faisal.harbi"), rbt.id)
    out = cards.issue_month(db, rbt, date(2026, 9, 1), t)
    assert out and all(c.status == ScCardStatus.issued for c in out)
