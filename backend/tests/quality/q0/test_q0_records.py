"""Q0 observations, quality alerts, complaints, licence read-only, PDPL, EN / AR, registries and
stubs, and the Appendix A seed (spec 8-quality §A.16 AC-Q0-42…48, §3.2, §3.3a, Appendix A)."""

import importlib
import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select

from app.db.session import get_sessionmaker
from app.models import AuditEntry, Notification
from app.models.quality import QAlert, QComplaint, QNcr
from app.services import licence
from app.services.quality import alerts, complaints
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, attach, err, ok, raise_ncr


def test_AC42_observation_to_ncr(qsetup: None, api: Api, ids: Ids) -> None:
    joseph = api.as_("joseph.mathew.qc")
    pid = ids.project("ANIA-EXP")
    o = ok(
        joseph.post(
            f"{API}/projects/{pid}/quality/observations",
            json={
                "site_id": ids.site("S-LAND"),
                "engagement_id": ids.engagement("RAWABI"),
                "category": "workmanship",
                "description": "Rebar stored on the ground near the pour.",
            },
        ),
        201,
    )
    n = ok(
        joseph.post(
            f"{API}/quality/observations/{o['id']}/ncr",
            json={
                "owner_id": ids.user("bilal.qureshi"),
                "requirement_en": "Store rebar on dunnage.",
                "category": "workmanship",
                "detection_stage": "in_process",
                "classification": "minor",
                "open": True,
            },
        ),
        201,
    )
    assert n["source_type"] == "observation" and n["source_ref"] == o["obs_no"]
    assert any(lk["kind"] == "raised_from" and lk["record_id"] == o["id"] for lk in n["links"])
    assert ok(joseph.get(f"{API}/quality/observations/{o['id']}"))["status"] == "actioned"


def _alert(api: Api, ids: Ids) -> dict[str, Any]:
    hatem = api.as_("hatem.shehri")
    pid = ids.project("ANIA-EXP")
    a = ok(
        hatem.post(
            f"{API}/projects/{pid}/quality/alerts",
            json={
                "title_en": "Rebar heat H71203 — do not use",
                "title_ar": "حديد الصبّة H71203 — لا يُستخدم",
                "message_en": "Held pending the mill certificate.",
                "message_ar": "محجوز حتى ورود الشهادة.",
                "severity": "stop_use",
                "site_ids": [ids.site("S-LAND")],
                "dist_roles": ["qc_inspector"],
                "ack_required": True,
                "valid_until": "2026-10-31",
            },
        ),
        201,
    )
    return ok(api.as_("hatem.shehri").post(f"{API}/quality/alerts/{a['id']}/issue", json={}))


def test_AC43_stop_use_alert_ack_and_reminder(qsetup: None, api: Api, ids: Ids) -> None:
    hatem = api.as_("hatem.shehri")
    pid = ids.project("ANIA-EXP")
    a = ok(
        hatem.post(
            f"{API}/projects/{pid}/quality/alerts",
            json={
                "title_en": "Rebar heat H71203 — do not use",
                "title_ar": "حديد الصبّة H71203 — لا يُستخدم",
                "message_en": "Held pending the mill certificate.",
                "message_ar": "محجوز حتى ورود الشهادة.",
                "severity": "stop_use",
                "site_ids": [ids.site("S-LAND")],
                "dist_roles": ["qc_inspector"],
                "ack_required": True,
                "valid_until": "2026-10-31",
            },
        ),
        201,
    )
    # the drafter (Hatem) cannot issue his own draft; the HSE Manager does not resolve
    err(hatem.post(f"{API}/quality/alerts/{a['id']}/issue", json={}), 422, "SOD_CONFLICT")
    with get_sessionmaker()() as db:
        row = db.get(QAlert, uuid.UUID(a["id"]))
        assert row is not None
        row.created_by_user_id = uuid.UUID(ids.user("rania.zahrani"))
        db.commit()
    a = ok(hatem.post(f"{API}/quality/alerts/{a['id']}/issue", json={}))
    joseph = api.as_("joseph.mathew.qc")
    home = ok(joseph.get(f"{API}/projects/{pid}/quality/home"))
    assert [b["id"] for b in home["stop_use_alerts"]] == [a["id"]]
    assert ok(joseph.post(f"{API}/quality/alerts/{a['id']}/ack"))["i_acked"] is True
    again = ok(joseph.post(f"{API}/quality/alerts/{a['id']}/ack"))
    assert again["ack_count"] == 1
    with get_sessionmaker()() as db:
        row = db.get(QAlert, uuid.UUID(a["id"]))
        assert row is not None and row.issued_at is not None
        day3 = row.issued_at + timedelta(days=3, minutes=1)
        alerts.remind(db, day3)
        alerts.remind(db, day3 + timedelta(hours=1))
        db.commit()
        rem = list(
            db.scalars(
                select(Notification).where(
                    Notification.entity_id == row.id, Notification.title_en.like("Reminder%")
                )
            )
        )
    users = [r.user_id for r in rem]
    assert uuid.UUID(ids.user("joseph.mathew.qc")) not in users
    assert sorted(users) == sorted({*users}) and uuid.UUID(ids.user("mazen.harbi")) in users


