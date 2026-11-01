"""Quality audits on the 6d engine, the programme, management reviews and suppliers (spec
8-quality §E.2, §E.3; AC-Q4-07…16)."""

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.session import get_sessionmaker
from app.models import CorrectiveAction, FieldAudit
from app.models.quality import QNcr
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, err, ok

D = Decimal


@pytest.fixture
def q4lib(qsetup: None) -> Iterator[None]:
    from app.seed_quality_q4 import ensure_templates

    with get_sessionmaker()() as db:
        ensure_templates(db)
        db.commit()
    yield


def _process(
    api: Api, ids: Ids, pc: str, code: str, owner: str, risk: str = "high", who: str = ""
) -> dict:
    c = api.as_(who or ("reem.mutairi" if pc == "RUH-CCH" else "hatem.shehri"))
    return ok(
        c.post(
            f"{API}/projects/{ids.project(pc)}/quality/processes",
            json={
                "code": code,
                "name_en": code,
                "name_ar": code,
                "owner_user_id": ids.user(owner),
                "risk": risk,
            },
        ),
        201,
    )


def _plan(api: Api, ids: Ids, pc: str, lead: str, procs: list[str], who: str, **kw: object) -> dict:
    body = {
        "audit_type": "qms_internal",
        "template_code": "Q9K",
        "lead_auditor_id": ids.user(lead),
        "process_ids": procs,
        "planned_start": "2026-10-07",
        "planned_end": "2026-10-08",
    }
    body.update(kw)  # type: ignore[arg-type]
    return api.as_(who).post(f"{API}/projects/{ids.project(pc)}/quality/audits", json=body)  # type: ignore[no-any-return]


def _conduct(api: Api, a: dict, lead: str, ratings: dict[int, str]) -> dict:
    c = api.as_(lead)
    items = a["response"]["items"] if a.get("response") else None
    from app.models.field import ChecklistTemplate

    with get_sessionmaker()() as db:
        t = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.template_code == "Q9K"))
        assert t is not None
        codes = [it["item_code"] for it in t.items]
    _ = items
    answers = [
        {
            "item_code": code,
            "answer": ratings.get(i, "3"),
            **({"note": "Evidence missing for this clause."} if ratings.get(i, "3") != "3" else {}),
        }
        for i, code in enumerate(codes, start=1)
    ]
    ok(c.put(f"{API}/quality/audits/{a['id']}/answers", json={"answers": answers}))
    ok(
        c.patch(
            f"{API}/quality/audits/{a['id']}",
            json={
                "fieldwork_start": "2026-10-06",
                "fieldwork_end": "2026-10-06",
                "closing_meeting_at": "2026-10-06T12:00:00Z",
                "summary_en": "Audit summary of the QMS.",
            },
        )
    )
    return ok(c.post(f"{API}/quality/audits/{a['id']}/complete-fieldwork"))  # type: ignore[no-any-return]


def test_AC07_AC08_planning(q4lib: None, api: Api, ids: Ids) -> None:
    rcv = _process(api, ids, "RUH-CCH", "RCV", "imran.siddiq")
    # Q-AUD-02: the process owner cannot audit it (checked before the capability)
    err(
        _plan(api, ids, "RUH-CCH", "imran.siddiq", [rcv["id"]], "reem.mutairi"), 422, "SOD_CONFLICT"
    )
    # Noura (6d 194 / 195 only) cannot plan a quality audit, in Quality or through 6d
    noura = api.as_("noura.qahtani")
    err(_plan(api, ids, "ANIA-EXP", "rania.zahrani", [], "noura.qahtani"), 403, "FORBIDDEN")
    res = noura.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/field-audits",
        json={
            "audit_type": "qms_internal",
            "template_code": "Q9K",
            "site_ids": [ids.site("S-LAND")],
            "lead_auditor_id": ids.user("rania.zahrani"),
            "team_ids": [],
            "planned_start": "2026-10-07",
            "planned_end": "2026-10-08",
        },
    )
    assert res.status_code == 403
    a = ok(_plan(api, ids, "RUH-CCH", "reem.mutairi", [rcv["id"]], "reem.mutairi"), 201)
    assert a["audit_no"] == "QAU-RUH-CCH-2026-0001" and a["domain"] == "quality"
    six_d = ok(api.as_("faisal.harbi").get(f"{API}/projects/{ids.project('RUH-CCH')}/field-audits"))
    assert all(x["id"] != a["id"] for x in six_d["items"])  # Q-AUD-05


