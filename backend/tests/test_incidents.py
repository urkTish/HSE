"""Spec 1-dashboard §4.2/§5.2 incidents & classification — AC13-AC28 (API side), AC29-AC33."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.models import AuditEntry, Notification, PeriodLock, Project
from tests.conftest import Api, Ids
from tests.hse_helpers import API, add_case, create_incident, reported_incident, transition


def test_AC13_first_aid_then_sutures_is_mtc(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    inc = create_incident(c, ids)
    case = add_case(c, ids, inc["id"], treatments=["wound_cleaning", "wound_covering_steristrips"])
    assert case["derived_category"] == "FAC"
    res = c.patch(
        f"{API}/injury-cases/{case['id']}",
        json={
            "treatments": ["wound_cleaning", "wound_covering_steristrips", "sutures_staples_glue"]
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["derived_category"] == "MTC"


def test_AC14_fracture_with_first_aid_is_mtc(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    inc = create_incident(c, ids)
    case = add_case(
        c, ids, inc["id"], nature="fracture", treatments=["temporary_immobilisation_transport"]
    )
    assert case["derived_category"] == "MTC"


def test_AC15_lti_with_restriction_day_counts(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    inc = create_incident(c, ids, occurred_at="2026-09-01T06:00:00Z")
    case = add_case(
        c,
        ids,
        inc["id"],
        away_start_date="2026-09-02",
        rtw_date="2026-09-12",
        restricted_start="2026-09-12",
        restricted_end="2026-10-11",
    )
    assert case["derived_category"] == "LTI"
    full = c.get(f"{API}/injury-cases/{case['id']}", params={"as_of": "2026-10-31"}).json()
    assert full["day_counts"]["days_away"] == 10
    assert full["day_counts"]["restricted_days"] == 30


def test_AC19_near_miss_cannot_combine(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    res = c.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/incidents",
        json={
            "site_id": ids.site("S-AIR"),
            "occurred_at": "2026-09-08T06:40:00Z",
            "incident_types": ["near_miss", "property_damage"],
            "primary_type": "near_miss",
            "title": "Dropped load near the apron",
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "NEAR_MISS_EXCLUSIVE"


def test_AC20_injury_needs_a_case(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    inc = create_incident(c, ids)
    res = transition(c, inc["id"], "reported")
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INJURY_CASE_REQUIRED"


def test_AC21_not_work_related_listed_as_excluded(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    inc = create_incident(c, ids, work_related=False, not_work_related_reason="off_duty_camp")
    add_case(c, ids, inc["id"])
    assert transition(c, inc["id"], "reported").status_code == 200
    rows = c.get(f"{API}/projects/{ids.project('ANIA-EXP')}/incidents/excluded-cases").json()
    row = next(r for r in rows["items"] if r["incident_id"] == inc["id"])
    assert row["reasons"] == ["not_work_related"]
    assert row["reason_detail"] == "off_duty_camp"


def test_AC22_commuting_excluded_but_gosi_required(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    inc = create_incident(c, ids)
    case = add_case(c, ids, inc["id"], commuting=True)
    assert case["excluded_from_rates"] is True
    assert "commuting" in case["exclusion_reasons"]
    out = transition(c, inc["id"], "reported").json()
    gosi = next(n for n in out["external_notifications"] if n["body"] == "gosi")
    assert gosi["required"] is True and gosi["state"] in ("due", "overdue")


def test_AC23_hipo_near_miss_needs_l3(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    inc = create_incident(
        c,
        ids,
        incident_types=["near_miss"],
        primary_type="near_miss",
        actual_severity=1,
        potential_severity=4,
    )
    out = transition(c, inc["id"], "reported").json()
    assert out["hipo"] is True
    assert out["minimum_investigation_level"] == "L3"
    res = transition(
        c,
        inc["id"],
        "under_investigation",
        investigation={"level": "L2", "lead_investigator_id": ids.user("noura.qahtani")},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INVESTIGATION_LEVEL_TOO_LOW"


def test_AC26_voided_hidden_unless_requested(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    inc = reported_incident(c, ids)
    assert transition(c, inc["id"], "voided").status_code == 422  # reason required
    res = transition(c, inc["id"], "voided", reason="duplicate of another report")
    assert res.status_code == 200
    url = f"{API}/projects/{ids.project('ANIA-EXP')}/incidents"
    assert inc["id"] not in {i["id"] for i in c.get(url).json()["items"]}
    voided = c.get(url, params={"status": "voided"}).json()["items"]
    assert inc["id"] in {i["id"] for i in voided}


def test_AC27_late_report_flag(api: Api, ids: Ids, db: Session) -> None:
    c = api.as_("noura.qahtani")
    inc = reported_incident(c, ids, occurred_at="2026-09-10T05:00:00Z")
    assert inc["late_report"] is True  # reported "now", long after occurrence
    url = f"{API}/projects/{ids.project('ANIA-EXP')}/incidents"
    items = c.get(url, params={"late_report": True}).json()["items"]
    assert inc["id"] in {i["id"] for i in items}


def test_AC28_reclassification_in_locked_month_restates(api: Api, ids: Ids, db: Session) -> None:
    c = api.as_("noura.qahtani")
    inc = reported_incident(c, ids, occurred_at="2026-08-12T06:00:00Z")
    case_id = inc["cases"][0]["id"]
    assert (
        c.post(
            f"{API}/injury-cases/{case_id}/classification", json={"case_category": "FAC"}
        ).status_code
        == 200
    )
    m = api.as_("faisal.harbi")
    pid = ids.project("ANIA-EXP")
    assert m.post(f"{API}/projects/{pid}/workforce-months/2026-08/lock", json={}).status_code == 200
    res = c.patch(f"{API}/injury-cases/{case_id}", json={"treatments": ["sutures_staples_glue"]})
    assert res.status_code == 200
    assert res.json()["case_category"] == "MTC"
    lock = db.get(
        PeriodLock,
        (db.scalar(select(Project.id).where(Project.code == "ANIA-EXP")), date(2026, 8, 1)),
    )
    assert lock is not None and lock.restated
    note = db.scalars(
        select(Notification).where(
            Notification.user_id == ids.user("faisal.harbi"),
            Notification.kind == "case_restated",
        )
    ).all()
    assert note
    kpi = m.get(
        f"{API}/kpi/dashboard",
        params={
            "project_id": pid,
            "period": "month",
            "anchor": "2026-08-15",
            "as_of": "2026-08-31",
        },
    )
    assert kpi.status_code == 200, kpi.text
    assert kpi.json()["context"]["restated"] is True


def test_AC29_site_engineer_sees_deidentified_case(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    inc = reported_incident(n, ids)
    omar = api.as_("omar.siddiqui")
    res = omar.get(f"{API}/incidents/{inc['id']}")
    assert res.status_code == 200
    assert res.json()["cases"][0]["display_label"] == "Person 1 · scaffolder · NAJD"
    case = omar.get(f"{API}/injury-cases/{inc['cases'][0]['id']}").json()
    for absent in ("person_name", "id_number_masked", "treatments", "medical_notes"):
        assert absent not in case
    assert set(case["redacted_groups"]) == {"identity", "medical"}
    assert "Imran" not in res.text


def test_AC30_officer_sees_masked_id_and_read_is_audited(api: Api, ids: Ids, db: Session) -> None:
    n = api.as_("noura.qahtani")
    inc = reported_incident(n, ids)
    case = n.get(f"{API}/injury-cases/{inc['cases'][0]['id']}").json()
    assert case["person_name"].startswith("Imran Hussain")
    assert case["id_number_masked"] == "2*******17"
    entry = db.scalars(
        select(AuditEntry)
        .where(AuditEntry.action == AuditAction.sensitive_field_read)
        .order_by(AuditEntry.occurred_at.desc())
    ).first()
    assert entry is not None
    assert "person_name" in (entry.fields_read or [])
    full = n.get(f"{API}/injury-cases/{inc['cases'][0]['id']}/id-number").json()
    assert full["id_number"] == "2000000017"


def test_AC31_privacy_case_name_hidden_except_manager(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    inc = create_incident(n, ids)
    case = add_case(n, ids, inc["id"], privacy_case=True, privacy_reason="employee_request")
    seen = n.get(f"{API}/injury-cases/{case['id']}").json()
    assert seen["person_name"].startswith("Privacy case")
    assert "id_number_masked" not in seen
    assert n.get(f"{API}/injury-cases/{case['id']}/id-number").status_code == 403
    f = api.as_("faisal.harbi").get(f"{API}/injury-cases/{case['id']}").json()
    assert f["person_name"].startswith("Imran Hussain")


def test_AC33_possible_id_warning(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    inc = create_incident(c, ids, description="Worker 2000000017 slipped")
    assert any(w["code"] == "POSSIBLE_ID_NUMBER" for w in inc["warnings"])


def test_incident_ref_and_draft_delete(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    a = create_incident(c, ids)
    b = create_incident(c, ids)
    assert a["ref"] == "INC-ANIA-EXP-2026-0001" and b["ref"] == "INC-ANIA-EXP-2026-0002"
    assert c.delete(f"{API}/incidents/{a['id']}").status_code == 204
    r = reported_incident(c, ids)
    res = c.delete(f"{API}/incidents/{r['id']}")
    assert res.status_code == 409


def test_contractor_rep_scope_on_register(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    inc = reported_incident(n, ids)
    url = f"{API}/projects/{ids.project('ANIA-EXP')}/incidents"
    assert inc["id"] in {i["id"] for i in api.as_("ahmed.zahrani").get(url).json()["items"]}
    y = api.as_("yousef.ghamdi")
    assert y.get(f"{API}/incidents/{inc['id']}").status_code == 404


def test_investigation_flow_l2(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    inc = reported_incident(n, ids)
    case_id = inc["cases"][0]["id"]
    n.patch(f"{API}/injury-cases/{case_id}", json={"treatments": ["sutures_staples_glue"]})
    res = transition(
        n,
        inc["id"],
        "under_investigation",
        investigation={"level": "L2", "lead_investigator_id": ids.user("omar.siddiqui")},
    )
    assert res.status_code == 200, res.text
    inv = n.get(f"{API}/incidents/{inc['id']}/investigation").json()
    assert inv["due_date"] == "2026-09-15"
    assert "root_causes" in inv["missing_for_submit"]
    omar = api.as_("omar.siddiqui")
    res = omar.patch(
        f"{API}/incidents/{inc['id']}/investigation",
        json={
            "sequence_of_events": "Slipped on wet deck.",
            "immediate_causes": "Wet surface",
            "root_causes": [
                {
                    "code": "OF-04",
                    "text": "Inadequate supervision",
                    "no_action_justification": "Covered by the existing supervision plan",
                }
            ],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["missing_for_submit"] == []
    assert transition(omar, inc["id"], "pending_review").status_code == 200
    # approver != lead; cases must be confirmed
    assert transition(n, inc["id"], "closed").json()["detail"]["code"] == "CASES_NOT_CONFIRMED"
    n.post(f"{API}/injury-cases/{case_id}/classification", json={"case_category": "MTC"})
    res = transition(n, inc["id"], "closed")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "closed"


def test_classification_override_needs_manager_and_justification(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    inc = reported_incident(n, ids)
    case_id = inc["cases"][0]["id"]
    url = f"{API}/injury-cases/{case_id}/classification"
    assert n.post(url, json={"case_category": "MTC"}).status_code == 403
    f = api.as_("faisal.harbi")
    res = f.post(url, json={"case_category": "MTC"})
    assert res.json()["detail"]["code"] == "JUSTIFICATION_REQUIRED"
    res = f.post(
        url, json={"case_category": "MTC", "justification": "Clinic note confirms sutures applied"}
    )
    assert res.status_code == 200
    assert res.json()["case_category"] == "MTC"
