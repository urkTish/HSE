"""Option 7b site vehicle & plant readiness (spec 7b-fleet-driver v2.0 §9, ACs 1-24; prototype).
All tests run on the 7b template (`sv_seed`: Phase 0-7a + the 7b Appendix A seed) with the clock
pinned to 2026-10-12 10:00 Asia/Riyadh (`sc_clock`)."""

from __future__ import annotations

import base64
import uuid
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.cert_enums import DefectCategory, DefectSource
from app.core.clock import set_now
from app.core.hse_enums import CaSourceType, KpiMetric
from app.models import (
    CorrectiveAction,
    DriverAuthorisation,
    EquipmentDefect,
    EquipmentItem,
    JourneyPlan,
    Notification,
    Vehicle,
    VehicleCheck,
    Worker,
)
from tests.cert_helpers import API, err_code, project, riyadh, worker

M = KpiMetric
PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa75\x81\x84"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
).decode()
TPL = {"light": ("VPL", 12), "heavy": ("VPH", 16), "plant": ("VPH", 16), "bus": ("VPB", 18)}

pytestmark = pytest.mark.usefixtures("sv_seed", "sc_clock")


# ---- helpers -------------------------------------------------------------------------------------


def pid(db: Session) -> str:
    return str(project(db, "ANIA-EXP").id)


def veh(db: Session, no: int) -> Vehicle:
    v = db.scalar(select(Vehicle).where(Vehicle.vehicle_no == f"VEH-0{no}"))
    assert v is not None, no
    return v


def driver_of(db: Session, no: int) -> uuid.UUID:
    """The regular (authorised) driver of a seeded site vehicle."""
    w = db.scalar(
        select(VehicleCheck.driver_worker_id)
        .where(VehicleCheck.vehicle_id == veh(db, no).id, VehicleCheck.driver_authorised)
        .order_by(VehicleCheck.check_date.desc())
        .limit(1)
    )
    assert w is not None, no
    return w


def unauthorised_driver(db: Session, no: int) -> uuid.UUID:
    w = db.scalar(
        select(VehicleCheck.driver_worker_id)
        .where(VehicleCheck.vehicle_id == veh(db, no).id, VehicleCheck.driver_authorised.is_(False))
        .limit(1)
    )
    assert w is not None, no
    return w


