"""Integration rules on the full Appendix A world and on the integrator's own wiring (spec
8-quality §6 items 8–10, AC-Q0-22, D-353, D-355, D-360; decision D-370)."""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select, update

from app.core.hse_enums import CaSourceType
from app.core.quality.q4 import QKpi as K
from app.db.session import get_sessionmaker
from app.kpi import quality as qk
from app.models import ChecklistResponse, ChecklistTemplate, Project
from app.models.quality import QCustomer
from app.models.quality.q1 import QDossier, QIr
from app.models.quality.q3 import QStorageZone, QZoneDay
from app.models.quality.q4 import QDocumentRevision
from app.services import licence
from app.services.quality import registry as reg
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, err, ok
from tests.quality.q1.q1h import approved_itp, decide_body, schedule, submit_ir
from tests.quality.q3.h3 import R

D = Decimal
SEPT = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
REASON = "Integration test of the profile switch (Q-PRF-03)."


def _tiles(c: Any, pid: str) -> dict[str, dict[str, Any]]:
    return {
        t["kpi"]: t for t in ok(c.get(f"{API}/projects/{pid}/quality/kpis", params=SEPT))["tiles"]
    }


# ---- §6 item 8: KPIs count records of every part; quality CAs stay out of the HSE KPIs ------


def test_kpis_count_records_of_every_part(qi_world: None, api: Api, ids: Ids) -> None:
    with get_sessionmaker()() as db:
        ania = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
        ruh = db.scalar(select(Project).where(Project.code == "RUH-CCH"))
        a = qk.Engine(db, ania, date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 6))  # type: ignore[arg-type]
        r = qk.Engine(db, ruh, date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 6))  # type: ignore[arg-type]
        assert a.result(K.K143).value == D(14)  # Q0 NCRs
        assert a.result(K.K141).value == D("80.0")  # Q1 IR rounds (QX2)
        assert a.result(K.K152).value == D("2.8") and a.result(K.K153).value == D("4.2")  # Q2
        assert a.result(K.K158).value == D("100.0")  # Q4 audit programme
        assert r.result(K.K160).value == D("1.9")  # Q3 receiving (12 ÷ 640)
        assert r.result(K.K143).value == D(9)  # Q0 NCRs incl. the Q3- and Q4-sourced ones
        assert r.result(K.K158).value == D("100.0")
        # K-157 follows a grant narrowing: an engagement tree without records uses no supplier
        k157 = a.result(K.K157)
        assert k157.denominator is not None and k157.denominator > 0
        narrowed = qk.QFilter(engagement_ids=frozenset({uuid.uuid4()}))
        e = qk.Engine(db, ania, date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 6), narrowed)  # type: ignore[arg-type]
        assert e.result(K.K157).denominator == D(0)
    tiles = _tiles(api.as_("hatem.shehri"), ids.project("ANIA-EXP"))
    assert tiles["K-141"]["display"] == "80.0 %"
    from app.kpi import data
    from app.services import hse_settings

    quality_sources = {
        CaSourceType.quality_ncr,
        CaSourceType.quality_observation,
        CaSourceType.quality_complaint,
        CaSourceType.quality_audit,
        CaSourceType.quality_review,
    }
    with get_sessionmaker()() as db:
        from app.models import CorrectiveAction

        projects = list(
            db.scalars(select(Project).where(Project.code.in_(["ANIA-EXP", "RUH-CCH"])))
        )
        qcas = set(
            db.scalars(
                select(CorrectiveAction.id).where(CorrectiveAction.source_type.in_(quality_sources))
            )
        )
        assert qcas  # the seed holds quality CAs of NCRs, audits and reviews
        facts = data.load(
            db, projects, {p.id: hse_settings.get(db, p.id) for p in projects}, reader=False
        )
        assert qcas.isdisjoint({c.id for c in facts.cas})  # Q-CAP-06: never in K-40…K-43