def test_AC44_complaint_justified_needs_ncr_and_ack_alert(qsetup: None, api: Api, ids: Ids) -> None:
    from app.models.quality import QCustomer

    hatem = api.as_("hatem.shehri")
    pid = ids.project("ANIA-EXP")
    with get_sessionmaker()() as db:
        anc = db.scalar(select(QCustomer).where(QCustomer.code == "ANC"))
        assert anc is not None
        cust = str(anc.id)
    c = ok(
        hatem.post(
            f"{API}/projects/{pid}/quality/complaints",
            json={
                "customer_id": cust,
                "channel": "letter",
                "category": "workmanship",
                "description": "Water ponding at stand 23 after rain.",
                "severity": "medium",
                "site_id": ids.site("S-AIR"),
            },
        ),
        201,
    )
    with get_sessionmaker()() as db:
        row = db.get(QComplaint, uuid.UUID(c["id"]))
        assert row is not None
        complaints.overdue_alerts(db, row.received_at + timedelta(hours=23))
        db.commit()
        assert not db.scalar(select(Notification.id).where(Notification.entity_id == row.id))
        complaints.overdue_alerts(db, row.received_at + timedelta(hours=24, minutes=1))
        complaints.overdue_alerts(db, row.received_at + timedelta(hours=25))
        db.commit()
        n = db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.entity_id == row.id,
                Notification.title_en.like("%acknowledgement%"),
                Notification.user_id == uuid.UUID(ids.user("hatem.shehri")),
            )
        )
        assert n == 1
    url = f"{API}/quality/complaints/{c['id']}/transitions"
    ok(hatem.post(url, json={"to_status": "acknowledged", "ack_method": "email"}))
    ok(hatem.post(url, json={"to_status": "under_investigation"}))
    rania = api.as_("rania.zahrani")
    with get_sessionmaker()() as db:  # Hatem recorded it; Rania (245) responds, Hatem signs
        row = db.get(QComplaint, uuid.UUID(c["id"]))
        assert row is not None
        row.created_by_user_id = uuid.UUID(ids.user("rania.zahrani"))
        db.commit()
    resp = {"to_status": "responded", "justified": "yes", "response_en": "Falls will be corrected."}
    err(hatem.post(url, json=resp), 422, "NCR_REQUIRED_FOR_JUSTIFIED")
    n = ok(
        rania.post(
            f"{API}/quality/complaints/{c['id']}/ncr",
            json={
                "owner_id": ids.user("rania.zahrani"),
                "requirement_en": "Falls 1 % to the drains.",
                "responsible_engagement_id": ids.engagement("GULFPAVE"),
                "category": "workmanship",
                "classification": "major",
                "open": True,
            },
        ),
        201,
    )
    assert n["detection_stage"] == "at_customer" and n["failure_class"] == "external"
    assert ok(hatem.post(url, json=resp))["status"] == "responded"


@pytest.fixture
def read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    st = SimpleNamespace(read_only=True, state="expired", terms=None)
    monkeypatch.setattr(licence, "current", lambda *a, **k: st)