def answers(group: str, fail: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    prefix, n = TPL[group]
    out = []
    for i in range(1, n + 1):
        code = f"{prefix}-{i:02d}"
        bad = code in fail
        out.append(
            {
                "item_code": code,
                "answer": "non_compliant" if bad else "compliant",
                "note": "Brake pedal soft, stopping distance long" if bad else None,
            }
        )
    return out


def settings(api: Any, db: Session, **body: Any) -> None:
    res = api.as_("faisal.harbi").patch(
        f"{API}/projects/{pid(db)}/site-vehicle-settings", json=body
    )
    assert res.status_code == 200, res.text


def check(
    c: TestClient, db: Session, no: int, driver: uuid.UUID, fail: tuple[str, ...] = (), **kw: Any
) -> Any:
    v = veh(db, no)
    group = v.driver_group.value if v.driver_group else "light"
    body = {
        "vehicle_id": str(v.id),
        "driver_worker_id": str(driver),
        "answers": answers(group, fail),
        **kw,
    }
    return c.post(f"{API}/projects/{pid(db)}/pre-use-checks", json=body)


def kpi(c: TestClient, db: Session, metric: M, **params: Any) -> dict[str, Any]:
    res = c.get(
        f"{API}/kpi/site-vehicles",
        params={"project_id": pid(db), "metric": metric.value, **params},
    )
    assert res.status_code == 200, res.text
    out: dict[str, Any] = res.json()["metrics"][0]
    return out


def chips(m: dict[str, Any]) -> dict[str, str]:
    return {x["key"]: x["value"] for x in m["components"]}


def warn_codes(body: dict[str, Any]) -> list[str]:
    return [w["code"] for w in body.get("warnings", [])]


def free_worker(db: Session, eng: str) -> Worker:
    """A mobilised worker of `eng` on ANIA-EXP without any driver authorisation or 7b check."""
    from app.core.access_enums import DeploymentStatus
    from app.models import Contractor, Deployment, ProjectEngagement

    taken = select(DriverAuthorisation.worker_id).union(select(VehicleCheck.driver_worker_id))
    w = db.scalar(
        select(Worker)
        .join(Deployment, Deployment.worker_id == Worker.id)
        .join(ProjectEngagement, ProjectEngagement.id == Deployment.engagement_id)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(
            Contractor.short_code == eng,
            Deployment.project_id == project(db, "ANIA-EXP").id,
            Deployment.status == DeploymentStatus.mobilised,
            Worker.id.not_in(taken),
            Worker.id_expiry_date > date(2027, 6, 1),
        )
        .order_by(Worker.worker_no)
        .limit(1)
    )
    assert w is not None
    return w


def auth_body(w: Worker, **kw: Any) -> dict[str, Any]:
    return {
        "worker_id": str(w.id),
        "groups": ["light"],
        "licence_issuer": "ksa",
        "licence_class": "private",
        "licence_expiry": "2029-01-31",
        "assessment_date": "2026-10-05",
        "assessor": "Noura Al-Qahtani",
        "issued_on": "2026-10-12",
        **kw,
    }


def create_auth(c: TestClient, db: Session, body: dict[str, Any]) -> Any:
    return c.post(f"{API}/projects/{pid(db)}/driver-authorisations", json=body)


def activate(c: TestClient, auth_id: str) -> Any:
    return c.post(f"{API}/driver-authorisations/{auth_id}/transition", json={"to_status": "active"})


# ---- readiness (AC 1-6) --------------------------------------------------------------------------


class TestReadiness:
    def test_ac1_not_live(self, api: Any, db: Session) -> None:
        c = api.as_("faisal.harbi")
        rbt = project(db, "RBT-52").id
        for path in ("site-vehicles", "driver-authorisations", "pre-use-checks", "journey-plans"):
            res = c.get(f"{API}/projects/{rbt}/{path}")
            assert res.status_code == 422 and err_code(res) == "SITE_VEHICLES_NOT_LIVE", path
        # Phase 2 vehicles are unchanged (existing rows default to airside_only)
        res = c.get(f"{API}/projects/{pid(db)}/vehicles", params={"page_size": 100})
        assert res.status_code == 200, res.text
        old = [x for x in res.json()["items"] if x["vehicle_no"] < "VEH-0101"]
        assert old and all(x["site_scope"] == "airside_only" for x in old)

    def test_ac2_operating_card(self, api: Any, db: Session) -> None:
        from tests.conftest import Ids

        body = {
            "engagement_id": Ids(db).engagement("GULFPAVE"),
            "owner_type": "company",
            "category": "bus",
            "plate_type": "private",
            "plate_letters_ar": "ا ب ح",
            "plate_letters_en": "ABH",
            "plate_digits": "7301",
            "fleet_no": "GP-CB-30",
            "serial_or_vin": "JT7BTESTVN0000301",
            "make_model": "Toyota Coaster",
            "year": 2022,
            "insurance_policy_no": "TEST-POL-0301",
            "insurance_expiry": "2027-05-31",
            "istimara_expiry": "2027-05-31",
            "mvpi_expiry": "2027-05-31",
            "site_scope": "site",
            "use_class": "crew_bus",
            "seats": 30,
        }
        c = api.as_("noura.qahtani")
        res = c.post(f"{API}/projects/{pid(db)}/site-vehicles", json=body)
        assert res.status_code == 422 and err_code(res) == "OPERATING_CARD_REQUIRED", res.text
        body |= {"operating_card_no": "TEST-OC-0301", "operating_card_expiry": "2027-05-31"}
        res = c.post(f"{API}/projects/{pid(db)}/site-vehicles", json=body)
        assert res.status_code == 201, res.text
        out = res.json()
        assert out["driver_group"] == "bus" and out["vehicle_no"].startswith("VEH-")
        assert out["readiness"] == "ready" and "VEHICLE_DOCS_UNVERIFIED" in warn_codes(out)

    def test_ac3_doc_alerts_once(self, db: Session) -> None:
        from app.core.enums import NotificationKind
        from app.services.site_vehicle import common as c
        from app.site_vehicle_jobs import site_vehicle_daily

        v = veh(db, 107)
        assert v.insurance_expiry == date(2026, 10, 19)

        def titles() -> list[str]:
            return sorted(
                set(
                    db.scalars(
                        select(Notification.title_en).where(
                            Notification.kind == NotificationKind.site_vehicle_doc_expiry,
                            Notification.entity_id == v.id,
                        )
                    )
                )
            )

        assert titles() == []
        seen = []
        for day in (date(2026, 9, 19), date(2026, 10, 5), date(2026, 10, 12)):
            set_now(riyadh(day.year, day.month, day.day, 0, 30))
            site_vehicle_daily(db, day)
            site_vehicle_daily(db, day)  # second run of the day: nothing new
            seen.append(len(titles()))
        assert seen == [1, 2, 3]
        # officers get the 7-day alert, reps all three
        from app.models import User

        officer = db.scalar(select(User.id).where(User.email == "noura.qahtani@example.com"))
        n_officer = db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.entity_id == v.id, Notification.user_id == officer)
        )
        assert n_officer == 1
        assert c.readiness_on(v, date(2026, 10, 20), None, [])[0].value == "docs_expired"
        assert c.readiness_on(v, date(2026, 10, 19), None, [])[0].value == "ready"
        db.rollback()

    def test_ac4_rep_scope(self, api: Any, db: Session) -> None:
        from tests.conftest import Ids

        c = api.as_("ahmed.zahrani")
        res = c.get(f"{API}/projects/{pid(db)}/site-vehicles", params={"page_size": 100})
        assert res.status_code == 200, res.text
        engs = {x["engagement"]["short_code"] for x in res.json()["items"]}
        assert engs == {"RAWABI"} and res.json()["total"] == 10
        res = c.get(f"{API}/site-vehicles/{veh(db, 120).id}")
        assert res.status_code in (403, 404)
        base = {
            "owner_type": "company",
            "category": "pickup",
            "plate_type": "private",
            "plate_letters_ar": "د ر س",
            "plate_letters_en": "DRS",
            "plate_digits": "7302",
            "fleet_no": "RW-CP-30",
            "serial_or_vin": "JT7BTESTVN0000302",
            "make_model": "Toyota Hilux",
            "year": 2023,
            "insurance_policy_no": "TEST-POL-0302",
            "insurance_expiry": "2027-05-31",
            "istimara_expiry": "2027-05-31",
            "mvpi_expiry": "2027-05-31",
            "site_scope": "site",
            "use_class": "crew_pickup",
            "seats": 5,
        }
        res = c.post(
            f"{API}/projects/{pid(db)}/site-vehicles",
            json={**base, "engagement_id": Ids(db).engagement("NAJD")},
        )
        assert res.status_code == 403, res.text
        res = c.post(
            f"{API}/projects/{pid(db)}/site-vehicles",
            json={**base, "engagement_id": Ids(db).engagement("RAWABI")},
        )
        assert res.status_code == 201, res.text
        res = c.post(f"{API}/site-vehicles/{res.json()['id']}/verify-documents")
        assert res.status_code == 403, res.text
        res = api.as_("noura.qahtani").post(
            f"{API}/site-vehicles/{veh(db, 115).id}/verify-documents"
        )
        assert res.status_code == 200 and res.json()["docs_verified"], res.text

    def test_ac5_phase4_not_certified(self, api: Any, db: Session) -> None:
        from app.main import app

        v = veh(db, 119)
        item = db.scalar(select(EquipmentItem).where(EquipmentItem.vehicle_id == v.id))
        assert item is not None and item.equipment_no == "EQP-000206"
        res = api.as_("noura.qahtani").get(f"{API}/site-vehicles/{v.id}")
        assert res.status_code == 200, res.text
        out = res.json()
        assert out["readiness"] == "not_certified"
        assert out["phase4"]["equipment_no"] == "EQP-000206"
        assert out["phase4"]["service_status"] == "out_of_service"
        # no 7b endpoint writes Phase 4 rows
        spec = app.openapi()
        for path, ops in spec["paths"].items():
            for op in ops.values():
                if "site-vehicles" in op.get("tags", []):
                    assert "equipment" not in path and "defect" not in path, path

    def test_ac6_sw1(self, api: Any, db: Session) -> None:
        m = kpi(api.as_("faisal.harbi"), db, M.K138, period="day", anchor="2026-10-12")
        assert m["display"] == "82.6 %" and (m["numerator"], m["denominator"]) == ("19", "23")
        ch = chips(m)
        assert (
            ch["readiness:docs_expired"],
            ch["readiness:defect_hold"],
            ch["readiness:not_certified"],
            ch["readiness:idle"],
        ) == ("2", "1", "1", "1")
        s = api.as_("faisal.harbi").get(f"{API}/projects/{pid(db)}/site-vehicles/summary").json()
        assert s["site_vehicles"] == 24 and s["by_readiness"]["ready"] == 19


