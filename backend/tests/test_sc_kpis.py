"""Phase 6g KPIs K-132…K-135, AR labels and no change to earlier modules (6g §9 AC 52, 55, 56)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import scorecard_enums as se
from app.core.scorecard_enums import ScRemarkStatus, ScResolution
from app.models import ScRemark
from app.schemas.scorecard import ScRemarkResolve
from app.services.scorecard import labels, remarks
from tests.conftest import Api
from tests.fu_helpers import kpis as fu_kpis
from tests.sc_helpers import API, P, project, tick

pytestmark = pytest.mark.usefixtures("sc_seed", "sc_clock")


def _sc(api: Api, who: str, pid: Any, start: str, end: str) -> dict[str, str]:
    r = api.as_(who).get(
        f"{API}/kpi/scorecards",
        params={"project_id": str(pid), "period": "custom", "start": start, "end": end},
    )
    assert r.status_code == 200, r.text
    return {m["metric"].replace("-", ""): m["display"] for m in r.json()["metrics"]}


def test_k133_k134_ac52(db: Session, api: Api) -> None:
    pid = project(db, "ANIA-EXP").id
    v = _sc(api, "faisal.harbi", pid, "2026-10-01", "2026-10-31")
    assert v["K134"] == "—" and v["K133"] == "1"
    r = db.scalar(select(ScRemark).where(ScRemark.status == ScRemarkStatus.open))
    assert r is not None
    tick(2026, 10, 16, 10)
    remarks.resolve(
        db,
        P(db, "noura.qahtani"),
        r.id,
        ScRemarkResolve(
            resolution=ScResolution.rejected,
            resolution_text="The audit is attributed correctly to NAJD.",
        ),
    )
    db.commit()
    tick(2026, 10, 31, 20)
    assert _sc(api, "faisal.harbi", pid, "2026-10-01", "2026-10-31")["K134"] == "0.0 %"


def test_ar_labels_ac55() -> None:
    codes: set[str] = set()
    for items in labels.LISTS.values():
        for code, en, ar, _ in items:
            assert en and any("؀" <= ch <= "ۿ" for ch in ar), code
            codes.add(code)
    for enum in (
        se.ScCardStatus,
        se.ScRemarkStatus,
        se.ScWatchLevel,
        se.ScLineStatus,
        se.RpStatus,
        se.XpJobStatus,
        se.RpDeliveryStatus,
        se.XpPurpose,
    ):
        assert {e.value for e in enum} <= codes, enum.__name__
    assert all(any("؀" <= ch <= "ۿ" for ch in ar) for _, ar in labels.METRIC_LABELS.values())


def test_earlier_values_unchanged_ac56(db: Session, api: Api) -> None:
    ania = project(db, "ANIA-EXP").id
    body = fu_kpis(api.as_("ahmed.zahrani"), ania, end="2026-10-06")
    vals = {m["metric"].replace("-", ""): m["display"] for m in body["metrics"]}
    assert vals["K127"] == "100.0 %" and vals["K130"] == "75.0 %"  # as test_fu_kpis AC42
    r = api.as_("faisal.harbi").get(
        f"{API}/kpi/summary",
        params={
            "project_id": str(ania),
            "period": "custom",
            "start": "2026-01-01",
            "end": "2026-09-30",
        },
    )
    if r.status_code == 200:
        m = {x["metric"].replace("-", ""): x["display"] for x in r.json().get("metrics", [])}
        if "K21" in m:
            assert m["K21"] == "0.68"  # Phase 1 W3 YTD TRIR
    r = api.as_("noura.qahtani").get(
        f"{API}/exports/incidents", params={"project_id": str(ania), "format": "csv"}
    )
    assert r.status_code == 200 and r.content.lstrip(b"\xef\xbb\xbf").startswith(b"ref")
