"""6b-heat-stress §9 ACs 48, 49, 51-53 (heat-illness log: HS6 context, HI-1, HI-4, voids, P6b-2)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.core.hse_enums import IncidentStatus
from app.models import AuditEntry, HeatIllnessEntry, Incident, InjuryCase
from app.services.heat import log as heat_log
from tests.conftest import Api
from tests.heat_helpers import API, local, notified, project

pytestmark = pytest.mark.usefixtures("heat_seed", "clock")


def entry(db: Session, no: str) -> HeatIllnessEntry:
    db.expire_all()
    e = db.scalar(select(HeatIllnessEntry).where(HeatIllnessEntry.entry_no == no))
    assert e is not None, no
    return e


def test_AC48_hs6_context(db: Session) -> None:
    e = entry(db, "HIL-ANIA-EXP-2026-014")
    cx = e.context
    assert (cx["reading_no"], cx["wbgt_c"], cx["state"]) == (
        "WBG-ANIA-EXP-20260922-0032", "30.4", "current"
    )  # fmt: skip
    assert (cx["workload"], cx["acclimatisation"], cx["regime"]) == ("heavy", "acclimatised", "R3")
    assert cx["ban_in_force"] is False and cx["possible_ban_breach"] is False
    assert cx["heat_awr_in_force"] is True
    assert cx["welfare"]["result"] == "pass" and cx["welfare"]["station_code"] == "RS-SAIR-01"
    assert cx["hold_no"] == "MFH-ANIA-EXP-2026-00019"
    assert e.review is not None and e.review["answers"]["HC3"] == "no"
    assert e.control_gap is True
    assert e.event_at == local(2026, 9, 22, 13, 50)


def _fac_case(db: Session) -> tuple[InjuryCase, Incident]:
    pid = project(db, "ANIA-EXP").id
    row = db.execute(
        select(InjuryCase, Incident)
        .join(Incident, Incident.id == InjuryCase.incident_id)
        .where(
            Incident.project_id == pid,
            Incident.occurred_date >= local(2026, 9, 1).date(),
            InjuryCase.nature != "heat_exhaustion",
            Incident.work_related.is_(True),
            Incident.status != IncidentStatus.voided,
        )
        .order_by(Incident.occurred_at)
    ).first()
    assert row is not None
    return row[0], row[1]


def test_AC49_AC51_AC52_hi1_overdue_void(db: Session) -> None:
    c, inc = _fac_case(db)
    heat_log.on_case(db, c)  # laceration etc.: no entry
    db.commit()
    assert db.scalar(select(HeatIllnessEntry).where(HeatIllnessEntry.source_id == c.id)) is None
    c.nature = type(c.nature)("heat_exhaustion")
    heat_log.on_case(db, c)
    db.commit()
    e = db.scalar(select(HeatIllnessEntry).where(HeatIllnessEntry.source_id == c.id))
    assert e is not None and e.status.value == "open"
    # HI-4: due at created + 3 days → officers; +2 days → manager
    since = e.created_at
    due = heat_log.review_due(db, e)
    set_now(due + timedelta(minutes=1))
    heat_log.overdue_alerts(db, e.project_id, due + timedelta(minutes=1))
    db.commit()
    got = notified(db, "heat_review_overdue", since)
    assert "noura.qahtani" in got and "faisal.harbi" not in got
    heat_log.overdue_alerts(db, e.project_id, due + timedelta(days=2))
    db.commit()
    assert "faisal.harbi" in notified(db, "heat_review_overdue", since)
    # source incident voided → entry voided
    inc.status = IncidentStatus.voided
    heat_log.on_case(db, c)
    db.commit()
    db.refresh(e)
    assert e.status.value == "voided"


def test_AC53_access(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    url = f"{API}/projects/{pid}/heat-illness-log"
    assert api.as_("sanjay.verma").get(url).status_code == 403
    ahmed = api.as_("ahmed.zahrani")
    res = ahmed.get(url, params={"page_size": 100})
    assert res.status_code == 200, res.text
    rows = {x["entry_no"]: x for x in res.json()["items"]}
    assert "HIL-ANIA-EXP-2026-014" in rows
    e = entry(db, "HIL-ANIA-EXP-2026-014")
    one = ahmed.get(f"{API}/heat-illness-log/{e.id}").json()
    assert one["worker"]["worker_no"] == "WKR-000033"  # names follow capability 29 (P6b-2)
    assert one["review"]["factors_text"] is None
    full = api.as_("noura.qahtani").get(f"{API}/heat-illness-log/{e.id}").json()
    assert full["review"]["factors_text"]
    reads = db.scalars(
        select(AuditEntry).where(
            AuditEntry.entity_id == e.id, AuditEntry.action == "sensitive_field_read"
        )
    ).all()
    assert len(reads) >= 2
