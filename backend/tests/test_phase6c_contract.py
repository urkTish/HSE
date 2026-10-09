"""Phase 6c contract surface: paths, enums, error codes and the capability matrix (spec
6c-emergency-drills)."""

from app.core.access_enums import QrKind
from app.core.enums import Capability, Role
from app.core.errors import ErrorCode
from app.core.hse_enums import CaSourceType, KpiMetric, LeadingWarningCode
from app.core.ptw_enums import ROUTINE_REASONS, PermitBlocker, PermitWarningCode, StatusReason
from app.kpi.catalogue import CATALOGUE, PHASE6C_METRICS
from app.main import create_app
from app.services.permissions import MATRIX

PHASE6C_PATHS = {
    "/api/v1/emergency-reference",
    "/api/v1/projects/{project_id}/emergency-settings",
    "/api/v1/projects/{project_id}/erps",
    "/api/v1/erps/{erp_id}",
    "/api/v1/erps/{erp_id}/transitions",
    "/api/v1/projects/{project_id}/assembly-points",
    "/api/v1/assembly-points/{ap_id}",
    "/api/v1/projects/{project_id}/emergency-contacts",
    "/api/v1/emergency-contacts/{contact_id}",
    "/api/v1/projects/{project_id}/zone-emergency-profiles",
    "/api/v1/zones/{zone_id}/emergency-profile",
    "/api/v1/projects/{project_id}/emergency-roster",
    "/api/v1/emergency-roster/{assignment_id}/end",
    "/api/v1/projects/{project_id}/rescue-teams",
    "/api/v1/rescue-teams/{team_id}",
    "/api/v1/projects/{project_id}/emergency-coverage",
    "/api/v1/projects/{project_id}/emergency-board",
    "/api/v1/projects/{project_id}/emergency-action-panel",
    "/api/v1/projects/{project_id}/emergency-info",
    "/api/v1/projects/{project_id}/emergency-assets",
    "/api/v1/emergency-assets/{asset_id}",
    "/api/v1/emergency-assets/{asset_id}/transitions",
    "/api/v1/projects/{project_id}/emergency-asset-checks",
    "/api/v1/emergency-asset-checks/{check_id}/void",
    "/api/v1/projects/{project_id}/drill-programme",
    "/api/v1/projects/{project_id}/drills",
    "/api/v1/drills/{drill_id}",
    "/api/v1/drills/{drill_id}/transitions",
    "/api/v1/drills/{drill_id}/evaluation",
    "/api/v1/musters/{muster_id}",
    "/api/v1/musters/{muster_id}/scan",
    "/api/v1/musters/{muster_id}/entries/{entry_id}/tick",
    "/api/v1/musters/{muster_id}/entries/{entry_id}/resolve",
    "/api/v1/musters/{muster_id}/counts",
    "/api/v1/musters/{muster_id}/sheet",
    "/api/v1/musters/{muster_id}/void",
    "/api/v1/projects/{project_id}/muster-devices",
    "/api/v1/muster-devices/{device_pk}/revoke",
    "/api/v1/emergency/muster-session",
    "/api/v1/emergency/muster-scan",
    "/api/v1/projects/{project_id}/emergency-events",
    "/api/v1/emergency-events/{event_id}",
    "/api/v1/emergency-events/{event_id}/transitions",
    "/api/v1/emergency-events/{event_id}/review",
    "/api/v1/permits/{permit_id}/drill-resume",
    "/api/v1/kpi/emergency",
}


def test_phase6c_paths_in_contract() -> None:
    spec = create_app().openapi()
    assert spec["info"]["version"] == "0.9.0"
    assert set(spec["paths"]) >= PHASE6C_PATHS
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))
    # P6c-3: events carry casualty counts only
    props = set(spec["components"]["schemas"]["EventRead"]["properties"])
    assert "casualties_count" in props and not {"casualty_names", "injured"} & props


def test_phase6c_enums_and_matrix() -> None:
    codes = {c.value for c in ErrorCode}
    assert {
        "ERP_INCOMPLETE", "ERP_NOT_APPROVED", "DRILL_FREQUENCY_TOO_LOW", "TIMELINE_ORDER",
        "ASSEMBLY_POINT_IN_RESTRICTED_AREA", "ZONE_WITHOUT_ASSEMBLY_POINT", "ALREADY_IN_TEAM",
        "CHECK_BACKDATED", "INCIDENT_LINK_REQUIRED", "RESCUE_PLAN_REF_REQUIRED",
    } <= codes  # fmt: skip
    assert {f"K-{n}" for n in range(104, 110)} <= {m.value for m in KpiMetric}
    assert {"E18", "E19"} <= {c.value for c in LeadingWarningCode}
    assert CaSourceType.emergency.value == "emergency"
    assert StatusReason.emergency_drill in ROUTINE_REASONS
    assert StatusReason.emergency not in ROUTINE_REASONS
    assert {PermitBlocker.RESCUE_TEAM_NOT_REGISTERED, PermitBlocker.RESCUE_DRILL_OVERDUE} <= set(
        PermitBlocker
    )
    assert {"HEIGHT_RESCUE_NOT_READY", "NO_READY_EXTINGUISHER"} <= {
        w.value for w in PermitWarningCode
    }
    assert {QrKind.EA, QrKind.MP} <= set(QrKind)
    for m in PHASE6C_METRICS:
        assert CATALOGUE[m].spec_ref.startswith("6c-emergency-drills §6.8")
    # §5.13: 180 is HSE Manager only; reps never plan or evaluate drills; viewers never write
    for role, caps in MATRIX.items():
        if role != Role.hse_manager:
            assert Capability.erp_approve not in caps, role
    assert Capability.drill_plan not in MATRIX[Role.contractor_hse_rep]
    assert Capability.drill_evaluate not in MATRIX[Role.permit_issuer]
    assert Capability.emergency_declare not in MATRIX[Role.viewer_client]
    assert Capability.emergency_declare in MATRIX[Role.oh_practitioner]
    assert Capability.emergency_void not in MATRIX[Role.site_engineer]
