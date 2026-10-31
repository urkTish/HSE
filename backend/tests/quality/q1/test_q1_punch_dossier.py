"""Q1 punch list, floor plans, handover dossier, jobs, registries and the Appendix A seed (spec
8-quality §B.11 AC-Q1-15, -19 … -25, -27; §3.2)."""

import io
import uuid
import zipfile
from datetime import date
from typing import Any

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import Notification
from app.models.quality import QNcr
from app.services.quality import registry as reg
from tests.conftest import Api, Ids
from tests.quality.q1.q1h import (
    API,
    approved_itp,
    clock_at,
    decide_body,
    err,
    local,
    ok,
    photo,
    schedule,
    submit_ir,
)


def _pid(ids: Ids) -> str:
    return ids.project("ANIA-EXP")


def _punch(c: Any, ids: Ids, **kw: Any) -> dict[str, Any]:
    body = {
        "site_id": ids.site("S-LAND"),
        "zone_id": ids.zone("Z-PIERB"),
        "location_ref": "Gate B4 lounge, column C17",
        "discipline": "ARC",
        "description_en": "Ceiling tile damaged and stained",
        "category": "B",
        "raised_during": "pre_handover",
        "responsible_engagement_id": ids.engagement("RAWABI"),
        "photos": [photo()],
        **kw,
    }
    return ok(c.post(f"{API}/projects/{_pid(ids)}/quality/punch", json=body), 201)


def _png(w: int, h: int) -> bytes:
    from PIL import Image  # noqa: PLC0415

    buf = io.BytesIO()
    Image.new("L", (w, h), 255).save(buf, "PNG")
    return buf.getvalue()


def test_AC19_punch_evidence_and_sod(q1lib: None, api: Api, ids: Ids) -> None:
    mazen = api.as_("mazen.harbi")
    it = _punch(mazen, ids)
    assert it["punch_no"] == "PCH-ANIA-EXP-2026-00001" and it["status"] == "open"
    assert it["target_date"] == "2026-11-05"  # B: 30 days
    joseph = api.as_("joseph.mathew.qc")
    url = f"{API}/quality/punch/{it['id']}"
    err(
        joseph.post(f"{url}/ready", json={"note": "Tile replaced.", "photos": []}),
        422,
        "PUNCH_EVIDENCE_REQUIRED",
    )
    err(
        joseph.post(f"{url}/ready", json={"note": "short", "photos": [photo()]}),
        422,
        "PUNCH_EVIDENCE_REQUIRED",
    )
    r = ok(
        joseph.post(
            f"{url}/ready", json={"note": "Tile replaced and cleaned.", "photos": [photo()]}
        )
    )
    assert r["status"] == "ready_for_review"
    # the user who marked it ready never closes it, even when named
    hatem = api.as_("hatem.shehri")
    rule = next(
        x
        for x in ok(
            hatem.get(f"{API}/projects/{_pid(ids)}/quality/rp-rules?record_type=punch_item")
        )
        if x["step"] == "verify"
    )
    ok(
        hatem.patch(
            f"{API}/quality/rp-rules/{rule['id']}",
            json={
                "assignee_kind": "user",
                "assignee": ids.user("joseph.mathew.qc"),
                "own_tree_allowed": True,
            },
        )
    )
    err(joseph.post(f"{url}/verify", json={"decision": "approved"}), 422, "SOD_CONFLICT")
    ok(
        hatem.patch(
            f"{API}/quality/rp-rules/{rule['id']}",
            json={"assignee_kind": "position", "assignee": "CONSULTANT_RE"},
        )
    )
    abd = api.as_("abdullah.dossary")
    back = ok(
        abd.post(f"{url}/verify", json={"decision": "rejected", "comment": "Stain still visible."})
    )
    assert back["status"] == "open"
    ok(joseph.post(f"{url}/ready", json={"note": "Stain removed; repainted.", "photos": [photo()]}))
    done = ok(abd.post(f"{url}/verify", json={"decision": "approved"}))
    assert (
        done["status"] == "closed"
        and done["closed_date"] == "2026-10-06"
        and len(done["signoffs"]) == 2
    )