def test_AC46_read_only_licence(
    qsetup: None, api: Api, ids: Ids, monkeypatch: pytest.MonkeyPatch
) -> None:
    hatem = api.as_("hatem.shehri")
    n = raise_ncr(hatem, ids)
    pid = ids.project("ANIA-EXP")
    st = SimpleNamespace(read_only=True, state="expired", terms=None)
    monkeypatch.setattr(licence, "current", lambda *a, **k: st)
    err(
        hatem.post(f"{API}/projects/{pid}/quality/ncrs", json={"title": "x"}),
        403,
        "LICENCE_READ_ONLY",
    )
    err(
        hatem.patch(f"{API}/projects/{pid}/quality/settings", json={"values": {}}),
        403,
        "LICENCE_READ_ONLY",
    )
    err(
        hatem.put(
            f"{API}/projects/{pid}/quality/profile",
            json={"sector_profile": "logistics", "reason": "x" * 25},
        ),
        403,
        "LICENCE_READ_ONLY",
    )
    assert hatem.get(f"{API}/projects/{pid}/quality/ncrs").status_code == 200
    assert hatem.get(f"{API}/quality/ncrs/{n['id']}/pdf").status_code == 200
    res = hatem.post(f"{API}/exports", json={"dataset": "quality_ncrs", "project_id": pid})
    assert res.status_code == 201, res.text


def test_AC47_viewer_sees_no_names_costs_photos_or_contacts(
    qsetup: None, api: Api, ids: Ids
) -> None:
    hatem = api.as_("hatem.shehri")
    n = raise_ncr(hatem, ids)
    attach(api.as_("bilal.qureshi"), "q_ncr", n["id"])
    ok(
        api.as_("bilal.qureshi").post(
            f"{API}/quality/ncrs/{n['id']}/costs",
            json={"cost_type": "rework_labour", "quantity": "2"},
        ),
        201,
    )
    sarah = api.as_("sarah.mitchell")
    pid = ids.project("ANIA-EXP")
    item = ok(sarah.get(f"{API}/projects/{pid}/quality/ncrs"))["items"][0]
    assert item["owner"] is None and item["cost_gross_sar"] is None
    full = ok(sarah.get(f"{API}/quality/ncrs/{n['id']}"))
    assert full["raised_by"] is None and full["cost_lines"] == [] and full["names_hidden"] is True
    assert (
        sarah.get(
            f"{API}/attachments", params={"owner_type": "q_ncr", "owner_id": n["id"]}
        ).status_code
        == 403
    )
    sup = ok(sarah.get(f"{API}/quality/suppliers"))["items"][0]
    assert sup["contact_email"] is None and sup["contacts_visible"] is False
    res = hatem.post(
        f"{API}/exports",
        json={"dataset": "quality_ncrs", "project_id": pid, "columns": ["ncr_no", "raised_by"]},
    )
    assert res.status_code == 201, res.text
    with get_sessionmaker()() as db:
        assert db.scalar(
            select(AuditEntry.id).where(
                AuditEntry.action == "export",
                AuditEntry.actor_user_id == uuid.UUID(ids.user("hatem.shehri")),
            )
        )


def test_AC48_errors_carry_arabic(qsetup: None, api: Api, ids: Ids) -> None:
    faisal = api.as_("faisal.harbi")
    d = err(
        faisal.post(
            f"{API}/projects/{ids.project('RBT-52')}/quality/ncrs",
            json={"site_id": ids.site("S-TWR"), "title": "x"},
        ),
        422,
        "PROFILE_REQUIRED",
    )
    assert d["message_ar"] and any("؀" <= ch <= "ۿ" for ch in d["message_ar"])
    ref = ok(faisal.get(f"{API}/quality/reference"))
    for kind in ("ncr_status", "ncr_class", "ncr_category", "disposition", "cost_type"):
        assert all(ar.strip() for _en, ar in ref["labels"][kind].values()), kind


# ---- registries, stubs and jobs (§3.2, §3.3a, §4) ----------------------------------------------