def test_AC09_AC10_issue(q4lib: None, api: Api, ids: Ids) -> None:
    rcv = _process(api, ids, "RUH-CCH", "RCV", "imran.siddiq")
    a = ok(_plan(api, ids, "RUH-CCH", "reem.mutairi", [rcv["id"]], "reem.mutairi"), 201)
    a = _conduct(api, a, "reem.mutairi", {1: "0", 2: "0", 3: "1", 4: "1", 5: "1"})
    assert a["status"] == "fieldwork_complete"
    err(
        api.as_("reem.mutairi").post(f"{API}/quality/audits/{a['id']}/issue", json={}),
        422,
        "SOD_CONFLICT",
    )
    with get_sessionmaker()() as db:
        cas_before = db.scalar(select(func.count()).select_from(CorrectiveAction))
    out = ok(api.as_("faisal.harbi").post(f"{API}/quality/audits/{a['id']}/issue", json={}))
    assert out["status"] == "issued" and out["report_en_id"] and out["report_ar_id"]
    assert len(out["ncr_ids"]) == 5
    with get_sessionmaker()() as db:
        ncrs = list(
            db.scalars(select(QNcr).where(QNcr.id.in_([uuid.UUID(str(x)) for x in out["ncr_ids"]])))
        )
        assert sorted(n.classification.value for n in ncrs) == [
            "major",
            "major",
            "minor",
            "minor",
            "minor",
        ]  # type: ignore[union-attr]
        assert {n.source_type.value for n in ncrs} == {"q_audit_finding"}
        assert all((n.requirement_en or "").startswith("ISO 9001:2015 ") for n in ncrs)
        assert (
            db.scalar(select(func.count()).select_from(CorrectiveAction)) == cas_before
        )  # no HSE CA
        fa = db.get(FieldAudit, a["id"])
        assert fa is not None and fa.domain.value == "quality"


def test_AC11_programme_months_and_on_time(q4lib: None, api: Api, ids: Ids) -> None:
    from app.models.quality.q4 import QAuditProgrammeLine
    from app.services.quality.q4 import audits

    assert audits.months_for(D("2"), 2026) == [3, 9] and audits.months_for(D("1"), 2026) == [6]
    assert audits.months_for(D("0.5"), 2026) == [6] and audits.months_for(D("0.5"), 2027) == []
    rcv = _process(api, ids, "RUH-CCH", "RCV", "imran.siddiq")
    reem = api.as_("reem.mutairi")
    lines = ok(
        reem.post(
            f"{API}/projects/{ids.project('RUH-CCH')}/quality/audit-programme/generate",
            params={"year": 2026},
        )
    )
    assert sorted(x["planned_month"] for x in lines if x["process_id"] == rcv["id"]) == [3, 9]
    a = ok(_plan(api, ids, "RUH-CCH", "reem.mutairi", [rcv["id"]], "reem.mutairi"), 201)
    sept = next(x for x in lines if x["planned_month"] == 9)
    with get_sessionmaker()() as db:
        ln = db.get(QAuditProgrammeLine, sept["id"])
        fa = db.get(FieldAudit, a["id"])
        assert ln is not None and fa is not None
        ln.audit_id = fa.id
        fa.status = "issued"  # type: ignore[assignment]
        fa.fieldwork_end = date(2026, 9, 30)
        assert audits.line_on_time(db, ln) is True
        fa.fieldwork_end = date(2026, 10, 1)
        assert audits.line_on_time(db, ln) is False
        db.rollback()


