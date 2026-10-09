"""6c-emergency-drills §9 ACs 18, 60-62, 64-66 (KPIs, E18/E19, PDPL, retention, AR lists)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from tests.conftest import Api
from tests.emer_helpers import API, kpi, project

pytestmark = pytest.mark.usefixtures("emergency_seed", "clock")

# ED9 as reproduced by the seed (DECISIONS: K-106 and K-104 RBT-52 differ from the printed table).
ED9 = {
    "ANIA-EXP": {"K104": "80.0 %", "K105": "50.0 %", "K107": "96.6 %", "K108": "100.0 %",
                 "K109": "2"},
    "RBT-52": {"K104": "75.0 %", "K105": "100.0 %", "K107": "94.2 %", "K108": "0.0 %",
               "K109": "0"},
}  # fmt: skip


def emer(c: Any, db: Session, pcode: str, **params: Any) -> dict[str, Any]:
    q = {"project_id": str(project(db, pcode).id), "as_of": "2026-09-30", "period": "month",
         "anchor": "2026-09-30", **params}  # fmt: skip
    res = c.get(f"{API}/kpi/emergency", params=q)
    assert res.status_code == 200, res.text
    return res.json()  # type: ignore[no-any-return]


def comps(m: dict[str, Any]) -> dict[str, str]:
    return {c["key"]: c["display"] for c in m["components"]}


@pytest.mark.parametrize("code", ["ANIA-EXP", "RBT-52"])
def test_AC60_AC18_ed9(api: Api, db: Session, code: str) -> None:
    body = emer(api.as_("faisal.harbi"), db, code,
                group_by=["site", "drill_type", "asset_type", "event_type"])  # fmt: skip
    got = {m: kpi(body, m)["display"] for m in ED9[code]}
    for metric, display in ED9[code].items():
        assert got[metric].startswith(display), (metric, got)
    k105 = comps(kpi(body, "K105"))
    if code == "ANIA-EXP":
        assert ("7.5" in str(k105), "20.8" in str(k105)) == (True, True), k105
        k107 = kpi(body, "K107")
        assert (k107["numerator"], k107["denominator"]) == ("398", "412")
    else:
        assert "9.2" in str(k105) and "15.0" in str(k105), k105
        k107 = kpi(body, "K107")
        assert (k107["numerator"], k107["denominator"]) == ("147", "156")
    k106 = kpi(body, "K106")
    assert k106["denominator"] not in (None, "0"), k106
    kinds = {b["group_by"] for b in body["breakdowns"]}
    assert {"site", "asset_type"} <= kinds
    # EM-2: aggregates only — no worker numbers or names anywhere in the payload
    assert "WKR-" not in str(body)


def test_AC61_e18_e19(db: Session) -> None:
    from app.hse_jobs import project_scope
    from app.kpi import warnings as kwarn
    from app.kpi.periods import Window

    found: dict[str, dict[tuple[str, str | None], Any]] = {}
    for code in ("ANIA-EXP", "RBT-52"):
        sc = project_scope(db, project(db, code), date(2026, 10, 2))
        ws = kwarn.evaluate(sc, [Window(date(2026, 9, 1), date(2026, 9, 30))])
        found[code] = {
            (w.code.value, w.engagement.code if w.engagement else None): w
            for w in ws
            if w.code.value in ("E18", "E19")
        }
    assert {("E18", None), ("E18", "RAWABI"), ("E19", None), ("E19", "RAWABI")} <= set(
        found["ANIA-EXP"]
    )
    assert {("E19", None), ("E19", "QIMMA")} <= set(found["RBT-52"])
    e18 = {i.key: i.value for i in found["ANIA-EXP"][("E18", None)].inputs}
    assert (e18["k104_numerator"], e18["k104_denominator"]) == (4, 5)
    e19 = {i.key: i.value for i in found["RBT-52"][("E19", None)].inputs}
    assert Decimal(str(e19["k108"])) == 0
    text = " ".join(w.message_en + str([i.value for i in w.inputs])
                    for f in found.values() for w in f.values())  # fmt: skip
    assert "WKR-" not in text and "Ganesh" not in text


def test_AC62_ed10a_rounding() -> None:
    from app.core.hse_enums import KpiMetric
    from app.kpi import present
    from app.kpi.catalogue import CATALOGUE

    v = Decimal(9495) / Decimal(10000) * 100
    assert present.display(CATALOGUE[KpiMetric.K106], v) == "95.0 %"
    assert v < Decimal("95.0")  # E18 compares unrounded values


def test_AC64_viewer_and_contractor_names(api: Api, db: Session) -> None:
    from app.models import AuditEntry
    from tests.emer_helpers import drill, muster_of

    sarah = api.as_("sarah.mitchell")
    body = emer(sarah, db, "ANIA-EXP")
    assert {m["metric"] for m in body["metrics"]} == {f"K-{n}" for n in range(104, 110)}
    pid = project(db, "ANIA-EXP").id
    assert sarah.get(f"{API}/projects/{pid}/erps").status_code == 200
    m = muster_of(db, drill(db, "DRL-ANIA-EXP-2026-034"))
    res = sarah.get(f"{API}/musters/{m.id}")
    assert res.status_code == 200 and res.json()["entries"] is None
    before = db.query(AuditEntry).filter(AuditEntry.action == "sensitive_field_read").count()
    ahmed = api.as_("ahmed.zahrani")
    got = ahmed.get(f"{API}/musters/{m.id}").json()
    tree = {"RAWABI", "NAJD", "GULFPAVE", "SAHARA"}
    assert got["entries"] and {e["engagement_code"] for e in got["entries"]} <= tree
    db.expire_all()
    after = db.query(AuditEntry).filter(AuditEntry.action == "sensitive_field_read").count()
    assert after == before + 1


def test_AC65_retention_purge(api: Api, db: Session) -> None:
    from app.emergency_jobs import emergency_daily
    from app.models import AuditEntry, MusterEntry
    from tests.emer_helpers import drill, local, muster_of

    x = drill(db, "DRL-ANIA-EXP-2026-034")
    m = muster_of(db, x)
    n = db.query(MusterEntry).filter(MusterEntry.muster_id == m.id).count()
    emergency_daily(db, local(2027, 9, 25, 0, 8))
    db.commit()
    db.expire_all()
    m = muster_of(db, drill(db, "DRL-ANIA-EXP-2026-034"))
    assert db.query(MusterEntry).filter(MusterEntry.muster_id == m.id).count() == 0
    assert m.purged_at is not None and sum(m.summary["by_state"].values()) == n
    assert db.query(AuditEntry).filter(AuditEntry.action == "retention_purge",
                                       AuditEntry.entity_id == m.id).count() == 1  # fmt: skip
    d = api.as_("noura.qahtani").get(f"{API}/drills/{x.id}").json()
    assert (d["measures"]["evac_min"], d["result"]) == ("6.3", "satisfactory")
    got = api.as_("noura.qahtani").get(f"{API}/musters/{m.id}").json()
    assert got["entries"] is None and got["expected"] == n - m.extras


def test_AC66_arabic_lists(api: Api) -> None:
    ref = api.as_("noura.qahtani").get(f"{API}/emergency-reference").json()
    for key, items in ref.items():
        assert items, key
        for it in items:
            assert it["label_ar"].strip() and it["label_ar"] != it["label_en"], (key, it)
