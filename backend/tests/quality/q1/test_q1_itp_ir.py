"""Q1 ITPs and inspection requests (spec 8-quality §B.11 AC-Q1-01 … -14, -16 … -18). Clock: the
shared HSE_CLOCK_AT (2026-10-06 10:00 Riyadh) unless a test moves it with `clock_at`."""

from typing import Any

from sqlalchemy import select

from app.core.clock import set_now
from app.db.session import get_sessionmaker
from app.models import Notification
from app.models.quality import QMteItem, QMteUsage, QRpRule
from app.services.quality import registry as reg
from tests.conftest import Api, Ids
from tests.quality.q1.q1h import (
    API,
    approved_itp,
    clock_at,
    crit,
    decide_body,
    err,
    itp_body,
    local,
    ok,
    photo,
    schedule,
    stc_points,
    submit_ir,
)


def _pid(ids: Ids) -> str:
    return ids.project("ANIA-EXP")


# ---- ITP ---------------------------------------------------------------------------------------


def test_AC01_submit_needs_h_or_w(q1lib: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    pts = [{"seq": 10, "activity_en": "Mix", "activity_ar": "خلطة", "characteristic_en": "MAR", "characteristic_ar": "اعتماد",
            "point_type": "R", "acceptance_text_en": "Approved"},
           {"seq": 30, "activity_en": "Rebar", "activity_ar": "تسليح", "characteristic_en": "Cover", "characteristic_ar": "غطاء",
            "point_type": "S", "criteria_ids": [crit("COVER-40")]}]  # fmt: skip
    it = ok(
        bilal.post(f"{API}/projects/{_pid(ids)}/quality/itps", json=itp_body(ids, points=pts)), 201
    )
    assert it["itp_no"] is None and it["problems"]
    err(bilal.post(f"{API}/quality/itps/{it['id']}/submit"), 422, "ITP_INCOMPLETE")
    pts[1]["point_type"] = "H"
    ok(bilal.patch(f"{API}/quality/itps/{it['id']}", json={"points": pts}))
    sub = ok(bilal.post(f"{API}/quality/itps/{it['id']}/submit"))
    assert sub["status"] == "submitted"
    assert sub["itp_no"] == "ITP-ANIA-EXP-STC-001" and sub["display_no"].endswith("Rev.0")


def test_AC02_AC03_approval_supersedes_and_immutable(q1lib: None, api: Api, ids: Ids) -> None:
    rev0 = approved_itp(api, ids)
    assert rev0["status"] == "approved"
    bilal = api.as_("bilal.qureshi")
    # Q-ITP-03: an approved revision is immutable
    err(
        bilal.patch(f"{API}/quality/itps/{rev0['id']}", json={"title_en": "Changed"}),
        409,
        "ITP_IMMUTABLE",
    )
    rev1 = ok(
        bilal.post(
            f"{API}/quality/itps/{rev0['id']}/revisions",
            json={"change_note": "Point 50 adds concrete temperature"},
        ),
        201,
    )
    assert rev1["revision"] == 1 and rev1["status"] == "draft" and len(rev1["points"]) == 7
    ok(bilal.post(f"{API}/quality/itps/{rev1['id']}/submit"))
    # SOD: Bilal resolves only if named; he authored and submitted → never approves
    with get_sessionmaker()() as db:
        r = db.scalar(
            select(QRpRule).where(
                QRpRule.record_type == "itp", QRpRule.step == "approve", QRpRule.record_id.is_(None)
            )
        )
        assert r is not None
        r.assignee_kind, r.assignee = "user", ids.user("bilal.qureshi")
        db.commit()
    err(
        bilal.post(f"{API}/quality/itps/{rev1['id']}/decide", json={"code": "B", "comment": "ok"}),
        422,
        "SOD_CONFLICT",
    )
    with get_sessionmaker()() as db:
        r = db.scalar(
            select(QRpRule).where(
                QRpRule.record_type == "itp", QRpRule.step == "approve", QRpRule.record_id.is_(None)
            )
        )
        assert r is not None
        r.assignee_kind, r.assignee = "position", "CONSULTANT_RE"
        db.commit()
    abd = api.as_("abdullah.dossary")
    err(
        abd.post(f"{API}/quality/itps/{rev1['id']}/decide", json={"code": "B"}),
        422,
        "VALIDATION_ERROR",
    )
    out = ok(
        abd.post(
            f"{API}/quality/itps/{rev1['id']}/decide",
            json={"code": "B", "comment": "Add the sampling log."},
        )
    )
    assert out["status"] == "approved" and out["approval_code"] == "B"
    assert out["signoffs"][0]["decision"] == "approved_with_comments"
    old = ok(bilal.get(f"{API}/quality/itps/{rev0['id']}"))
    assert old["status"] == "superseded"


def test_itp_code_c_and_d(q1lib: None, api: Api, ids: Ids) -> None:
    bilal = api.as_("bilal.qureshi")
    it = ok(bilal.post(f"{API}/projects/{_pid(ids)}/quality/itps", json=itp_body(ids)), 201)
    ok(bilal.post(f"{API}/quality/itps/{it['id']}/submit"))
    abd = api.as_("abdullah.dossary")
    err(
        abd.post(f"{API}/quality/itps/{it['id']}/decide", json={"code": "C", "comment": "short"}),
        422,
        "VALIDATION_ERROR",
    )
    r = ok(
        abd.post(
            f"{API}/quality/itps/{it['id']}/decide",
            json={"code": "C", "comment": "Add the hold point for striking."},
        )
    )
    assert r["status"] == "revise_resubmit"
    ok(bilal.post(f"{API}/quality/itps/{it['id']}/submit"))
    r = ok(
        abd.post(
            f"{API}/quality/itps/{it['id']}/decide",
            json={"code": "D", "comment": "Wrong work package for this plan."},
        )
    )
    assert r["status"] == "rejected"


def test_AC04_ir_pins_revision(q1lib: None, api: Api, ids: Ids) -> None:
    rev0 = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    ir = ok(submit_ir(joseph, ids, rev0, [30]), 201)
    assert ir["status"] == "submitted" and ir["itp_revision"] == 0
    bilal = api.as_("bilal.qureshi")
    rev1 = ok(
        bilal.post(
            f"{API}/quality/itps/{rev0['id']}/revisions",
            json={"change_note": "Point 50 adds temperature"},
        ),
        201,
    )
    ok(bilal.post(f"{API}/quality/itps/{rev1['id']}/submit"))
    ok(
        api.as_("abdullah.dossary").post(
            f"{API}/quality/itps/{rev1['id']}/decide", json={"code": "A"}
        )
    )
    again = ok(joseph.get(f"{API}/quality/inspection-requests/{ir['id']}"))
    assert again["itp_revision"] == 0 and again["status"] == "submitted"
    err(submit_ir(joseph, ids, rev0, [20], loc="Level 4 slab"), 422, "ITP_NOT_APPROVED")


def test_AC26_logistics_profile_refuses_itp(q1lib: None, api: Api, ids: Ids) -> None:
    reem = api.as_("reem.mutairi")
    body = itp_body(ids, engagement_id=ids.engagement("WAHAT"), zone_ids=[])
    err(
        reem.post(f"{API}/projects/{ids.project('RUH-CCH')}/quality/itps", json=body),
        409,
        "PROFILE_INACTIVE",
    )


# ---- IR: notice, self-check, holds ---------------------------------------------------------------


def test_AC05_AC06_notice_and_self_check(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    clock_at(2026, 10, 6, 10)
    e = err(
        submit_ir(joseph, ids, itp, [30], proposed_at=local(2026, 10, 6, 18).isoformat()),
        422,
        "IR_NOTICE_TOO_SHORT",
    )
    assert e["meta"]["notice_hours"] == 24
    ok(submit_ir(joseph, ids, itp, [30], proposed_at=local(2026, 10, 7, 10).isoformat()), 201)
    urgent = ok(submit_ir(joseph, ids, itp, [30], loc="Level 4 slab", proposed_at=local(2026, 10, 6, 18).isoformat(),
                          short_notice_reason="Concrete truck booked; client asked to advance the pour."), 201)  # fmt: skip
    assert urgent["short_notice"] is True and any(
        w["code"] == "IR_SHORT_NOTICE" for w in urgent["warnings"]
    )
    err(
        submit_ir(joseph, ids, itp, [20], loc="Level 5 slab", self_check_done=False),
        422,
        "SELF_CHECK_REQUIRED",
    )


def test_AC07_hold_point_blocks_next_step(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    r30 = ok(submit_ir(joseph, ids, itp, [30]), 201)
    assert r30["location_key"] == "Z-PIERB|level 3 slab, grid c14–c20"
    e = err(
        submit_ir(joseph, ids, itp, [40], loc="Level 3 Slab,  grid C14–C20"),
        422,
        "HOLD_POINT_NOT_RELEASED",
    )
    assert "30" in e["message"]
    schedule(abd, r30["id"])
    rej = ok(
        abd.post(
            f"{API}/quality/inspection-requests/{r30['id']}/decide",
            json=decide_body([30], "rejected", cover="33", fail="RB-03"),
        )
    )
    assert rej["status"] == "rejected" and rej["ncr_prompt"]
    ok(
        joseph.post(
            f"{API}/quality/inspection-requests/{r30['id']}/reinspection",
            json={"note": "Spacers added and cover checked at every bar.", "photos": [photo()]},
        )
    )
    schedule(abd, r30["id"])
    ok(
        abd.post(
            f"{API}/quality/inspection-requests/{r30['id']}/decide",
            json=decide_body([30], raise_ncr=False),
        )
    )
    r40 = ok(submit_ir(joseph, ids, itp, [40], loc="Level 3 Slab,  grid C14–C20"), 201)
    assert r40["status"] == "submitted"


def test_AC08_void_reblocks_and_notifies(q1lib: None, api: Api, ids: Ids, db: Any) -> None:
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    r30 = ok(submit_ir(joseph, ids, itp, [30]), 201)
    schedule(abd, r30["id"])
    ok(abd.post(f"{API}/quality/inspection-requests/{r30['id']}/decide", json=decide_body([30])))
    r50 = ok(submit_ir(joseph, ids, itp, [50]), 201)
    hatem = api.as_("hatem.shehri")
    err(
        hatem.post(f"{API}/quality/inspection-requests/{r30['id']}/void", json={"reason": "short"}),
        422,
        "VALIDATION_ERROR",
    )
    ok(
        hatem.post(
            f"{API}/quality/inspection-requests/{r30['id']}/void",
            json={"reason": "Released on the wrong drawing revision; re-inspect."},
        )
    )
    again = ok(joseph.get(f"{API}/quality/inspection-requests/{r50['id']}"))
    assert again["reblocked"] and again["hold_blockers"]
    n = db.scalars(
        select(Notification).where(Notification.user_id == ids.user("joseph.mathew.qc"))
    ).all()
    assert any("blocked again" in x.title_en for x in n)
    schedule(abd, r50["id"])  # scheduling stays possible; the decision is blocked
    err(
        abd.post(f"{API}/quality/inspection-requests/{r50['id']}/decide", json=decide_body([50])),
        422,
        "HOLD_POINT_NOT_RELEASED",
    )


# ---- decisions -------------------------------------------------------------------------------------


def test_AC09_result_consistency(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    r = ok(submit_ir(joseph, ids, itp, [30]), 201)
    schedule(abd, r["id"])
    url = f"{API}/quality/inspection-requests/{r['id']}/decide"
    err(abd.post(url, json=decide_body([30], cover="33")), 422, "IR_RESULT_INCONSISTENT")
    err(abd.post(url, json=decide_body([30], fail="RB-03")), 422, "IR_RESULT_INCONSISTENT")
    body = decide_body([30], "rejected", cover="33")
    body["photos"] = []
    err(abd.post(url, json=body), 422, "EVIDENCE_REQUIRED")
    err(abd.post(url, json={**decide_body([30]), "measurements": []}), 422, "VALIDATION_ERROR")
    awc = decide_body([30], "approved_with_comments")
    awc["comments"] = []
    err(abd.post(url, json=awc), 422, "VALIDATION_ERROR")
    ok(abd.post(url, json=decide_body([30], "approved_with_comments")))


def test_AC10_ncr_offered_then_required(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    r = ok(submit_ir(joseph, ids, itp, [30]), 201)
    url = f"{API}/quality/inspection-requests/{r['id']}/decide"
    schedule(abd, r["id"])
    one = ok(abd.post(url, json=decide_body([30], "rejected", cover="33")))
    assert one["ncr_prompt"] and not one["ncrs"]
    ok(
        joseph.post(
            f"{API}/quality/inspection-requests/{r['id']}/reinspection",
            json={"note": "Spacers fitted along the whole bay.", "photos": [photo()]},
        )
    )
    schedule(abd, r["id"])
    err(abd.post(url, json=decide_body([30], "rejected", cover="33")), 422, "NCR_REQUIRED")
    two = ok(abd.post(url, json=decide_body([30], "rejected", cover="33", raise_ncr=True)))
    assert len(two["ncrs"]) == 1 and two["ncrs"][0]["status"] == "open"
    n = ok(abd.get(f"{API}/quality/ncrs/{two['ncrs'][0]['id']}"))
    assert (
        n["source_type"] == "ir"
        and n["item_key"] == "ITP:STC-001:30"
        and n["classification"] == "minor"
    )
    # material / testing failures need an NCR in round 1 too; not_ready never prompts
    r2 = ok(submit_ir(joseph, ids, itp, [30], loc="Level 4 slab"), 201)
    schedule(abd, r2["id"])
    u2 = f"{API}/quality/inspection-requests/{r2['id']}/decide"
    err(
        abd.post(u2, json=decide_body([30], "rejected", cover="33", reject_category="material")),
        422,
        "NCR_REQUIRED",
    )
    nr = ok(abd.post(u2, json=decide_body([30], "not_ready", answers={}, measurements=[])))
    assert (
        nr["status"] == "rejected"
        and not nr["ncr_prompt"]
        and nr["rounds"][0]["result"] == "not_ready"
    )


def test_AC11_resolution_for_s_points(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids, points=stc_points(rebar_type="W"))
    joseph = api.as_("joseph.mathew.qc")
    r = ok(submit_ir(joseph, ids, itp, [60], loc="Level 2 slab"), 201)
    assert r["governing_type"] == "S"
    names = {u["full_name_en"] for u in r["responsible"]}
    assert (
        "Mazen Al-Harbi" in names
        and "Joseph Mathew" not in names
        and "Abdullah Al-Dossary" not in names
    )
    # Joseph (RAWABI) holds the role but cannot sign his own tree (Q-RPM-07)
    err(api.as_("joseph.mathew.qc").post(f"{API}/quality/inspection-requests/{r['id']}/schedule",
                                        json={"scheduled_at": local(2026, 10, 6, 14).isoformat()}), 422, "SOD_CONFLICT")  # fmt: skip
    mazen = api.as_("mazen.harbi")
    schedule(mazen, r["id"])
    # Abdullah: no row names him for S → 403
    assert (
        api.as_("abdullah.dossary").get(f"{API}/quality/inspection-requests/{r['id']}").status_code
        == 404
    )


def test_AC12_witness_waiver(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    clock_at(2026, 10, 3, 9)
    w = ok(submit_ir(joseph, ids, itp, [20], loc="Level 1 slab"), 201)
    schedule(abd, w["id"], local(2026, 10, 6, 8))
    url = f"{API}/quality/inspection-requests/{w['id']}/waive"
    body: dict[str, Any] = {"answers": decide_body([20])["answers"], "photos": [photo()]}
    clock_at(2026, 10, 6, 8, 50)
    err(joseph.post(url, json=body), 422, "WITNESS_WAIT_NOT_OVER")
    clock_at(2026, 10, 6, 9, 5)
    err(joseph.post(url, json={**body, "photos": []}), 422, "EVIDENCE_REQUIRED")
    out = ok(joseph.post(url, json=body))
    assert out["status"] == "witness_waived" and out["rounds"][0]["result"] == "waived"
    # H points are never waived
    clock_at(2026, 10, 3, 9)
    h = ok(submit_ir(joseph, ids, itp, [30], loc="Level 1 slab"), 201)
    schedule(abd, h["id"], local(2026, 10, 6, 8))
    clock_at(2026, 10, 6, 10)
    err(
        joseph.post(f"{API}/quality/inspection-requests/{h['id']}/waive", json=body),
        422,
        "HOLD_NOT_WAIVABLE",
    )
    # review overdue alert on 2026-10-09 (witness_review_days 3)
    from app.services.quality.jobs import run_slot  # noqa: PLC0415

    with get_sessionmaker()() as db:
        out1 = run_slot(db, "quality_alerts", local(2026, 10, 8, 7, 12))
        assert out1["q1_ir_alerts"]["waiver_review_due"] == 0
        out2 = run_slot(db, "quality_alerts", local(2026, 10, 9, 7, 12))
        assert out2["q1_ir_alerts"]["waiver_review_due"] >= 1
        n = db.scalars(
            select(Notification).where(Notification.user_id == ids.user("abdullah.dossary"))
        ).all()
        assert any("waived witness" in x.title_en for x in n)
        db.commit()
    # the review decides the IR; the waiver recorder never reviews
    rv = ok(
        abd.post(f"{API}/quality/inspection-requests/{w['id']}/decide", json={"result": "approved"})
    )
    assert rv["status"] == "approved" and rv["rounds"][0]["review_result"] == "approved"


def test_AC13_comments_before_next_hold(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    r30 = ok(submit_ir(joseph, ids, itp, [30]), 201)
    schedule(abd, r30["id"])
    d = ok(abd.post(f"{API}/quality/inspection-requests/{r30['id']}/decide",
                    json=decide_body([30], "approved_with_comments", close_comments_before_next_hold=True)))  # fmt: skip
    assert d["comments"][0]["status"] == "open"
    e = err(submit_ir(joseph, ids, itp, [70]), 422, "HOLD_POINT_NOT_RELEASED")
    assert "Clean the soffit" in e["message"]
    cid = d["comments"][0]["id"]
    ok(
        joseph.post(
            f"{API}/quality/ir-comments/{cid}/respond",
            json={"response_text": "Soffit cleaned and photographed."},
        )
    )
    err(
        joseph.post(f"{API}/quality/ir-comments/{cid}/close", json={"accept": True}),
        403,
        "FORBIDDEN",
    )
    ok(abd.post(f"{API}/quality/ir-comments/{cid}/close", json={"accept": True}))
    ok(submit_ir(joseph, ids, itp, [70]), 201)


def test_AC14_competence(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids, points=stc_points(rebar_type="W"))
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    r = ok(submit_ir(joseph, ids, itp, [50], loc="Level 2 slab"), 201)
    # default registry (Q2 absent): allowed with an info note
    out = schedule(abd, r["id"])
    assert any(w["code"] == "COMPETENCE_NOT_CONFIGURED" for w in out["warnings"])
    hatem = api.as_("hatem.shehri")
    pid = _pid(ids)
    ok(
        hatem.patch(
            f"{API}/projects/{pid}/quality/settings",
            json={"values": {"competence_policy": "block"}},
        )
    )
    old = reg.COMPETENCE[0]
    reg.COMPETENCE[0] = lambda _db, _u, _c, _d: reg.CompetenceVerdict(
        False, "COMPETENCE_NOT_MET", "No valid record.", "لا يوجد سجل ساري."
    )
    try:
        e = err(abd.post(f"{API}/quality/inspection-requests/{r['id']}/schedule",
                         json={"scheduled_at": local(2026, 10, 7, 9).isoformat(), "reason": "Inspector change"}), 422, "COMPETENCE_NOT_MET")  # fmt: skip
        assert e["meta"]["competence_code"] == "CONC-FIELD-TECH"
    finally:
        reg.COMPETENCE[0] = old


def test_AC16_mte_overdue_warns_and_records_usage(q1lib: None, api: Api, ids: Ids, db: Any) -> None:
    pid = _pid(ids)
    hatem = api.as_("hatem.shehri")
    m = ok(
        hatem.post(
            f"{API}/projects/{pid}/quality/mte",
            json={
                "mte_type": "thermometer",
                "description": "Concrete thermometer",
                "check_kind": "calibration",
                "interval_months": 12,
            },
        ),
        201,
    )
    with get_sessionmaker()() as s:
        it = s.get(QMteItem, m["id"])
        assert it is not None
        it.cal_status = "overdue"
        s.commit()
    itp = approved_itp(api, ids, points=stc_points(rebar_type="W"))
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    r = ok(submit_ir(joseph, ids, itp, [50], loc="Level 2 slab"), 201)
    schedule(abd, r["id"])
    body = decide_body([50])
    body["measurements"][0]["mte_id"] = m["id"]
    out = ok(abd.post(f"{API}/quality/inspection-requests/{r['id']}/decide", json=body))
    assert any(w["code"] == "MTE_NOT_CALIBRATED" for w in out["warnings"])
    assert out["rounds"][0]["measurements"][0]["mte_no"] == m["mte_no"]
    use = db.scalars(select(QMteUsage).where(QMteUsage.record_id == r["id"])).all()
    assert len(use) == 1 and use[0].verdict.value == "warned"


def test_AC17_paper_signoff_pdf_ar(q1lib: None, api: Api, ids: Ids) -> None:
    from app.services.permissions import build_principal  # noqa: PLC0415
    from app.services.quality.q1 import pdf  # noqa: PLC0415

    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    hatem = api.as_("hatem.shehri")
    r = ok(submit_ir(joseph, ids, itp, [30]), 201)
    schedule(api.as_("abdullah.dossary"), r["id"])
    scan = {
        "file_name": "signed-ir.pdf",
        "content_base64": "JVBERi0xLjQKMSAwIG9iajw8Pj5lbmRvYmoKdHJhaWxlcjw8Pj4KJSVFT0YK",
    }
    paper = {
        "name": "Abdullah Al-Dossary",
        "organisation": "Consultant (PMC)",
        "position": "Resident Engineer",
        "signed_on": "2026-10-06",
        "scans": [scan],
    }
    out = ok(
        hatem.post(
            f"{API}/quality/inspection-requests/{r['id']}/decide",
            json=decide_body([30], paper=paper),
        )
    )
    assert out["status"] == "approved" and out["signoffs"][0]["channel"] == "paper"
    res = hatem.get(f"{API}/quality/inspection-requests/{r['id']}/pdf?lang=ar")
    assert res.status_code == 200 and res.content.startswith(b"%PDF")
    with get_sessionmaker()() as db:
        from app.models import User  # noqa: PLC0415

        u = db.get(User, ids.user("hatem.shehri"))
        p = build_principal(db, u, None)
        texts = " ".join(pdf.text_of(db, p, r["id"], "ar"))
    assert "وُقّع ورقياً من Abdullah Al-Dossary" in texts
    assert "هـ" in texts or "١٤" in texts or "1448" in texts  # Hijri issue date
    assert "COVER-40" in texts


def test_AC18_offline_round_needs_confirmation(q1lib: None, api: Api, ids: Ids) -> None:
    clock_at(2026, 10, 5, 9)
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    r30 = ok(submit_ir(joseph, ids, itp, [30]), 201)
    schedule(abd, r30["id"])
    ok(abd.post(f"{API}/quality/inspection-requests/{r30['id']}/decide", json=decide_body([30])))
    r50 = ok(submit_ir(joseph, ids, itp, [50]), 201)
    schedule(abd, r50["id"], local(2026, 10, 6, 8))
    clock_at(2026, 10, 6, 9)
    hatem = api.as_("hatem.shehri")
    ok(
        hatem.post(
            f"{API}/quality/inspection-requests/{r30['id']}/void",
            json={"reason": "Released on the wrong drawing revision; re-inspect."},
        )
    )
    clock_at(2026, 10, 6, 11)
    abd = api.as_("abdullah.dossary")
    body = decide_body(
        [50],
        recorded_at=local(2026, 10, 6, 8, 10).isoformat(),
        client_uuid="7c3e1a52-2d3b-4c1f-9a77-8f1d2c3b4a51",
    )
    out = ok(abd.post(f"{API}/quality/inspection-requests/{r50['id']}/decide", json=body))
    assert out["status"] == "scheduled" and out["needs_confirmation"]
    assert any(w["code"] == "IR_NEEDS_CONFIRMATION" for w in out["warnings"])
    assert "confirm_offline" in out["allowed_actions"]
    # resent by the phone: idempotent, still not decided
    again = ok(abd.post(f"{API}/quality/inspection-requests/{r50['id']}/decide", json=body))
    assert again["status"] == "scheduled"
    from app.services.quality.q1 import kpi  # noqa: PLC0415

    with get_sessionmaker()() as db:
        from datetime import date  # noqa: PLC0415

        c = kpi.ir_counts(
            db, __import__("uuid").UUID(_pid(ids)), date(2026, 10, 1), date(2026, 10, 31)
        )
        assert c.rounds_decided == 0  # r30 voided, r50 not decided
    err(
        abd.post(f"{API}/quality/inspection-requests/{r50['id']}/confirm-offline", json={}),
        422,
        "HOLD_POINT_NOT_RELEASED",
    )
    set_now(local(2026, 10, 6, 7))
    _ = crit