def test_AC12_management_review(q_seed: None, api: Api, ids: Ids) -> None:
    reem = api.as_("reem.mutairi")
    pid = ids.project("RUH-CCH")
    m = ok(
        reem.post(
            f"{API}/projects/{pid}/quality/management-reviews",
            json={"period_start": "2026-09-01", "period_end": "2026-09-30"},
        ),
        201,
    )
    from app.core.quality.q4 import MRV_INPUT_KEYS

    inputs = {k: {"note": "Reviewed with the team."} for k in MRV_INPUT_KEYS[:-1]}
    ok(reem.patch(f"{API}/quality/management-reviews/{m['id']}", json={"inputs": inputs}))
    d = err(
        reem.post(f"{API}/quality/management-reviews/{m['id']}/hold", json={}),
        422,
        "MRV_INPUTS_INCOMPLETE",
    )
    assert d["meta"]["missing"] == ["improvement"]
    ok(
        reem.patch(
            f"{API}/quality/management-reviews/{m['id']}",
            json={"inputs": {"improvement": {"not_applicable": True}}},
        )
    )
    held = ok(reem.post(f"{API}/quality/management-reviews/{m['id']}/hold", json={}))
    k143 = next(x for x in held["kpi_snapshot"]["kpis"] if x["kpi"] == "K-143")
    assert k143["value"] == "9"
    with get_sessionmaker()() as db:
        n = db.scalar(select(QNcr).where(QNcr.ncr_no == "NCR-RUH-CCH-2026-0028"))
        assert n is not None
        n.status = "voided"  # type: ignore[assignment]
        db.commit()
    again = ok(reem.get(f"{API}/quality/management-reviews/{m['id']}"))
    assert next(x for x in again["kpi_snapshot"]["kpis"] if x["kpi"] == "K-143")["value"] == "9"
    out = ok(
        api.as_("faisal.harbi").post(
            f"{API}/quality/management-reviews/{m['id']}/issue-minutes", json={}
        )
    )
    assert out["status"] == "minutes_issued" and out["minutes_en_id"] and out["minutes_ar_id"]


def test_AC13_supplier_gate(qsetup: None, api: Api, ids: Ids) -> None:
    from app.models.quality import QSupplier
    from app.services.quality.q4 import suppliers

    hatem = api.as_("hatem.shehri")
    with get_sessionmaker()() as db:
        s = db.scalar(select(QSupplier).where(QSupplier.supplier_code == "RMX"))
        assert s is not None
        s.status = "pending_approval"  # type: ignore[assignment]
        sid = str(s.id)
        db.commit()
        assert suppliers.gate(db, s, "approved")[0].code == "SUPPLIER_EVALUATION_REQUIRED"
    err(
        hatem.post(
            f"{API}/quality/suppliers/{sid}/transitions",
            json={"to_status": "approved", "project_id": ids.project("ANIA-EXP")},
        ),
        422,
        "SUPPLIER_EVALUATION_REQUIRED",
    )
    bilal = api.as_("bilal.qureshi")
    e = ok(
        bilal.post(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/supplier-evaluations",
            json={
                "supplier_id": sid,
                "kind": "initial",
                "method": "document_review",
                "recommendation": "approve",
                "criteria": [
                    {"criterion": "Quality system", "weight": 60, "score": 80},
                    {"criterion": "Capacity", "weight": 40, "score": 90},
                ],
            },
        ),
        201,
    )
    assert e["total"] == "84.00"
    ok(
        bilal.post(
            f"{API}/quality/supplier-evaluations/{e['id']}/transition", json={"action": "submit"}
        )
    )
    err(
        bilal.post(
            f"{API}/quality/supplier-evaluations/{e['id']}/transition", json={"action": "approve"}
        ),
        403,
        "FORBIDDEN",
    )
    e = ok(
        hatem.post(
            f"{API}/quality/supplier-evaluations/{e['id']}/transition", json={"action": "approve"}
        )
    )
    assert e["status"] == "approved" and e["next_evaluation_due"] == "2027-10-05"
    with get_sessionmaker()() as db:
        s = db.scalar(select(QSupplier).where(QSupplier.supplier_code == "RMX"))
        assert s is not None and suppliers.gate(db, s, "approved") == []