def test_punch_escalated_to_ncr_blocks_close(q1lib: None, api: Api, ids: Ids) -> None:
    mazen = api.as_("mazen.harbi")
    it = _punch(mazen, ids, category="A")
    n = ok(mazen.post(f"{API}/projects/{_pid(ids)}/quality/ncrs", json={
        "source_type": "punch_item", "source_id": it["id"], "category": "workmanship",
        "owner_id": ids.user("bilal.qureshi"), "classification": "minor", "open": True}), 201)  # fmt: skip
    assert n["source_ref"] == it["punch_no"] and n["status"] == "open"
    with get_sessionmaker()() as db:
        from app.services.quality.ncr import core  # noqa: PLC0415

        ncr = db.get(QNcr, uuid.UUID(n["id"]))
        assert ncr is not None
        assert any(b.code == "PUNCH_ITEM_OPEN" for b in core.close_blockers(db, ncr))


def test_AC20_plan_revision_keeps_or_flags_pins(q1lib: None, api: Api, ids: Ids) -> None:
    hatem = api.as_("hatem.shehri")
    pid = _pid(ids)
    up = hatem.post(f"{API}/projects/{pid}/quality/floor-plans",
                    data={"zone_id": ids.zone("Z-PIERB"), "level_label": "Level 1", "title_en": "Pier B Level 1", "title_ar": "الرصيف B المستوى 1"},
                    files={"file": ("plan.png", _png(4200, 2800), "image/png")})  # fmt: skip
    fp = ok(up, 201)
    assert fp["width_px"] == 4200 and fp["height_px"] == 2800
    items = [
        _punch(hatem, ids, pin={"floor_plan_id": fp["id"], "x_pct": 10 + i, "y_pct": 20 + i})
        for i in range(12)
    ]
    assert all(x["floor_plan_id"] == fp["id"] for x in items)
    same = ok(hatem.post(f"{API}/projects/{pid}/quality/floor-plans", data={"revision_of": fp["id"]},
                         files={"file": ("plan-r1.png", _png(2100, 1400), "image/png")}), 201)  # fmt: skip
    assert same["pin_count"] == 12 and not any(p["pin_check"] for p in same["pins"])
    assert same["pins"][0]["pin_x_pct"] in {f"{10 + i}.00" for i in range(12)}
    other = ok(hatem.post(f"{API}/projects/{pid}/quality/floor-plans", data={"revision_of": same["id"]},
                          files={"file": ("plan-r2.png", _png(3000, 3000), "image/png")}), 201)  # fmt: skip
    assert other["pin_count"] == 12 and all(p["pin_check"] for p in other["pins"])
    # a PDF is refused; the image is served
    bad = hatem.post(f"{API}/projects/{pid}/quality/floor-plans", data={"zone_id": ids.zone("Z-PIERB")},
                     files={"file": ("plan.pdf", b"%PDF-1.4 x", "application/pdf")})  # fmt: skip
    err(bad, 422, "PLAN_IMAGE_INVALID")
    img = hatem.get(f"{API}/quality/floor-plans/{other['id']}/image")
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")
    confirmed = ok(hatem.patch(f"{API}/quality/punch/{items[0]['id']}", json={"confirm_pin": True}))
    assert confirmed["pin_check"] is False


