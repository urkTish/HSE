"""4-third-party-cert §9 ACs 1-2 (catalogue boundary), 4-12 (TPI organisations) and 13-20
(equipment register and mobilisation)."""

import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.models import (
    EquipmentDeployment,
    GasDetector,
    Notification,
    TpiAccreditation,
    Vehicle,
)
from app.services.cert import tpis as tsvc
from app.services.cert import validity
from tests.cert_helpers import (
    API,
    contractor,
    dep,
    ec_body,
    err_code,
    item,
    line,
    project,
    riyadh,
    tpi,
)
from tests.conftest import Api

pytestmark = pytest.mark.usefixtures("cert_seed", "clock")


def preview(api: Api, db: Session, who: str, pcode: str, body: dict[str, Any]) -> dict[str, Any]:
    pid = project(db, pcode).id
    res = api.as_(who).post(f"{API}/projects/{pid}/equipment-certificates/preview", json=body)
    assert res.status_code == 200, res.text
    out: dict[str, Any] = res.json()
    return out


def create_ec(api: Api, db: Session, who: str, pcode: str, body: dict[str, Any]) -> Any:
    pid = project(db, pcode).id
    return api.as_(who).post(f"{API}/projects/{pid}/equipment-certificates", json=body)


def line_codes(pv: dict[str, Any]) -> list[str]:
    return [e["code"] for ln in pv["lines"] for e in ln["errors"]] + [
        e["code"] for e in pv["errors"]
    ]


def line_warnings(pv: dict[str, Any]) -> list[str]:
    return [w["code"] for ln in pv["lines"] for w in ln["warnings"]] + [
        w["code"] for w in pv["warnings"]
    ]


# ---- boundary and catalogues (AC1-2) ------------------------------------------------------------


def test_P4AC1_catalogues_are_disjoint_both_ways(api: Api, db: Session) -> None:
    c = api.as_("faisal.harbi")
    # A PCT type whose code is an existing training-catalogue code.
    res = c.post(
        f"{API}/cert-types",
        json={
            "code": "GAS-TEST",
            "label_en": "Gas test",
            "label_ar": "اختبار الغاز",
            "cap_months": 24,
        },
    )
    assert res.status_code == 422 and err_code(res) == "CODE_IN_OTHER_CATALOGUE", res.text
    # The reverse: a training-catalogue code (induction course / training_course hook) RIGGER.
    pid = project(db, "ANIA-EXP").id
    from app.services.access import inductions
    from app.services.cert import settings as cset
    from tests.cert_helpers import P, expect

    expect("CODE_IN_OTHER_CATALOGUE", lambda: cset.require_not_cert_type(db, "RIGGER"), 422)
    from app.schemas.inductions import InductionCourseCreate

    body = InductionCourseCreate.model_validate(
        {
            "code": "rigger",
            "induction_type": "zone_specific",
            "name_en": "Rigger",
            "name_ar": "مُربِّط",
            "version": "1.0",
            "validity_months": 12,
            "min_duration_minutes": 30,
            "test_required": False,
            "languages_offered": ["en"],
            "delivered_by_roles": ["hse_officer"],
        }
    )
    expect(
        "CODE_IN_OTHER_CATALOGUE",
        lambda: inductions.create_course(db, P(db, "faisal.harbi"), pid, body),
        422,
    )


def test_P4AC2_tpi_kinds_have_no_training_provider(api: Api, db: Session) -> None:
    from app.core.cert_enums import TpiKind

    assert {k.value for k in TpiKind} == {
        "inspection_body",
        "personnel_certification_body",
        "calibration_lab",
        "ndt_body",
        "client_scheme",
        "fire_protection_service",  # 4-third-party-cert v1.2 (6c §11.5)
    }
    body = {
        "tpi_code": "TRNX",
        "legal_name_en": "Training Provider Test",
        "legal_name_ar": "مزود تدريب",
        "kinds": ["training_provider"],
        "country": "SA",
        "cr_number": "1010999999",
        "verification_domains": ["trn-test.example"],
    }
    res = api.as_("faisal.harbi").post(f"{API}/tpis", json=body)
    assert res.status_code == 422, res.text


# ---- TPI organisations (AC4-12) ---------------------------------------------------------------


