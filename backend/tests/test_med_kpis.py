"""6a-occupational-health §9 ACs 23, 77, 78, 82, 101-105, 109 (KPIs K-89…K-96 on the seed)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Contractor, ProjectEngagement
from tests.conftest import Api
from tests.med_helpers import API, hold, kpi, project, referral

pytestmark = pytest.mark.usefixtures("med_seed", "clock")

MF4 = {
    "ANIA-EXP": {"K89": "98.1 %", "K90": "97.5 %", "K91": "96", "K92": "71", "K93": "3",
                 "K94": "88.9 %", "K95": "83.3 %", "K96": "41"},
    "RBT-52": {"K89": "97.7 %", "K90": "97.7 %", "K91": "16", "K92": "12", "K93": "1",
               "K94": "100.0 %", "K95": "100.0 %", "K96": "6"},
}  # fmt: skip


def med(c: Any, db: Session, pcode: str, **params: Any) -> dict[str, Any]:
    q = {"project_id": str(project(db, pcode).id), "as_of": "2026-09-30", "period": "month",
         "anchor": "2026-09-30", **params}  # fmt: skip
    res = c.get(f"{API}/kpi/occupational-health", params=q)
    assert res.status_code == 200, res.text
    return res.json()  # type: ignore[no-any-return]


def comps(m: dict[str, Any]) -> dict[str, str]:
    return {c["key"]: c["display"] for c in m["components"]}


@pytest.mark.parametrize("code", ["ANIA-EXP", "RBT-52"])
def test_AC101_AC102_mf4(api: Api, db: Session, code: str) -> None:
    body = med(api.as_("faisal.harbi"), db, code)
    for metric, display in MF4[code].items():
        assert kpi(body, metric)["display"] == display, (metric, kpi(body, metric))
    k91 = comps(kpi(body, "K91"))
    assert (k91["workers"], k91["hook_gaps"]) == (
        ("87", "76") if code == "ANIA-EXP" else ("15", "16")
    )
    assert comps(kpi(body, "K93"))["overdue"] == ("1" if code == "ANIA-EXP" else "0")


def test_AC102_AC105_small_cells(api: Api, db: Session) -> None:
    sarah = med(api.as_("sarah.mitchell"), db, "RBT-52", group_by="trade", metric="K-91")
    k93 = med(api.as_("sarah.mitchell"), db, "RBT-52")
    assert kpi(k93, "K93")["display"] == "<5" and kpi(k93, "K93")["value"] is None
    assert comps(kpi(k93, "K93"))["overdue"] == "0"
    rows = {r["key"]: r for b in sarah["breakdowns"] for r in b["rows"]}
    small = [r for r in rows.values() if r["suppressed"]]
    assert small and all(r["display"] == "<5" for r in small)
    huda = med(api.as_("huda.mansour"), db, "RBT-52", group_by="trade", metric="K-91")
    assert not any(r["suppressed"] for b in huda["breakdowns"] for r in b["rows"])
    assert kpi(med(api.as_("huda.mansour"), db, "RBT-52"), "K93")["display"] == "1"


def test_AC23_wah_line_counts(api: Api, db: Session) -> None:
    body = med(api.as_("faisal.harbi"), db, "ANIA-EXP", code="WAH-FIT", metric="K-89")
    k89 = kpi(body, "K89")
    assert (k89["numerator"], k89["denominator"]) == ("504", "519")


def test_AC109_rawabi_tree(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    eng = db.scalar(
        select(ProjectEngagement)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(ProjectEngagement.project_id == pid, Contractor.short_code == "RAWABI")
    )
    assert eng is not None
    body = med(api.as_("faisal.harbi"), db, "ANIA-EXP", engagement_id=str(eng.id))
    assert kpi(body, "K89")["value"] is not None


def test_AC77_AC78_AC82_holds_and_referrals(db: Session) -> None:
    from app.core.med_enums import HoldStatus

    r = referral(db, "MFR-ANIA-EXP-2026-00012")
    assert r.assessed_at is not None
    assert round((r.assessed_at - r.raised_at).total_seconds() / 3600, 1) == 40.7
    assert r.assessed_at > r.due_at
    h16 = hold(db, "MFH-ANIA-EXP-2026-00016")
    assert h16.work_during_hold and h16.work_during_hold[0]["event_type"] == "gate_entry"
    for no, hours in (("MFH-ANIA-EXP-2026-00015", 458.7), ("MFH-ANIA-EXP-2026-00019", 15.9)):
        h = hold(db, no)
        assert h.status == HoldStatus.released and not h.work_during_hold
        assert h.released_at is not None
        assert round((h.released_at - h.started_at).total_seconds() / 3600, 1) == hours
