"""Phase 6f contract surface: paths, enums, error codes, the capability matrix and the schema
names of earlier phases (spec 6f-incident-followup; DECISIONS D-202 `Fu` prefix)."""

from pathlib import Path

import yaml

from app.core.enums import Capability, Role
from app.core.errors import ErrorCode
from app.core.hse_enums import CaSourceType, KpiMetric, LeadingWarningCode
from app.kpi.catalogue import CATALOGUE, PHASE6F_METRICS
from app.main import create_app
from app.services.permissions import MATRIX

PHASE6F_PATHS = {
    "/api/v1/followup-reference",
    "/api/v1/projects/{project_id}/followup-settings",
    "/api/v1/projects/{project_id}/notification-rules",
    "/api/v1/notification-rules/{rule_id}",
    "/api/v1/projects/{project_id}/notification-requirements",
    "/api/v1/notification-requirements/{requirement_id}",
    "/api/v1/notification-requirements/{requirement_id}/waive",
    "/api/v1/notification-requirements/{requirement_id}/packs",
    "/api/v1/projects/{project_id}/notification-packs",
    "/api/v1/notification-packs/{pack_id}",
    "/api/v1/notification-packs/{pack_id}/transitions",
    "/api/v1/notification-packs/{pack_id}/file-url",
    "/api/v1/notification-requirements/{requirement_id}/submissions",
    "/api/v1/projects/{project_id}/notification-submissions",
    "/api/v1/notification-submissions/{submission_id}",
    "/api/v1/notification-submissions/{submission_id}/acknowledge",
    "/api/v1/notification-submissions/{submission_id}/void",
    "/api/v1/projects/{project_id}/followup-band",
    "/api/v1/projects/{project_id}/followup-action-panel",
    "/api/v1/lessons",
    "/api/v1/lessons/{lesson_id}",
    "/api/v1/lessons/{lesson_id}/transitions",
    "/api/v1/lessons/{lesson_id}/distribution",
    "/api/v1/projects/{project_id}/lesson-distribution",
    "/api/v1/lesson-distribution/{item_id}/acknowledge",
    "/api/v1/lessons/{lesson_id}/links",
    "/api/v1/template-change-requests",
    "/api/v1/lesson-links/{link_id}/reject",
    "/api/v1/incidents/{incident_id}/similar-lessons",
    "/api/v1/projects/{project_id}/effectiveness-checks",
    "/api/v1/effectiveness-checks/{check_id}",
    "/api/v1/effectiveness-checks/{check_id}/complete",
    "/api/v1/kpi/incident-followup",
}
CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "openapi.yaml"


def test_phase6f_paths_and_schema_names() -> None:
    spec = create_app().openapi()
    assert tuple(map(int, spec["info"]["version"].split("."))) >= (0, 12, 0)
    assert set(spec["paths"]) >= PHASE6F_PATHS
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))
    names = set(spec["components"]["schemas"])
    new = {n for n in names if n.startswith("Fu") or "_Fu" in n}
    assert new and all(n.startswith(("Fu", "Page_Fu")) for n in new)
    # every schema name exported before 6f is still present (no clash renamed an older one)
    committed = set(yaml.safe_load(CONTRACT.read_text())["components"]["schemas"])
    assert committed - names == set()


def test_phase6f_enums_and_matrix() -> None:
    codes = {c.value for c in ErrorCode}
    assert {
        "RULE_LOOSENING", "CLIENT_RECIPIENT_REQUIRED", "WAIVER_EVIDENCE_REQUIRED",
        "INVESTIGATION_NOT_APPROVED", "PACK_NOT_APPROVED", "CHANNEL_NOT_ALLOWED",
        "EVIDENCE_REQUIRED", "SUBMITTED_AT_INVALID", "IDENTITY_IN_TEXT", "LESSON_INCOMPLETE",
        "REDACTION_NOT_CONFIRMED", "SELF_APPROVAL", "NOT_DISTRIBUTED", "ON_BEHALF_NOTE_REQUIRED",
        "LESSON_NOT_PUBLISHED", "RATIONALE_REQUIRED", "FOLLOW_UP_REQUIRED", "SETTING_LOOSENING",
        "PACK_IMMUTABLE", "SUBMISSION_LOCKED",
    } <= codes  # fmt: skip
    assert {f"K-{n}" for n in range(127, 132)} <= {m.value for m in KpiMetric}
    assert "E24" in {c.value for c in LeadingWarningCode}
    assert CaSourceType.lesson.value == "lesson"
    for m in PHASE6F_METRICS:
        assert CATALOGUE[m].spec_ref.startswith("6f-incident-followup §6.2")
    for role, caps in MATRIX.items():
        if role != Role.hse_manager:
            assert Capability.followup_settings not in caps, role
            assert Capability.lesson_publish not in caps, role
    for role in Role:
        if role != Role.hse_manager:
            assert Capability.lesson_library_view in MATRIX[role], role
    assert set(MATRIX[Role.viewer_client]) >= {Capability.followup_view}
    assert Capability.followup_record not in MATRIX[Role.viewer_client]
    assert Capability.followup_approve in MATRIX[Role.contractor_hse_rep]
    assert Capability.lesson_effectiveness not in MATRIX[Role.contractor_hse_rep]
