"""Document control and transmittals (spec 8-quality §E.1, AC-Q4-01…06)."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import EmailMessage
from app.models.quality.q1 import QItp
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, attach, err, ok


def _new(api: Api, ids: Ids, author: str = "bilal.qureshi", **kw: object) -> dict:
    c = api.as_(author)
    body = {"doc_type": "procedure", "title_en": "Concrete curing procedure", "title_ar": "إجراء المعالجة"}
    body.update(kw)  # type: ignore[arg-type]
    return ok(c.post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/documents", json=body), 201)


def _with_pdf(api: Api, d: dict, author: str = "bilal.qureshi") -> str:
    c = api.as_(author)
    rev = d["revisions"][0]
    att = attach(c, "q_document_file", rev["id"], "proc.pdf")
    ok(c.patch(f"{API}/quality/document-revisions/{rev['id']}", json={"file_attachment_id": att}))
    return str(rev["id"])


def _approved(api: Api, ids: Ids) -> tuple[dict, str]:
    d = _new(api, ids)
    rid = _with_pdf(api, d)
    ok(api.as_("bilal.qureshi").post(f"{API}/quality/document-revisions/{rid}/submit"))
    ok(api.as_("rania.zahrani").post(f"{API}/quality/document-revisions/{rid}/review", json={}))
    return ok(api.as_("hatem.shehri").post(f"{API}/quality/document-revisions/{rid}/approve", json={})), rid


def test_AC01_approval_rules(qsetup: None, api: Api, ids: Ids) -> None:
    hatem = api.as_("hatem.shehri")
    d = _new(api, ids, "hatem.shehri", doc_type="pqp", title_en="Project Quality Plan")
    assert d["doc_no"] == "ANIA-EXP-QA-PQP-001" and d["revisions"][0]["rev_code"] == "A"
    rid = d["revisions"][0]["id"]
    err(hatem.post(f"{API}/quality/document-revisions/{rid}/submit"), 422, "DOCUMENT_FILE_REQUIRED")
    _with_pdf(api, d, "hatem.shehri")
    ok(hatem.post(f"{API}/quality/document-revisions/{rid}/submit"))
    err(hatem.post(f"{API}/quality/document-revisions/{rid}/approve", json={}), 422, "SOD_CONFLICT")
    # another approver without a review sign-off
    rania = api.as_("rania.zahrani")
    d2 = _new(api, ids)
    r2 = _with_pdf(api, d2)
    ok(api.as_("bilal.qureshi").post(f"{API}/quality/document-revisions/{r2}/submit"))
    err(hatem.post(f"{API}/quality/document-revisions/{r2}/approve", json={}), 422, "SIGNOFF_REQUIRED")
    ok(rania.post(f"{API}/quality/document-revisions/{r2}/review", json={}))
    out = ok(hatem.post(f"{API}/quality/document-revisions/{r2}/approve", json={}))
    assert out["status"] == "approved" and out["current_rev"] == "0"


def test_AC02_AC03_supersede_immutable_review_date(qsetup: None, api: Api, ids: Ids) -> None:
    d, r0 = _approved(api, ids)
    assert d["review_due_on"] == "2028-10-05"  # approved 2026-10-06, 24 months − 1 day
    bilal = api.as_("bilal.qureshi")
    err(bilal.patch(f"{API}/quality/document-revisions/{r0}", json={"change_summary": "x"}), 409,
        "DOCUMENT_IMMUTABLE")  # fmt: skip
    d = ok(bilal.post(f"{API}/quality/documents/{d['id']}/revisions"))
    r1 = next(r["id"] for r in d["revisions"] if r["status"] == "draft")
    att = attach(bilal, "q_document_file", r1, "rev1.pdf")
    ok(bilal.patch(f"{API}/quality/document-revisions/{r1}", json={"file_attachment_id": att}))
    ok(bilal.post(f"{API}/quality/document-revisions/{r1}/submit"))
    # returned for comments → next letter
    back = ok(api.as_("rania.zahrani").post(
        f"{API}/quality/document-revisions/{r1}/review",
        json={"decision": "returned", "comment": "Add the curing duration table for hot weather."}))  # fmt: skip
    assert next(r["rev_code"] for r in back["revisions"] if r["id"] == r1) == "B"
    ok(bilal.post(f"{API}/quality/document-revisions/{r1}/submit"))
    ok(api.as_("rania.zahrani").post(f"{API}/quality/document-revisions/{r1}/review", json={}))
    d = ok(api.as_("hatem.shehri").post(f"{API}/quality/document-revisions/{r1}/approve", json={}))
    revs = {r["id"]: r for r in d["revisions"]}
    assert revs[r0]["status"] == "superseded" and revs[r1]["status"] == "approved"
    assert revs[r1]["rev_code"] == "1" and d["current_rev"] == "1"
    res = bilal.get(f"{API}/quality/document-revisions/{r0}/download")
    assert res.status_code == 200 and "-SUPERSEDED.pdf" in res.headers["content-disposition"]
    err(bilal.patch(f"{API}/quality/document-revisions/{r1}", json={"change_summary": "x"}), 409,
        "DOCUMENT_IMMUTABLE")  # fmt: skip
    from app.models.quality.q4 import QDocument
    from app.services.quality.q4 import documents

    with get_sessionmaker()() as db:
        doc = db.get(QDocument, d["id"])
        assert doc is not None
        doc.review_due_on = doc.review_due_on.replace(year=2028, month=10, day=5)  # type: ignore[union-attr]
        n1 = documents.daily(db, datetime(2028, 9, 4, 9, 0, tzinfo=UTC))["q4_documents"]
        n2 = documents.daily(db, datetime(2028, 9, 5, 9, 0, tzinfo=UTC))["q4_documents"]
        n3 = documents.daily(db, datetime(2028, 10, 5, 9, 0, tzinfo=UTC))["q4_documents"]
        db.rollback()
    assert (n1, n2, n3) == (0, 1, 1)


def test_AC04_read_and_acknowledge(qsetup: None, api: Api, ids: Ids) -> None:
    d = _new(api, ids)
    rid = _with_pdf(api, d)
    bilal = api.as_("bilal.qureshi")
    ok(bilal.put(f"{API}/quality/documents/{d['id']}/distribution",
                 json={"roles": ["qc_inspector"], "ack_required": True}))  # fmt: skip
    ok(bilal.post(f"{API}/quality/document-revisions/{rid}/submit"))
    ok(api.as_("rania.zahrani").post(f"{API}/quality/document-revisions/{rid}/review", json={}))
    d = ok(api.as_("hatem.shehri").post(f"{API}/quality/document-revisions/{rid}/approve", json={}))
    rev = d["revisions"][0]
    assert rev["ack_due_on"] == "2026-10-13" and rev["acks"]["required"] == 3
    joseph = api.as_("joseph.mathew.qc")
    mine = ok(joseph.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/my-acknowledgements"))
    assert [m["revision_id"] for m in mine] == [rid]
    a1 = ok(joseph.post(f"{API}/quality/document-revisions/{rid}/ack"))
    a2 = ok(joseph.post(f"{API}/quality/document-revisions/{rid}/ack"))
    assert a1["acked_at"] == a2["acked_at"] and a2["acks"]["acked"] == 1 and a2["acks"]["pct"] == "33.3"
    err(api.as_("rania.zahrani").post(f"{API}/quality/document-revisions/{rid}/ack"), 403, "FORBIDDEN")


def test_AC02_AC05_citation_newer_revision(q_seed: None, api: Api, ids: Ids) -> None:
    with get_sessionmaker()() as db:
        itp = db.scalar(select(QItp).where(QItp.itp_no == "ITP-ANIA-EXP-STC-001", QItp.status == "approved"))
        assert itp is not None
        itp_id = str(itp.id)
    hatem = api.as_("hatem.shehri")
    cites = ok(hatem.get(f"{API}/quality/citations", params={"record_type": "itp", "record_id": itp_id}))
    assert [(c["doc_no"], c["rev_code"], c["newer_revision_available"]) for c in cites] == [
        ("ANIA-EXP-QA-MS-004", "2", False)]  # fmt: skip
    bilal = api.as_("bilal.qureshi")
    ms = ok(bilal.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/documents", params={"q": "MS-004"}))
    did = ms["items"][0]["id"]
    d = ok(bilal.post(f"{API}/quality/documents/{did}/revisions"))
    rid = next(r["id"] for r in d["revisions"] if r["status"] == "draft")
    att = attach(bilal, "q_document_file", rid, "ms3.pdf")
    ok(bilal.patch(f"{API}/quality/document-revisions/{rid}", json={"file_attachment_id": att}))
    ok(bilal.post(f"{API}/quality/document-revisions/{rid}/submit"))
    ok(api.as_("rania.zahrani").post(f"{API}/quality/document-revisions/{rid}/review", json={}))
    d = ok(hatem.post(f"{API}/quality/document-revisions/{rid}/approve", json={}))
    assert d["current_rev"] == "3"
    cites = ok(hatem.get(f"{API}/quality/citations", params={"record_type": "itp", "record_id": itp_id}))
    assert cites[0]["newer_revision_available"] is True and cites[0]["newer_rev_code"] == "3"
    links = ok(hatem.get(f"{API}/quality/links", params={"record_type": "itp", "record_id": itp_id}))
    assert any("newer revision available: Rev.3" in (x.get("title") or "") for x in links)


def test_AC06_transmittal_by_email(qsetup: None, api: Api, ids: Ids) -> None:
    d, rid = _approved(api, ids)
    bilal = api.as_("bilal.qureshi")
    t = ok(bilal.post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/transmittals", json={
        "to_kind": "external", "to_name": "Al-Noor Airport Company", "to_email": "docs.anc@example.com",
        "purpose": "for_approval", "method": "email", "subject": "Curing procedure for approval",
        "response_due_on": "2026-10-20", "items": [{"revision_id": rid}]}), 201)  # fmt: skip
    t = ok(bilal.post(f"{API}/quality/transmittals/{t['id']}/send"))
    assert t["status"] == "sent" and t["trm_no"] == "TRM-ANIA-EXP-2026-0001"
    assert t["cover_en_id"] and t["cover_ar_id"] and t["outbox_id"]
    with get_sessionmaker()() as db:
        m = db.get(EmailMessage, t["outbox_id"])
        assert m is not None and m.to_email == "docs.anc@example.com"
        assert str(t["cover_en_id"]) in m.attachment_ids and len(m.attachment_ids) == 3
    item = t["items"][0]["id"]
    t = ok(bilal.post(f"{API}/quality/transmittals/{t['id']}/response", json={
        "response_name": "Document controller", "items": [{"item_id": item, "response_code": "B"}]}))  # fmt: skip
    assert t["status"] == "responded" and t["items"][0]["response_code"] == "B"
    _ = d