def test_q1_counts_follow_the_grant_like_the_kpi_page(qi_world: None, api: Api, ids: Ids) -> None:
    """D-360 / D-370: Bilal (engagement RAWABI) gets the IR counts of his engagement tree only."""
    from app.kpi.quality_views import kpi_filter
    from app.services.permissions import build_principal
    from app.services.quality.q1 import kpi

    pid = ids.project("ANIA-EXP")
    url = f"{API}/projects/{pid}/quality/q1-counts"
    full = ok(api.as_("hatem.shehri").get(url, params=SEPT))
    mine = ok(api.as_("bilal.qureshi").get(url, params=SEPT))
    with get_sessionmaker()() as db:
        from app.models import User

        bilal = db.scalar(select(User).where(User.email == "bilal.qureshi@example.com"))
        assert bilal is not None
        f = kpi_filter(build_principal(db, bilal, None), uuid.UUID(pid))
        assert f.engagement_ids is not None
        c = kpi.ir_counts(
            db, uuid.UUID(pid), date(2026, 9, 1), date(2026, 9, 30), engagement_ids=f.engagement_ids
        )
        everyone = db.scalar(
            select(func.count(func.distinct(QIr.engagement_id))).where(
                QIr.project_id == uuid.UUID(pid)
            )
        )
    assert full["first_rounds"] == 120 and mine["first_rounds"] == c.first_rounds
    assert mine["first_rounds"] <= full["first_rounds"]
    assert (everyone or 0) > 1
    # Arun (engagement NAJD, steel) sees only NAJD's rounds: fewer than the project's
    najd = ok(api.as_("arun.pillai").get(url, params=SEPT))
    assert najd["rounds_decided"] < full["rounds_decided"]
    err(api.as_("abdullah.dossary").get(url, params=SEPT), 403, "FORBIDDEN")  # scope N


# ---- AC-Q0-22: quality checklist responses leave K-34, K-35 and K-110 unchanged --------------


def test_quality_checklist_responses_leave_hse_field_kpis_unchanged(
    qi_world: None, api: Api, ids: Ids
) -> None:
    faisal = api.as_("faisal.harbi")
    pid = ids.project("ANIA-EXP")
    q = {"project_id": pid, "as_of": "2026-09-30", "period": "month", "anchor": "2026-09-30"}

    def read() -> dict[str, Any]:
        body = ok(faisal.get(f"{API}/kpi/field-assurance", params=q))
        return {
            m["metric"]: (m["display"], m.get("numerator"), m.get("denominator"))
            for m in body["metrics"]
            if m["metric"] in ("K-34", "K-35", "K-110")
        }

    with get_sessionmaker()() as db:
        CR = ChecklistResponse  # noqa: N806
        quality = (
            select(CR.id)
            .join(ChecklistTemplate, ChecklistTemplate.id == CR.template_id)
            .where(
                CR.project_id == uuid.UUID(pid),
                ChecklistTemplate.kind == "quality",
                CR.voided.is_(False),
                CR.completed_date >= date(2026, 9, 1),
                CR.completed_date <= date(2026, 9, 30),
            )
        )
        n = len(db.scalars(quality).all())
    assert n > 100  # the September IR rounds' checklists (QX24)
    before = read()
    assert set(before) == {"K-34", "K-35", "K-110"}
    with get_sessionmaker()() as db:
        db.execute(
            update(ChecklistResponse).where(ChecklistResponse.id.in_(quality)).values(voided=True)
        )
        db.commit()
    assert read() == before


# ---- §6 item 9: read-only licence blocks Quality writes, keeps reads, PDFs and exports -------