def test_AC21_overdue_and_sunday_digest(q1lib: None, api: Api, ids: Ids) -> None:
    clock_at(2026, 9, 17, 10)
    mazen = api.as_("mazen.harbi")
    it = _punch(mazen, ids, category="A")
    assert it["target_date"] == "2026-10-01"
    clock_at(2026, 10, 6, 10)
    hatem = api.as_("hatem.shehri")
    got = ok(hatem.get(f"{API}/quality/punch/{it['id']}"))
    assert got["overdue"] is True
    page = ok(hatem.get(f"{API}/projects/{_pid(ids)}/quality/punch?overdue=true"))
    assert page["total"] == 1
    from app.services.quality.jobs import run_slot  # noqa: PLC0415

    with get_sessionmaker()() as db:
        out = run_slot(db, "quality_weekly", local(2026, 10, 11, 7, 12))
        assert out["q1_punch_digest"]["digests"] >= 1
        again = run_slot(db, "quality_weekly", local(2026, 10, 11, 7, 12))
        assert again["q1_punch_digest"]["digests"] == 0  # once per digest and recipient
        to = {
            str(n.user_id)
            for n in db.scalars(
                select(Notification).where(Notification.title_en.like("%punch item(s) overdue%"))
            )
        }
        assert ids.user("bilal.qureshi") in to and ids.user("joseph.mathew.qc") in to
        assert ids.user("hatem.shehri") not in to
        db.commit()


def _ready_dossier(api: Api, ids: Ids) -> tuple[Any, dict[str, Any]]:
    hatem = api.as_("hatem.shehri")
    d = ok(hatem.post(f"{API}/projects/{_pid(ids)}/quality/dossiers",
                      json={"title_en": "Pier B level 3", "title_ar": "الرصيف B المستوى 3", "zone_ids": [ids.zone("Z-PIERB")]}), 201)  # fmt: skip
    assert d["dossier_no"] == "DOS-ANIA-EXP-2026-0001" and "ncr" in d["sections"]
    return hatem, d


def test_AC22_dossier_blockers(q1lib: None, api: Api, ids: Ids) -> None:
    from tests.quality.q0.qh import raise_ncr  # noqa: PLC0415

    hatem, d = _ready_dossier(api, ids)
    url = f"{API}/quality/dossiers/{d['id']}"
    n = raise_ncr(api.as_("bilal.qureshi"), ids, zone_id=ids.zone("Z-PIERB"))
    a = _punch(api.as_("mazen.harbi"), ids, category="A")
    ok(
        hatem.post(
            f"{url}/asbuilt",
            json={
                "drawing_no": "S-PB-301",
                "title": "Level 3 slab",
                "revision": "1",
                "status": "approved",
            },
        ),
        201,
    )
    ok(hatem.post(f"{url}/compile"))
    e = err(hatem.post(f"{url}/submit"), 422, "DOSSIER_BLOCKED")
    text = " ".join(b["detail_en"] for b in e["meta"]["blockers"])
    assert n["ncr_no"] in text and a["punch_no"] in text
    pid = _pid(ids)
    ok(
        hatem.patch(
            f"{API}/projects/{pid}/quality/settings",
            json={"values": {"dossier_blockers": ["a", "b", "d", "e", "f"]}},
        )
    )
    e2 = err(hatem.post(f"{url}/submit"), 422, "DOSSIER_BLOCKED")
    assert a["punch_no"] not in " ".join(b["detail_en"] for b in e2["meta"]["blockers"])
    assert a["punch_no"] in " ".join(w["detail_en"] for w in e2["meta"]["warnings"])


