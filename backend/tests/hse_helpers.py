"""Builders for Phase 1 API tests (incidents, cases, CAs)."""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import Ids

API = "/api/v1"


def incident_body(ids: Ids, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "site_id": ids.site("S-AIR"),
        "responsible_engagement_id": ids.engagement("RAWABI"),
        "occurred_at": "2026-09-08T06:40:00Z",
        "shift": "day",
        "incident_types": ["injury_illness"],
        "primary_type": "injury_illness",
        "title": "Fall from scaffold working platform",
        "description": "Worker slipped on the platform.",
        "immediate_actions": "Area barricaded, scaffold tagged red",
        "activity": "scaffolding",
        "actual_severity": 2,
        "potential_severity": 3,
    }
    body.update(over)
    return body


def case_body(ids: Ids, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "person_type": "contractor_worker",
        "employer_engagement_id": ids.engagement("NAJD"),
        "person_name": "Imran Hussain (seed-fake)",
        "id_type": "iqama",
        "id_number": "2000000017",
        "trade": "scaffolder",
        "body_part": "wrist",
        "nature": "laceration",
        "mechanism": "slip_trip_same_level",
        "agency": "scaffold",
        "treatments": ["wound_cleaning"],
        "treated_at": "site_clinic",
    }
    body.update(over)
    return body


def create_incident(c: TestClient, ids: Ids, project: str = "ANIA-EXP", **over: Any) -> Any:
    res = c.post(
        f"{API}/projects/{ids.project(project)}/incidents", json=incident_body(ids, **over)
    )
    assert res.status_code == 201, res.text
    return res.json()


def add_case(c: TestClient, ids: Ids, incident_id: str, **over: Any) -> Any:
    res = c.post(f"{API}/incidents/{incident_id}/injury-cases", json=case_body(ids, **over))
    assert res.status_code == 201, res.text
    return res.json()


def transition(c: TestClient, incident_id: str, to: str, **extra: Any) -> Any:
    return c.post(f"{API}/incidents/{incident_id}/transitions", json={"to_status": to, **extra})


def reported_incident(c: TestClient, ids: Ids, cases: int = 1, **over: Any) -> Any:
    inc = create_incident(c, ids, **over)
    for _ in range(cases):
        add_case(c, ids, inc["id"])
    res = transition(c, inc["id"], "reported")
    assert res.status_code == 200, res.text
    return res.json()


def ca_body(ids: Ids, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Install toe-boards and double guardrails",
        "description": "All Pier B platforms",
        "control_level": "engineering",
        "priority": "medium",
        "owner_id": ids.user("ramesh.kumar"),
        "verifier_id": ids.user("noura.qahtani"),
    }
    body.update(over)
    return body


def create_ca(c: TestClient, ids: Ids, source_type: str, source_id: str | None, **over: Any) -> Any:
    body = ca_body(ids, **over)
    body.update({"source_type": source_type, "source_id": source_id})
    if source_type == "other":
        body.setdefault("site_id", ids.site("S-LAND"))
        body.setdefault("responsible_engagement_id", ids.engagement("NAJD"))
    res = c.post(f"{API}/projects/{ids.project('ANIA-EXP')}/corrective-actions", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def ca_to(c: TestClient, ca_id: str, to: str, **extra: Any) -> Any:
    return c.post(f"{API}/corrective-actions/{ca_id}/transitions", json={"to_status": to, **extra})