def test_stubs_and_registries_exist() -> None:
    from app.services.quality import ensure_registered
    from app.services.quality import registry as reg

    for n in (1, 2, 3, 4):
        for mod in (
            f"app.core.quality.q{n}",
            f"app.models.quality.q{n}",
            f"app.schemas.quality.q{n}",
            f"app.services.quality.q{n}",
            f"app.api.routers.quality.q{n}",
            f"app.seed_quality_q{n}",
        ):
            importlib.import_module(mod)
        assert callable(importlib.import_module(f"app.services.quality.q{n}").register)
    ensure_registered()
    from app.core.quality.common import QNcrSourceType, QRecordType

    assert {QNcrSourceType.observation, QNcrSourceType.complaint} <= set(reg.NCR_SOURCES)
    assert QRecordType.ncr in reg.RECORD_TYPES and "Q0" in reg.PENDING_STEPS
    assert "quality_ncrs" in reg.DATASETS
    assert reg.competence_check(None, uuid.uuid4(), "CWI", date(2026, 10, 6)).met is None  # type: ignore[arg-type]


def test_job_slots_run(qsetup: None) -> None:
    from app.jobs import JOBS

    for slot in ("quality_daily", "quality_alerts", "quality_weekly", "quality_monthly"):
        assert slot in JOBS
    with get_sessionmaker()() as db:
        out = JOBS["quality_daily"](db)
        assert "Q0" in out
        db.commit()


# ---- Appendix A seed ----------------------------------------------------------------------------


def test_seed_appendix_a(q_seed: None, api: Api, ids: Ids) -> None:
    from app.services.quality.ncr import core

    with get_sessionmaker()() as db:

        def rows(code: str) -> list[QNcr]:
            return list(db.scalars(select(QNcr).where(QNcr.ncr_no.like(f"NCR-{code}-%"))))

        ania, ruh = rows("ANIA-EXP"), rows("RUH-CCH")
        assert len(ania) == 44 and len(ruh) == 36
        sept = [n for n in ania if n.opened_date and n.opened_date.month == 9]
        cls = {
            c: sum(1 for n in sept if n.classification == c) for c in ("minor", "major", "critical")
        }
        assert len(sept) == 14 and cls == {"minor": 9, "major": 4, "critical": 1}
        sep30 = date(2026, 9, 30)
        open_at = [
            n
            for n in ania
            if n.opened_date
            and n.opened_date <= sep30
            and (n.closed_date is None or n.closed_date > sep30)
        ]
        ages = [(sep30 - n.opened_date).days for n in open_at if n.opened_date]
        buckets = [
            sum(1 for a in ages if lo <= a <= hi)
            for lo, hi in ((0, 30), (31, 60), (61, 90), (91, 10_000))
        ]
        assert buckets == [8, 2, 1, 0]
        closed_sept = sorted(
            core.closure_days(n) or 0 for n in ania if n.closed_date and n.closed_date.month == 9
        )
        assert len(closed_sept) == 10
        assert (closed_sept[4] + closed_sept[5]) / 2 == 12
        due = [n for n in ania if n.target_close_date and n.target_close_date.month == 9]
        assert len(due) == 10 and sum(1 for n in due if core.on_time(n)) == 8
        gross = sum(n.cost_gross_sar for n in sept)
        assert gross == 186_450 and sum(n.cost_recovered_sar for n in sept) == 22_600
        ext = sum(n.cost_gross_sar for n in sept if n.detection_stage == "at_customer")
        assert ext == 15_250
        assert sum(1 for n in sept if n.repeat_of_id) == 1
        n44 = next(n for n in ania if n.ncr_no == "NCR-ANIA-EXP-2026-0044")
        assert n44.status == "disposition_approved" and n44.cost_gross_sar == 20_010
        rsept = [n for n in ruh if n.opened_date and n.opened_date.month == 9]
        assert len(rsept) == 9 and sum(1 for n in rsept if n.classification == "major") == 3
    hatem = api.as_("hatem.shehri")
    assert raise_ncr(hatem, ids)["ncr_no"] == "NCR-ANIA-EXP-2026-0045"
    reem = api.as_("reem.mutairi")
    assert raise_ncr(reem, ids, "RUH-CCH")["ncr_no"] == "NCR-RUH-CCH-2026-0037"