def test_AC23_AC24_AC25_compile_snapshot_accept_and_downloads(
    q1lib: None, api: Api, ids: Ids
) -> None:
    itp = approved_itp(api, ids, points=[
        {"seq": 30, "activity_en": "Rebar", "activity_ar": "التسليح", "characteristic_en": "Cover", "characteristic_ar": "الغطاء",
         "point_type": "H", "criteria_ids": [], "acceptance_text_en": "Cover per drawing", "checklist_template_code": "QSTC-RB"}])  # fmt: skip
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    r = ok(submit_ir(joseph, ids, itp, [30]), 201)
    schedule(abd, r["id"])
    body = decide_body([30], photos=[photo("rebar.png")])
    body["measurements"] = []
    ok(abd.post(f"{API}/quality/inspection-requests/{r['id']}/decide", json=body))
    hatem, d = _ready_dossier(api, ids)
    url = f"{API}/quality/dossiers/{d['id']}"
    ok(
        hatem.post(
            f"{url}/asbuilt",
            json={
                "drawing_no": "S-PB-301",
                "title": "Level 3 slab",
                "revision": "1",
                "status": "approved",
            },
        ),
        201,
    )
    c1 = ok(hatem.post(f"{url}/compile"))
    assert c1["status"] == "compiled" and c1["package_sha256"]
    sha = c1["package_sha256"]
    pkg = hatem.get(f"{url}/package")
    assert pkg.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(pkg.content)).namelist()
    assert any(x.endswith("index-EN.pdf") for x in names) and any(
        x.endswith("index-AR.pdf") for x in names
    )
    assert any(x.startswith("02-ir/") and x.endswith("rebar.png") for x in names), names
    ar = hatem.get(f"{url}/index?lang=ar")
    assert ar.status_code == 200 and ar.content.startswith(b"%PDF")
    # Q-DOS-02: a later change to a record in scope leaves the compiled files unchanged
    joseph.post(f"{API}/attachments", data={"owner_type": "q_ir_round", "owner_id": ok(joseph.get(f"{API}/quality/inspection-requests/{r['id']}"))["rounds"][0]["id"]},
                files={"file": ("later.png", io.BytesIO(_png(500, 500)), "image/png")})  # fmt: skip
    again = ok(hatem.get(url))
    assert again["package_sha256"] == sha
    assert zipfile.ZipFile(io.BytesIO(hatem.get(f"{url}/package").content)).namelist() == names
    # Viewer: no index before acceptance, never the ZIP
    sarah = api.as_("sarah.mitchell")
    err(sarah.get(f"{url}/index"), 403, "FORBIDDEN")
    ok(hatem.post(f"{url}/submit"))
    sultan = api.as_("sultan.mutlaq")
    assert sultan.get(f"{url}/package").status_code == 200  # the acceptor (254) reviews the ZIP
    acc = ok(sultan.post(f"{url}/decide", json={"decision": "approved"}))
    assert acc["status"] == "accepted"
    err(hatem.post(f"{url}/compile"), 409, "DOSSIER_IMMUTABLE")
    assert sarah.get(f"{url}/index").status_code == 200
    err(sarah.get(f"{url}/package"), 403, "FORBIDDEN")
    rev2 = ok(hatem.post(f"{url}/revisions"), 201)
    assert (
        rev2["revision"] == 2
        and rev2["status"] == "draft"
        and rev2["dossier_no"] == d["dossier_no"]
    )
    assert len(rev2["asbuilt"]) == 1


def test_registries_and_reference_labels(q1lib: None, api: Api, ids: Ids) -> None:
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    assert "itp_point" in reg.HOLD_CHECKS
    assert {"itp", "ir", "punch", "asbuilt", "ncr"} <= set(reg.DOSSIER_SECTIONS)
    assert {"ir", "punch_item"} <= {k.value for k in reg.NCR_SOURCES}
    ref = ok(api.as_("hatem.shehri").get(f"{API}/quality/reference"))
    # AC-Q1-27: every Part B list has its Arabic label
    for kind in (
        "point_type",
        "ir_status",
        "ir_result",
        "itp_status",
        "punch_status",
        "dossier_status",
        "discipline",
    ):
        assert kind in ref["labels"], kind
        assert all(len(v) == 2 and v[1] for v in ref["labels"][kind].values())
    assert ref["labels"]["point_type"]["H"][1] == "نقطة توقف"