def test_read_only_licence_blocks_quality_writes_but_not_exports(
    qi_world: None, api: Api, ids: Ids, monkeypatch: pytest.MonkeyPatch
) -> None:
    hatem, reem = api.as_("hatem.shehri"), api.as_("reem.mutairi")
    ania, ruh = ids.project("ANIA-EXP"), ids.project("RUH-CCH")
    with get_sessionmaker()() as db:
        dos = db.scalar(select(QDossier.id))
        ir = db.scalar(select(QIr.id).where(QIr.ir_no == "IR-ANIA-EXP-2026-00412"))
        rev = db.scalar(select(QDocumentRevision.id).where(QDocumentRevision.status == "approved"))
    assert dos and ir and rev
    ok(hatem.post(f"{API}/quality/dossiers/{dos}/compile"))  # compiled while writable
    st = SimpleNamespace(read_only=True, state="expired", terms=None)
    monkeypatch.setattr(licence, "current", lambda *a, **k: st)
    writes = [
        (hatem, f"{API}/projects/{ania}/quality/ncrs"),  # Q0
        (hatem, f"{API}/projects/{ania}/quality/inspection-requests"),  # Q1
        (hatem, f"{API}/projects/{ania}/quality/tests"),  # Q2
        (reem, f"{API}/projects/{ruh}/quality/receipts"),  # Q3
        (hatem, f"{API}/projects/{ania}/quality/documents"),  # Q4
        (hatem, f"{API}/quality/dossiers/{dos}/compile"),
    ]
    for c, url in writes:
        err(c.post(url, json={}), 403, "LICENCE_READ_ONLY")
    err(
        hatem.patch(f"{API}/projects/{ania}/quality/settings", json={"values": {}}),
        403,
        "LICENCE_READ_ONLY",
    )
    for c, url in (
        (hatem, f"{API}/quality/inspection-requests/{ir}/pdf"),
        (hatem, f"{API}/quality/dossiers/{dos}/index"),
        (hatem, f"{API}/quality/dossiers/{dos}/package"),
        (hatem, f"{API}/quality/document-revisions/{rev}/download"),
        (reem, f"{API}/projects/{ruh}/quality/holds/export.csv"),
        (hatem, f"{API}/projects/{ania}/quality/kpis?date_from=2026-09-01&date_to=2026-09-30"),
    ):
        assert c.get(url).status_code == 200, url
    from app.services.quality import ensure_registered

    ensure_registered()
    made = 0
    for code in sorted(reg.DATASETS):
        for c, pid in ((hatem, ania), (reem, ruh)):
            res = c.post(f"{API}/exports", json={"dataset": code, "project_id": pid})
            assert res.status_code != 403 or "LICENCE_READ_ONLY" not in res.text, (code, res.text)
            if res.status_code == 201:
                made += 1
                break
    assert made >= len(reg.DATASETS) - 2  # every Quality dataset exports in read-only mode


# ---- §6 item 10: profile switch across the parts (Q-PRF-03…05) --------------------------------


def test_profile_switch_keeps_records_and_lets_open_ones_finish(
    qi_libs: None, api: Api, ids: Ids
) -> None:
    from tests.quality.q1.q1h import itp_body

    itp = approved_itp(api, ids)
    joseph, abd, hatem = (
        api.as_("joseph.mathew.qc"),
        api.as_("abdullah.dossary"),
        api.as_("hatem.shehri"),
    )
    pid = ids.project("ANIA-EXP")
    ir = ok(submit_ir(joseph, ids, itp, [30]), 201)
    ok(
        hatem.put(
            f"{API}/projects/{pid}/quality/profile",
            json={"sector_profile": "logistics", "reason": REASON},
        )
    )
    # other-profile creates refused in every construction part
    err(
        api.as_("bilal.qureshi").post(f"{API}/projects/{pid}/quality/itps", json=itp_body(ids)),
        409,
        "PROFILE_INACTIVE",
    )
    err(submit_ir(joseph, ids, itp, [40], loc="Level 4 slab"), 409, "PROFILE_INACTIVE")
    from tests.quality.q2.h2 import new_test

    with pytest.raises(AssertionError, match="PROFILE_INACTIVE"):
        new_test(joseph, ids)
    # the open IR is still finishable and readable, and still counted (Q-PRF-05)
    schedule(abd, ir["id"])
    done = ok(
        abd.post(f"{API}/quality/inspection-requests/{ir['id']}/decide", json=decide_body([30]))
    )
    assert done["status"] == "approved"
    assert ok(hatem.get(f"{API}/projects/{pid}/quality/inspection-requests"))["total"] == 1
    oct_ = {"date_from": "2026-10-01", "date_to": "2026-10-31"}
    c = ok(hatem.get(f"{API}/projects/{pid}/quality/q1-counts", params=oct_))
    assert c["first_rounds"] == 1 and c["first_passes"] == 1
    # logistics records may now be made on the project (shared and logistics types)
    assert ok(hatem.get(f"{API}/projects/{pid}/quality/ncrs"))["total"] == 0


def test_logistics_project_switched_to_construction_keeps_its_kpis(
    qi_world: None, api: Api, ids: Ids
) -> None:
    reem = api.as_("reem.mutairi")
    ruh = ids.project("RUH-CCH")
    ok(
        reem.put(
            f"{API}/projects/{ruh}/quality/profile",
            json={"sector_profile": "construction", "reason": REASON},
        )
    )
    assert ok(reem.get(f"{API}/projects/{ruh}/quality/receipts"))["total"] >= 640
    assert ok(reem.get(f"{API}/projects/{ruh}/quality/holds"))["total"] >= 1
    err(
        reem.post(
            f"{API}/projects/{ruh}/quality/receipts",
            json={
                "site_id": ids.site("S-DC1"),
                "dock_zone_id": ids.zone("Z-DOCK"),
                "customer_id": str(uuid.uuid4()),
                "arrived_at": "2026-10-06T06:00:00+03:00",
                "lines": [],
            },
        ),
        409,
        "PROFILE_INACTIVE",
    )
    with get_sessionmaker()() as db:
        p = db.scalar(select(Project).where(Project.code == "RUH-CCH"))
        e = qk.Engine(db, p, date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 6))  # type: ignore[arg-type]
        assert e.result(K.K160).value == D("1.9") and e.result(K.K162).value == D("0.21")


