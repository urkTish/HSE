"""Contractors & engagements — AC17, AC18, AC21, AC28, §4.2 state machine."""

from sqlalchemy.orm import Session

from tests.conftest import Api, Ids

NEW = {
    "legal_name_en": "Red Sea MEP Services",
    "legal_name_ar": "شركة البحر الأحمر للأعمال الكهروميكانيكية",
    "short_code": "REDSEA",
    "cr_number": "7010000007",
    "contractor_category": "mep",
    "primary_contact_name": "Hani Al-Juhani",
    "primary_contact_mobile": "+966500000107",
    "primary_contact_email": "redsea.hse@example.com",
    "vat_number": "300000000000073",
}


def _engagement(ids: Ids, contractor: str, tier: int, parent: str | None) -> dict[str, object]:
    return {
        "contractor_id": ids.contractor(contractor),
        "tier": tier,
        "parent_engagement_id": ids.engagement(parent) if parent else None,
        "scope_of_work_en": "Test scope",
        "scope_of_work_ar": "نطاق اختبار",
        "site_ids": [ids.site("S-LAND")],
        "mobilisation_date": "2026-01-01",
    }


def _approve(c: object, cid: str) -> None:
    for st in ("pending_approval", "approved"):
        r = c.post(f"/api/v1/contractors/{cid}/transitions", json={"to_status": st})  # type: ignore[attr-defined]
        assert r.status_code == 200, r.text


def test_AC18_cr_unique_and_format(api: Api) -> None:
    c = api.as_("noura.qahtani")
    dup = c.post("/api/v1/contractors", json={**NEW, "cr_number": "1010000001"})
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "DUPLICATE_VALUE"
    assert dup.json()["detail"]["errors"][0]["loc"] == ["body", "cr_number"]
    bad = c.post("/api/v1/contractors", json={**NEW, "cr_number": "12345"})
    assert bad.status_code == 422
    assert bad.json()["detail"]["errors"][0]["loc"] == ["body", "cr_number"]
    ok = c.post("/api/v1/contractors", json=NEW)
    assert ok.status_code == 201 and ok.json()["status"] == "draft"


def test_rule24_other_uniqueness(api: Api) -> None:
    c = api.as_("faisal.harbi")
    assert c.post("/api/v1/contractors", json={**NEW, "short_code": "RAWABI"}).status_code == 409
    # case / diacritic insensitive legal name
    res = c.post("/api/v1/contractors", json={**NEW, "legal_name_ar": "شَرِكة الروابى للمقاولات"})
    assert res.status_code == 409
    assert c.post("/api/v1/contractors", json={**NEW, "vat_number": "123"}).status_code == 422
    assert (
        c.post(
            "/api/v1/contractors", json={**NEW, "primary_contact_mobile": "+96612345"}
        ).status_code
        == 422
    )


