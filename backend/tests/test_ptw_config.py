"""3-ptw §9 AC1-AC9 (configuration, appointments, segregation of duties)."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.models import AuditEntry, Contractor, User
from app.schemas.permits import IssueInput, PermitCrewInput, PermitUpdate
from app.services.ptw import lifecycle, permits
from tests.conftest import Api, Ids
from tests.ptw_helpers import SEED_AT, activate, at, expect, fx, permit, wind, world

API = "/api/v1"


@pytest.fixture
def n(ptw_seed: None, db: Session) -> Iterator[Any]:
    set_now(SEED_AT)
    yield world(db)
    set_now(None)


def test_AC1_taxiway_profile_cannot_be_loosened(n: Any, api: Api, ids: Ids) -> None:
    n.db.commit()
    zone = {
        "code": "Z-TWX", "name_en": "Taxiway X", "name_ar": "الممر X", "zone_type": "airside",
        "airside": {"airside_area": "taxiway", "in_movement_area": True, "escort_required": True, "adp_required": True},
    }  # fmt: skip
    res = api.as_("faisal.harbi").post(f"{API}/sites/{ids.site('S-AIR')}/zones", json=zone)
    assert res.status_code == 201, res.text
    zid = res.json()["id"]
    noura = api.as_("noura.qahtani")
    prof = noura.get(f"{API}/zones/{zid}/ptw-profile")
    assert prof.status_code == 200, prof.text
    assert prof.json()["permit_required_all_work"] is True
    res = noura.patch(f"{API}/zones/{zid}/ptw-profile", json={"permit_required_all_work": False})
    assert res.status_code == 422 and res.json()["detail"]["code"] == "PROFILE_LOOSENING", res.text


def test_AC2_issuer_appointment_manager_only(n: Any, api: Api, ids: Ids, db: Session) -> None:
    n.db.commit()
    body = {
        "function": "issuer", "holder_user_id": ids.user("omar.siddiqui"), "permit_types": ["general"],
        "site_ids": [ids.site("S-AIR")], "basis": "PTW issuer course TEST-PTW-77", "valid_from": "2026-10-06", "valid_to": "2026-12-31",
    }  # fmt: skip
    url = f"{API}/projects/{ids.project('ANIA-EXP')}/ptw-appointments"
    assert api.as_("noura.qahtani").post(url, json=body).status_code == 403
    res = api.as_("faisal.harbi").post(url, json=body)
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "active"
    db.expire_all()
    assert db.scalar(select(AuditEntry).where(AuditEntry.entity_id == res.json()["id"])) is not None


def test_AC3_issuer_appointment_must_cover_type(n: Any) -> None:
    p = fx(
        n,
        key="joseph.mathew",
        project="RBT-52",
        site="S-TWR",
        zones=("Z-CORE",),
        con="QIMMA",
        receiver="joseph.mathew",
        area="ibrahim.saleh",
        issuer="majed.shammari",
    )
    lifecycle.require_issuer(n.db, n.p("majed.shammari"), p, SEED_AT)
    p.work_types = ["radiography"]
    p.primary_type = "radiography"
    expect(
        "APPOINTMENT_INVALID",
        lambda: lifecycle.require_issuer(n.db, n.p("majed.shammari"), p, SEED_AT),
        422,
    )


def test_AC4_receiver_area_authority_and_contractor_issuer(n: Any) -> None:
    p = permit(n.db, "PTW-ANIA-EXP-2026-0413")
    expect(
        "SOD_CONFLICT",
        lambda: permits.update(
            n.db,
            n.p("faris.anazi"),
            p.id,
            PermitUpdate.model_validate({"area_authority_user_id": str(n.ctx.uid("faris.anazi"))}),
        ),
        422,
    )
    khalid = n.db.get(User, n.ctx.uid("khalid.otaibi"))
    lifecycle.issuer_sod(n.db, p, khalid.id)  # Khalid approved and issued 0413
    rawabi = n.db.scalar(select(Contractor.id).where(Contractor.short_code == "RAWABI"))
    khalid.employer_contractor_id = rawabi  # stands in for a RAWABI-employed permit issuer
    expect("SOD_CONFLICT", lambda: lifecycle.issuer_sod(n.db, p, khalid.id), 422)


def test_AC5_area_authority_cannot_issue(n: Any) -> None:
    p = permit(n.db, "PTW-ANIA-EXP-2026-0412")
    expect(
        "SOD_CONFLICT",
        lambda: permits.update(
            n.db,
            n.p("ramesh.kumar"),
            p.id,
            PermitUpdate.model_validate({"issuer_user_id": str(n.ctx.uid("fahad.mutairi"))}),
        ),
        422,
    )


def test_AC6_fire_watch_sod_and_busy(n: Any) -> None:
    raza = str(n.w("WKR-000015"))
    p = permit(n.db, "PTW-ANIA-EXP-2026-0412")
    expect(
        "SOD_CONFLICT",
        lambda: permits.add_crew(
            n.db,
            n.p("ramesh.kumar"),
            p.id,
            PermitCrewInput.model_validate({"worker_id": raza, "crew_role": "hot_work_operative"}),
        ),
        422,
    )
    q = fx(n, x="10.0", y="10.0", zones=("Z-LAY1",))
    activate(n, q, hse=None)
    assert q.status.value == "active"
    expect(
        "KEY_ROLE_BUSY",
        lambda: permits.add_crew(
            n.db,
            n.p("ramesh.kumar"),
            q.id,
            PermitCrewInput.model_validate({"worker_id": raza, "crew_role": "fire_watch"}),
        ),
        422,
    )


def test_AC7_standby_cannot_enter(n: Any) -> None:
    p = permit(n.db, "PTW-ANIA-EXP-2026-0413")
    expect(
        "SOD_CONFLICT",
        lambda: permits.add_crew(
            n.db,
            n.p("faris.anazi"),
            p.id,
            PermitCrewInput.model_validate(
                {"worker_id": str(n.w("WKR-000017")), "crew_role": "entrant"}
            ),
        ),
        422,
    )


def test_AC8_reauth_for_issue(n: Any) -> None:
    p = permit(n.db, "PTW-ANIA-EXP-2026-0410")
    set_now(at(2026, 10, 6, 12, 45))
    stale = n.p("khalid.otaibi")
    t = at(2026, 10, 6, 13, 5)
    set_now(t)
    body = IssueInput.model_validate(
        {
            "site_visit_confirmed": True,
            "receiver_cosign": n.cosign("faris.anazi"),
            "wind_reading": wind("7.2", t),
        }
    )
    expect("REAUTH_REQUIRED", lambda: lifecycle.issue(n.db, stale, p.id, body), 401)
    lifecycle.issue(n.db, n.p("khalid.otaibi"), p.id, body)
    n.db.refresh(p)
    assert p.status.value == "issued"
    assert t - timedelta(minutes=20) == at(2026, 10, 6, 12, 45)


def test_AC9_type_duration_ranges(n: Any, api: Api, ids: Ids, db: Session) -> None:
    n.db.commit()
    c = api.as_("faisal.harbi")
    url = f"{API}/projects/{ids.project('ANIA-EXP')}/ptw-settings"
    cur = c.get(url).json()["type_max_duration_days"]
    for bad in ({"hot_work": 8}, {"confined_space": 2}):
        res = c.patch(url, json={"type_max_duration_days": {**cur, **bad}})
        assert res.status_code == 422, res.text
    res = c.patch(url, json={"type_max_duration_days": {**cur, "hot_work": 7}})
    assert res.status_code == 200, res.text
    assert res.json()["type_max_duration_days"]["hot_work"] == 7
    db.expire_all()
    rows = db.scalars(
        select(AuditEntry)
        .where(AuditEntry.project_id == ids.project("ANIA-EXP"))
        .order_by(AuditEntry.seq.desc())
        .limit(3)
    ).all()
    assert any("type_max_duration_days" in str(r.after) for r in rows)


def test_phase3_history_endpoints(n: Any, api: Api) -> None:
    from app.models import GasDetector, GasTest, IsolationCertificate, Jsa, PtwAppointment, PtwAudit

    n.db.commit()
    c = api.as_("faisal.harbi")
    rows = {
        "permit": permit(n.db, "PTW-ANIA-EXP-2026-0413").id,
        "ptw_appointment": n.db.scalar(select(PtwAppointment.id).limit(1)),
        "jsa": n.db.scalar(select(Jsa.id).limit(1)),
        "gas_detector": n.db.scalar(select(GasDetector.id).limit(1)),
        "gas_test": n.db.scalar(select(GasTest.id).limit(1)),
        "isolation_certificate": n.db.scalar(select(IsolationCertificate.id).limit(1)),
        "ptw_audit": n.db.scalar(select(PtwAudit.id).limit(1)),
    }
    for et, eid in rows.items():
        res = c.get(f"{API}/history/{et}/{eid}")
        assert res.status_code == 200, (et, res.text)
    assert c.get(f"{API}/history/permit/{n.ctx.uid('faisal.harbi')}").status_code == 404


def test_clock_pin_from_env() -> None:
    from app.core import clock

    try:
        assert clock.pin_from_env("2026-10-06T10:00:00+03:00", "fixed", "test") is not None
        assert clock.now() == at(2026, 10, 6, 10, 0)
        set_now(None)
        clock.pin_from_env("2026-10-06T10:00:00+03:00", None, "development")
        assert abs((clock.now() - at(2026, 10, 6, 10, 0)).total_seconds()) < 5
        with pytest.raises(RuntimeError):
            clock.pin_from_env("2026-10-06T10:00:00+03:00", None, "production")
    finally:
        clock._offset.clear()
        set_now(None)
