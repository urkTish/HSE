# ruff: noqa: E501
"""Phase 6e aspects, permits, licences, providers and settings (6e §9 AC 1-8, 55)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.env_enums import PermitStatus
from app.env_jobs import env_alerts
from app.kpi import env as ke
from app.models import EnvAspect
from app.schemas.env import (
    AspectCreate,
    AspectTransition,
    PermitCreate,
    ProviderTransition,
)
from app.services.env import common as ec
from app.services.env import register, waste
from tests.conftest import Api
from tests.env_helpers import (
    API,
    D,
    P,
    area,
    con_body,
    eng,
    err,
    exd,
    expect,
    notified,
    permit,
    point,
    project,
    prov,
    tick,
)
from tests.env_helpers import fresh as _fresh


def _aspect(db: Session, sev: int, lik: int, **kw: object) -> AspectCreate:
    data = {
        "activity": "paving_asphalt", "aspect": "dust_emission", "impact": "aviation_safety",
        "condition": "normal", "site_ids": [project(db, "ANIA-EXP") and _site(db, "S-AIR")],
        "severity": sev, "likelihood": lik,
    }  # fmt: skip
    data.update(kw)
    return AspectCreate.model_validate(data)


def _site(db: Session, code: str) -> str:
    from app.models import Site

    return str(db.scalar(select(Site.id).where(Site.code == code)))


def test_aspect_significance_and_activation(env_seed: None, clock: None, db: Session) -> None:
    """AC 1-2: score, significance, ASP-2 controls and links, review_due_on."""
    p = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    a = register.create_aspect(db, p, pid, _aspect(db, 4, 3))
    assert (a.score, a.significant) == (12, True)
    act = AspectTransition(action="activate")
    expect("ASPECT_CONTROL_REQUIRED", lambda: register.transition_aspect(db, p, a.id, act))
    ppe = [{"text_en": "Dust masks", "control_level": "ppe"}]
    register.update_aspect(db, p, a.id, _upd(controls=ppe))
    expect("CONTROL_LEVEL_TOO_LOW", lambda: register.transition_aspect(db, p, a.id, act))
    register.update_aspect(
        db, p, a.id,
        _upd(controls=[{"text_en": "Spray bars", "control_level": "engineering"}],
             monitoring_links=[{"point_id": str(point(db, "D-SAIR-01").id), "parameter": "pm10"}]),
    )  # fmt: skip
    out = register.transition_aspect(db, p, a.id, act)
    assert out.status == "active"
    assert out.review_due_on == date(2026, 10, 5) + timedelta(days=365) or out.review_due_on == (
        date(2027, 10, 5)
    )
    b = register.create_aspect(db, p, pid, _aspect(db, 2, 3, legal_requirement=True))
    assert b.significant
    c = register.create_aspect(db, p, pid, _aspect(db, 2, 3))
    assert not c.significant
    assert register.transition_aspect(db, p, c.id, act).status == "active"


def _upd(**kw: object) -> object:
    from app.schemas.env import AspectUpdate

    return AspectUpdate.model_validate(kw)


def test_review_flags_aspect(env_seed: None, clock: None, db: Session) -> None:
    """AC 3: a project_activity review on S-AIR pm10 flags ASP-ANIA-EXP-004 (dust_emission)."""
    from app.models import EnvExceedance
    from app.schemas.env import ExceedanceReview
    from app.services.env import exceedances

    x = exd(db, "ENX-ANIA-EXP-2026-0017")
    x.status, x.cause, x.ca_id = "open", None, None
    db.flush()
    since = tick(2026, 10, 6, 10)
    body = ExceedanceReview(
        cause="project_activity", responsible_engagement_id=eng(db, "ANIA-EXP", "GULFPAVE").id,
        activity_en="Milling", immediate_action_en="Stopped",
    )  # fmt: skip
    exceedances.review(db, P(db, "noura.qahtani"), x.id, body)
    a4 = db.scalar(select(EnvAspect).where(EnvAspect.aspect_no == "ASP-ANIA-EXP-004"))
    assert a4 is not None and a4.review_flag
    assert len(notified(db, "aspect_review", since).get("noura.qahtani", [])) == 1
    flagged = db.scalars(select(EnvAspect.aspect_no).where(EnvAspect.review_flag.is_(True)))
    assert set(flagged) == {"ASP-ANIA-EXP-004"}
    # a noise exceedance on S-LAND does not flag it
    a4.review_flag = False
    register.flag_aspects(db, x.project_id, point(db, "N-SLAND-01").site_id, {"noise_vibration"},
                          "ENX-TEST")  # fmt: skip
    assert not a4.review_flag
    assert db.get(EnvExceedance, x.id) is not None


def test_permit_alerts_expiry_and_producer_check(env_seed: None, db: Session) -> None:
    """AC 4-6: EV4 alert dates, expiring / expired, PRODUCER_REGISTRATION_INVALID, K-118."""
    pm = permit(db, "MWAN-PRD-TEST-0420")
    pid = project(db, "ANIA-EXP").id
    assert ec.permit_status(db, pm, date(2026, 10, 6)) == PermitStatus.expiring
    assert ec.permit_status(db, pm, date(2026, 11, 1)) == PermitStatus.expired
    sent = []

    def count() -> int:
        got = notified(db, "env_permit_expiry").get("faisal.harbi", [])
        return len([t for t in got if "EPL-ANIA-EXP-002" in t])

    for d in (date(2026, 8, 2), date(2026, 9, 1), date(2026, 10, 1), date(2026, 10, 17),
              date(2026, 10, 24), date(2026, 10, 31), date(2026, 11, 1), date(2026, 10, 18)):  # fmt: skip
        n0 = count()
        tick(d.year, d.month, d.day, 7, 8)
        env_alerts(db)
        sent.append(count() - n0)
    assert sent == [1, 1, 1, 1, 1, 1, 1, 0]
    assert ke.permit_stats(db, [pid], date(2026, 11, 1))[:2] == (3, 4)
    expect(
        "PRODUCER_REGISTRATION_INVALID", lambda: waste.producer_check(db, pid, date(2026, 11, 1))
    )
    rbt = project(db, "RBT-52").id
    assert ke.permit_stats(db, [rbt], date(2026, 9, 30))[:2] == (3, 4)


def test_renewal_supersedes(env_seed: None, db: Session) -> None:
    """AC 5: a renewal stops the alerts; the old record is superseded; dispatch accepted."""
    tick(2026, 10, 20, 9)
    p = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    register.create_permit(db, p, pid, None, PermitCreate(
        permit_type="mwan_producer_registration", issuer="mwan", requirement_code="MWAN-REG",
        required=True, reference_no="MWAN-PRD-TEST-0421", valid_from=date(2026, 11, 1),
        valid_to=date(2027, 10, 31),
    ))  # fmt: skip
    _fresh(db)
    for d in (24, 31):
        since = tick(2026, 10, d, 7, 8)
        env_alerts(db)
        got = notified(db, "env_permit_expiry", since).get("faisal.harbi", [])
        assert not [t for t in got if "EPL-ANIA-EXP-002" in t]
    old = permit(db, "MWAN-PRD-TEST-0420")
    assert ec.permit_status(db, old, date(2026, 11, 1)) == PermitStatus.superseded
    waste.producer_check(db, pid, date(2026, 11, 1))


def test_discharge_permit_not_valid(env_seed: None, db: Session) -> None:
    """AC 6: discharge records from 09-21 carry PERMIT_NOT_VALID; one alert per day."""
    from app.models import DischargeDay
    from app.schemas.env import DischargeCreate
    from app.services.env import water

    rows = db.scalars(select(DischargeDay).order_by(DischargeDay.day)).all()
    assert all(("PERMIT_NOT_VALID" in r.warnings) == (r.day >= date(2026, 9, 21)) for r in rows)
    since = tick(2026, 10, 6, 18)
    db.execute(DischargeDay.__table__.delete().where(DischargeDay.day == date(2026, 10, 6)))
    out = water.create_discharge(
        db, P(db, "lina.haddad"), project(db, "RBT-52").id,
        DischargeCreate(point_id=point(db, "W-SPOD-01").id, day=date(2026, 10, 6),
                        volume_m3=D("100")),
    )  # fmt: skip
    assert [w.code for w in out.warnings] == ["PERMIT_NOT_VALID"]
    n = notified(db, "discharge_permit_invalid", since)
    assert len(n.get("lina.haddad", [])) == 1 and len(n.get("faisal.harbi", [])) == 1


def test_permissions_and_settings(env_seed: None, clock: None, api: Api, db: Session) -> None:
    """AC 7, 55: 204 / 213 / settings loosening and Noura not allowed to edit settings."""
    pid = project(db, "ANIA-EXP").id
    body = {"permit_type": "eia_approval", "issuer": "ncec", "reference_no": "EIA-TEST-1"}
    r = api.as_("ahmed.zahrani").post(f"{API}/projects/{pid}/env-permits", json=body)
    assert r.status_code in (403, 404), r.text
    r = api.as_("noura.qahtani").post(f"{API}/projects/{pid}/env-permits", json=body)
    assert r.status_code == 201, r.text
    f = api.as_("faisal.harbi")
    r = f.patch(
        f"{API}/projects/{pid}/env-settings", json={"permit_alert_days": [60, 30, 14, 7, 0]}
    )
    assert r.status_code == 422 and err(r) == "SETTING_LOOSENING"
    for bad in ({"spill_reportable_l": 30}, {"manifest_return_days": 10},
                {"airside_spill_always_reportable": False}):  # fmt: skip
        r = f.patch(f"{API}/projects/{pid}/env-settings", json=bad)
        assert r.status_code == 422 and err(r) == "SETTING_LOOSENING", (bad, r.text)
    r = f.patch(f"{API}/projects/{pid}/env-settings",
                json={"spill_reportable_l": 10, "manifest_return_days": 5})  # fmt: skip
    assert r.status_code == 200, r.text
    assert D(r.json()["spill_reportable_l"]) == 10 and r.json()["manifest_return_days"] == 5
    r = api.as_("noura.qahtani").patch(f"{API}/projects/{pid}/env-settings",
                                       json={"spill_reportable_l": 5})  # fmt: skip
    assert r.status_code == 403
    pv = prov(db, "GREENHAUL")
    r = api.as_("noura.qahtani").post(f"{API}/env-providers/{pv.id}/transitions",
                                      json={"action": "blacklist", "reason": "Repeated breaches"})  # fmt: skip
    assert r.status_code == 403


def test_licence_checks(env_seed: None, clock: None, db: Session) -> None:
    """AC 8: EV5 variants; blacklisted transporter; sewage needs a sewage tanker."""
    from app.services.env import waste as w

    p = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    hws = area(db, "HWS-SLAND-01").id
    oil = {"stream_code": "used_oil", "storage_area_id": hws, "quantity": D("1000"), "unit": "L",
           "facility_provider_id": prov(db, "OILREF").id, "facility_code": "OILREF-1",
           "mwan_manifest_ref": "MWAN-MF-TEST-9"}  # fmt: skip
    lic = db.get(type(permit(db, "MWAN-TR-TEST-1102")), permit(db, "MWAN-TR-TEST-1102").id)
    assert lic is not None
    lic.valid_to = date(2026, 10, 5)
    db.flush()
    _fresh(db)
    expect("PROVIDER_LICENCE_INVALID", lambda: w.create_consignment(
        db, p, pid, con_body(db, transporter_id=prov(db, "HAZMOVE").id, **oil)))  # fmt: skip
    expect("LICENCE_SCOPE_MISMATCH", lambda: w.create_consignment(
        db, p, pid, con_body(db, transporter_id=prov(db, "GREENHAUL").id, **oil)))  # fmt: skip
    register.transition_provider(db, P(db, "faisal.harbi"), prov(db, "GREENHAUL").id,
                                 ProviderTransition(action="blacklist", reason="Fly-tipping found at two sites"))  # fmt: skip
    expect("PROVIDER_NOT_APPROVED", lambda: w.create_consignment(db, p, pid, con_body(db)))
    body = con_body(db, "sewage", storage_area_id=None, site_id=_site(db, "S-LAND"),
                    quantity=D("20"), unit="m3",
                    transporter_id=prov(db, "METALCO").id,
                    facility_provider_id=prov(db, "STP-RUH").id, facility_code="STP-RUH")  # fmt: skip
    expect("LICENCE_SCOPE_MISMATCH", lambda: w.create_consignment(db, p, pid, body))