def test_AC14_AC15_score_maths(qsetup: None) -> None:
    from app.core.quality.common import SETTINGS_BY_KEY
    from app.services.quality.q4 import suppliers

    w = SETTINGS_BY_KEY["supplier_score_weights"].default
    anc = SETTINGS_BY_KEY["supplier_score_anchors"].default
    bands = SETTINGS_BY_KEY["supplier_score_bands"].default
    r = suppliers.score_of(
        {
            "M1": D("97.5"),
            "M2": D("1.2"),
            "M3": D("91.0"),
            "M4": D("95.8"),
            "M5": D("100"),
            "M6": None,
        },
        w,
        anc,
        bands,
    )
    assert r["score"] == D("72.2") and r["band"] == "B" and r["weight_total"] == "95"
    assert r["points"] == {
        "M1": "75.00",
        "M2": "76.00",
        "M3": "61.11",
        "M4": "58.00",
        "M5": "100.00",
    }
    low = suppliers.score_of(
        {"M1": D("92"), "M2": D("4"), "M3": D("85"), "M4": None, "M5": None, "M6": None},
        w,
        anc,
        bands,
    )
    assert low["band"] == "D" and low["recommendation"] == "suspend"


def test_AC15_band_d_alert_keeps_status(qsetup: None) -> None:
    from app.core.quality.q4 import QScorePeriod
    from app.models import Notification
    from app.models.quality import QSupplier
    from app.models.quality.q4 import QSupplierEvaluation, QSupplierScore
    from app.services.quality.q4 import suppliers

    with get_sessionmaker()() as db:
        s = db.scalar(select(QSupplier).where(QSupplier.supplier_code == "RMX"))
        assert s is not None
        from app.models import Project

        p = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
        assert p is not None
        db.add(
            QSupplierEvaluation(
                project_id=p.id,
                supplier_id=s.id,
                kind="initial",
                method="audit",
                criteria=[],
                status="approved",
            )
        )
        row = QSupplierScore(
            supplier_id=s.id,
            period_kind=QScorePeriod.quarter,
            period_start=date(2026, 7, 1),
            period_end=date(2026, 9, 30),
            metrics={},
            score=D("48.0"),
            band="D",
            computed_at=suppliers.now(),
        )
        db.add(row)
        db.flush()
        before = db.scalar(select(func.count()).select_from(Notification))
        assert suppliers.band_alert(db, s, row) >= 1
        assert db.scalar(select(func.count()).select_from(Notification)) > (before or 0)
        assert s.status.value == "approved"
        db.rollback()


def test_AC16_contractor_page_score(q_seed: None, api: Api, ids: Ids) -> None:
    from app.models.quality import QSupplier
    from app.models.quality.q4 import QSupplierScore

    with get_sessionmaker()() as db:
        s = db.scalar(select(QSupplier).where(QSupplier.supplier_code == "RMX"))
        assert s is not None
        s.contractor_id = uuid.UUID(ids.contractor("RAWABI"))
        db.commit()
        n_scores = db.scalar(select(func.count()).select_from(QSupplierScore))
    rows = ok(
        api.as_("hatem.shehri").get(f"{API}/quality/contractor-quality/{ids.contractor('RAWABI')}")
    )
    assert rows[0]["score"] == "72.2" and rows[0]["band"] == "B"
    with get_sessionmaker()() as db:
        assert db.scalar(select(func.count()).select_from(QSupplierScore)) == n_scores