def test_AC21_engagement_requires_approved_contractor(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    cid = c.post("/api/v1/contractors", json=NEW).json()["id"]
    assert (
        c.post(
            f"/api/v1/contractors/{cid}/transitions", json={"to_status": "pending_approval"}
        ).status_code
        == 200
    )
    body = {**_engagement(ids, "RAWABI", 2, "RAWABI"), "contractor_id": cid}
    res = c.post(f"/api/v1/projects/{ids.project('ANIA-EXP')}/engagements", json=body)
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "CONTRACTOR_NOT_APPROVED"


def test_AC17_tier_parent_rules(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    mgr = api.as_("faisal.harbi")
    cid = c.post("/api/v1/contractors", json=NEW).json()["id"]
    _approve(mgr, cid)
    pid = ids.project("ANIA-EXP")
    bad = {**_engagement(ids, "RAWABI", 3, "RAWABI"), "contractor_id": cid}
    res = c.post(f"/api/v1/projects/{pid}/engagements", json=bad)
    assert res.status_code == 422
    assert res.json()["detail"]["errors"][0]["loc"] == ["body", "parent_engagement_id"]
    other_project = {**_engagement(ids, "QIMMA", 2, "QIMMA"), "contractor_id": cid}
    assert c.post(f"/api/v1/projects/{pid}/engagements", json=other_project).status_code == 422
    good = {**_engagement(ids, "NAJD", 3, "NAJD"), "contractor_id": cid}
    res = c.post(f"/api/v1/projects/{pid}/engagements", json=good)
    assert res.status_code == 201, res.text
    eng = res.json()
    assert eng["tier"] == 3 and eng["root_engagement_id"] == ids.engagement("RAWABI")
    # The RAWABI rep now sees the new tier-3 engagement in his tree
    rep = api.as_("ahmed.zahrani").get(f"/api/v1/projects/{pid}/engagements").json()
    assert "REDSEA" in {e["contractor"]["short_code"] for e in rep["items"]}
    # tier 1 must not have a parent; tier 2+ must
    t1 = {**_engagement(ids, "RAWABI", 1, "RAWABI"), "contractor_id": cid}
    assert c.post(f"/api/v1/projects/{pid}/engagements", json=t1).status_code == 422
    dup = c.post(f"/api/v1/projects/{pid}/engagements", json=good)
    assert dup.status_code == 409


def test_contractor_state_machine(api: Api, ids: Ids) -> None:
    officer = api.as_("noura.qahtani")
    mgr = api.as_("faisal.harbi")
    cid = officer.post("/api/v1/contractors", json=NEW).json()["id"]
    url = f"/api/v1/contractors/{cid}/transitions"
    assert officer.post(url, json={"to_status": "approved"}).status_code == 409
    assert officer.post(url, json={"to_status": "pending_approval"}).status_code == 200
    assert officer.post(url, json={"to_status": "approved"}).status_code == 403
    assert mgr.post(url, json={"to_status": "draft"}).status_code == 422  # comment required
    assert mgr.post(url, json={"to_status": "draft", "reason": "Missing VAT"}).status_code == 200
    _approve(mgr, cid)
    assert mgr.post(url, json={"to_status": "suspended"}).status_code == 422
    assert mgr.post(url, json={"to_status": "suspended", "reason": "x"}).status_code == 200
    assert mgr.post(url, json={"to_status": "approved", "reason": "fixed"}).status_code == 200
    # no engagements → demobilise allowed
    assert mgr.post(url, json={"to_status": "demobilised"}).status_code == 200
    # RAWABI has an open engagement → demobilise blocked
    rurl = f"/api/v1/contractors/{ids.contractor('RAWABI')}/transitions"
    res = mgr.post(rurl, json={"to_status": "demobilised"})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "TRANSITION_CONDITION_NOT_MET"
    # managers were notified of the submission
    notes = mgr.get("/api/v1/notifications").json()
    assert any(n["kind"] == "contractor_submitted" for n in notes["items"])


def test_AC28_arabic_normalised_search(api: Api) -> None:
    c = api.as_("faisal.harbi")
    for q in ["الروابى", "شركه الروابي", "شَرِكة الرّوابي", "rawabi", "RAWABI", "1010000001"]:
        items = c.get("/api/v1/contractors", params={"q": q}).json()["items"]
        assert "RAWABI" in {x["short_code"] for x in items}, q


def test_contractor_list_filters(api: Api) -> None:
    c = api.as_("faisal.harbi")
    sus = c.get("/api/v1/contractors", params={"status": "suspended"}).json()["items"]
    assert [x["short_code"] for x in sus] == ["DLIFT"]
    exp = c.get("/api/v1/contractors", params={"cr_expiring_within_days": 365}).json()
    codes = {x["short_code"] for x in exp["items"]}
    assert "GULFPAVE" in codes  # CR expires 2026-10-30
    assert "SAHARA" not in codes  # no expiry date
    c.patch("/api/v1/auth/me", json={"preferred_language": "ar"})
    res = c.get("/api/v1/contractors", params={"sort": "name"})
    names = [x["legal_name_ar"] for x in res.json()["items"]]
    assert len(names) == 6 and names[0].startswith("شركة")  # Arabic collation (ش before م)


def test_officer_edits_only_unapproved(api: Api, ids: Ids, db: Session) -> None:
    officer = api.as_("noura.qahtani")
    res = officer.patch(
        f"/api/v1/contractors/{ids.contractor('RAWABI')}", json={"vat_number": "300000000000093"}
    )
    assert res.status_code == 403
    mgr = api.as_("faisal.harbi")
    res = mgr.patch(
        f"/api/v1/contractors/{ids.contractor('RAWABI')}", json={"vat_number": "300000000000093"}
    )
    assert res.status_code == 200 and res.json()["vat_number"] == "300000000000093"
