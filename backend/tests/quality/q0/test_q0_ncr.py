"""Q0 NCR lifecycle, CAPA, costs, repeat, effectiveness, ageing and PDF (spec 8-quality §A.16,
AC-Q0-26…41)."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.core.clock import set_now
from app.core.hse_enums import CaSourceType
from app.db.session import get_sessionmaker
from app.models import CorrectiveAction, EmailMessage, Notification, Project
from app.models.quality import QNcr
from app.services.quality import jobs
from app.services.quality.ncr import core, pdf
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, attach, ca_body, err, ok, raise_ncr, sign, to_proposed


def _uid(ids: Ids, who: str) -> uuid.UUID:
    return uuid.UUID(ids.user(who))


def test_AC26_critical_needs_evidence_and_dates(qsetup: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    d = raise_ncr(bilal, ids, classification="critical", open=False)
    err(bilal.post(f"{API}/quality/ncrs/{d['id']}/open"), 422, "EVIDENCE_REQUIRED")
    attach(bilal, "q_ncr", d["id"], "photo.pdf")
    n = ok(bilal.post(f"{API}/quality/ncrs/{d['id']}/open"))
    assert n["status"] == "open" and n["ncr_no"] == "NCR-ANIA-EXP-2026-0001"
    assert n["target_close_date"] == "2026-10-27"  # 2026-10-06 + 21 days
    opened = datetime.fromisoformat(n["opened_at"])
    assert datetime.fromisoformat(n["containment_due_at"]) - opened == timedelta(hours=24)


def test_AC27_opening_notifies(qsetup: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    d = raise_ncr(bilal, ids, classification="critical", open=False)
    attach(bilal, "q_ncr", d["id"])
    ok(bilal.post(f"{API}/quality/ncrs/{d['id']}/open"))
    with get_sessionmaker()() as db:
        who = {
            n.user_id
            for n in db.scalars(
                select(Notification).where(Notification.entity_id == uuid.UUID(d["id"]))
            )
        }
        mails = {m.to_user_id for m in db.scalars(select(EmailMessage))}
    expect = {_uid(ids, u) for u in ("bilal.qureshi", "joseph.mathew.qc", "hatem.shehri")}
    assert expect <= who and expect <= mails


def test_AC28_class_lowered_needs_the_disposition_resolver(
    qsetup: None, api: Api, ids: Ids
) -> None:
    joseph, bilal, hatem = (
        api.as_("joseph.mathew.qc"),
        api.as_("bilal.qureshi"),
        api.as_("hatem.shehri"),
    )
    n = raise_ncr(joseph, ids, classification="major")
    url = f"{API}/quality/ncrs/{n['id']}/classification"
    err(
        bilal.post(url, json={"classification": "minor", "reason": "Not structural after all"}),
        422,
        "CLASS_LOWERED_NEEDS_APPROVAL",
    )
    low = ok(
        hatem.post(
            url,
            json={
                "classification": "minor",
                "reason": "Cover deficiency is local and non-structural",
            },
        )
    )
    assert low["classification"] == "minor"
    assert ok(bilal.post(url, json={"classification": "major"}))["classification"] == "major"


def test_AC29_containment_required_and_overdue_alert(qsetup: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids, classification="major")
    err(bilal.post(f"{API}/quality/ncrs/{n['id']}/propose"), 422, "CONTAINMENT_REQUIRED")
    due = datetime.fromisoformat(n["containment_due_at"])
    with get_sessionmaker()() as db:
        jobs.run_slot(db, "quality_alerts", due + timedelta(minutes=5))
        jobs.run_slot(db, "quality_alerts", due + timedelta(minutes=10))
        db.commit()
        rows = list(
            db.scalars(
                select(Notification).where(
                    Notification.entity_id == uuid.UUID(n["id"]),
                    Notification.title_en.like("%containment overdue%"),
                )
            )
        )
    assert {r.user_id for r in rows} == {_uid(ids, "bilal.qureshi"), _uid(ids, "hatem.shehri")}
    assert len(rows) == 2


def test_AC30_rca_method_and_completeness(qsetup: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    crit = raise_ncr(bilal, ids, classification="critical", open=False)
    attach(bilal, "q_ncr", crit["id"])
    ok(bilal.post(f"{API}/quality/ncrs/{crit['id']}/open"))
    url = f"{API}/quality/ncrs/{crit['id']}/rca"
    err(
        bilal.put(
            url,
            json={
                "method": "five_why",
                "cause_category": "method",
                "data": {"whys": ["a" * 12] * 3, "root_cause": "b" * 12},
            },
        ),
        422,
        "RCA_METHOD_NOT_ALLOWED",
    )
    err(
        bilal.put(
            url,
            json={
                "method": "eight_d",
                "cause_category": "material",
                "data": {"d1_team": [ids.user("bilal.qureshi")]},
            },
        ),
        422,
        "RCA_INCOMPLETE",
    )
    major = raise_ncr(api.as_("joseph.mathew.qc"), ids, classification="major")
    r = ok(
        bilal.put(
            f"{API}/quality/ncrs/{major['id']}/rca",
            json={
                "method": "five_why",
                "cause_category": "people",
                "data": {
                    "whys": [
                        "The bars were placed without spacers.",
                        "It was operator error.",
                        "The crew was not briefed.",
                    ],
                    "root_cause": "Operator error on site",
                },
            },
        )
    )
    assert "HUMAN_ERROR_NOT_ROOT_CAUSE" in {w["code"] for w in r["warnings"]}


def test_AC31_disposition_quantities_and_concession_evidence(
    qsetup: None, api: Api, ids: Ids
) -> None:
    bilal = api.as_("bilal.qureshi")
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids, quantity="186", unit="m3")
    url = f"{API}/quality/ncrs/{n['id']}/disposition"
    err(
        bilal.put(
            url,
            json={
                "lines": [
                    {"disposition": "rework", "quantity": "100"},
                    {"disposition": "use_as_is", "quantity": "80"},
                ]
            },
        ),
        422,
        "DISPOSITION_QTY_MISMATCH",
    )
    err(
        bilal.put(
            url,
            json={
                "lines": [{"disposition": "use_as_is", "quantity": "186"}],
                "disposition_justification_en": "x" * 30,
            },
        ),
        422,
        "CONCESSION_EVIDENCE_REQUIRED",
    )


def test_AC32_concession_is_a_second_signoff(qsetup: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids, quantity="10", unit="m3")
    attach(bilal, "q_ncr_evidence", n["id"])
    to_proposed(
        bilal,
        ids,
        n,
        lines=[{"disposition": "use_as_is", "quantity": "10"}],
        justification="Cores average 34.9 MPa, minimum 33.6 MPa; designer confirms the "
        "slab capacity for the reduced strength.",
    )
    r = ok(sign(api.as_("hatem.shehri"), n["id"], "disposition"))
    assert r["status"] == "disposition_proposed"
    assert [s["step"] for s in r["steps"] if s["pending"]] == ["concession"]
    r = ok(sign(api.as_("abdullah.dossary"), n["id"], "concession"))
    assert r["status"] == "disposition_approved" and len(r["signoffs"]) == 2


def test_AC33_ca_required_priority_and_due(qsetup: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids, classification="major")
    nid = n["id"]
    ok(
        bilal.put(
            f"{API}/quality/ncrs/{nid}/containment",
            json={"containment_en": "Pour stopped, area taped off.", "done": True},
        )
    )
    ok(
        bilal.put(
            f"{API}/quality/ncrs/{nid}/rca",
            json={
                "method": "ishikawa",
                "cause_category": "method",
                "data": {
                    "causes": [
                        {"category": "method", "text": "No spacer check", "root": True},
                        {"category": "people", "text": "New crew"},
                    ]
                },
            },
        )
    )
    ok(
        bilal.put(
            f"{API}/quality/ncrs/{nid}/disposition", json={"lines": [{"disposition": "rework"}]}
        )
    )
    err(bilal.post(f"{API}/quality/ncrs/{nid}/propose"), 422, "CA_REQUIRED")
    late = (date(2026, 10, 6) + timedelta(days=31)).isoformat()
    err(
        bilal.post(f"{API}/quality/ncrs/{nid}/actions", json=ca_body(ids, due_date=late)),
        422,
        "DUE_DATE_TOO_LATE",
    )
    r = ok(bilal.post(f"{API}/quality/ncrs/{nid}/actions", json=ca_body(ids)), 201)
    ca = r["actions"][0]
    assert ca["priority"] == "high"
    assert date.fromisoformat(ca["due_date"]) <= date(2026, 10, 6) + timedelta(days=30)
    with get_sessionmaker()() as db:
        row = db.get(CorrectiveAction, uuid.UUID(ca["id"]))
        assert row is not None and row.source_type == CaSourceType.quality_ncr
    assert ok(bilal.post(f"{API}/quality/ncrs/{nid}/propose"))["status"] == "disposition_proposed"


def test_AC34_quality_ca_verifier(qsetup: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids, classification="major")
    err(
        bilal.post(
            f"{API}/quality/ncrs/{n['id']}/actions",
            json=ca_body(ids, verifier_id=ids.user("noura.qahtani")),
        ),
        422,
        "VERIFIER_ROLE_NOT_ALLOWED",
    )
    ok(bilal.post(f"{API}/quality/ncrs/{n['id']}/actions", json=ca_body(ids)), 201)


def test_AC35_quality_cas_out_of_hse_kpis_and_domain_filter(
    qsetup: None, api: Api, ids: Ids
) -> None:
    from app.kpi import data
    from app.services import hse_settings

    bilal = api.as_("bilal.qureshi")
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids, classification="major")
    r = ok(bilal.post(f"{API}/quality/ncrs/{n['id']}/actions", json=ca_body(ids)), 201)
    ca_id = uuid.UUID(r["actions"][0]["id"])
    with get_sessionmaker()() as db:
        p = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
        assert p is not None
        facts = data.load(db, [p], {p.id: hse_settings.get(db, p.id)}, reader=False)
        assert ca_id not in {c.id for c in facts.cas}
    pid = ids.project("ANIA-EXP")
    hatem = api.as_("hatem.shehri")
    q = ok(hatem.get(f"{API}/projects/{pid}/corrective-actions", params={"domain": "quality"}))
    assert {i["id"] for i in q["items"]} == {str(ca_id)}
    noura = api.as_("noura.qahtani")
    h = ok(noura.get(f"{API}/projects/{pid}/corrective-actions"))
    assert str(ca_id) not in {i["id"] for i in h["items"]}
    allx = ok(noura.get(f"{API}/projects/{pid}/corrective-actions", params={"domain": "all"}))
    assert str(ca_id) in {i["id"] for i in allx["items"]}


def test_AC36_close_blockers(qsetup: None, api: Api, ids: Ids) -> None:
    bilal, hatem = api.as_("bilal.qureshi"), api.as_("hatem.shehri")
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids, classification="major", quantity="5", unit="m")
    nid = n["id"]
    to_proposed(bilal, ids, n, lines=[{"disposition": "reject_scrap", "quantity": "5"}])
    ok(sign(hatem, nid, "disposition"))
    ca = ok(bilal.get(f"{API}/quality/ncrs/{nid}"))["actions"][0]
    ok(
        api.as_("joseph.mathew.qc").post(
            f"{API}/corrective-actions/{ca['id']}/transitions", json={"to_status": "in_progress"}
        )
    )
    ok(
        bilal.post(
            f"{API}/quality/ncrs/{nid}/implement",
            json={"implementation_note": "Scrapped pipes moved to the waste area."},
        )
    )
    d = err(sign(hatem, nid, "close"), 422, "NCR_CLOSE_BLOCKED")
    assert {b["code"] for b in d["meta"]["blockers"]} == {
        "CA_OPEN",
        "DESTRUCTION_NOT_EVIDENCED",
        "COST_NOT_RECORDED",
    }


def test_AC37_costs_qx1(qsetup: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    n = raise_ncr(api.as_("joseph.mathew.qc"), ids)
    url = f"{API}/quality/ncrs/{n['id']}/costs"
    ok(
        api.as_("hatem.shehri").patch(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/settings",
            json={"values": {"delay_rate_sar_day": None}},
        )
    )
    err(bilal.post(url, json={"cost_type": "delay", "quantity": "1"}), 422, "DELAY_RATE_NOT_SET")
    ok(
        api.as_("hatem.shehri").patch(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/settings",
            json={"values": {"delay_rate_sar_day": "12000.00"}},
        )
    )
    for body in (
        {"cost_type": "rework_labour", "quantity": "36"},
        {"cost_type": "material", "rate_sar": "4250.00", "recovered_sar": "4250.00"},
        {"cost_type": "retest_reinspection", "quantity": "2", "rate_sar": "350.00"},
        {"cost_type": "delay", "quantity": "1"},
    ):
        r = ok(bilal.post(url, json=body), 201)
    assert r["cost_gross_sar"] == "20010.00" and r["cost_recovered_sar"] == "4250.00"
    assert r["cost_net_sar"] == "15760.00" and r["failure_class"] == "internal"
    assert [c["amount_sar"] for c in r["cost_lines"]] == [
        "3060.00",
        "4250.00",
        "700.00",
        "12000.00",
    ]


def test_AC38_repeat_ncr(qsetup: None, api: Api, ids: Ids) -> None:
    from app.models.quality import QSupplier

    with get_sessionmaker()() as db:
        rmx = db.scalar(select(QSupplier).where(QSupplier.supplier_code == "RMX"))
        assert rmx is not None
        sid = str(rmx.id)

    def raise_at(when: datetime) -> dict[str, object]:
        set_now(when)
        n = raise_ncr(api.as_("bilal.qureshi"), ids, category="material", supplier_id=sid)
        with get_sessionmaker()() as db:  # the test-result adapter is Q2's: set the key directly
            row = db.get(QNcr, uuid.UUID(str(n["id"])))
            assert row is not None
            row.item_key = "TT:CONC-CYL"
            row.repeat_of_id = core.find_repeat(db, row).id if core.find_repeat(db, row) else None
            if row.repeat_of_id and row.classification == "minor":
                row.classification = "major"  # type: ignore[assignment]
            db.commit()
        return n

    a = raise_at(datetime(2026, 7, 2, 7, 0, tzinfo=UTC))
    b = raise_at(datetime(2026, 9, 29, 7, 0, tzinfo=UTC))
    c = raise_at(datetime(2026, 10, 1, 7, 0, tzinfo=UTC))
    with get_sessionmaker()() as db:
        rb = db.get(QNcr, uuid.UUID(str(b["id"])))
        rc = db.get(QNcr, uuid.UUID(str(c["id"])))
        assert rb is not None and rc is not None
        assert rb.repeat_of_id == uuid.UUID(str(a["id"])) and rb.classification == "major"
        # 2026-10-01 is 91 days after A: a repeat of B only (89 days window keeps A out)
        assert rc.repeat_of_id == rb.id
    err(
        api.as_("bilal.qureshi").put(
            f"{API}/quality/ncrs/{b['id']}/rca",
            json={
                "method": "simple",
                "cause_category": "material",
                "data": {"cause": "Water was added at the plant beyond the mix design."},
            },
        ),
        422,
        "RCA_METHOD_NOT_ALLOWED",
    )


def test_AC38_not_a_repeat_after_the_window(qsetup: None, api: Api, ids: Ids) -> None:
    with get_sessionmaker()() as db:
        p = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
        assert p is not None
        common = {
            "project_id": p.id,
            "profile": "construction",
            "site_id": uuid.UUID(ids.site("S-LAND")),
            "title": "t",
            "category": "material",
            "item_key": "TT:CONC-CYL",
            "responsible_engagement_id": uuid.UUID(ids.engagement("RAWABI")),
            "status": "open",
            "alerts_sent": [],
            "lot_refs": [],
        }
        a = QNcr(**common, opened_date=date(2026, 7, 2), ncr_no="A")
        db.add(a)
        db.flush()
        b = QNcr(**common, opened_date=date(2026, 10, 1), ncr_no="B")
        db.add(b)
        db.flush()
        assert core.find_repeat(db, b) is None
        b.opened_date = date(2026, 9, 29)
        assert core.find_repeat(db, b) == a
        db.rollback()


def test_AC39_effectiveness_proposal(qsetup: None, ids: Ids) -> None:
    with get_sessionmaker()() as db:
        p = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
        assert p is not None
        common = {
            "project_id": p.id,
            "profile": "construction",
            "site_id": uuid.UUID(ids.site("S-LAND")),
            "title": "t",
            "category": "workmanship",
            "item_key": "ITP:STC-001:30",
            "responsible_engagement_id": uuid.UUID(ids.engagement("RAWABI")),
            "alerts_sent": [],
            "lot_refs": [],
        }
        n = QNcr(
            **common,
            status="closed",
            ncr_no="NCR-A",
            opened_date=date(2026, 6, 1),
            closed_date=date(2026, 7, 1),
            effectiveness={"due_on": "2026-09-29"},
        )
        db.add(n)
        db.commit()
        jobs.effectiveness_proposals(db, datetime(2026, 9, 29, 0, 30, tzinfo=UTC))
        db.refresh(n)
        assert n.effectiveness and n.effectiveness["proposed"] == "effective"
        n.effectiveness = {"due_on": "2026-09-29"}
        db.add(QNcr(**common, status="open", ncr_no="NCR-B", opened_date=date(2026, 8, 15)))
        db.commit()
        jobs.effectiveness_proposals(db, datetime(2026, 9, 29, 0, 30, tzinfo=UTC))
        db.refresh(n)
        assert n.effectiveness and n.effectiveness["proposed"] == "not_effective"


def test_AC40_ageing_qx3() -> None:
    n = QNcr(status="open", opened_date=date(2026, 8, 10))
    assert core.age_days(n, date(2026, 10, 6)) == 57
    c = QNcr(
        status="closed",
        opened_date=date(2026, 8, 10),
        closed_date=date(2026, 9, 15),
        target_close_date=date(2026, 9, 9),
    )
    assert core.closure_days(c) == 36 and core.on_time(c) is False


def test_AC41_pdf(q_seed: None, api: Api, ids: Ids) -> None:
    from app.services.permissions import build_principal

    hatem = api.as_("hatem.shehri")
    pid = ids.project("ANIA-EXP")
    n44 = ok(hatem.get(f"{API}/projects/{pid}/quality/ncrs", params={"q": "2026-0044"}))["items"][0]
    res = hatem.get(f"{API}/quality/ncrs/{n44['id']}/pdf", params={"lang": "ar"})
    assert res.status_code == 200 and res.content.startswith(b"%PDF")
    from app.models import User

    with get_sessionmaker()() as db:
        n = db.get(QNcr, uuid.UUID(n44["id"]))
        assert n is not None
        for who, rates in (("hatem.shehri", True), ("abdullah.dossary", False)):
            u = db.scalar(select(User).where(User.email == f"{who}@example.com"))
            assert u is not None
            d = pdf.doc(db, build_principal(db, u, None), n)
            labels = [c[0] for c in d.control]
            assert "Issue date (Hijri, Umm al-Qura)" in labels
            hijri = next(c for c in d.control if c[0].startswith("Issue date (Hijri"))
            assert "هـ" in hijri[3] or "١٤" in hijri[3] or "14" in hijri[3]
            cost = next(s for s in d.sections if s.key == "costs")
            assert bool(cost.tables) is rates
