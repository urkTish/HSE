"""Phase 3 contract surface (stage 1): paths, schemas, enums, error codes and capability
matrix."""

from app.core.enums import Capability, Role
from app.core.errors import ErrorCode
from app.core.hse_enums import ChartId, KpiMetric, LeadingWarningCode
from app.core.ptw_enums import PermitBlocker, PermitType
from app.kpi.catalogue import CATALOGUE, PHASE3_METRICS
from app.main import create_app
from app.services.permissions import MANAGER_CAPABILITIES, MANAGER_EXCLUDED, MATRIX

PHASE3_PATHS = {
    "/api/v1/auth/reauth",
    "/api/v1/projects/{project_id}/permit-types",
    "/api/v1/zones/{zone_id}/ptw-profile",
    "/api/v1/projects/{project_id}/zone-adjacency",
    "/api/v1/projects/{project_id}/simops-rules",
    "/api/v1/ptw/risk-matrix",
    "/api/v1/projects/{project_id}/ptw-settings",
    "/api/v1/projects/{project_id}/ptw-appointments",
    "/api/v1/projects/{project_id}/permits",
    "/api/v1/permits/{permit_id}",
    "/api/v1/permits/{permit_id}/crew",
    "/api/v1/permits/{permit_id}/sections",
    "/api/v1/permits/{permit_id}/checklist",
    "/api/v1/permits/{permit_id}/request",
    "/api/v1/permits/{permit_id}/approve",
    "/api/v1/permits/{permit_id}/issue",
    "/api/v1/permits/{permit_id}/receiver-acceptance",
    "/api/v1/permits/{permit_id}/start",
    "/api/v1/permits/{permit_id}/suspend",
    "/api/v1/permits/{permit_id}/revalidate",
    "/api/v1/permits/{permit_id}/close",
    "/api/v1/permits/{permit_id}/handovers",
    "/api/v1/permit-handovers/{handover_id}/accept",
    "/api/v1/permits/{permit_id}/readiness",
    "/api/v1/permits/{permit_id}/print",
    "/api/v1/projects/{project_id}/ptw-board",
    "/api/v1/permits/{permit_id}/jsa",
    "/api/v1/jsas/{jsa_id}/residual-acceptances",
    "/api/v1/projects/{project_id}/gas-detectors",
    "/api/v1/gas-detectors/{detector_id}/bump-tests",
    "/api/v1/permits/{permit_id}/gas-tests",
    "/api/v1/permits/{permit_id}/gas-tests/preview",
    "/api/v1/projects/{project_id}/isolations",
    "/api/v1/isolations/{isolation_id}/points/{point_id}/verify",
    "/api/v1/personal-lock-events/{event_id}/cut",
    "/api/v1/projects/{project_id}/locks",
    "/api/v1/projects/{project_id}/simops-check",
    "/api/v1/permits/{permit_id}/simops-check",
    "/api/v1/simops-conflicts/{conflict_id}/coordination",
    "/api/v1/simops-coordinations/{coordination_id}/sign",
    "/api/v1/projects/{project_id}/ptw-audits",
    "/api/v1/ptw-audits/{audit_id}/complete",
    "/api/v1/kpi/ptw",
}


def test_phase3_paths_in_contract() -> None:
    spec = create_app().openapi()
    assert tuple(map(int, spec["info"]["version"].split("."))) >= (0, 4, 0)
    assert set(spec["paths"]) >= PHASE3_PATHS
    schemas = spec["components"]["schemas"]
    qr = schemas["PermitPrintRead"]["properties"]["qr_payload"]
    assert qr["pattern"] == r"^HSE2:PT:[A-Za-z0-9_-]{22}$"
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))


def test_phase3_enums_and_codes() -> None:
    assert {b.value for b in PermitBlocker} <= {c.value for c in ErrorCode}
    assert {"K-46b", "K-61", "K-71"} <= {m.value for m in KpiMetric}
    assert {"E8", "E9"} <= {c.value for c in LeadingWarningCode}
    assert {"C13", "C14", "C15"} <= {c.value for c in ChartId}
    assert len(PermitType) == 9
    for m in PHASE3_METRICS:
        assert CATALOGUE[m].available  # Stage 2: implemented
        assert CATALOGUE[m].spec_ref.startswith("3-ptw §6.11")


def test_phase3_capabilities_in_matrix() -> None:
    assert {
        Capability.permit_prepare,
        Capability.permit_receive,
        Capability.permit_area_review,
        Capability.permit_issue,
        Capability.isolation_manage,
        Capability.personal_lock_record,
        Capability.deisolation_authorise,
        Capability.simops_coordinate,
    } == MANAGER_EXCLUDED - {Capability.fitness_record_clinic}  # + Phase 6a MP-8
    assert set(MATRIX[Role.hse_manager]) == set(MANAGER_CAPABILITIES)
    assert Capability.lock_cut_approve in MATRIX[Role.hse_manager]
    assert Capability.permit_issue in MATRIX[Role.permit_issuer]
    assert Capability.permit_issue not in MATRIX[Role.hse_officer]
    assert Capability.permit_receive in MATRIX[Role.permit_receiver]
    assert Capability.ptw_settings_edit not in MATRIX[Role.hse_officer]
    assert Capability.lock_cut_approve not in MATRIX[Role.hse_officer]
    assert Capability.ptw_exemption_grant not in MATRIX[Role.hse_officer]
    assert Capability.permit_prepare in MATRIX[Role.contractor_hse_rep]
    assert Capability.permit_view in MATRIX[Role.viewer_client]
    assert Capability.permit_prepare not in MATRIX[Role.viewer_client]