# ---- driver / operator authorisation (AC 7-12) ---------------------------------------------------


class TestAuthorisation:
    def test_ac7_licence_class(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        w = worker(db, "WKR-003370")
        res = create_auth(c, db, auth_body(w, groups=["light", "bus"]))
        assert res.status_code == 422 and err_code(res) == "LICENCE_CLASS_NOT_COVERING", res.text
        res = create_auth(
            c, db, auth_body(w, groups=["light", "bus"], licence_class="public_transport")
        )
        assert res.status_code == 201, res.text
        out = res.json()
        assert out["status"] == "draft" and out["auth_no"].startswith("DA-ANIA-EXP-")

    def test_ac8_assessment_too_old(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        res = create_auth(
            c, db, auth_body(free_worker(db, "GULFPAVE"), assessment_date="2025-09-11")
        )
        assert res.status_code == 422 and err_code(res) == "ASSESSMENT_TOO_OLD", res.text
        res = create_auth(
            c, db, auth_body(free_worker(db, "GULFPAVE"), assessment_date="2025-10-12")
        )
        assert res.status_code == 201, res.text

    def test_ac9_hook_policy(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        w = db.get(Worker, unauthorised_driver(db, 101))  # no DEF-DRV record
        assert w is not None
        settings(api, db, driver_hook_policy="block")
        res = create_auth(c, db, auth_body(w))
        assert res.status_code == 201, res.text
        aid = res.json()["id"]
        res = activate(c, aid)
        assert res.status_code == 422 and err_code(res) == "HOOK_NOT_MET", res.text
        settings(api, db, driver_hook_policy="warn")
        res = activate(c, aid)
        assert res.status_code == 200, res.text
        out = res.json()
        assert out["status"] == "active" and "HOOK_NOT_MET_WARN" in warn_codes(out)
        hooks = {h["code"]: h["result"] for h in out["hook_results"]}
        assert hooks["DEF-DRV"] != "met"

    def test_ac10_plant_operator_hook(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        w = free_worker(db, "NAJD")
        v = veh(db, 119)
        body = auth_body(
            w,
            groups=["plant"],
            licence_class="heavy_equipment",
            plant_vehicle_ids=[str(v.id)],
        )
        res = create_auth(c, db, body)
        assert res.status_code == 201, res.text
        aid = res.json()["id"]
        settings(api, db, driver_hook_policy="block")
        res = activate(c, aid)
        assert res.status_code == 422 and err_code(res) == "HOOK_NOT_MET", res.text
        settings(api, db, driver_hook_policy="warn")
        res = activate(c, aid)
        assert res.status_code == 200, res.text
        p4 = [h for h in res.json()["hook_results"] if h["kind"] == "personnel_certificate"]
        assert p4 and p4[0]["provider_status"] == "not_met" and p4[0]["vehicle_id"] == str(v.id)
        assert p4[0]["result"] == "warn"  # not met, recorded as a warning under policy warn
        assert "HOOK_NOT_MET_WARN" in warn_codes(res.json())

    def test_ac11_driver_fit_limits(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        w = worker(db, "WKR-003370")
        body = auth_body(w, groups=["light", "heavy"], licence_class="heavy_transport")
        res = create_auth(c, db, body)
        assert res.status_code == 201, res.text
        out = activate(c, res.json()["id"]).json()
        fit = next(h for h in out["hook_results"] if h["code"] == "DRIVER-FIT")
        assert fit["result"] == "met" and fit["valid_until"] == "2027-12-03"
        assert out["own_valid_until"] == "2028-10-11"
        assert out["effective_valid_until"] == "2027-12-03"
        assert out["limiting_factor"] == "medical"

    def test_ac12_site_engineer_status_only(self, api: Any, db: Session) -> None:
        res = api.as_("omar.siddiqui").get(
            f"{API}/projects/{pid(db)}/driver-authorisations", params={"page_size": 100}
        )
        assert res.status_code == 200, res.text
        items = res.json()["items"]
        assert items and all(x["redacted"] for x in items)
        for x in items:
            assert x["licence_class"] is None and x["licence_expiry"] is None
            assert x["hook_results"] == [] and x["assessor"] is None
        full = api.as_("noura.qahtani").get(f"{API}/driver-authorisations/{items[0]['id']}").json()
        assert not full["redacted"] and full["licence_class"] is not None


# ---- pre-use checks (AC 13-18) -------------------------------------------------------------------


class TestPreUse:
    def test_ac13_defect_hold_and_clear(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        v = veh(db, 101)
        drv = driver_of(db, 101)
        res = check(c, db, 101, drv, fail=("VPL-01",))
        assert res.status_code == 201, res.text
        out = res.json()
        assert not out["passed"] and out["hold_set"] and out["failed_items"] == ["VPL-01"]
        assert len(out["findings"]) == 1 and out["findings"][0]["ca_ref"]
        ca = db.scalars(
            select(CorrectiveAction).where(
                CorrectiveAction.source_type == CaSourceType.site_vehicle,
                CorrectiveAction.source_id == uuid.UUID(out["id"]),
            )
        ).all()
        assert len(ca) == 1
        assert c.get(f"{API}/site-vehicles/{v.id}").json()["readiness"] == "defect_hold"
        clear = {"repair_note": "Brake pads and fluid replaced by the RAWABI workshop"}
        res = c.post(f"{API}/site-vehicles/{v.id}/clear-hold", json=clear)
        assert res.status_code == 409 and err_code(res) == "VEHICLE_DEFECT_HOLD", res.text
        set_now(riyadh(2026, 10, 12, 11, 30))  # after the repair
        c = api.as_("noura.qahtani")  # fresh session after the clock jump
        res = check(c, db, 101, drv)  # re-check on the same day is allowed while on hold
        assert res.status_code == 201 and res.json()["passed"], res.text
        res = c.post(f"{API}/site-vehicles/{v.id}/clear-hold", json=clear)
        assert res.status_code == 200, res.text
        assert res.json()["readiness"] == "ready"

    def test_ac14_phase4_defect(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        v = veh(db, 119)
        res = check(c, db, 119, driver_of(db, 119), fail=("VPH-01",))
        assert res.status_code == 201, res.text
        out = res.json()
        assert not out["passed"] and not out["hold_set"]
        ch = db.get(VehicleCheck, uuid.UUID(out["id"]))
        assert ch is not None and ch.phase4_defect_id is not None
        d = db.get(EquipmentDefect, ch.phase4_defect_id)
        assert d is not None
        assert d.source == DefectSource.pre_use_check and d.category == DefectCategory.A
        item = db.scalar(select(EquipmentItem).where(EquipmentItem.vehicle_id == v.id))
        assert item is not None and item.service_status.value == "out_of_service"
        assert c.get(f"{API}/site-vehicles/{v.id}").json()["readiness"] == "not_certified"

    def test_ac15_duplicate(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        drv = driver_of(db, 104)
        assert check(c, db, 104, drv).status_code == 201
        res = check(c, db, 104, drv)
        assert res.status_code == 422 and err_code(res) == "PRE_USE_CHECK_EXISTS", res.text

    def test_ac16_driver_not_authorised(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        other = unauthorised_driver(db, 101)
        settings(api, db, driver_auth_policy="block")
        res = check(c, db, 101, other)
        assert res.status_code == 422 and err_code(res) == "DRIVER_NOT_AUTHORISED", res.text
        settings(api, db, driver_auth_policy="warn")
        res = check(c, db, 101, other)
        assert res.status_code == 201, res.text
        assert "DRIVER_NOT_AUTHORISED_WARN" in warn_codes(res.json())
        assert not res.json()["driver_authorised"]
        m = kpi(c, db, M.K139, period="day", anchor="2026-10-12")
        # seeded: VEH-0109 check + JP-0118 (both authorised) + this one
        assert (m["numerator"], m["denominator"]) == ("2", "3")

    def test_ac17_paper(self, api: Any, db: Session) -> None:
        c = api.as_("ahmed.zahrani")
        res = check(c, db, 111, driver_of(db, 111), source="paper")
        assert res.status_code == 422, res.text
        photo = {"file_name": "card.png", "content_base64": PNG}
        res = check(c, db, 111, driver_of(db, 111), source="paper", paper_photo=photo)
        assert res.status_code == 201, res.text
        assert res.json()["source"] == "paper" and res.json()["paper_photo_id"]
        m = kpi(c, db, M.K140, period="day", anchor="2026-10-12")
        assert chips(m)["paper"] == "1"
        sw2 = kpi(api.as_("faisal.harbi"), db, M.K140, period="day", anchor="2026-10-11")
        assert chips(sw2)["paper"] == "2"

    def test_ac18_sw2_sw3(self, api: Any, db: Session) -> None:
        c = api.as_("faisal.harbi")
        k140 = kpi(c, db, M.K140, period="day", anchor="2026-10-11")
        assert k140["display"] == "87.0 %" and (k140["numerator"], k140["denominator"]) == (
            "20",
            "23",
        )
        assert kpi(c, db, M.K140, period="day", anchor="2026-10-09")["display"] == "—"
        k139 = kpi(c, db, M.K139, period="month", anchor="2026-09-15")
        assert k139["display"] == "97.1 %"
        assert (k139["numerator"], k139["denominator"]) == ("400", "412")
        assert chips(k139) == {"pre_use_checks": "398", "journey_plans": "14"}
        res = c.get(
            f"{API}/projects/{pid(db)}/pre-use-checks/missing", params={"day": "2026-10-11"}
        )
        assert res.status_code == 200, res.text
        miss = res.json()
        assert (miss["required"], miss["completed"]) == (23, 20)
        assert sorted(x["vehicle"]["vehicle_no"] for x in miss["items"]) == [
            "VEH-0113",
            "VEH-0122",
            "VEH-0124",
        ]


# ---- journey plans (AC 19-21) --------------------------------------------------------------------


def plan_body(
    db: Session, no: int, km: int, dep: tuple[int, int], arr: tuple[int, int], **kw: Any
) -> dict[str, Any]:
    from tests.conftest import Ids

    return {
        "vehicle_id": str(veh(db, no).id),
        "driver_worker_id": str(driver_of(db, no)),
        "passengers": 3,
        "origin": "ANIA-EXP site",
        "destination": "Quarry Q3",
        "distance_km": km,
        "planned_depart": riyadh(2026, 10, 13, *dep).isoformat(),
        "planned_arrive": riyadh(2026, 10, 13, *arr).isoformat(),
        "contact_user_id": Ids(db).user("noura.qahtani"),
        **kw,
    }


class TestJourney:
    def test_ac19_hint(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        cases = [(160, (9, 0), (11, 30), True), (40, (4, 30), (5, 30), True),
                 (40, (9, 0), (10, 0), False)]  # fmt: skip
        for km, dep, arr, rec in cases:
            b = plan_body(db, 105, km, dep, arr)
            h = c.post(
                f"{API}/projects/{pid(db)}/journey-plans/hint",
                json={k: b[k] for k in ("distance_km", "planned_depart", "planned_arrive")},
            )
            assert h.status_code == 200 and h.json()["recommended"] is rec, (km, h.text)
            res = c.post(f"{API}/projects/{pid(db)}/journey-plans", json=b)
            assert res.status_code == 201, res.text
            assert res.json()["hint_recommended"] is rec
            assert ("JOURNEY_PLAN_RECOMMENDED" in warn_codes(res.json())) is rec

    def test_ac20_errors(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        url = f"{API}/projects/{pid(db)}/journey-plans"
        res = c.post(url, json=plan_body(db, 109, 40, (9, 0), (10, 0)))
        assert res.status_code == 409 and err_code(res) == "VEHICLE_NOT_READY", res.text
        res = c.post(url, json=plan_body(db, 120, 40, (9, 0), (10, 0), passengers=5))
        assert res.status_code == 422 and err_code(res) == "PASSENGERS_EXCEED_SEATS", res.text
        assert (
            c.post(url, json=plan_body(db, 120, 40, (9, 0), (10, 0), passengers=4)).status_code
            == 201
        )
        ramesh = worker(db, "WKR-000026")
        assert ramesh.user_id is not None
        b = plan_body(db, 120, 40, (11, 0), (12, 0), driver_worker_id=str(ramesh.id),
                      contact_user_id=str(ramesh.user_id))  # fmt: skip
        res = c.post(url, json=b)
        assert res.status_code == 422 and err_code(res) == "JOURNEY_CONTACT_IS_DRIVER", res.text

    def test_ac21_overdue_flag(self, api: Any, db: Session) -> None:
        c = api.as_("noura.qahtani")
        j = db.scalar(select(JourneyPlan).where(JourneyPlan.plan_no == "JP-ANIA-EXP-2026-0118"))
        assert j is not None and j.status.value == "planned"
        n0 = db.scalar(select(func.count()).select_from(Notification))
        set_now(riyadh(2026, 10, 12, 8, 59))
        assert not c.get(f"{API}/journey-plans/{j.id}").json()["overdue"]
        set_now(riyadh(2026, 10, 12, 9, 1))
        rows = c.get(f"{API}/projects/{pid(db)}/journey-plans", params={"status": "planned"})
        assert rows.status_code == 200, rows.text
        row = next(x for x in rows.json()["items"] if x["plan_no"] == j.plan_no)
        assert row["overdue"]
        from app.site_vehicle_jobs import site_vehicle_daily

        site_vehicle_daily(db, date(2026, 10, 12))
        db.commit()
        assert not db.scalar(
            select(func.count()).select_from(Notification).where(Notification.entity_id == j.id)
        )
        assert db.scalar(select(func.count()).select_from(Notification)) >= n0
        res = c.post(f"{API}/journey-plans/{j.id}/arrive", json={})
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "arrived" and not res.json()["overdue"]


# ---- scope, PDPL, schema, i18n (AC 22-24) --------------------------------------------------------


class TestScope:
    def test_ac22_viewer_aggregates(self, api: Any, db: Session) -> None:
        c = api.as_("sarah.mitchell")
        res = c.get(
            f"{API}/kpi/site-vehicles", params={"project_id": pid(db), "group_by": "contractor"}
        )
        assert res.status_code == 200, res.text
        assert [m["metric"] for m in res.json()["metrics"]] == ["K-138", "K-139", "K-140"]
        assert res.json()["breakdowns"]
        for path in ("site-vehicles", "driver-authorisations", "pre-use-checks", "journey-plans"):
            assert c.get(f"{API}/projects/{pid(db)}/{path}").status_code == 403, path
        assert c.get(f"{API}/projects/{pid(db)}/site-vehicles/summary").status_code == 200
        from app.ai.tools import ToolContext, run
        from tests.cert_helpers import P

        ctx = ToolContext(db=db, p=P(db, "sarah.mitchell"), project=project(db, "ANIA-EXP"),
                          as_of=date(2026, 10, 12))  # fmt: skip
        text = ""
        for eng in ("GULFPAVE", "RAWABI", "NAJD"):
            text += str(
                run(
                    ctx,
                    "get_kpis",
                    {
                        "project_codes": ["ANIA-EXP"],
                        "metrics": ["K-140"],
                        "period": {"preset": "custom", "start": "2026-10-11", "end": "2026-10-11"},
                        "filters": {"contractor_codes": [eng]},
                    },
                )
            )
        assert "K-140" in text and "%" in text
        plates = [
            v.plate_digits
            for v in db.scalars(select(Vehicle).where(Vehicle.plate_digits.is_not(None)))
        ]
        for secret in [*plates, "Jomar", "VEH-01"]:
            assert secret and secret not in text, secret

    def test_ac23_schema_and_additive(self, db: Session) -> None:
        from app.core import access_enums
        from app.seed_site_vehicle import seed_site_vehicle_data

        tables = inspect(db.get_bind()).get_table_names()
        for bad in ("telematic", "mileage", "driver_point", "penalty_point", "gps", "odometer"):
            assert not [t for t in tables if bad in t], bad
        reasons = (
            [m.value for m in access_enums.GateReasonCode]
            if hasattr(access_enums, "GateReasonCode")
            else []
        )
        assert not [r for r in reasons if "SITE_VEH" in r or "PRE_USE" in r or "DRIVER_AUTH" in r]
        # 7b rows are fake; the only earlier row touched is FX-EX-11's vehicle link
        assert not db.scalar(
            select(func.count()).select_from(VehicleCheck).where(VehicleCheck.seed_fake.is_(False))
        )
        linked = db.scalars(
            select(EquipmentItem.equipment_no).where(EquipmentItem.vehicle_id.is_not(None))
        ).all()
        assert "EQP-000206" in linked
        n = db.scalar(select(func.count()).select_from(VehicleCheck))
        seed_site_vehicle_data(db)  # a second run is a no-op
        assert db.scalar(select(func.count()).select_from(VehicleCheck)) == n
        # Phase 2 rows keep airside_only and no readiness
        old = db.scalars(select(Vehicle).where(Vehicle.vehicle_no < "VEH-0101")).all()
        assert old and all(v.site_scope.value == "airside_only" for v in old)

    def test_ac23_phase4_kpis_unchanged_by_link(self, db: Session) -> None:
        """The SV-3 link does not move any Phase 4 KPI (D-251)."""
        from app.api.kpi_params import KpiQuery
        from app.core.hse_enums import PeriodPreset
        from app.kpi import scope as kscope
        from tests.cert_helpers import P

        def values() -> list[Any]:
            q = KpiQuery(project_ids=[project(db, "ANIA-EXP").id], all_projects=False,
                         site_ids=[], zone_ids=[], zone_type=None, engagement_ids=[],
                         include_subcontractors=True, tiers=[], period=PeriodPreset.month,
                         anchor=date(2026, 10, 12), start=None, end=None, as_of=None)  # fmt: skip
            s = kscope.build(db, P(db, "faisal.harbi"), q)
            ms = [M.K72, M.K73, M.K74, M.K75, M.K78, M.K80]
            return [r.value for r in s.engine.results(ms, s.window)]

        with_link = values()
        item = db.scalar(select(EquipmentItem).where(EquipmentItem.equipment_no == "EQP-000206"))
        assert item is not None
        item.vehicle_id = None
        db.flush()
        assert values() == with_link
        db.rollback()

    def test_ac24_arabic(self, api: Any, db: Session) -> None:
        from app.core.errors import ErrorCode
        from app.services.site_vehicle import reference as ref

        res = api.as_("noura.qahtani").get(f"{API}/site-vehicles/reference")
        assert res.status_code == 200, res.text
        body = res.json()
        for key, val in body.items():
            rows = val if isinstance(val, list) else [val]
            for r in rows:
                if isinstance(r, dict) and "label_en" in r:
                    assert r["label_ar"] and r["label_ar"] != r["label_en"], (key, r)
        assert body["prototype_badge"]["label_ar"] == ref.PROTOTYPE[1]
        codes = [
            "SITE_VEHICLES_NOT_LIVE", "OPERATING_CARD_REQUIRED", "LICENCE_CLASS_NOT_COVERING",
            "ASSESSMENT_TOO_OLD", "HOOK_NOT_MET", "VEHICLE_DEFECT_HOLD", "PRE_USE_CHECK_EXISTS",
            "DRIVER_NOT_AUTHORISED", "VEHICLE_NOT_READY", "PASSENGERS_EXCEED_SEATS",
            "JOURNEY_CONTACT_IS_DRIVER",
        ]  # fmt: skip
        for code in codes:
            assert ErrorCode(code)
        # an error carries Arabic text; plates and refs stay ASCII / LTR in the Arabic title
        res = api.as_("noura.qahtani").post(
            f"{API}/projects/{pid(db)}/journey-plans", json=plan_body(db, 109, 40, (9, 0), (10, 0))
        )
        assert res.json().get("message_ar") or res.json().get("detail", {}).get("message_ar")
        from app.core.enums import NotificationKind

        res = check(api.as_("noura.qahtani"), db, 102, driver_of(db, 102), fail=("VPL-01",))
        assert res.status_code == 201, res.text
        n = db.scalars(
            select(Notification).where(Notification.kind == NotificationKind.vehicle_defect_hold)
        ).first()
        assert n is not None and "VEH-0102" in n.title_ar and n.title_ar != n.title_en
