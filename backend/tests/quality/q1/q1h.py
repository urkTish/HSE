"""Helpers of the Q1 tests: build an approved ITP and walk IRs through their states via the API."""

import base64
import io
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.clock import now, set_now
from app.db.session import get_sessionmaker
from app.models.quality import QCriterion
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, err, ok

RIYADH = ZoneInfo("Asia/Riyadh")
__all__ = ["API", "err", "ok"]


def local(y: int, m: int, d: int, hh: int = 10, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=RIYADH).astimezone(UTC)


def clock_at(y: int, m: int, d: int, hh: int = 10, mm: int = 0) -> datetime:
    t = local(y, m, d, hh, mm)
    set_now(t)
    return t


_PHOTO: str | None = None


def photo(name: str = "work.png") -> dict[str, str]:
    global _PHOTO  # noqa: PLW0603
    if _PHOTO is None:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (640, 480), (120, 140, 160)).save(buf, "PNG")
        _PHOTO = base64.b64encode(buf.getvalue()).decode()
    return {"file_name": name, "content_base64": _PHOTO}


def crit(code: str) -> str:
    with get_sessionmaker()() as db:
        c = db.scalar(
            select(QCriterion)
            .where(QCriterion.code == code, QCriterion.status == "published")
            .order_by(QCriterion.version.desc())
        )
        assert c is not None, code
        return str(c.id)


def stc_points(*, rebar_type: str = "H") -> list[dict[str, Any]]:
    """The points of §B.3.2 (ITP-…-STC-001)."""
    return [
        {
            "seq": 10,
            "activity_en": "Approved mix design",
            "activity_ar": "اعتماد الخلطة",
            "characteristic_en": "MAR approved",
            "characteristic_ar": "اعتماد المواد",
            "point_type": "R",
            "acceptance_text_en": "MAR approved (A or B)",
            "verifying_record": "document",
        },
        {
            "seq": 20,
            "activity_en": "Formwork",
            "activity_ar": "القوالب",
            "characteristic_en": "Line and level",
            "characteristic_ar": "الاستقامة",
            "point_type": "W",
            "criteria_ids": [crit("FORM-TOL")],
            "checklist_template_code": "QSTC-FW",
        },
        {
            "seq": 30,
            "activity_en": "Reinforcement before pour",
            "activity_ar": "التسليح قبل الصب",
            "characteristic_en": "Cover 40 ± 5 mm",
            "characteristic_ar": "الغطاء",
            "point_type": rebar_type,
            "criteria_ids": [crit("COVER-40")],
            "checklist_template_code": "QSTC-RB",
        },
        {
            "seq": 40,
            "activity_en": "Embedded items",
            "activity_ar": "العناصر المدفونة",
            "characteristic_en": "As drawings",
            "characteristic_ar": "حسب المخططات",
            "point_type": "W",
            "acceptance_text_en": "As drawings",
        },
        {
            "seq": 50,
            "activity_en": "Pour",
            "activity_ar": "الصب",
            "characteristic_en": "Slump and temperature",
            "characteristic_ar": "الهبوط والحرارة",
            "point_type": "W",
            "criteria_ids": [crit("CONC-TEMP-32")],
            "competence_code": "CONC-FIELD-TECH",
        },
        {
            "seq": 60,
            "activity_en": "Curing",
            "activity_ar": "المعالجة",
            "characteristic_en": "Wet curing",
            "characteristic_ar": "المعالجة الرطبة",
            "point_type": "S",
            "acceptance_text_en": "Wet curing 7 days",
        },
        {
            "seq": 70,
            "activity_en": "Striking",
            "activity_ar": "فك القوالب",
            "characteristic_en": "70 % f'c",
            "characteristic_ar": "70 %",
            "point_type": "H",
            "acceptance_text_en": "≥ 70 % f'c or 7 days",
        },
    ]


