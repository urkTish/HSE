"""Q1 rules the package left untested (integration notes, D-370): Q-ITP-05 across revisions, the
Q-ITP-06 coverage grid, the IR not-scheduled and comment-overdue alerts (D-338) and
DOSSIER_TOO_LARGE (Q-DOS-04). Clock HSE_CLOCK_AT 2026-10-06 10:00 Riyadh."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.clock import now
from app.db.session import get_sessionmaker
from app.models import Notification
from app.services.quality.q1 import jobs
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, attach, err, ok
from tests.quality.q1.q1h import approved_itp, decide_body, schedule, submit_ir


def _sent(ir_id: str, words: str) -> set[str]:
    """Recipients of the IR's notifications whose English title contains `words`."""
    with get_sessionmaker()() as db:
        return {
            str(u)
            for u in db.scalars(
                select(Notification.user_id).where(
                    Notification.entity_id == ir_id, Notification.title_en.contains(words)
                )
            )
        }


def test_q_itp_05_hold_released_on_an_earlier_revision(q1lib: None, api: Api, ids: Ids) -> None:
    rev0 = approved_itp(api, ids)
    joseph, abd, bilal = (
        api.as_("joseph.mathew.qc"),
        api.as_("abdullah.dossary"),
        api.as_("bilal.qureshi"),
    )
    r30 = ok(submit_ir(joseph, ids, rev0, [30]), 201)
    schedule(abd, r30["id"])
    ok(abd.post(f"{API}/quality/inspection-requests/{r30['id']}/decide", json=decide_body([30])))
    rev1 = ok(
        bilal.post(
            f"{API}/quality/itps/{rev0['id']}/revisions",
            json={"change_note": "Point 50 adds the concrete temperature"},
        ),
        201,
    )
    ok(bilal.post(f"{API}/quality/itps/{rev1['id']}/submit"))
    rev1 = ok(abd.post(f"{API}/quality/itps/{rev1['id']}/decide", json={"code": "A"}))
    assert rev1["status"] == "approved"
    # point 30 kept its seq and type H in Rev.1 → the Rev.0 approval releases it (Q-ITP-05)
    r40 = ok(submit_ir(joseph, ids, rev1, [40]), 201)
    assert r40["status"] == "submitted" and r40["itp_revision"] == 1
    # at another location the hold is not released
    err(submit_ir(joseph, ids, rev1, [40], loc="Level 4 slab"), 422, "HOLD_POINT_NOT_RELEASED")


def test_q_itp_06_coverage_grid(q1lib: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids)
    joseph, abd = api.as_("joseph.mathew.qc"), api.as_("abdullah.dossary")
    r30 = ok(submit_ir(joseph, ids, itp, [30]), 201)
    schedule(abd, r30["id"])
    ok(abd.post(f"{API}/quality/inspection-requests/{r30['id']}/decide", json=decide_body([30])))
    r40 = ok(submit_ir(joseph, ids, itp, [40]), 201)
    cov = ok(joseph.get(f"{API}/quality/itps/{itp['id']}/coverage"))
    assert [p["seq"] for p in cov["points"]] == [10, 20, 30, 40, 50, 60, 70]
    (row,) = cov["rows"]
    assert row["location_key"] == r30["location_key"]
    cells = {c["seq"]: (c["state"], c["ir_no"]) for c in row["cells"]}
    assert cells[30] == ("approved", r30["ir_no"]) and cells[40] == ("scheduled", r40["ir_no"])
    assert cells[70] == ("not_started", None)


def test_ir_not_scheduled_and_comment_overdue_alerts(q1lib: None, api: Api, ids: Ids) -> None:
    from app.services.quality import settings as qs

    itp = approved_itp(api, ids)
    joseph, abd = api.as_("joseph.mathew.qc"), api.as_("abdullah.dossary")
    r = ok(submit_ir(joseph, ids, itp, [30]), 201)
    with get_sessionmaker()() as db:
        hours = int(qs.value(db, r["project_id"], "ir_schedule_hours"))
        early = jobs.ir_alerts(db, now() + timedelta(hours=hours) - timedelta(minutes=5))
        late = jobs.ir_alerts(db, now() + timedelta(hours=hours, minutes=5))
        again = jobs.ir_alerts(db, now() + timedelta(hours=hours, minutes=10))
        db.commit()
    assert early["not_scheduled"] == 0 and late["not_scheduled"] >= 1
    assert again["not_scheduled"] == 0  # once per IR
    to = _sent(r["id"], "is not scheduled")
    assert ids.user("abdullah.dossary") in to
    assert ids.user("joseph.mathew.qc") not in to  # not the requester
    schedule(abd, r["id"])
    body = decide_body([30], "approved_with_comments")
    d = ok(abd.post(f"{API}/quality/inspection-requests/{r['id']}/decide", json=body))
    assert d["status"] == "approved_with_comments"
    cm = d["comments"][0]
    from datetime import date

    due = date.fromisoformat(cm["due_on"])
    with get_sessionmaker()() as db:
        on_due = jobs.ir_alerts(db, now().replace(year=due.year, month=due.month, day=due.day))
        after = jobs.ir_alerts(db, now() + timedelta(days=(due - now().date()).days + 1))
        db.commit()
    assert on_due["comments_overdue"] == 0 and after["comments_overdue"] >= 1  # per recipient
    assert ids.user("joseph.mathew.qc") in _sent(r["id"], "approval comment overdue")


def test_dossier_too_large(
    q1lib: None, api: Api, ids: Ids, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.quality.q1 import dossier

    hatem = api.as_("hatem.shehri")
    d = ok(
        hatem.post(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/dossiers",
            json={"title_en": "Pier B", "title_ar": "الرصيف B", "zone_ids": [ids.zone("Z-PIERB")]},
        ),
        201,
    )
    from tests.quality.q0.qh import raise_ncr

    n = raise_ncr(api.as_("bilal.qureshi"), ids, zone_id=ids.zone("Z-PIERB"))
    attach(api.as_("bilal.qureshi"), "q_ncr_evidence", n["id"], "evidence.pdf")
    monkeypatch.setattr(dossier, "DOSSIER_MAX_BYTES", 10)
    err(hatem.post(f"{API}/quality/dossiers/{d['id']}/compile"), 422, "DOSSIER_TOO_LARGE")
    monkeypatch.setattr(dossier, "DOSSIER_MAX_BYTES", 2 * 1024**3)
    assert ok(hatem.post(f"{API}/quality/dossiers/{d['id']}/compile"))["status"] == "compiled"
