"""Phase 6d contract surface: paths, enums, error codes and the capability matrix (spec
6d-field-assurance)."""

from app.core.enums import Capability, Role
from app.core.errors import ErrorCode
from app.core.hse_enums import (
    CaSourceType,
    ImportCode,
    InspectionFrequency,
    KpiMetric,
    LeadingWarningCode,
)
from app.kpi.catalogue import CATALOGUE, PHASE6D_METRICS
from app.main import create_app
from app.services.permissions import MATRIX

PHASE6D_PATHS = {
    "/api/v1/field-reference",
    "/api/v1/projects/{project_id}/field-settings",
    "/api/v1/checklist-templates",
    "/api/v1/checklist-templates/{template_id}",
    "/api/v1/checklist-templates/{template_id}/new-version",
    "/api/v1/checklist-templates/{template_id}/transitions",
    "/api/v1/toolbox-topics",
    "/api/v1/toolbox-topics/{topic_id}",
    "/api/v1/toolbox-topics/{topic_id}/new-version",
    "/api/v1/toolbox-topics/{topic_id}/transitions",
    "/api/v1/projects/{project_id}/checklist-submissions",
    "/api/v1/checklist-responses/{response_id}",
    "/api/v1/inspections/{inspection_id}/void",
    "/api/v1/projects/{project_id}/field-findings",
    "/api/v1/projects/{project_id}/field-offline-pack",
    "/api/v1/projects/{project_id}/stop-work-orders",
    "/api/v1/stop-work-orders/{order_id}",
    "/api/v1/stop-work-orders/{order_id}/release",
    "/api/v1/stop-work-orders/{order_id}/void",
    "/api/v1/projects/{project_id}/field-action-panel",
    "/api/v1/projects/{project_id}/field-band",
    "/api/v1/projects/{project_id}/field-audits",
    "/api/v1/field-audits/{audit_id}",
    "/api/v1/field-audits/{audit_id}/answers",
    "/api/v1/field-audits/{audit_id}/transitions",
    "/api/v1/projects/{project_id}/audit-programme",
    "/api/v1/projects/{project_id}/toolbox-talks",
    "/api/v1/toolbox-talks/{talk_id}",
    "/api/v1/toolbox-talks/{talk_id}/attendance",
    "/api/v1/toolbox-talks/{talk_id}/attendance/{row_id}",
    "/api/v1/toolbox-talks/{talk_id}/void",
    "/api/v1/projects/{project_id}/toolbox-suggestions",
    "/api/v1/projects/{project_id}/briefing-campaigns",
    "/api/v1/briefing-campaigns/{campaign_id}",
    "/api/v1/briefing-campaigns/{campaign_id}/transitions",
    "/api/v1/kpi/field-assurance",
}


def test_phase6d_paths_in_contract() -> None:
    spec = create_app().openapi()
    assert spec["info"]["version"] == "0.10.0"
    assert set(spec["paths"]) >= PHASE6D_PATHS
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))
    # P6d-4: attendance rows expose "signed", never a signature image
    props = set(spec["components"]["schemas"]["AttendanceRowRead"]["properties"])
    assert "signed" in props and not {"signature", "signature_id"} & props
    plan = set(spec["components"]["schemas"]["InspectionPlanCreate"]["properties"])
    assert {"template_code", "rotation", "rotation_list"} <= plan


def test_phase6d_enums_and_matrix() -> None:
    codes = {c.value for c in ErrorCode}
    assert {
        "TEMPLATE_INCOMPLETE", "TEMPLATE_IN_USE", "TEMPLATE_REQUIRED", "TEMPLATE_NOT_APPLICABLE",
        "TEMPLATE_IMMUTABLE", "NA_NOT_ALLOWED", "PHOTO_REQUIRED", "SEVERITY_LOWERED",
        "FIX_ON_SPOT_NOT_ALLOWED", "STOP_RECORD_REQUIRED", "STOP_RELEASE_CA_REQUIRED",
        "STOP_WORK_ACTIVE", "OFFLINE_SUBMIT_TOO_LATE", "CLOCK_SKEW", "TOPIC_INCOMPLETE",
        "TOPIC_REVIEW_OVERDUE", "WORKER_NOT_MOBILISED", "DUPLICATE_ATTENDEE",
        "ATTENDANCE_EVIDENCE_REQUIRED", "TALK_LOCKED", "TBT_SHORT", "LANGUAGE_MISMATCH",
        "TOKEN_UNKNOWN", "SOD_CONFLICT", "SETTING_LOOSENING",
    } <= codes  # fmt: skip
    assert {f"K-{n}" for n in range(110, 118)} <= {m.value for m in KpiMetric}
    assert {"E20", "E21"} <= {c.value for c in LeadingWarningCode}
    assert CaSourceType.field_audit.value == "field_audit"
    assert ImportCode.W08.value == "W08"
    assert InspectionFrequency.quarterly.value == "quarterly"
    for m in PHASE6D_METRICS:
        assert CATALOGUE[m].spec_ref.startswith("6d-field-assurance §6.7")
    # §5.13: 193 is HSE Manager only; reps and receivers never release or void; viewers never
    # record
    for role, caps in MATRIX.items():
        if role != Role.hse_manager:
            assert Capability.field_library_publish not in caps, role
    for role in (Role.contractor_hse_rep, Role.permit_receiver, Role.permit_issuer):
        assert Capability.stop_work_release not in MATRIX[role]
        assert Capability.field_void not in MATRIX[role]
    assert Capability.toolbox_record not in MATRIX[Role.viewer_client]
    assert Capability.field_view in MATRIX[Role.viewer_client]
    assert Capability.field_void not in MATRIX[Role.site_engineer]
    assert Capability.stop_work_release in MATRIX[Role.site_engineer]