def itp_body(ids: Ids, **kw: Any) -> dict[str, Any]:
    b = {
        "title_en": "Cast-in-situ concrete, Pier B",
        "title_ar": "الخرسانة المصبوبة في الموقع، الرصيف B",
        "discipline": "STC",
        "engagement_id": ids.engagement("RAWABI"),
        "zone_ids": [ids.zone("Z-PIERB")],
        "points": stc_points(),
    }
    b.update(kw)
    return b


def approved_itp(api: Api, ids: Ids, **kw: Any) -> dict[str, Any]:
    bilal = api.as_("bilal.qureshi")
    it = ok(
        bilal.post(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/itps", json=itp_body(ids, **kw)
        ),
        201,
    )
    ok(bilal.post(f"{API}/quality/itps/{it['id']}/submit"))
    abd = api.as_("abdullah.dossary")
    return ok(abd.post(f"{API}/quality/itps/{it['id']}/decide", json={"code": "A"}))


def ir_body(
    ids: Ids,
    itp: dict[str, Any],
    seqs: list[int],
    loc: str = "Level 3 slab, grid C14–C20",
    **kw: Any,
) -> dict[str, Any]:
    b = {
        "itp_id": itp["id"],
        "point_seqs": seqs,
        "site_id": ids.site("S-LAND"),
        "zone_id": ids.zone("Z-PIERB"),
        "location_ref": loc,
        "proposed_at": (now() + timedelta(days=30)).isoformat(),
        "self_check_done": True,
    }
    b.update(kw)
    return b


def submit_ir(
    c: TestClient, ids: Ids, itp: dict[str, Any], seqs: list[int], status: int = 201, **kw: Any
) -> Any:
    kw.setdefault("proposed_at", (now() + timedelta(hours=30)).isoformat())
    return c.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/quality/inspection-requests",
        json=ir_body(ids, itp, seqs, submit=True, **kw),
    )


def schedule(c: TestClient, ir_id: str, when: datetime | None = None, **kw: Any) -> dict[str, Any]:
    body = {"scheduled_at": (when or now() + timedelta(hours=2)).isoformat(), **kw}
    return ok(c.post(f"{API}/quality/inspection-requests/{ir_id}/schedule", json=body))


def answers(template: str, *, fail: str | None = None) -> list[dict[str, Any]]:
    """All compliant, or one item non-compliant with a note."""
    from app.seed_quality_q1 import TEMPLATES, _items

    out = []
    for it in _items(template, TEMPLATES[template][3]):
        bad = it["item_code"] == fail
        out.append(
            {
                "item_code": it["item_code"],
                "answer": "non_compliant" if bad else "compliant",
                **({"note": "Spacers missing under bars."} if bad else {}),
            }
        )
    return out


def decide_body(
    seqs: list[int],
    result: str = "approved",
    *,
    cover: str = "41",
    temp: str = "29",
    fail: str | None = None,
    **kw: Any,
) -> dict[str, Any]:
    tpl = {20: "QSTC-FW", 30: "QSTC-RB"}
    m = []
    a: dict[str, Any] = {}
    for s in seqs:
        if s in tpl:
            a[str(s)] = answers(tpl[s], fail=fail if s == 30 else None)
        if s == 20:
            m.append({"point_seq": 20, "value": "3", "criterion_id": crit("FORM-TOL")})
        if s == 30:
            m.append({"point_seq": 30, "value": cover, "criterion_id": crit("COVER-40")})
        if s == 50:
            m.append({"point_seq": 50, "value": temp, "criterion_id": crit("CONC-TEMP-32")})
    b: dict[str, Any] = {"result": result, "answers": a, "measurements": m}
    if result in ("rejected", "not_ready"):
        b.setdefault("comment", "Spacers missing under the bottom mat.")
    if result == "rejected":
        b["reject_category"] = "workmanship"
        b["photos"] = [photo()]
    if result == "approved_with_comments":
        b["comments"] = [{"text_en": "Clean the soffit before the pour."}]
    b.update(kw)
    return b