def test_P4AC4_only_the_manager_approves_a_tpi(api: Api, db: Session) -> None:
    from app.models import AuditEntry

    t = tpi(db, "MLIS")
    url = f"{API}/tpis/{t.id}/transitions"
    res = api.as_("noura.qahtani").post(url, json={"to_status": "approved"})
    assert res.status_code == 403, res.text
    res = api.as_("faisal.harbi").post(url, json={"to_status": "approved"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"
    db.expire_all()
    assert db.scalar(select(AuditEntry.id).where(AuditEntry.entity_id == t.id)) is not None


def test_P4AC5_accreditation_without_register_check_does_not_count(api: Api, db: Session) -> None:
    t = tpi(db, "MLIS")
    api.as_("faisal.harbi").post(f"{API}/tpis/{t.id}/transitions", json={"to_status": "approved"})
    db.expire_all()
    res = tsvc.acceptability(db, t, date(2026, 10, 6), categories=["lifting_accessory"])
    assert not res.ok and res.reason == "TPI_ACCREDITATION_INVALID"
    pv = preview(
        api, db, "noura.qahtani", "ANIA-EXP",
        ec_body(db, "MLIS", "MLIS-TEST-26-0001", date(2026, 10, 5), [line(db, "FX-ACC-0219")]),
    )  # fmt: skip
    assert pv["tpi_acceptable"] is False and pv["tpi_reason"] == "TPI_ACCREDITATION_INVALID"
    res = create_ec(
        api, db, "noura.qahtani", "ANIA-EXP",
        ec_body(db, "MLIS", "MLIS-TEST-26-0001", date(2026, 10, 5), [line(db, "FX-ACC-0219")]),
    )  # fmt: skip
    assert res.status_code == 422 and err_code(res) == "TPI_NOT_ACCEPTABLE", res.text
    assert "TPI_ACCREDITATION_INVALID" in res.text


def test_P4AC6_Z8_accreditation_valid_to_the_inspection_day(api: Api, db: Session) -> None:
    set_now(riyadh(2026, 11, 4))
    ok = preview(
        api, db, "noura.qahtani", "ANIA-EXP",
        ec_body(db, "NKTI", "NKTI-TEST-26-1102", date(2026, 11, 2),
                [line(db, "NJ-MC-02", swl_t="40.000")]),
    )  # fmt: skip
    assert ok["tpi_acceptable"] is True, ok
    late = ec_body(
        db, "NKTI", "NKTI-TEST-26-1103", date(2026, 11, 3), [line(db, "NJ-MC-02", swl_t="40.000")]
    )
    pv = preview(api, db, "noura.qahtani", "ANIA-EXP", late)
    assert pv["tpi_reason"] == "TPI_ACCREDITATION_INVALID"
    res = create_ec(api, db, "noura.qahtani", "ANIA-EXP", late)
    assert res.status_code == 422 and err_code(res) == "TPI_NOT_ACCEPTABLE"
    assert "TPI_ACCREDITATION_INVALID" in res.text


def test_P4AC7_lapsed_accreditation_keeps_issued_certificates(api: Api, db: Session) -> None:
    set_now(riyadh(2026, 11, 3))
    for tag, until in (("NJ-MC-02", date(2027, 3, 15)), ("TC-01", date(2027, 9, 28))):
        ic = validity.current_line(db, item(db, tag).id, riyadh(2026, 11, 3))
        assert ic.ev.in_force, tag
        assert ic.ev.valid_until == until
        assert ic.cert is not None
        assert tsvc.accreditation_lapsed_note(db, tpi(db, "NKTI"), ic.cert.inspected_on)
    res = api.as_("faisal.harbi").get(f"{API}/equipment/{item(db, 'TC-01').id}")
    assert res.status_code == 200
    assert res.json()["current_line"]["tpi_accreditation_lapsed"] is True


def test_P4AC8_accreditation_expiry_alert_schedule(db: Session) -> None:
    from app.cert_jobs import cert_alerts
    from app.services.cert import alerts

    a = db.scalar(select(TpiAccreditation).where(TpiAccreditation.tpi_id == tpi(db, "NKTI").id))
    assert a is not None and a.valid_until == date(2026, 11, 2)
    assert alerts.scheduled_steps(a.valid_until, (30, 14, 7, 0)) == [
        date(2026, 10, 3),
        date(2026, 10, 19),
        date(2026, 10, 26),
        date(2026, 11, 2),
    ]

    def sent(d: date) -> int:
        set_now(riyadh(d.year, d.month, d.day, 7))
        cert_alerts(db)
        db.flush()
        return (
            db.query(Notification)
            .filter(Notification.title_en.like("NKTI: accreditation%"))
            .count()
        )

    n0 = sent(date(2026, 10, 3))
    assert n0 > 0  # 30-day
    assert sent(date(2026, 10, 6)) == n0  # nothing new between steps
    n1 = sent(date(2026, 10, 19))
    assert n1 > n0  # 14-day
    assert sent(date(2026, 10, 20)) == n1


def test_P4AC9_scope_not_covered(api: Api, db: Session) -> None:
    a = db.scalar(select(TpiAccreditation).where(TpiAccreditation.tpi_id == tpi(db, "NKTI").id))
    assert a is not None
    a.scope_categories = ["pressure_vessel"]
    db.flush()
    db.commit()
    body = ec_body(db, "NKTI", "NKTI-TEST-26-1001", date(2026, 10, 5), [line(db, "SH-MEWP-12")])
    pv = preview(api, db, "noura.qahtani", "ANIA-EXP", body)
    assert pv["tpi_reason"] == "TPI_SCOPE_NOT_COVERED"
    res = create_ec(api, db, "noura.qahtani", "ANIA-EXP", body)
    assert res.status_code == 422 and "TPI_SCOPE_NOT_COVERED" in res.text


def test_P4AC10_tpi_not_independent(api: Api, db: Session) -> None:
    t = tpi(db, "AICC")
    t.affiliated_contractor_ids = [contractor(db, "RAWABI").id]
    db.commit()
    body = ec_body(
        db,
        "AICC",
        "AICC-EQ-TEST-26-1005",
        date(2026, 10, 5),
        [line(db, "RW-MC-03", swl_t="50.000")],
    )
    res = create_ec(api, db, "noura.qahtani", "ANIA-EXP", body)
    assert res.status_code == 422 and err_code(res) == "TPI_NOT_INDEPENDENT", res.text


def test_P4AC11_require_client_approved_tpi_impact(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    res = api.as_("faisal.harbi").patch(
        f"{API}/projects/{pid}/cert-settings", json={"require_client_approved_tpi": True}
    )
    assert res.status_code == 200, res.text
    impact = res.json()["client_approval_impact"]
    assert impact, res.text
    refs = {x["subject_ref"] for x in impact}
    assert "RW-MC-03" in refs
    assert {x["not_in_force_from"] for x in impact} == {"2026-10-13"}
    db.expire_all()
    eid = item(db, "RW-MC-03").id
    assert validity.current_line(db, eid, riyadh(2026, 10, 12), pid).ev.in_force
    assert not validity.current_line(db, eid, riyadh(2026, 10, 13), pid).ev.in_force


def test_P4AC12_suspended_tpi_from_the_suspension_day(api: Api, db: Session) -> None:
    t = tpi(db, "AICC")
    res = api.as_("faisal.harbi").post(
        f"{API}/tpis/{t.id}/transitions",
        json={"to_status": "suspended", "reason": "Accreditation body investigation (test)."},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    today = ec_body(db, "AICC", "AICC-EQ-TEST-26-1006", date(2026, 10, 6), [line(db, "SH-MEWP-12")])
    assert preview(api, db, "noura.qahtani", "ANIA-EXP", today)["tpi_reason"] == "TPI_SUSPENDED"
    res = create_ec(api, db, "noura.qahtani", "ANIA-EXP", today)
    assert res.status_code == 422 and "TPI_SUSPENDED" in res.text
    before = ec_body(
        db, "AICC", "AICC-EQ-TEST-26-1005", date(2026, 10, 5), [line(db, "SH-MEWP-12")]
    )
    assert preview(api, db, "noura.qahtani", "ANIA-EXP", before)["tpi_acceptable"] is True
    assert validity.current_line(db, item(db, "RW-MC-03").id, riyadh(2026, 10, 6, 11)).ev.in_force


# ---- equipment register and mobilisation (AC13-20) ----------------------------------------------


def eq_body(db: Session, owner: str, serial: str, **kw: Any) -> dict[str, Any]:
    return {
        "category": "mobile_crane",
        "manufacturer": "testlift",
        "model": "MC Test",
        "serial_no": serial,
        "year_of_manufacture": 2020,
        "owner_contractor_id": str(contractor(db, owner).id),
        "rated_capacity_t": "50.000",
        **kw,
    }


def test_P4AC13_duplicate_serial_in_and_out_of_scope(api: Api, db: Session) -> None:
    assert item(db, "RW-MC-03").serial_no == "TESTSN-MC-0003"
    res = api.as_("ahmed.zahrani").post(
        f"{API}/equipment", json=eq_body(db, "RAWABI", "testsn mc 0003")
    )
    assert res.status_code == 409 and err_code(res) == "EQUIPMENT_EXISTS", res.text
    assert item(db, "RW-MC-03").equipment_no in res.text
    res = api.as_("yousef.ghamdi").post(
        f"{API}/equipment", json=eq_body(db, "QIMMA", "TestSN/MC-0003")
    )
    assert res.status_code == 409 and err_code(res) == "EQUIPMENT_EXISTS_OUT_OF_SCOPE", res.text
    assert item(db, "RW-MC-03").equipment_no not in res.text


def test_P4AC14_blacklisted_serial_cannot_be_registered(api: Api, db: Session) -> None:
    body = eq_body(db, "SAHARA", "testsn-th-0202", category="telehandler", manufacturer="Other")
    res = api.as_("faisal.harbi").post(f"{API}/equipment", json=body)
    assert res.status_code == 409 and err_code(res) == "EQUIPMENT_BLACKLISTED", res.text


def test_P4AC15_vehicle_link_category_and_one_to_one(api: Api, db: Session) -> None:
    v = db.scalar(select(Vehicle).where(Vehicle.vehicle_no == "VEH-0003"))
    assert v is not None
    c = api.as_("faisal.harbi")
    fl = eq_body(db, "RAWABI", "TESTSN-FL-9001", category="forklift", rated_capacity_t="3.000",
                 vehicle_id=str(v.id))  # fmt: skip
    res = c.post(f"{API}/equipment", json=fl)
    assert res.status_code == 422 and err_code(res) == "CATEGORY_MISMATCH", res.text
    mc = eq_body(db, "RAWABI", "TESTSN-MC-9002", vehicle_id=str(v.id))
    res = c.post(f"{API}/equipment", json=mc)
    assert res.status_code == 422 and err_code(res) == "VEHICLE_ALREADY_LINKED", res.text


def test_P4AC16_gas_detectors_stay_in_the_detector_register(api: Api, db: Session) -> None:
    # Appendix A's GD-0007 is the Phase 3 seed's GD-ANIA-003 here.
    gd = db.scalar(select(GasDetector).where(GasDetector.detector_no == "GD-ANIA-003"))
    assert gd is not None
    body = eq_body(db, "RAWABI", gd.serial, category="pressure_vessel", rated_capacity_t=None,
                   subtype="air_receiver")  # fmt: skip
    res = api.as_("faisal.harbi").post(f"{API}/equipment", json=body)
    assert res.status_code == 422 and err_code(res) == "USE_DETECTOR_REGISTER", res.text


def _new_mobile_crane(api: Api, db: Session) -> tuple[str, str]:
    """Register a RAWABI mobile crane (no load chart) and deploy it on ANIA-EXP."""
    c = api.as_("faisal.harbi")
    res = c.post(
        f"{API}/equipment", json=eq_body(db, "RAWABI", "TESTSN-MC-7001", max_radius_m="40.00")
    )
    assert res.status_code in (200, 201), res.text
    eid = res.json()["id"]
    ref = dep(db, "RW-MC-03")
    pid = project(db, "ANIA-EXP").id
    res = c.post(
        f"{API}/projects/{pid}/equipment-deployments",
        json={"equipment_id": eid, "engagement_id": str(ref.engagement_id), "tag": "RW-MC-70",
              "site_ids": [str(s) for s in ref.site_ids], "planned_arrival_on": "2026-10-07"},
    )  # fmt: skip
    assert res.status_code in (200, 201), res.text
    return eid, res.json()["id"]


def test_P4AC17_first_certificate_needs_the_load_chart(api: Api, db: Session) -> None:
    eid, _ = _new_mobile_crane(api, db)
    db.expire_all()
    from app.models import EquipmentItem

    it = db.get(EquipmentItem, uuid.UUID(eid))
    assert it is not None
    ln = {"equipment_id": eid, "serial_as_printed": it.serial_no, "result": "pass",
          "swl_t": "50.000", "load_test": {"performed": True, "percent_of_swl": "110.0"}}  # fmt: skip
    body = ec_body(db, "AICC", "AICC-EQ-TEST-26-1007", date(2026, 10, 5), [ln],
                   inspection_type="initial")  # fmt: skip
    pv = preview(api, db, "noura.qahtani", "ANIA-EXP", body)
    errs = [e for x in pv["lines"] for e in x["errors"]]
    assert any(e["code"] == "ATTRIBUTE_REQUIRED" and "load_chart" in str(e) for e in errs), pv


def _transition_dep(api: Api, who: str, dep_id: Any, **body: Any) -> Any:
    return api.as_(who).post(f"{API}/equipment-deployments/{dep_id}/transitions", json=body)


def test_P4AC18_quarantined_item_cannot_be_approved(api: Api, db: Session) -> None:
    """DLIFT is Suspended in the Phase 0 seed, so its new deployment is put in Planned directly;
    EM-2 (item In Service) is checked before EQ-5 (contractor) at approval."""
    from sqlalchemy import inspect

    from app.core.cert_enums import EquipmentDeploymentStatus as Eds

    d = dep(db, "DL-MC-01")
    res = _transition_dep(api, "lina.haddad", d.id, to_status="demobilised")
    assert res.status_code == 200, res.text
    db.expire_all()
    cols = {a.key: getattr(d, a.key) for a in inspect(EquipmentDeployment).mapper.column_attrs}
    cols.update(id=uuid.uuid4(), deployment_no=d.deployment_no + "-N", seq=d.seq + 1000,
                status=Eds.planned, approved_at=None, approved_by_user_id=None, arrived_at=None,
                demobilised_on=None, arrival_inspection=None, arrival_inspection_passed=False,
                alerts_sent=[], status_reason=None)  # fmt: skip
    new = EquipmentDeployment(**cols)
    db.add(new)
    db.commit()
    res = _transition_dep(api, "lina.haddad", new.id, to_status="approved")
    assert res.status_code == 422 and err_code(res) == "EQUIPMENT_NOT_IN_SERVICE", res.text
    assert "certificate_expired" in res.text


def test_P4AC19_one_live_deployment_per_item(api: Api, db: Session) -> None:
    rbt = dep(db, "TC-01")
    res = api.as_("faisal.harbi").post(
        f"{API}/projects/{project(db, 'RBT-52').id}/equipment-deployments",
        json={"equipment_id": str(item(db, "RW-MC-03").id), "engagement_id": str(rbt.engagement_id),
              "tag": "MC-03X", "site_ids": [str(s) for s in rbt.site_ids],
              "planned_arrival_on": "2026-10-07"},
    )  # fmt: skip
    assert res.status_code == 422 and err_code(res) == "EQUIPMENT_DEPLOYED_ELSEWHERE", res.text


def test_P4AC20_tag_unique_case_insensitive(api: Api, db: Session) -> None:
    _new_mobile_crane(api, db)  # tag RW-MC-70 on ANIA-EXP
    c = api.as_("faisal.harbi")
    res = c.post(f"{API}/equipment", json=eq_body(db, "RAWABI", "TESTSN-MC-7002"))
    assert res.status_code in (200, 201), res.text
    ref = dep(db, "RW-MC-03")
    res = c.post(
        f"{API}/projects/{project(db, 'ANIA-EXP').id}/equipment-deployments",
        json={"equipment_id": res.json()["id"], "engagement_id": str(ref.engagement_id),
              "tag": "rw-mc-70", "site_ids": [str(s) for s in ref.site_ids],
              "planned_arrival_on": "2026-10-07"},
    )  # fmt: skip
    assert res.status_code == 409 and err_code(res) == "TAG_EXISTS", res.text


def test_tag_out_reason_visible_to_the_rep_but_ban_text_is_hse_only(api: Api, db: Session) -> None:
    it = item(db, "RW-MC-03")
    res = api.as_("noura.qahtani").post(
        f"{API}/equipment/{it.id}/tag-out",
        json={"project_id": str(project(db, "ANIA-EXP").id), "reason": "Hydraulic leak at boom",
              "physical_tag_applied": True},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    rep = api.as_("ahmed.zahrani").get(f"{API}/equipment/{it.id}").json()
    assert rep["service_status"] == "out_of_service"
    assert rep["service_status_text"] == "Hydraulic leak at boom"
    why = "Forged load test certificate found (test)."
    res = api.as_("faisal.harbi").post(
        f"{API}/equipment/{it.id}/blacklist", json={"reason_code": "other", "reason_text": why}
    )
    assert res.status_code == 200, res.text
    assert (
        api.as_("faisal.harbi").get(f"{API}/equipment/{it.id}").json()["service_status_text"] == why
    )
    assert (
        api.as_("ahmed.zahrani").get(f"{API}/equipment/{it.id}").json()["service_status_text"]
        is None
    )