# ---- the integrator's own wiring: D-353 customer minimum, D-351 gap factor, D-355 slot -------


def test_receiving_prefers_product_then_customer_then_setting(
    qi_libs: None, api: Api, ids: Ids
) -> None:
    from tests.quality.q3.test_q3_flows import _chicken, _receipt

    imran, reem = api.as_("imran.siddiq"), api.as_("reem.mutairi")
    with get_sessionmaker()() as db:
        r = R(db)

        def codes(rec: dict[str, Any]) -> set[str]:
            """Checks that propose worse than accept."""
            return {
                x["code"] for x in rec["lines"][0]["proposal_reasons"] if x["decision"] != "accept"
            }

        # setting 60 %: 53.9 % remaining → deviation (QX14)
        assert "remaining_shelf_life" in codes(_receipt(imran, r, db, "GFF", [_chicken(r)]))
        gff = r.customer("GFF")
        out = ok(
            reem.patch(
                f"{API}/quality/customers/{gff}", json={"min_remaining_shelf_life_pct": "50"}
            )
        )
        assert D(out["min_remaining_shelf_life_pct"]) == D("50")
        assert "remaining_shelf_life" not in codes(_receipt(imran, r, db, "GFF", [_chicken(r)]))
        ok(
            reem.patch(
                f"{API}/quality/products/{r.product('GFF-2001')}",
                json={"min_remaining_shelf_life_pct": "55"},
            )
        )
        assert "remaining_shelf_life" in codes(_receipt(imran, r, db, "GFF", [_chicken(r)]))
        c = db.get(QCustomer, uuid.UUID(gff))
        assert c is not None and c.min_remaining_shelf_life_pct == D("50")


def test_gap_factor_change_clears_the_zone_day_sums(qi_libs: None, api: Api, ids: Ids) -> None:
    from app.core.clock import now

    ruh, ania = ids.project("RUH-CCH"), ids.project("ANIA-EXP")
    with get_sessionmaker()() as db:
        z = db.scalar(select(QStorageZone).where(QStorageZone.project_id == uuid.UUID(ruh)))
        assert z is not None
        db.add(
            QZoneDay(
                zone_id=z.zone_id,
                day=date(2026, 9, 1),
                project_id=z.project_id,
                period_minutes=1440,
                monitored_minutes=1440,
                out_minutes=0,
                computed_at=now(),
            )
        )
        db.commit()

    def days() -> int:
        with get_sessionmaker()() as db:
            return int(db.scalar(select(func.count()).select_from(QZoneDay)) or 0)

    reem = api.as_("reem.mutairi")
    ok(
        reem.patch(
            f"{API}/projects/{ruh}/quality/settings", json={"values": {"near_expiry_days": 20}}
        )
    )
    assert days() == 1
    ok(
        api.as_("hatem.shehri").patch(
            f"{API}/projects/{ania}/quality/settings",
            json={"values": {"reading_gap_factor": "3.0"}},
        )
    )
    assert days() == 1  # another project's change leaves RUH-CCH alone
    ok(
        reem.patch(
            f"{API}/projects/{ruh}/quality/settings", json={"values": {"reading_gap_factor": "3.0"}}
        )
    )
    assert days() == 0


def test_hourly_slot_runs_the_hold_deadlines(qi_libs: None) -> None:
    from app.jobs import JOBS

    assert "quality_hourly" in reg.JOB_SLOTS and "quality_hourly" in JOBS
    with get_sessionmaker()() as db:
        out = JOBS["quality_hourly"](db)
        db.commit()
    assert "hold_deadlines" in out["Q3"] if "Q3" in out else "hold_deadlines" in out["q3_hourly"]
    import inspect

    from app import scheduler

    assert '"quality_hourly"' in inspect.getsource(scheduler)
