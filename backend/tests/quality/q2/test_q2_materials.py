"""Materials: MAR, MIR, quarantine and the profile gate (spec 8-quality §C.3, AC-Q2-15…19, -32)."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.quality import QNcr
from tests.conftest import Api, Ids
from tests.quality.q2.h2 import API, attach, err, ok, supplier


def _mar(
    c: TestClient,
    ids: Ids,
    *,
    category: str = "waterproofing",
    deviation: bool = False,
    note: str | None = None,
) -> dict[str, Any]:
    rows = [
        {
            "requirement": "Tensile strength ≥ 800 N/50 mm",
            "offered": "850 N/50 mm",
            "result": "complies",
        }
    ]
    if deviation:
        rows.append({"requirement": "Thickness 4.0 mm", "offered": "3.8 mm", "result": "deviation"})
    body = {
        "engagement_id": ids.engagement("RAWABI"),
        "title_en": "Waterproofing membrane, podium",
        "category": category,
        "supplier_id": supplier("SAHEL"),
        "compliance": rows,
        "deviations_note": note,
    }
    return ok(c.post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/mars", json=body), 201)


def _submitted_mar(api: Api, ids: Ids, **kw: Any) -> dict[str, Any]:
    bilal = api.as_("bilal.qureshi")
    m = _mar(bilal, ids, **kw)
    attach(bilal, "q_mar", m["id"], "technical-data-sheet.pdf")
    return ok(bilal.post(f"{API}/quality/mars/{m['id']}/submit"))


def test_AC15_mar_completeness_and_comment_rules(q2: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    m = _mar(bilal, ids, deviation=True)
    assert m["with_deviations"] is True
    attach(bilal, "q_mar", m["id"], "technical-data-sheet.pdf")
    d = err(bilal.post(f"{API}/quality/mars/{m['id']}/submit"), 422, "MAR_INCOMPLETE")
    assert d["meta"]["missing"] == ["deviations note"]
    ok(
        bilal.patch(
            f"{API}/quality/mars/{m['id']}",
            json={
                "deviations_note": (
                    "Thickness 3.8 mm offered; supplier test data attached"
                    " for the 4.0 mm equivalent."
                )
            },
        )
    )
    s = ok(bilal.post(f"{API}/quality/mars/{m['id']}/submit"))
    assert s["mar_no"] == "MAR-ANIA-EXP-2026-0001" and s["status"] == "submitted"
    abdullah = api.as_("abdullah.dossary")
    err(
        abdullah.post(f"{API}/quality/mars/{m['id']}/decide", json={"approval_code": "C"}),
        422,
        "VALIDATION_ERROR",
    )
    err(
        abdullah.post(f"{API}/quality/mars/{m['id']}/decide", json={"approval_code": "A"}),
        422,
        "VALIDATION_ERROR",
    )  # deviations not accepted
    a = ok(
        abdullah.post(
            f"{API}/quality/mars/{m['id']}/decide",
            json={"approval_code": "A", "accept_deviations": True},
        )
    )
    assert a["status"] == "approved" and a["deviations_accepted"] is True
    assert err(
        bilal.post(f"{API}/quality/mars/{m['id']}/decide", json={"approval_code": "A"}),
        409,
        "INVALID_TRANSITION",
    )


def test_mar_revise_and_resubmit_supersedes(q2: None, api: Api, ids: Ids) -> None:
    m = _submitted_mar(api, ids)
    abdullah, bilal = api.as_("abdullah.dossary"), api.as_("bilal.qureshi")
    c = ok(
        abdullah.post(
            f"{API}/quality/mars/{m['id']}/decide",
            json={
                "approval_code": "C",
                "comment": "Provide the durability data and a sample board.",
            },
        )
    )
    assert c["status"] == "revise_resubmit"
    r1 = ok(bilal.post(f"{API}/quality/mars/{m['id']}/resubmit"), 201)
    assert r1["revision"] == 1 and r1["mar_no"] == m["mar_no"] and r1["status"] == "draft"
    attach(bilal, "q_mar", r1["id"], "tds-rev1.pdf")
    ok(bilal.post(f"{API}/quality/mars/{r1['id']}/submit"))
    a = ok(
        abdullah.post(
            f"{API}/quality/mars/{r1['id']}/decide",
            json={"approval_code": "B", "comment": "Approved; seal the laps per the noted detail."},
        )
    )
    assert a["status"] == "approved_as_noted" and [x["revision"] for x in a["revisions"]] == [0, 1]


def _mir(c: TestClient, ids: Ids, **kw: Any) -> dict[str, Any]:
    body = {
        "quantity": "240",
        "unit": "m",
        "site_id": ids.site("S-LAND"),
        "material_description": "HDPE pipes DN200",
        **kw,
    }
    return ok(c.post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/mirs", json=body), 201)


def test_AC16_mir_needs_an_approved_mar(q2: None, api: Api, ids: Ids) -> None:
    m = _submitted_mar(api, ids)
    ok(
        api.as_("abdullah.dossary").post(
            f"{API}/quality/mars/{m['id']}/decide",
            json={
                "approval_code": "C",
                "comment": "Provide the durability data and a sample board.",
            },
        )
    )
    joseph = api.as_("joseph.mathew.qc")
    x = _mir(joseph, ids, mar_id=m["id"])
    assert x["engagement_id"] == ids.engagement("RAWABI") and x["category"] == "waterproofing"
    d = err(joseph.post(f"{API}/quality/mirs/{x['id']}/submit"), 422, "MAR_NOT_APPROVED")
    assert d["meta"]["mar_status"] == "revise_resubmit"
    y = _mir(
        joseph,
        ids,
        category="consumables",
        engagement_id=ids.engagement("RAWABI"),
        material_description="Welding rods",
    )
    assert ok(joseph.post(f"{API}/quality/mirs/{y['id']}/submit"))["status"] == "submitted"


def _decided_mar(api: Api, ids: Ids, category: str = "pipes_fittings") -> dict[str, Any]:
    m = _submitted_mar(api, ids, category=category)
    return ok(
        api.as_("abdullah.dossary").post(
            f"{API}/quality/mars/{m['id']}/decide", json={"approval_code": "A"}
        )
    )


def test_AC17_rejected_quantity_quarantines_and_raises_ncr(q2: None, api: Api, ids: Ids) -> None:
    mar = _decided_mar(api, ids)
    joseph, abdullah = api.as_("joseph.mathew.qc"), api.as_("abdullah.dossary")
    x = _mir(joseph, ids, mar_id=mar["id"], supplier_id=supplier("GULFPIPE"))
    s = ok(joseph.post(f"{API}/quality/mirs/{x['id']}/submit"))
    assert s["mir_no"] == "MIR-ANIA-EXP-2026-0001"
    body = {
        "result": "accepted_with_comments",
        "accepted_qty": "180",
        "rejected_qty": "50",
        "comment": "60 m ovality beyond tolerance, ends damaged.",
    }
    err(abdullah.post(f"{API}/quality/mirs/{x['id']}/decide", json=body), 422, "MIR_QTY_MISMATCH")
    d = ok(
        abdullah.post(f"{API}/quality/mirs/{x['id']}/decide", json={**body, "rejected_qty": "60"})
    )
    assert d["status"] == "decided" and len(d["quarantine_ids"]) == 1
    q = ok(abdullah.get(f"{API}/quality/quarantine/{d['quarantine_ids'][0]}"))
    assert (
        q["quantity"] == "60.000" and q["unit"] == "m" and q["tag_no"] == "QTN-ANIA-EXP-2026-0001"
    )
    with get_sessionmaker()() as db:
        n = db.get(QNcr, uuid.UUID(q["ncr_id"]))
        assert n is not None
        assert (n.source_type.value, n.classification.value, n.status.value) == (
            "mir",
            "major",
            "open",
        )
        assert n.supplier_id is not None and str(n.quantity) == "60.000"


def test_AC18_heat_number_mismatch_needs_a_comment(q2: None, api: Api, ids: Ids) -> None:
    mar = _decided_mar(api, ids, "rebar")
    joseph, abdullah = api.as_("joseph.mathew.qc"), api.as_("abdullah.dossary")
    x = _mir(
        joseph,
        ids,
        mar_id=mar["id"],
        quantity="40",
        unit="t",
        lot_numbers=["H71203", "H71204"],
        cert_heat_numbers=["H71204"],
    )
    assert "HEAT_NUMBER_MISMATCH" in {w["code"] for w in x["warnings"]} and x["heat_mismatch"] == [
        "H71203"
    ]
    ok(joseph.post(f"{API}/quality/mirs/{x['id']}/submit"))
    body = {"result": "accepted", "accepted_qty": "40", "rejected_qty": "0"}
    err(abdullah.post(f"{API}/quality/mirs/{x['id']}/decide", json=body), 422, "VALIDATION_ERROR")
    d = ok(
        abdullah.post(
            f"{API}/quality/mirs/{x['id']}/decide",
            json={
                **body,
                "comment": "Mill confirmed heat H71203 by letter; certificate to follow.",
            },
        )
    )
    assert d["result"] == "accepted"


def test_AC19_quarantine_release_blocked_until_disposition(q2: None, api: Api, ids: Ids) -> None:
    mar = _decided_mar(api, ids)
    joseph, abdullah, hatem = (
        api.as_("joseph.mathew.qc"),
        api.as_("abdullah.dossary"),
        api.as_("hatem.shehri"),
    )
    x = _mir(joseph, ids, mar_id=mar["id"])
    ok(joseph.post(f"{API}/quality/mirs/{x['id']}/submit"))
    d = ok(
        abdullah.post(
            f"{API}/quality/mirs/{x['id']}/decide",
            json={
                "result": "accepted_with_comments",
                "accepted_qty": "180",
                "rejected_qty": "60",
                "comment": "60 m ovality beyond tolerance.",
            },
        )
    )
    qid = d["quarantine_ids"][0]
    err(
        hatem.post(f"{API}/quality/quarantine/{qid}/dispose", json={"to_status": "released"}),
        422,
        "QUARANTINE_RELEASE_BLOCKED",
    )
    err(
        hatem.post(f"{API}/quality/quarantine/{qid}/dispose", json={"to_status": "returned"}),
        422,
        "VALIDATION_ERROR",
    )
    r = ok(
        hatem.post(
            f"{API}/quality/quarantine/{qid}/dispose",
            json={"to_status": "returned", "return_note_no": "RN-GP-0091"},
        )
    )
    assert r["status"] == "returned" and r["return_note_no"] == "RN-GP-0091"
    with get_sessionmaker()() as db:
        from app.services.quality.q2 import materials

        n = db.scalar(select(QNcr).where(QNcr.id == uuid.UUID(r["ncr_id"])))
        assert n is not None and materials.mir_close_check(db, n) == []


def test_AC32_logistics_profile_refuses_construction_records(q2: None, api: Api, ids: Ids) -> None:
    reem = api.as_("reem.mutairi")
    pid = ids.project("RUH-CCH")
    mar = {"engagement_id": ids.engagement("WAHAT"), "title_en": "Pallet wrap", "category": "other"}
    err(reem.post(f"{API}/projects/{pid}/quality/mars", json=mar), 409, "PROFILE_INACTIVE")
    pour = {"element": "Slab", "site_id": ids.site("S-DC1"), "grade": "C30", "volume_m3": "10"}
    err(reem.post(f"{API}/projects/{pid}/quality/pours", json=pour), 409, "PROFILE_INACTIVE")
    weld = {
        "joint_id": "X-001",
        "wps_id": str(uuid.uuid4()),
        "position": "1G",
        "thickness_mm": "10",
        "welders": [{"stamp": "W-1"}],
        "welded_on": "2026-10-01",
    }
    err(reem.post(f"{API}/projects/{pid}/quality/welds", json=weld), 409, "PROFILE_INACTIVE")
    m = ok(
        reem.post(
            f"{API}/projects/{pid}/quality/mte",
            json={"mte_type": "temp_probe", "description": "Probe", "interval_months": 6},
        ),
        201,
    )
    assert m["cal_status"] == "overdue"  # Q-CAL-02: never calibrated (Q2 replaces `unknown`)
