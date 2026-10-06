"""Spec 1-dashboard §4.5/§5.5 corrective actions, §4.3 observations, §4.4 inspections,
P1-3 attachments, P1-6 exports — AC24, AC25, AC32, AC34-AC37, AC40-AC43, AC64."""

import time
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.models import AuditEntry, CorrectiveAction, Inspection
from tests.conftest import Api, Ids
from tests.hse_helpers import (
    API,
    ca_to,
    create_ca,
    create_incident,
    reported_incident,
    transition,
)

EVIDENCE = "Guardrails installed on all platforms, photos attached"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64


def _l3_pending_review(api: Api, ids: Ids) -> tuple[dict, str]:
    """An L3 (HiPo) near miss in Pending Review with one administrative CA."""
    n = api.as_("noura.qahtani")
    inc = create_incident(
        n,
        ids,
        incident_types=["near_miss"],
        primary_type="near_miss",
        actual_severity=1,
        potential_severity=4,
    )
    assert transition(n, inc["id"], "reported").status_code == 200
    res = transition(
        n,
        inc["id"],
        "under_investigation",
        investigation={
            "level": "L3",
            "lead_investigator_id": ids.user("noura.qahtani"),
            "team_member_ids": [ids.user("ahmed.zahrani"), ids.user("omar.siddiqui")],
        },
    )
    assert res.status_code == 200, res.text
    ca = create_ca(n, ids, "incident", inc["id"], control_level="administrative")
    res = n.patch(
        f"{API}/incidents/{inc['id']}/investigation",
        json={
            "sequence_of_events": "Load swung over the walkway.",
            "immediate_causes": "Tag line not used",
            "preliminary_report": "Initial findings shared.",
            "lessons_learned": "Use tag lines on every lift.",
            "root_causes": [{"code": "OF-04", "text": "Supervision", "linked_ca_ids": [ca["id"]]}],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["missing_for_submit"] == [], res.json()["missing_for_submit"]
    assert transition(n, inc["id"], "pending_review").status_code == 200
    return inc, ca["id"]


def test_AC24_higher_control_required(api: Api, ids: Ids) -> None:
    inc, _ = _l3_pending_review(api, ids)
    f = api.as_("faisal.harbi")
    res = transition(f, inc["id"], "actions_pending")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "HIGHER_CONTROL_REQUIRED"
    res = transition(
        f,
        inc["id"],
        "actions_pending",
        higher_control_justification="Lift plan already engineered; no feasible alternative.",
    )
    assert res.status_code == 200, res.text


def test_AC25_last_ca_closed_closes_incident(api: Api, ids: Ids) -> None:
    inc, ca_id = _l3_pending_review(api, ids)
    f = api.as_("faisal.harbi")
    n = api.as_("noura.qahtani")
    create_ca(n, ids, "incident", inc["id"], control_level="engineering")
    res = transition(f, inc["id"], "actions_pending")
    assert res.status_code == 200, res.text
    r = api.as_("ramesh.kumar")
    cas = n.get(
        f"{API}/projects/{ids.project('ANIA-EXP')}/corrective-actions",
        params={"source_id": inc["id"]},
    ).json()["items"]
    for ca in cas:
        assert ca_to(r, ca["id"], "pending_verification", evidence_text=EVIDENCE).status_code == 200
        assert ca_to(n, ca["id"], "closed").status_code == 200
    assert n.get(f"{API}/incidents/{inc['id']}").json()["status"] == "closed"
    assert ca_id in {c["id"] for c in cas}


def test_AC32_viewer_export_has_no_identity_and_purpose_required(
    api: Api, ids: Ids, db: Session
) -> None:
    n = api.as_("noura.qahtani")
    reported_incident(n, ids)
    pid = ids.project("ANIA-EXP")
    s = api.as_("sarah.mitchell")
    res = s.get(f"{API}/exports/incidents", params={"project_id": pid})
    assert res.status_code == 200, res.text
    header = res.content.decode("utf-8-sig").splitlines()[0]
    for col in ("person_name", "id_number", "treatments", "medical_notes"):
        assert col not in header
    assert "Imran" not in res.content.decode("utf-8-sig")
    assert (
        s.get(
            f"{API}/exports/incidents", params={"project_id": pid, "include_identity": True}
        ).status_code
        == 403
    )
    res = n.get(f"{API}/exports/incidents", params={"project_id": pid, "include_identity": True})
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "EXPORT_PURPOSE_REQUIRED"
    res = n.get(
        f"{API}/exports/incidents",
        params={"project_id": pid, "include_identity": True, "purpose": "gosi"},
    )
    assert res.status_code == 200
    assert "person_name" in res.content.decode("utf-8-sig").splitlines()[0]
    entry = db.scalars(
        select(AuditEntry)
        .where(AuditEntry.action == AuditAction.export)
        .order_by(AuditEntry.occurred_at.desc())
    ).first()
    assert entry is not None and entry.details["purpose"] == "gosi"


def test_AC34_medical_attachment_signed_url_short_lived(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    inc = reported_incident(n, ids)
    case = inc["cases"][0]
    res = n.post(
        f"{API}/attachments",
        data={"owner_type": "injury_case_medical", "owner_id": case["id"]},
        files={"file": ("report.pdf", PDF, "application/pdf")},
    )
    assert res.status_code == 201, res.text
    att = res.json()
    signed = n.post(f"{API}/attachments/{att['id']}/signed-url").json()
    exp = datetime.fromisoformat(signed["expires_at"])
    assert exp - datetime.now(UTC) <= timedelta(minutes=5, seconds=5)
    anon = api.anon
    got = anon.get(signed["url"])
    assert got.status_code == 200 and got.content == PDF
    tampered = signed["url"].replace("signature=", "signature=x")
    assert anon.get(tampered).status_code == 410
    expired = f"{API}/attachments/{att['id']}/content?expires={int(time.time()) - 1}&signature=a"
    assert anon.get(expired).status_code == 410
    omar = api.as_("omar.siddiqui")
    assert omar.post(f"{API}/attachments/{att['id']}/signed-url").status_code == 403


def test_AC35_anonymous_observer_hidden_except_manager(api: Api, ids: Ids) -> None:
    omar = api.as_("omar.siddiqui")
    res = omar.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/observations",
        json={
            "site_id": ids.site("S-AIR"),
            "observed_at": "2026-09-14T20:10:00Z",
            "anonymous": True,
            "observed_engagement_id": ids.engagement("GULFPAVE"),
            "obs_type": "unsafe_condition",
            "category": "airside_fod_control",
            "risk_rating": "high",
            "description": "Loose aggregate on TWB shoulder",
            "immediate_action": "Swept, FOD walk repeated",
            "closed_on_spot": False,
        },
    )
    assert res.status_code == 201, res.text
    obs = res.json()
    assert obs["status"] == "open"
    seen = api.as_("noura.qahtani").get(f"{API}/observations/{obs['id']}").json()
    assert "observer" not in seen
    f = api.as_("faisal.harbi").get(f"{API}/observations/{obs['id']}").json()
    assert f["observer"]["id"] == ids.user("omar.siddiqui")


def test_observation_ca_raises_and_closes(api: Api, ids: Ids) -> None:
    omar = api.as_("omar.siddiqui")
    obs = omar.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/observations",
        json={
            "site_id": ids.site("S-LAND"),
            "observed_at": "2026-09-14T08:00:00Z",
            "observed_engagement_id": ids.engagement("NAJD"),
            "obs_type": "unsafe_act",
            "category": "work_at_height",
            "risk_rating": "medium",
            "description": "No harness tie-off",
            "immediate_action": "Work stopped",
        },
    )
    assert obs.status_code in (201, 403), obs.text
    n = api.as_("noura.qahtani")
    if obs.status_code == 403:  # Omar's scope is S-AIR only
        obs = n.post(
            f"{API}/projects/{ids.project('ANIA-EXP')}/observations",
            json={
                "site_id": ids.site("S-LAND"),
                "observed_at": "2026-09-14T08:00:00Z",
                "observed_engagement_id": ids.engagement("NAJD"),
                "obs_type": "unsafe_act",
                "category": "work_at_height",
                "risk_rating": "medium",
                "description": "No harness tie-off",
                "immediate_action": "Work stopped",
            },
        )
    o = obs.json()
    ca = create_ca(n, ids, "observation", o["id"])
    assert n.get(f"{API}/observations/{o['id']}").json()["status"] == "action_raised"
    r = api.as_("ramesh.kumar")
    ca_to(r, ca["id"], "pending_verification", evidence_text=EVIDENCE)
    ca_to(n, ca["id"], "closed")
    assert n.get(f"{API}/observations/{o['id']}").json()["status"] == "closed"


def test_AC37_inspection_timeliness(api: Api, ids: Ids, db: Session) -> None:
    n = api.as_("noura.qahtani")
    pid = ids.project("ANIA-EXP")
    res = n.post(
        f"{API}/projects/{pid}/inspection-plans",
        json={
            "name_en": "Daily FOD walk",
            "name_ar": "جولة يومية",
            "inspection_type": "general_site",
            "site_id": ids.site("S-AIR"),
            "frequency": "daily",
            "start_date": date.today().isoformat(),
            "assignee_role": "hse_officer",
            "assignee_user_id": ids.user("noura.qahtani"),
        },
    )
    assert res.status_code == 201, res.text
    plan = res.json()
    items = n.get(f"{API}/projects/{pid}/inspections", params={"plan_id": plan["id"]}).json()
    assert items["total"] == 36  # today + 35 days
    first = sorted(items["items"], key=lambda x: x["planned_date"])[0]
    assert first["timeliness"] == "pending"
    done = n.post(
        f"{API}/inspections/{first['id']}/complete",
        json={
            "completed_at": datetime.now(UTC).isoformat(),
            "items_checked": 40,
            "items_compliant": 36,
            "findings": [{"description": "Loose cones", "severity": "low", "ca_required": True}],
        },
    )
    assert done.status_code == 422
    assert done.json()["detail"]["code"] == "FINDING_CA_REQUIRED"
    done = n.post(
        f"{API}/inspections/{first['id']}/complete",
        json={
            "completed_at": datetime.now(UTC).isoformat(),
            "items_checked": 40,
            "items_compliant": 36,
            "findings": [
                {
                    "description": "Loose cones",
                    "severity": "low",
                    "ca_required": True,
                    "corrective_action": {
                        "title": "Re-secure cones",
                        "description": "Use weighted bases",
                        "control_level": "engineering",
                        "priority": "low",
                        "owner_id": ids.user("ahmed.zahrani"),
                        "verifier_id": ids.user("noura.qahtani"),
                        "responsible_engagement_id": ids.engagement("GULFPAVE"),
                    },
                }
            ],
        },
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["timeliness"] == "on_time" and body["score_pct"] == "90.0"
    assert body["findings"][0]["ca_ref"].startswith("CA-ANIA-EXP-")
    # a past planned instance not done: missed after the grace period
    later = db.get(Inspection, sorted(items["items"], key=lambda x: x["planned_date"])[1]["id"])
    assert later is not None
    later.planned_date = date.today() - timedelta(days=5)
    db.commit()
    from app.models import Project
    from app.services import inspections as svc

    proj = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
    assert proj is not None
    svc.mark_missed(db, proj, date.today())
    db.commit()
    got = n.get(f"{API}/inspections/{later.id}").json()
    assert got["status"] == "missed" and got["timeliness"] == "missed"


def test_AC40_owner_cannot_verify(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    res = n.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/corrective-actions",
        json={
            "source_type": "other",
            "site_id": ids.site("S-LAND"),
            "responsible_engagement_id": ids.engagement("NAJD"),
            "title": "x",
            "description": "y",
            "control_level": "engineering",
            "priority": "medium",
            "owner_id": ids.user("ramesh.kumar"),
            "verifier_id": ids.user("ramesh.kumar"),
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "VERIFIER_IS_OWNER"
    ca = create_ca(n, ids, "other", None)
    r = api.as_("ramesh.kumar")
    assert ca_to(r, ca["id"], "pending_verification", evidence_text=EVIDENCE).status_code == 200
    res = ca_to(r, ca["id"], "closed")
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "VERIFIER_IS_OWNER"


def test_AC41_extension_limit(api: Api, ids: Ids, db: Session) -> None:
    n = api.as_("noura.qahtani")
    r = api.as_("ramesh.kumar")
    ca = create_ca(n, ids, "other", None)
    original = ca["original_due_date"]
    due = date.fromisoformat(ca["due_date"])
    for i in range(2):
        due += timedelta(days=7)
        res = r.post(
            f"{API}/corrective-actions/{ca['id']}/extensions",
            json={"new_due_date": due.isoformat(), "reason": f"Material delay {i}"},
        )
        assert res.status_code == 201, res.text
        ext = res.json()["extensions"][-1]
        # the owner cannot approve their own request
        assert (
            r.post(
                f"{API}/corrective-actions/{ca['id']}/extensions/{ext['id']}/decision",
                json={"approve": True},
            ).status_code
            == 403
        )
        res = n.post(
            f"{API}/corrective-actions/{ca['id']}/extensions/{ext['id']}/decision",
            json={"approve": True},
        )
        assert res.status_code == 200
        assert res.json()["original_due_date"] == original
    res = r.post(
        f"{API}/corrective-actions/{ca['id']}/extensions",
        json={"new_due_date": (due + timedelta(days=7)).isoformat(), "reason": "Third"},
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "EXTENSION_LIMIT_REACHED"
    row = db.get(CorrectiveAction, ca["id"])
    assert row is not None and row.original_due_date.isoformat() == original


def test_AC42_evidence_required(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    ca = create_ca(n, ids, "other", None)
    r = api.as_("ramesh.kumar")
    res = ca_to(r, ca["id"], "pending_verification")
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "EVIDENCE_REQUIRED"
    up = r.post(
        f"{API}/attachments",
        data={"owner_type": "corrective_action_evidence", "owner_id": ca["id"]},
        files={"file": ("photo.png", PNG, "image/png")},
    )
    assert up.status_code == 201, up.text
    assert ca_to(r, ca["id"], "pending_verification").status_code == 200


def test_AC43_rejection_returns_to_in_progress(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    ca = create_ca(n, ids, "other", None)
    r = api.as_("ramesh.kumar")
    ca_to(r, ca["id"], "pending_verification", evidence_text=EVIDENCE)
    assert ca_to(n, ca["id"], "in_progress").status_code == 422  # comment required
    res = ca_to(n, ca["id"], "in_progress", comment="Guardrail on level 3 missing")
    assert res.status_code == 200
    assert res.json()["status"] == "in_progress" and res.json()["completed_at"] is None


def test_verifier_role_per_priority(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    res = n.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/corrective-actions",
        json={
            "source_type": "other",
            "site_id": ids.site("S-LAND"),
            "responsible_engagement_id": ids.engagement("NAJD"),
            "title": "x",
            "description": "y",
            "control_level": "engineering",
            "priority": "high",
            "owner_id": ids.user("ramesh.kumar"),
            "verifier_id": ids.user("ahmed.zahrani"),
        },
    )
    assert res.json()["detail"]["code"] == "VERIFIER_ROLE_NOT_ALLOWED"
    # medium: the contractor HSE rep of the responsible tree may verify
    create_ca(n, ids, "other", None, verifier_id=ids.user("ahmed.zahrani"))


def test_AC64_action_panel_equals_k42(api: Api, ids: Ids, db: Session) -> None:
    n = api.as_("noura.qahtani")
    ca = create_ca(n, ids, "other", None)
    row = db.get(CorrectiveAction, ca["id"])
    assert row is not None
    row.created_date = date.today() - timedelta(days=20)
    row.due_date = date.today() - timedelta(days=10)
    db.commit()
    pid = ids.project("ANIA-EXP")
    panel = n.get(f"{API}/dashboard/action-panel", params={"project_id": pid})
    assert panel.status_code == 200, panel.text
    item = next(i for i in panel.json()["items"] if i["key"] == "overdue_cas")
    k42 = n.get(f"{API}/kpi/metrics/K-42", params={"project_id": pid}).json()
    assert item["count"] == int(k42["kpi"]["value"]) == 1
    link = item["link"]
    listed = n.get(link["path"].replace("{project_id}", pid), params=link["query"]).json()
    assert listed["total"] == item["count"]
    assert listed["items"][0]["overdue_bucket"] == "8-30"
