"""Option 7a vehicle accident details (spec 7a-vehicle-accident-details v1.1 §9, ACs 1-31 that the
backend can test). Section rules run on the Phase 2 world (`access_seed`, clock 2026-10-06), 6f
rules on the 6f world (`fu_seed`), the seed / KPI / AI / export ACs on the 7a template
(`veh_seed`, clock 2026-10-12 10:00 Riyadh)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import LicenceClass, LicenceIssuer
from app.core.hse_enums import AttachmentOwner, KpiMetric
from app.core.vehicle_enums import (
    VehCategory,
    VehDriverKind,
    VehLicenceCheck,
    VehOwnership,
    VehRoadType,
    VehRole,
    VehSeatBelt,
)
from app.kpi.engine import Engine, EngineConfig
from app.kpi.facts import Facts, Filter, VehFact, WfFact
from app.kpi.periods import Window
from app.models import Attachment, Incident, IncidentVehicle, Vehicle
from app.schemas.incidents import (
    IncidentCreate,
    IncidentTransitionRequest,
    IncidentUpdate,
    InjuryCaseCreate,
    InjuryCaseUpdate,
)
from app.schemas.vehicle import (
    VehAccidentReportUpdate,
    VehIncidentVehicleCreate,
    VehIncidentVehicleUpdate,
)
from app.services import attachments as att
from app.services import incident_vehicles as veh
from app.services import incidents as inc_svc
from app.services import injury_cases as cases_svc
from app.services import vehicle_rules as rules
from tests.cert_helpers import P, expect, project, worker
from tests.heat_helpers import eng, zone

M = KpiMetric
PDF = b"%PDF-1.4\n% TEST report\n%%EOF\n"


# ---- pure rules and the VW1 worked example ----------------------------------------------------


def _vf(
    i: int,
    road: str,
    types: set[str],
    *,
    company: bool = True,
    rnc: bool = False,
    primary: str | None = None,
    eng_id: uuid.UUID | None = None,
) -> VehFact:
    return VehFact(
        id=uuid.UUID(int=500 + i),
        ref=f"INC-ANIA-EXP-2026-{i:04d}",
        d=date(2026, 9, 10 + i % 15),
        eng=eng_id or uuid.UUID(int=13),
        site=uuid.UUID(int=1),
        zone=None,
        types=frozenset(types),
        primary=primary or sorted(types)[0],
        road_type=road,
        rnc=rnc,
        work_related=not rnc,
        company=company,
    )


def _vw1_engine() -> Engine:
    """VW1: ANIA-EXP September 2026, MH = 1,240,000 h (unit fixture)."""
    f = Facts(project_start=date(2025, 3, 1))
    f.wf = [
        WfFact(
            date(2026, 9, 15), uuid.UUID(int=13), uuid.UUID(int=1), None, Decimal(1_240_000), 5000
        )
    ]
    f.vehicles = [
        _vf(201, "public_road", {"injury_illness"}),  # contractor pickup, MTC
        _vf(204, "site_road", {"near_miss"}),  # near miss, contractor tipper
        _vf(209, "airside", {"property_damage"}),  # GSE damage, contractor
        _vf(212, "public_road", {"injury_illness"}, company=False, rnc=True),  # commuting own
        _vf(215, "public_road", {"injury_illness"}, rnc=True),  # company bus commuting
    ]
    f.sort()
    return Engine(f, Filter(), date(2026, 9, 30), EngineConfig())


def test_vw1_k136_k137_ac25_ac26() -> None:
    e = _vw1_engine()
    w = Window(date(2026, 9, 1), date(2026, 9, 30))
    k136, k137 = e.results([M.K136, M.K137], w)
    assert k136.value == 5
    chips = {c.key: c.value for c in k136.components}
    assert chips["road_type:public_road"] == 3
    assert chips["road_type:site_road"] == 1
    assert chips["road_type:airside"] == 1
    assert chips["with_injury"] == 3
    assert chips["recorded_not_counted"] == 2
    assert k137.value is not None and round(k137.value, 2) == Decimal("0.32")
    assert k137.numerator == 2
    # AC26: K-137 ignores include_commuting_in_rates (the engine has no input for it, VA-13)
    assert sorted(e.sources(M.K137, w)[0][1]) == [uuid.UUID(int=701), uuid.UUID(int=709)]


def test_rules_va3_va6() -> None:
    occurred = date(2026, 9, 21)
    lc = rules.licence_check
    w = VehDriverKind.worker
    assert lc(w, LicenceClass.private, date(2028, 1, 1), VehCategory.tipper, occurred) == (
        VehLicenceCheck.wrong_class
    )
    assert lc(w, LicenceClass.heavy_transport, date(2026, 9, 1), VehCategory.tipper, occurred) == (
        VehLicenceCheck.expired
    )
    assert lc(w, None, None, VehCategory.pickup, occurred) == VehLicenceCheck.no_licence
    assert lc(VehDriverKind.external, None, None, VehCategory.pickup, occurred) == (
        VehLicenceCheck.not_checked
    )
    assert lc(w, None, date(2028, 1, 1), VehCategory.other, occurred, ["other"]) == (
        VehLicenceCheck.valid
    )
    assert rules.plate_key("ح ط ر", None, "9012") == rules.plate_key(None, "jtr", "9012")
    assert rules.speed_band(72).value == "60_89"


# ---- section rules (Phase 2 world) ------------------------------------------------------------


def _create(db: Session, who: str = "noura.qahtani", **over: Any) -> Any:
    pr = project(db, "ANIA-EXP")
    from app.models import Site

    site = db.scalar(select(Site).where(Site.code == over.pop("site", "S-LAND")))
    assert site is not None
    body: dict[str, Any] = {
        "site_id": site.id,
        "responsible_engagement_id": eng(db, "ANIA-EXP", "GULFPAVE").id,
        "occurred_at": datetime(2026, 10, 5, 5, 0, tzinfo=UTC),
        "shift": "day",
        "incident_types": ["near_miss"],
        "primary_type": "near_miss",
        "title": "Vehicle near miss (TEST)",
        "description": "Pickup braked hard to avoid a pedestrian.",
        "immediate_actions": "Area barricaded",
        "activity": "driving_transport",
        "actual_severity": 1,
        "potential_severity": 3,
    }
    body.update(over)
    return inc_svc.create(db, P(db, who), pr.id, IncidentCreate.model_validate(body))


def _case(db: Session, incident_id: uuid.UUID, **over: Any) -> Any:
    body: dict[str, Any] = {
        "person_type": "contractor_worker",
        "employer_engagement_id": str(eng(db, "ANIA-EXP", "GULFPAVE").id),
        "person_name": "Test Person (seed-fake)",
        "id_type": "iqama",
        "id_number": "2999999901",
        "trade": "driver",
        "body_part": "neck",
        "nature": "sprain_strain",
        "mechanism": "vehicle_plant_collision",
        "agency": "light_vehicle",
        "treatments": ["prescription_medication"],
        "treated_at": "hospital_outpatient",
    }
    body.update(over)
    return cases_svc.create(
        db, P(db, "noura.qahtani"), incident_id, InjuryCaseCreate.model_validate(body)
    )


def _row(db: Session, incident_id: uuid.UUID, who: str = "noura.qahtani", **kw: Any) -> Any:
    body: dict[str, Any] = {"ownership": "contractor", "role": "striking"}
    body.update(kw)
    return veh.create_row(
        db, P(db, who), incident_id, VehIncidentVehicleCreate.model_validate(body)
    )


def _to(db: Session, incident_id: uuid.UUID, to: str, who: str = "noura.qahtani", **kw: Any) -> Any:
    return inc_svc.transition(
        db,
        P(db, who),
        incident_id,
        IncidentTransitionRequest.model_validate({"to_status": to, **kw}),
    )


@pytest.mark.usefixtures("access_seed", "clock")
class TestSection:
    def test_ac1_signal_locks(self, db: Session) -> None:
        inc = _create(db, incident_types=["injury_illness"], primary_type="injury_illness")
        assert inc.vehicle_involved is False
        _case(db, inc.id)
        read = inc_svc.read(db, P(db, "noura.qahtani"), inc.id)
        assert read.vehicle_involved is True
        assert read.vehicle_section is not None and read.vehicle_section.vehicle_involved_locked
        expect(
            "VEHICLE_INVOLVED_LOCKED",
            lambda: inc_svc.update(
                db, P(db, "noura.qahtani"), inc.id, IncidentUpdate(vehicle_involved=False)
            ),
            422,
        )

    def test_ac2_ac3_ac4_submit_and_zone(self, db: Session) -> None:
        inc = _create(db, vehicle_involved=True)  # AC2: near miss marked manually
        assert inc.vehicle_involved and inc.vehicle_section is not None
        err = expect("VEHICLE_SECTION_INCOMPLETE", lambda: _to(db, inc.id, "reported"), 422)
        assert err.meta and "road_type" in err.meta["missing"]
        noura = P(db, "noura.qahtani")
        inc_svc.update(db, noura, inc.id, IncidentUpdate(road_type=VehRoadType.site_road))
        expect("VEHICLE_REQUIRED", lambda: _to(db, inc.id, "reported"), 422)
        _row(db, inc.id)
        assert _to(db, inc.id, "reported").status.value == "reported"
        # AC4: airside on a landside zone
        expect(
            "ROAD_TYPE_ZONE_MISMATCH",
            lambda: inc_svc.update(
                db,
                noura,
                inc.id,
                IncidentUpdate(zone_id=zone(db, "Z-PIERB").id, road_type=VehRoadType.airside),
            ),
            422,
        )

    def test_ac5_ac6_register_vehicle_docs(self, db: Session) -> None:
        v = db.scalar(select(Vehicle).where(Vehicle.vehicle_no == "VEH-0002"))
        assert v is not None
        inc = _create(db, vehicle_involved=True, road_type="site_road")
        r = _row(db, inc.id, vehicle_id=str(v.id))
        assert (r.plate_digits, r.plate_letters_en, r.category) == (
            "9012",
            "JTR",
            VehCategory.pickup,
        )
        assert r.make_model and r.docs_valid_at_time.source == "register"
        assert r.docs_valid_at_time.insurance.value == "valid" and not r.warnings
        v.insurance_expiry = date(2026, 9, 30)  # expired before the occurred date
        db.flush()
        r = veh.update_row(
            db, P(db, "noura.qahtani"), r.id, VehIncidentVehicleUpdate(damage="minor")
        )
        assert r.docs_valid_at_time.insurance.value == "expired"
        assert [w.code for w in r.warnings] == ["VEHICLE_DOCS_EXPIRED_AT_TIME"]
        section = inc_svc.read(db, P(db, "noura.qahtani"), inc.id).vehicle_section
        assert section is not None
        assert [p.code for p in section.investigation_prompts] == ["VEHICLE_DOCS_EXPIRED_AT_TIME"]
        from app.models import Notification

        assert db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.kind == "vehicle_docs_not_valid")
        )

    def test_ac7_ac8_ac9_licence(self, db: Session) -> None:
        inc = _create(
            db,
            vehicle_involved=True,
            road_type="site_road",
            responsible_engagement_id=eng(db, "ANIA-EXP", "RAWABI").id,
        )
        drv = worker(db, "WKR-001006")
        r = _row(
            db,
            inc.id,
            category="tipper",
            driver_kind="worker",
            worker_id=str(drv.id),
            licence_issuer="ksa",
            licence_class="private",
            licence_expiry="2028-05-31",
        )
        assert r.licence_check == VehLicenceCheck.wrong_class
        assert [w.code for w in r.warnings] == ["LICENCE_NOT_VALID_AT_TIME"]
        r = veh.update_row(
            db,
            P(db, "noura.qahtani"),
            r.id,
            VehIncidentVehicleUpdate(
                licence_class=LicenceClass.heavy_transport, licence_expiry=date(2026, 9, 1)
            ),
        )
        assert r.licence_check == VehLicenceCheck.expired
        expect(
            "VALIDATION_ERROR",
            lambda: veh.update_row(
                db, P(db, "noura.qahtani"), r.id, VehIncidentVehicleUpdate(licence_no="1234567890")
            ),
        )
        # AC8: ADP prefill (no KSA licence number field)
        jomar = worker(db, "WKR-000003")
        pre = veh.prefill(db, P(db, "noura.qahtani"), inc.id, None, None, None, None, jomar.id)
        assert pre.driver is not None and pre.driver.has_adp
        assert pre.driver.licence_class is not None
        assert pre.driver.licence_number_field is (pre.driver.licence_issuer != LicenceIssuer.ksa)
        r2 = _row(db, inc.id, category="pickup", driver_kind="worker", worker_id=str(jomar.id))
        assert r2.licence_prefilled_from_adp and r2.licence_class == pre.driver.licence_class
        # AC9: external driver without licence data
        r3 = _row(
            db,
            inc.id,
            ownership="third_party",
            role="struck",
            category="private_car",
            driver_kind="external",
            external_driver_name="Test External",
        )
        assert r3.licence_check == VehLicenceCheck.not_checked

    def test_ac10_plate_registered(self, db: Session) -> None:
        inc = _create(db, vehicle_involved=True, road_type="public_road")
        for ar, en in (("ح ط ر", None), (None, "JTR")):
            expect(
                "PLATE_IS_REGISTERED",
                lambda ar=ar, en=en: _row(
                    db,
                    inc.id,
                    ownership="third_party",
                    role="struck",
                    plate_type="private",
                    plate_letters_ar=ar,
                    plate_letters_en=en,
                    plate_digits="9012",
                ),
                422,
            )
        own = _row(db, inc.id, plate_type="private", plate_letters_en="JTR", plate_digits="9012")
        assert own.suggested_vehicle is not None and own.suggested_vehicle.vehicle_no == "VEH-0002"

    def test_ac11_ac12_ac13_ac14_ac24_report_archive(self, db: Session) -> None:
        expect(
            "ACCIDENT_REPORT_AUTHORITY_REQUIRED",
            lambda: _create(
                db, vehicle_involved=True, road_type="public_road", report_authority="none_internal"
            ),
            422,
        )
        inc = _create(
            db,
            vehicle_involved=True,
            road_type="public_road",
            road_location="Airport Rd km 3",
            journey_purpose="work_task",
            report_authority="najm",
            incident_types=["property_damage"],
            primary_type="property_damage",
            property_damage={"asset_type": "vehicle", "estimated_cost_sar": "4500"},
        )
        _row(
            db,
            inc.id,
            engagement_id=str(eng(db, "ANIA-EXP", "GULFPAVE").id),
            plate_type="private",
            plate_letters_en="TST",
            plate_digits="1111",
            category="pickup",
            damage="minor",
            seat_belt="worn",
            driver_kind="external",
            external_driver_name="Test Contract Driver",
        )
        _to(db, inc.id, "reported")
        err = expect(
            "ACCIDENT_REPORT_MISSING",
            lambda: _to(db, inc.id, "closed", who="faisal.harbi", reason="Quick close (TEST)"),
            422,
        )
        assert err.meta == {"missing": ["report_no", "report_date", "report_files"]}
        noura = P(db, "noura.qahtani")
        veh.put_report(
            db,
            noura,
            inc.id,
            VehAccidentReportUpdate(
                report_no="NJM-TEST-2026-09999", report_date=date(2026, 10, 5), liability_pct_own=50
            ),
        )
        first = veh.upload_file(db, noura, inc.id, "NJM-TEST.pdf", PDF, None).files[0]
        assert (
            _to(db, inc.id, "closed", who="faisal.harbi", reason="Quick close (TEST)").status.value
            == "closed"
        )
        # AC13: after Closed, a corrected file supersedes; nothing can be deleted
        rep = veh.upload_file(db, noura, inc.id, "NJM-TEST-v2.pdf", PDF, first.id)
        assert rep.locked and rep.file_count == 1 and len(rep.files) == 2
        old = next(f for f in rep.files if f.id == first.id)
        assert old.superseded and old.superseded_by_id is not None
        for f in rep.files:
            expect("ACCIDENT_REPORT_LOCKED", lambda f=f: att.delete(db, noura, f.id), 409)
        # AC14 / AC24: the viewer sees number and date, not the files (403 on the file URL)
        sarah = P(db, "sarah.mitchell")
        seen = veh.get_report(db, sarah, inc.id)
        assert seen.report_no == "NJM-TEST-2026-09999" and not seen.files_visible and not seen.files
        expect("FORBIDDEN", lambda: att.signed_url(db, sarah, first.id), 403)
        assert veh.get_report(db, noura, inc.id).files_visible
        # VA-15: the report raised no client notification
        from app.models import Notification

        clients = db.scalars(select(Notification).where(Notification.entity_id == inc.id))
        assert not [
            n
            for n in clients
            if "report" in n.title_en.lower() and n.kind == "external_notification_due"
        ]

    def test_ac23_pdpl_masking(self, db: Session) -> None:
        inc = _create(
            db,
            site="S-AIR",  # Omar's site grant
            vehicle_involved=True,
            road_type="public_road",
            report_authority="najm",
        )
        jomar = worker(db, "WKR-000003")
        _row(
            db,
            inc.id,
            plate_type="private",
            plate_letters_en="TST",
            plate_digits="2222",
            category="pickup",
            driver_kind="worker",
            worker_id=str(jomar.id),
        )
        _row(
            db,
            inc.id,
            ownership="third_party",
            role="struck",
            plate_type="private",
            plate_letters_en="QQQ",
            plate_digits="3333",
            category="private_car",
            driver_kind="external",
            external_driver_name="Test Other Driver",
            insurer="Test Takaful",
            policy_no="TEST-POL-1",
        )
        _to(db, inc.id, "reported")
        for who in ("sarah.mitchell", "omar.siddiqui"):
            rows = veh.list_rows(db, P(db, who), inc.id).items
            own, third = rows
            assert own.plate_digits == "2222" and own.worker is None and own.licence_class is None
            assert own.licence_check is not None and "worker of GULFPAVE" in own.driver_summary_en
            assert third.plate_digits is None and third.policy_no is None
            assert third.external_driver_name is None and "driver_identity" in third.redacted_groups
        rows = veh.list_rows(db, P(db, "noura.qahtani"), inc.id).items
        assert rows[0].worker is not None and rows[1].plate_digits == "3333"

    def test_ac16_ac17_ac18_commuting(self, db: Session) -> None:
        inc = _create(
            db,
            vehicle_involved=True,
            road_type="public_road",
            journey_purpose="commuting_own",
            report_authority="traffic_police",
            incident_types=["injury_illness"],
            primary_type="injury_illness",
            work_related=False,
            not_work_related_reason="commuting",
        )
        c = _case(db, inc.id)
        read = inc_svc.read(db, P(db, "noura.qahtani"), inc.id)
        assert read.recorded_not_counted
        assert read.vehicle_section and read.vehicle_section.commuting_proposed_case_ids == [c.id]
        _row(db, inc.id, ownership="third_party", role="single_vehicle", category="private_car")
        _to(db, inc.id, "reported")
        page = inc_svc.list_page(
            db, P(db, "noura.qahtani"), project(db, "ANIA-EXP").id, 1, 50, recorded_not_counted=True
        )
        assert [i.ref for i in page.items] == [read.ref] and page.items[0].recorded_not_counted
        # AC18: a commuting case on a work-task journey warns and saves
        other = _create(
            db,
            vehicle_involved=True,
            road_type="site_road",
            journey_purpose="work_task",
            incident_types=["injury_illness"],
            primary_type="injury_illness",
        )
        oc = _case(db, other.id)
        saved = cases_svc.update(
            db, P(db, "noura.qahtani"), oc.id, InjuryCaseUpdate(commuting=True)
        )
        assert "COMMUTING_PURPOSE_MISMATCH" in [w.code for w in saved.warnings or []]

    def test_ac22_phase1_police_item(self, db: Session) -> None:
        inc = _create(
            db,
            vehicle_involved=True,
            road_type="public_road",
            report_authority="najm",
            incident_types=["injury_illness"],
            primary_type="injury_illness",
        )
        _case(db, inc.id)
        _row(db, inc.id)
        read = _to(db, inc.id, "reported")
        police = [n for n in read.external_notifications if n.body.value == "police"]
        assert police and police[0].required


# ---- 6f (VA-10, VA-11) -------------------------------------------------------------------------


@pytest.mark.usefixtures("fu_seed", "clock")
def test_ac19_ac20_ac21_followup(db: Session) -> None:
    from app.schemas.followup import FuRuleUpdate
    from app.services.followup import config
    from tests.fu_helpers import due, local, make_inc, reqs, tick
    from tests.test_fu_rules import rule

    tick(2026, 10, 6, 9, 0)
    i = make_inc(
        db,
        "ANIA-EXP",
        "S-LAND",
        local(2026, 10, 6, 8, 0),
        "GULFPAVE",
        [{"cat": "MTC"}],
        vehicle_involved=True,
        road_type=VehRoadType.public_road,
    )
    got = reqs(db, i)
    assert "POL-RTA" in got and "NAJM-V" not in got
    assert due(got["POL-RTA"]) == "10-06 09:00"
    j = make_inc(
        db,
        "ANIA-EXP",
        "S-LAND",
        local(2026, 10, 6, 8, 30),
        "GULFPAVE",
        None,
        vehicle_involved=True,
        road_type=VehRoadType.public_road,
    )
    assert set(reqs(db, j)) >= {"NAJM-V"} and "POL-RTA" not in reqs(db, j)
    faisal = P(db, "faisal.harbi")
    pol = rule(db, "ANIA-EXP", "POL-RTA")
    expect(
        "RULE_LOOSENING",
        lambda: config.update_rule(db, faisal, pol.id, FuRuleUpdate(deadline_hours=2)),
    )
    pol.deadline_hours = 1
    db.flush()
    # AC21: report_no entered → offer to record the 6f submission with that reference
    j.report_no = "NJM-TEST-2026-01234"
    db.flush()
    offer = veh.submission_offer(db, j)
    assert offer is not None and offer.body.value == "najm" and offer.requirement_id is not None


# ---- seed, KPIs, AI, exports, AC31 (7a template) -----------------------------------------------


@pytest.fixture
def veh_clock() -> Any:
    from app.core.clock import set_now

    set_now(datetime(2026, 10, 12, 7, 0, tzinfo=UTC))
    yield
    set_now(None)


def _by_title(db: Session, key: str) -> Incident:
    from app.seed_vehicle import TITLES

    i = db.scalar(select(Incident).where(Incident.title == TITLES[key]))
    assert i is not None, key
    return i


@pytest.mark.usefixtures("veh_seed", "veh_clock")
class TestSeed:
    def test_seed_appendix_a(self, db: Session) -> None:
        i201 = _by_title(db, "0201")
        rows = veh.rows_of(db, i201.id)
        assert [r.ownership for r in rows] == [VehOwnership.contractor, VehOwnership.third_party]
        assert rows[0].licence_check == VehLicenceCheck.valid and rows[0].vehicle_id is not None
        assert rows[0].seat_belt == VehSeatBelt.worn and rows[0].role == VehRole.striking
        assert _by_title(db, "0204") and veh.rows_of(db, _by_title(db, "0204").id)[
            0
        ].licence_check == (VehLicenceCheck.wrong_class)
        assert (
            _by_title(db, "0212").recorded_not_counted
            and _by_title(db, "0215").recorded_not_counted
        )
        files = db.scalars(
            select(Attachment).where(
                Attachment.owner_type == AttachmentOwner.incident_accident_report
            )
        )
        assert len(list(files)) == 3
        from tests.fu_helpers import reqs

        r = reqs(db, _by_title(db, "0231"))
        assert "NAJM-V" in r and r["NAJM-V"].waived_at is None

    def test_ac25_ac27_ac28_kpis_chart(self, db: Session) -> None:
        from app.api.kpi_params import KpiQuery
        from app.core.hse_enums import ChartId, PeriodPreset
        from app.kpi import charts
        from app.kpi import scope as kscope

        def sc(who: str) -> Any:
            q = KpiQuery(
                project_ids=[project(db, "ANIA-EXP").id],
                all_projects=False,
                site_ids=[],
                zone_ids=[],
                zone_type=None,
                engagement_ids=[],
                include_subcontractors=True,
                tiers=[],
                period=PeriodPreset.custom,
                anchor=None,
                start=date(2026, 9, 1),
                end=date(2026, 9, 30),
                as_of=None,
            )
            return kscope.build(db, P(db, who), q)

        s = sc("faisal.harbi")
        k136, k137 = s.engine.results([M.K136, M.K137], s.window)
        chips = {c.key: c.value for c in k136.components}
        assert k136.value == 5
        assert (
            chips["road_type:public_road"],
            chips["road_type:site_road"],
            chips["road_type:airside"],
            chips["recorded_not_counted"],
        ) == (3, 1, 1, 2)
        assert k137.numerator == 2 and k137.value is not None and k137.value > 0
        # AC27: scope follows the caller's grant. RAWABI's tree holds GULFPAVE and NAJD as
        # subcontractors in the seed, so Ahmed sees all five; Omar (S-AIR only) sees 0209 only.
        ahmed = sc("ahmed.zahrani")
        assert ahmed.engine.result(M.K136, ahmed.engine.aggregate(ahmed.window)).value == 5
        omar = sc("omar.siddiqui")
        assert omar.engine.result(M.K136, omar.engine.aggregate(omar.window)).value == 1
        c41 = charts.chart(db, s, ChartId.C41)
        keys = [x.key for x in c41.series]
        assert keys == ["site_road", "airside", "public_road", "recorded_not_counted", "k137"]
        sep = {x.key: next(p for p in x.points if p.x == "2026-09").value for x in c41.series}
        assert (sep["public_road"], sep["recorded_not_counted"]) == ("1", "2")

    def test_ac29_ai(self, db: Session) -> None:
        from app.ai.tools import ToolContext, run

        ctx = ToolContext(
            db=db,
            p=P(db, "faisal.harbi"),
            project=project(db, "ANIA-EXP"),
            as_of=date(2026, 10, 12),
        )
        out = run(
            ctx,
            "get_breakdown",
            {
                "project_codes": ["ANIA-EXP"],
                "measure": "vehicle_incidents",
                "dimension": "road_type",
                "period": {"preset": "ytd", "anchor": "2026-10-12"},
            },
        )
        text = str(out)
        assert "recorded_not_counted" in text and "Public road" in text
        detail = str(run(ctx, "get_incident", {"ref": _by_title(db, "0201").ref}))
        assert "vehicles" in detail and "speed_band" in detail
        for secret in ("Test Driver", "Jomar", "1234", "TEST-POL-7781"):
            assert secret not in detail, secret
        found = str(
            run(
                ctx,
                "search_incidents",
                {
                    "project_codes": ["ANIA-EXP"],
                    "vehicle_involved": True,
                    "road_type": "public_road",
                    "period": {"preset": "custom", "start": "2026-09-01", "end": "2026-10-12"},
                },
            )
        )
        assert _by_title(db, "0215").ref in found and _by_title(db, "0204").ref not in found

    def test_ac30_export_columns(self, db: Session) -> None:
        from app.schemas.scorecard import XpExportRequest
        from app.services.scorecard import exports

        pid = project(db, "ANIA-EXP").id
        expect(
            "COLUMN_NOT_PERMITTED",
            lambda: exports.request(
                db,
                P(db, "omar.siddiqui"),
                XpExportRequest(
                    dataset="incident_vehicles", project_id=pid, columns=["external_driver_name"]
                ),
            ),
        )

    def test_report_reminder_job(self, db: Session) -> None:
        """7a §7: report number still missing at the reminder date → HSE Officers notified,
        next reminder a week later."""
        from app import hse_jobs
        from app.core.enums import NotificationKind
        from app.models import Notification

        i231 = _by_title(db, "0231")
        assert i231.report_no is None and i231.report_alert_on is not None
        day = i231.report_alert_on
        assert hse_jobs.vehicle_report_reminders(db, day)["notified"] >= 1
        assert i231.report_alert_on == day + timedelta(days=7)
        assert db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.kind == NotificationKind.accident_report_missing,
                Notification.entity_id == i231.id,
            )
        )
        assert hse_jobs.vehicle_report_reminders(db, day)["notified"] == 0
        db.rollback()

    def test_ac31_additive(self, db: Session) -> None:
        """AC31: the 7a seed only adds rows; seeding again is a no-op; the earlier incidents,
        6f requirements and 6g scorecards are untouched (their stored rows are older)."""
        from app.models import FuRequirement, ScCard
        from app.seed_vehicle import TITLES, seed_vehicle_data

        n = db.scalar(select(func.count()).select_from(IncidentVehicle))
        seed_vehicle_data(db)
        assert db.scalar(select(func.count()).select_from(IncidentVehicle)) == n
        new = set(db.scalars(select(Incident.id).where(Incident.title.in_(TITLES.values()))))
        assert len(new) == 6
        assert not db.scalar(
            select(func.count())
            .select_from(IncidentVehicle)
            .where(IncidentVehicle.incident_id.not_in(new))
        )
        assert not db.scalar(
            select(func.count())
            .select_from(Incident)
            .where(Incident.vehicle_involved.is_(True), Incident.id.not_in(new))
        )
        reqs = db.scalars(select(FuRequirement.incident_id))
        assert {r for r in reqs if r in new} == {_by_title(db, "0231").id}
        assert db.scalar(select(func.count()).select_from(ScCard))