def test_hold_check_registry_for_pours(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    abd = api.as_("abdullah.dossary")
    r = ok(submit_ir(joseph, ids, itp, [30]), 201)
    p30 = next(p for p in itp["points"] if p["seq"] == 30)
    with get_sessionmaker()() as db:
        assert reg.HOLD_CHECKS["itp_point"](db, uuid.UUID(p30["id"]), r["location_key"]) is False
    schedule(abd, r["id"])
    ok(abd.post(f"{API}/quality/inspection-requests/{r['id']}/decide", json=decide_body([30])))
    with get_sessionmaker()() as db:
        assert reg.HOLD_CHECKS["itp_point"](db, uuid.UUID(p30["id"]), r["location_key"]) is True
        assert reg.HOLD_CHECKS["itp_point"](db, uuid.UUID(p30["id"]), "Z-PIERB|other") is False
        assert reg.HOLD_CHECKS["itp_point"](db, uuid.uuid4(), None) is None


def test_awaiting_lists_q1_steps(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    r = ok(submit_ir(joseph, ids, itp, [30]), 201)
    aw = ok(api.as_("abdullah.dossary").get(f"{API}/projects/{_pid(ids)}/quality/awaiting"))
    assert any(x["record_id"] == r["id"] and x["step"] == "inspect" for x in aw["items"])
    mine = ok(joseph.get(f"{API}/projects/{_pid(ids)}/quality/awaiting"))
    assert not any(x["record_id"] == r["id"] for x in mine["items"])


def test_AC15_seed_counts(q_seed: None, api: Api, ids: Ids) -> None:
    """QX2 / QX24 / K-156 on the Appendix A.4 seed."""
    hatem = api.as_("hatem.shehri")
    pid = _pid(ids)
    c = ok(
        hatem.get(f"{API}/projects/{pid}/quality/q1-counts?date_from=2026-09-01&date_to=2026-09-30")
    )
    assert (c["first_rounds"], c["first_passes"], c["first_time_pass_pct"]) == (120, 96, "80.0")
    assert (c["rounds_decided"], c["rounds_failed"], c["rejection_rate_pct"]) == (141, 27, "19.1")
    assert c["waived"] == 4 and c["paper_signoffs"] == 1
    assert (c["opportunities"], c["defects"]) == (4820, 31)
    assert (c["punch_with_target"], c["punch_closed_on_time"], c["punch_closure_pct"]) == (
        46,
        24,
        "52.2",
    )
    assert c["punch_open_a"] == 3
    irs = ok(hatem.get(f"{API}/projects/{pid}/quality/inspection-requests?q=00412"))
    assert irs["total"] == 1
    d412 = ok(hatem.get(f"{API}/quality/inspection-requests/{irs['items'][0]['id']}"))
    assert [x["result"] for x in d412["rounds"]] == ["rejected", "approved"]
    p318 = ok(hatem.get(f"{API}/projects/{pid}/quality/punch?q=00318"))["items"][0]
    assert p318["category"] == "A" and p318["overdue"] and p318["target_date"] == "2026-09-28"
    dos = ok(hatem.get(f"{API}/projects/{pid}/quality/dossiers"))["items"][0]
    dd = ok(hatem.get(f"{API}/quality/dossiers/{dos['id']}"))
    txt = " ".join(b["detail_en"] for b in dd["blockers"])
    assert "NCR-ANIA-EXP-2026-0044" in txt and "PCH-ANIA-EXP-2026-00318" in txt
    plans = ok(hatem.get(f"{API}/projects/{pid}/quality/floor-plans"))
    assert plans[0]["title_en"] == "Pier B Level 1" and plans[0]["pin_count"] == 12
    itps = ok(hatem.get(f"{API}/projects/{pid}/quality/itps?current_only=true"))
    assert {i["display_no"] for i in itps["items"]} == {
        "ITP-ANIA-EXP-STC-001 Rev.2", "ITP-ANIA-EXP-STL-001 Rev.1", "ITP-ANIA-EXP-AFP-001 Rev.0", "ITP-ANIA-EXP-HVC-001 Rev.0"}  # fmt: skip
    # RUH-CCH (logistics) has no Part B record
    assert (
        ok(api.as_("reem.mutairi").get(f"{API}/projects/{ids.project('RUH-CCH')}/quality/itps"))[
            "total"
        ]
        == 0
    )
    _ = date
