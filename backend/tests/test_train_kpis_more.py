"""5-training §9 ACs 107-110, 113 (K-37 source switch, open sessions, staff hours, prior
learning, inductions) on the seeded September of ANIA-EXP."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import HseSettings, WorkforceReturn
from tests.conftest import Api
from tests.test_train_kpis import training
from tests.train_helpers import kpi, project, session

pytestmark = pytest.mark.usefixtures("train_seed", "clock")


def k(api: Api, db: Session, metric: str) -> dict[str, Any]:
    from app.kpi import data

    data.clear_cache()
    return kpi(training(api.as_("faisal.harbi"), db, "ANIA-EXP"), metric)


def dr_hours(db: Session, start: date, end: date) -> Decimal:
    pid = project(db, "ANIA-EXP").id
    return db.scalar(
        select(func.coalesce(func.sum(WorkforceReturn.training_hours), 0)).where(
            WorkforceReturn.project_id == pid,
            WorkforceReturn.work_date >= start,
            WorkforceReturn.work_date <= end,
        )
    ) or Decimal(0)


def set_from(db: Session, d: date | None) -> None:
    hs = db.scalar(select(HseSettings).where(HseSettings.project_id == project(db, "ANIA-EXP").id))
    assert hs is not None
    hs.training_register_from = d
    db.commit()


def test_P5AC107_source_switch(api: Api, db: Session) -> None:
    reg_all = Decimal(k(api, db, "K86")["value"])  # September register hours (contractors)
    before = dr_hours(db, date(2026, 9, 1), date(2026, 9, 15))
    after = dr_hours(db, date(2026, 9, 16), date(2026, 9, 30))
    set_from(db, date(2026, 9, 16))
    m = k(api, db, "K37")
    assert m["data_source"] == "mixed", m
    reg_late = Decimal(m["numerator"]) - before
    assert Decimal(0) < reg_late <= reg_all, (m["numerator"], before, reg_all)
    pct = abs(reg_late - after) / after * 100 if after else Decimal(0)
    has_note = any("differ" in (n.get("message_en") or n.get("text_en") or str(n))
                   for n in m["notes"])  # fmt: skip
    assert has_note == (pct > 5), (pct, m["notes"])
    set_from(db, None)
    m = k(api, db, "K37")
    assert m["data_source"] == "daily_returns", m
    assert Decimal(m["numerator"]) == before + after, m


def test_P5AC108_delivered_not_closed(api: Api, db: Session) -> None:
    base37, base86 = k(api, db, "K37"), k(api, db, "K86")
    s = session(db, "TRS-ANIA-EXP-2026-00062")  # SCAFF-AWR, closed, 2026-09-14
    s.status = "delivered"
    db.commit()
    m37, m86 = k(api, db, "K37"), k(api, db, "K86")
    assert Decimal(m86["value"]) < Decimal(base86["value"])
    assert Decimal(m37["numerator"]) < Decimal(base37["numerator"])
    assert "1 session" in str(m37["notes"]), m37["notes"]


def test_P5AC109_staff_hours_separate(api: Api, db: Session) -> None:
    m86, m37 = k(api, db, "K86"), k(api, db, "K37")
    staff = {c["key"]: c for c in m86["components"]}["staff"]
    assert Decimal(staff["value"]) > 0, staff
    # K-37 (register source for September) = contractor hours only
    assert Decimal(m37["numerator"]) == Decimal(m86["value"]), (m37, m86["value"])


def test_P5AC110_unsponsored_external_has_no_hours(api: Api, db: Session) -> None:
    import uuid

    from app.core.cert_enums import VerificationStatus
    from app.core.train_enums import TrainingRecordStatus
    from app.models import TrainingRecord
    from tests.train_helpers import provider, worker

    base = Decimal(k(api, db, "K86")["value"])
    w = worker(db, "WKR-000017")
    db.add(TrainingRecord(
        id=uuid.uuid4(), seq=999101, record_no="TRR-999101", worker_id=w.id,
        project_id=project(db, "ANIA-EXP").id, course_code="OSHA-30", source="external_certificate",
        provider_id=provider(db, "HAYAT").id, certificate_no="OSHA-PRIOR-1",
        completed_on=date(2026, 9, 20), valid_until=None, limiting_factor="none",
        hours=Decimal("30.00"), project_sponsored=False, name_as_printed="Biju Thomas",
        status=TrainingRecordStatus.accepted, verification_status=VerificationStatus.verified,
    ))  # fmt: skip
    db.commit()
    assert Decimal(k(api, db, "K86")["value"]) == base
    # control: the same record sponsored by the project counts (TH-3)
    r = db.scalar(select(TrainingRecord).where(TrainingRecord.record_no == "TRR-999101"))
    assert r is not None
    r.project_sponsored, r.sponsoring_project_id = True, r.project_id
    db.commit()
    assert Decimal(k(api, db, "K86")["value"]) == base + Decimal("30.00")


def test_P5AC113_inductions_in_k38_not_k37(api: Api, db: Session) -> None:
    from app.kpi import data
    from app.models import InductionRecord

    pid = project(db, "ANIA-EXP").id
    data.clear_cache()
    body = training(api.as_("faisal.harbi"), db, "ANIA-EXP")
    m37 = kpi(body, "K37")
    n_ind = db.scalar(select(func.count(InductionRecord.id)).where(
        InductionRecord.project_id == pid))  # fmt: skip
    assert n_ind
    from tests.train_helpers import API

    res = api.as_("faisal.harbi").get(f"{API}/kpi/dashboard", params={
        "project_id": str(pid), "period": "month", "anchor": "2026-09-30",
        "as_of": "2026-09-30"})  # fmt: skip
    assert res.status_code == 200, res.text
    k38 = next((m for m in res.json().get("metrics", []) if m["metric"] == "K-38"), None)
    if k38 is not None:
        assert Decimal(k38["value"] or 0) > 0, k38
    # K-37 numerator is register hours only (= K-86 contractor hours): no induction time
    assert Decimal(m37["numerator"]) == Decimal(kpi(body, "K86")["value"])
