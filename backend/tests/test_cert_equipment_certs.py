"""4-third-party-cert §9 ACs 23-32, 36, 38-41 (equipment certificates and configuration)."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConfigurationEvent, EquipmentDefect, Notification, User
from app.services.cert import validity
from tests.cert_helpers import (
    API,
    ec_body,
    ec_submitted,
    ecert,
    err_code,
    item,
    line,
    project,
    riyadh,
    verify_body,
)
from tests.conftest import Api

pytestmark = pytest.mark.usefixtures("cert_seed", "clock")


def preview(
    api: Api, db: Session, pcode: str, body: dict[str, Any], who: str = "noura.qahtani"
) -> Any:
    pid = project(db, pcode).id
    res = api.as_(who).post(f"{API}/projects/{pid}/equipment-certificates/preview", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def create(
    api: Api, db: Session, pcode: str, body: dict[str, Any], who: str = "noura.qahtani"
) -> Any:
    pid = project(db, pcode).id
    return api.as_(who).post(f"{API}/projects/{pid}/equipment-certificates", json=body)


def codes(pv: dict[str, Any], key: str = "errors") -> list[str]:
    return [e["code"] for ln in pv["lines"] for e in ln[key]] + [e["code"] for e in pv[key]]


def validity_of(pv: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = pv["lines"][0]["validity"]
    return out


def test_P4AC23_Z1a_interval_shortens_printed_date(api: Api, db: Session) -> None:
    ic = validity.current_line(db, item(db, "SH-MEWP-12").id, riyadh(2026, 10, 6))
    assert ic.cert is not None and ic.cert.inspected_on == date(2026, 9, 2)
    assert ic.ev.valid_until == date(2027, 3, 1)
    assert ic.line is not None and ic.line.limiting_factor.value == "category_interval"
    body = ec_body(db, "AICC", "AICC-EQ-TEST-26-0902B", date(2026, 9, 2), [line(db, "SH-MEWP-12")],
                   printed_next_due=date(2027, 9, 1))  # fmt: skip
    pv = preview(api, db, "ANIA-EXP", body)
    v = validity_of(pv)
    assert (v["valid_until"], v["limiting_factor"]) == ("2027-03-01", "category_interval")
    assert "W01" in codes(pv, "warnings")


def test_P4AC24_Z1b_printed_next_due_limits_and_30_day_alert(db: Session) -> None:
    from app.cert_jobs import cert_alerts

    ic = validity.current_line(db, item(db, "RW-MC-03").id, riyadh(2026, 10, 6))
    assert ic.cert is not None and ic.cert.cert_no == "AICC-EQ-TEST-25-1106"
    assert ic.ev.valid_until == date(2026, 11, 5)
    assert ic.line is not None and ic.line.limiting_factor.value == "printed_next_due"
    cert_alerts(db)
    db.flush()

    def got(email: str) -> bool:
        uid = db.scalar(select(User.id).where(User.email == email))
        return (
            db.scalar(
                select(Notification.id).where(
                    Notification.user_id == uid,
                    Notification.title_en.like("%AICC-EQ-TEST-25-1106%"),
                )
            )
            is not None
        )

    assert got("ahmed.zahrani@example.com")
    assert not got("yousef.ghamdi@example.com")


def test_P4AC25_Z1c_forklift_interval_without_printed_date(api: Api, db: Session) -> None:
    body = ec_body(db, "AICC", "AICC-EQ-TEST-26-0831", date(2026, 8, 31), [line(db, "FX-FL-06")])
    v = validity_of(preview(api, db, "ANIA-EXP", body))
    assert (v["valid_until"], v["limiting_factor"]) == ("2027-08-30", "category_interval")


def test_P4AC26_Z1d_accessory_batch_lines(db: Session) -> None:
    c = ecert(db, "AICC-EQ-TEST-26-0914")
    from app.services.cert import equipment_certs as ecs

    lines = ecs.lines_of(db, c.id)
    assert len(lines) == 38
    assert {ln.valid_until for ln in lines} == {date(2027, 3, 13)}


def test_P4AC27_cert_no_unique_per_tpi(api: Api, db: Session) -> None:
    body = ec_body(db, "AICC", "AICC-EQ-TEST-26-0914", date(2026, 10, 1), [line(db, "FX-FL-06")])
    res = create(api, db, "ANIA-EXP", body)
    assert res.status_code == 409 and err_code(res) in ("CERT_EXISTS", "CERT_NO_REUSED"), res.text


def test_P4AC28_already_expired_and_historic(api: Api, db: Session) -> None:
    body = ec_body(db, "AICC", "AICC-EQ-TEST-25-0801", date(2025, 8, 1), [line(db, "SH-MEWP-12")])
    res = create(api, db, "ANIA-EXP", body)
    assert res.status_code == 422 and err_code(res) == "CERT_ALREADY_EXPIRED", res.text
    res = create(api, db, "ANIA-EXP", {**body, "historic": True})
    assert res.status_code in (200, 201), res.text
    cid = res.json()["id"]
    assert res.json()["status"] in ("historic", "draft")
    if res.json()["status"] == "draft":
        res = api.as_("noura.qahtani").post(
            f"{API}/equipment-certificates/{cid}/transitions", json={"to_status": "historic"}
        )
        assert res.status_code == 200, res.text
    db.expire_all()
    ic = validity.current_line(db, item(db, "SH-MEWP-12").id, riyadh(2026, 10, 6))
    assert ic.cert is not None and ic.cert.cert_no != "AICC-EQ-TEST-25-0801"
    assert ecert(db, "AICC-EQ-TEST-25-0801").status.value == "historic"


def test_P4AC29_serial_mismatch(api: Api, db: Session) -> None:
    body = ec_body(db, "AICC", "AICC-EQ-TEST-26-1001", date(2026, 10, 1),
                   [line(db, "RW-MC-03", serial_as_printed="TESTSN-MC-0030")])  # fmt: skip
    res = create(api, db, "ANIA-EXP", body)
    assert res.status_code == 422 and err_code(res) == "SERIAL_MISMATCH", res.text


def test_P4AC30_failed_line_out_of_service_and_a_defect(api: Api, db: Session) -> None:
    body = ec_body(db, "AICC", "AICC-EQ-TEST-26-1002", date(2026, 10, 5),
                   [line(db, "FX-TH-A024", result="fail")])  # fmt: skip
    cert = ec_submitted(api.as_("noura.qahtani"), db, "ANIA-EXP", body)
    res = api.as_("faisal.harbi").post(
        f"{API}/equipment-certificates/{cert['id']}/transitions", json={"to_status": "accepted"}
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    it = item(db, "FX-TH-A024")
    assert (it.service_status.value, it.service_status_reason.value) == (  # type: ignore[union-attr]
        "out_of_service",
        "failed_inspection",
    )
    ds = db.scalars(select(EquipmentDefect).where(EquipmentDefect.equipment_id == it.id)).all()
    assert [d.category.value for d in ds] == ["A"]


def test_P4AC31_load_test_required_on_initial_crane_line(api: Api, db: Session) -> None:
    def body(pct: str) -> dict[str, Any]:
        ln = line(db, "FX-MC-A001", load_test={"performed": True, "percent_of_swl": pct})
        return ec_body(db, "AICC", f"AICC-EQ-TEST-26-L{pct[:2]}", date(2026, 10, 5), [ln],
                       inspection_type="initial")  # fmt: skip

    assert "LOAD_TEST_REQUIRED" in codes(preview(api, db, "ANIA-EXP", body("95.0")))
    assert "LOAD_TEST_REQUIRED" not in codes(preview(api, db, "ANIA-EXP", body("110.0")))
    res = create(api, db, "ANIA-EXP", body("95.0"))
    assert res.status_code == 422 and err_code(res) == "LOAD_TEST_REQUIRED", res.text


def test_P4AC32_swl_above_rating(api: Api, db: Session) -> None:
    body = ec_body(db, "AICC", "AICC-EQ-TEST-26-1003", date(2026, 10, 5),
                   [line(db, "RW-MC-03", swl_t="55.000")])  # fmt: skip
    res = create(api, db, "ANIA-EXP", body)
    assert res.status_code == 422 and err_code(res) == "SWL_ABOVE_RATING", res.text


def test_P4AC36_reviewer_sod_and_rep_cannot_accept(api: Api, db: Session) -> None:
    body = ec_body(db, "AICC", "AICC-EQ-TEST-26-1004", date(2026, 10, 5), [line(db, "GP-FL-03")])
    cert = ec_submitted(api.as_("noura.qahtani"), db, "ANIA-EXP", body)
    url = f"{API}/equipment-certificates/{cert['id']}/transitions"
    res = api.as_("noura.qahtani").post(url, json={"to_status": "accepted"})
    assert res.status_code == 422 and err_code(res) == "SOD_CONFLICT", res.text
    res = api.as_("sanjay.verma").post(url, json={"to_status": "accepted"})
    assert res.status_code == 403, res.text


def _climb(db: Session) -> ConfigurationEvent:
    ev = db.scalar(
        select(ConfigurationEvent).where(ConfigurationEvent.equipment_id == item(db, "TC-01").id)
    )
    assert ev is not None
    return ev


def test_P4AC38_Z3_clearing_certificate_after_the_climb(api: Api, db: Session) -> None:
    ev = _climb(db)
    assert ev.occurred_at == datetime(2026, 9, 28, 11, 0, tzinfo=UTC)  # 14:00 Riyadh
    ln = line(db, "TC-01", configuration_ref="HUH 236.00 m, jib 60 m, 9 tie-ins",
              load_test={"performed": True, "percent_of_swl": "110.0"})  # fmt: skip
    body = ec_body(db, "NKTI", "NKTI-TEST-26-0927", date(2026, 9, 27), [ln],
                   inspection_type="after_configuration_change",
                   configuration_event_id=str(ev.id))  # fmt: skip
    res = create(api, db, "RBT-52", body, who="lina.haddad")
    assert res.status_code == 422 and err_code(res) == "INSPECTION_BEFORE_EVENT", res.text
    c = ecert(db, "NKTI-TEST-26-0929")
    assert c.accepted_at == datetime(2026, 9, 29, 12, 40, tzinfo=UTC)
    assert c.verified_at == datetime(2026, 9, 29, 13, 0, tzinfo=UTC)
    tc = item(db, "TC-01").id
    assert not validity.current_line(db, tc, datetime(2026, 9, 29, 12, 59, tzinfo=UTC)).ev.in_force
    ic = validity.current_line(db, tc, datetime(2026, 9, 29, 13, 0, tzinfo=UTC))
    assert ic.ev.in_force and ic.ev.valid_until == date(2027, 9, 28)


def test_P4AC39_backdated_configuration_event(api: Api, db: Session) -> None:
    res = api.as_("lina.haddad").post(
        f"{API}/equipment/{item(db, 'TC-01').id}/configuration-events",
        json={"project_id": str(project(db, "RBT-52").id), "event_type": "climb_jacking",
              "occurred_at": "2026-10-04T06:00:00Z", "new_configuration": "HUH 248.00 m"},
    )  # fmt: skip
    assert res.status_code == 422 and err_code(res) == "BACKDATED_EVENT", res.text


def test_P4AC40_configuration_mismatch_needs_the_reviewer_tick(api: Api, db: Session) -> None:
    tc = item(db, "TC-01")
    res = api.as_("lina.haddad").post(
        f"{API}/equipment/{tc.id}/configuration-events",
        json={"project_id": str(project(db, "RBT-52").id), "event_type": "climb_jacking",
              "occurred_at": "2026-10-06T06:30:00Z", "new_configuration": "HUH 248.00 m, 10 tie-ins"},
    )  # fmt: skip
    assert res.status_code in (200, 201), res.text
    ev_id = res.json()["id"]
    ln = line(db, "TC-01", configuration_ref="HUH 236.00 m, jib 60 m, 9 tie-ins",
              load_test={"performed": True, "percent_of_swl": "110.0"})  # fmt: skip
    body = ec_body(db, "NKTI", "NKTI-TEST-26-1006", date(2026, 10, 6), [ln],
                   inspection_type="after_configuration_change", configuration_event_id=ev_id)  # fmt: skip
    assert "CONFIGURATION_MISMATCH" in codes(
        preview(api, db, "RBT-52", body, "lina.haddad"), "warnings"
    )
    cert = ec_submitted(api.as_("lina.haddad"), db, "RBT-52", body)
    assert "CONFIGURATION_MISMATCH" in [w["code"] for w in cert["warnings"]]
    url = f"{API}/equipment-certificates/{cert['id']}/transitions"
    res = api.as_("faisal.harbi").post(url, json={"to_status": "accepted"})
    assert res.status_code == 422 and err_code(res) == "CONFIGURATION_MISMATCH", res.text
    res = api.as_("faisal.harbi").post(
        url, json={"to_status": "accepted", "configuration_mismatch_confirmed": True}
    )
    assert res.status_code == 200, res.text


def test_P4AC41_colour_scheme_disabled(api: Api, db: Session) -> None:
    for extra in ({}, {"colour_code": "red"}):
        body = ec_body(db, "AICC", "AICC-EQ-TEST-26-1008", date(2026, 10, 5),
                       [line(db, "FX-ACC-0219", **extra)])  # fmt: skip
        pv = preview(api, db, "ANIA-EXP", body)
        assert not [c for c in codes(pv) + codes(pv, "warnings") if "COLOUR" in c], pv
        assert not [
            e
            for ln in pv["lines"]
            for e in ln["errors"]
            if e.get("field", "").endswith("colour_code")
        ]


def test_full_review_and_verification_puts_a_certificate_in_force(api: Api, db: Session) -> None:
    body = ec_body(db, "AICC", "AICC-EQ-TEST-26-1009", date(2026, 10, 5), [line(db, "FX-FL-06")])
    cert = ec_submitted(api.as_("ahmed.zahrani"), db, "ANIA-EXP", body)
    url = f"{API}/equipment-certificates/{cert['id']}"
    assert (
        api.as_("faisal.harbi")
        .post(f"{url}/transitions", json={"to_status": "accepted"})
        .status_code
        == 200
    )
    n = api.as_("noura.qahtani")
    res = n.post(f"{url}/verifications", json=verify_body(n, "equipment", cert["id"]))
    assert res.status_code in (200, 201), res.text
    db.expire_all()
    ic = validity.current_line(db, item(db, "FX-FL-06").id, riyadh(2026, 10, 6, 12))
    assert ic.ev.in_force and ic.cert is not None and ic.cert.cert_no == "AICC-EQ-TEST-26-1009"
