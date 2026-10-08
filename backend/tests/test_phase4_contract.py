"""Phase 4 contract surface (stage 1): paths, schemas, enums, error codes and capability
matrix (spec 4-third-party-cert)."""

import pytest

from app.api.routers import cert_config
from app.core.access_enums import GATE_WARN_CODES, GateReasonCode, QrKind
from app.core.cert_enums import HookReasonCode
from app.core.enums import Capability, ExportDataset, Role
from app.core.errors import ApiError, ErrorCode
from app.core.hse_enums import (
    ActionPanelItem,
    AiTool,
    CaSourceType,
    ChartId,
    ExpiringItemKind,
    KpiMetric,
    LeadingWarningCode,
)
from app.kpi.catalogue import CATALOGUE, PHASE4_METRICS
from app.main import create_app
from app.services.permissions import MANAGER_EXCLUDED, MATRIX

PHASE4_PATHS = {
    "/api/v1/tpis",
    "/api/v1/tpis/{tpi_id}",
    "/api/v1/tpis/{tpi_id}/transitions",
    "/api/v1/tpis/{tpi_id}/accreditations",
    "/api/v1/tpis/{tpi_id}/affected",
    "/api/v1/tpi-accreditations/{accreditation_id}/register-check",
    "/api/v1/projects/{project_id}/tpi-approvals",
    "/api/v1/equipment",
    "/api/v1/equipment/lookup",
    "/api/v1/equipment/{equipment_id}",
    "/api/v1/equipment/{equipment_id}/tag-out",
    "/api/v1/equipment/{equipment_id}/return-to-service",
    "/api/v1/equipment/{equipment_id}/blacklist",
    "/api/v1/equipment/{equipment_id}/configuration-events",
    "/api/v1/projects/{project_id}/equipment-deployments",
    "/api/v1/equipment-deployments/{deployment_id}/transitions",
    "/api/v1/equipment-deployments/{deployment_id}/arrival-inspection",
    "/api/v1/equipment-deployments/{deployment_id}/sticker",
    "/api/v1/projects/{project_id}/equipment-certificates",
    "/api/v1/projects/{project_id}/equipment-certificates/preview",
    "/api/v1/equipment-certificates/{certificate_id}/transitions",
    "/api/v1/equipment-certificates/{certificate_id}/verifications",
    "/api/v1/projects/{project_id}/verification-log",
    "/api/v1/projects/{project_id}/scaffolds",
    "/api/v1/scaffolds/{scaffold_id}/inspections",
    "/api/v1/projects/{project_id}/scaffold-board",
    "/api/v1/projects/{project_id}/scaffold-reinspection-requests",
    "/api/v1/projects/{project_id}/personnel-certificates",
    "/api/v1/personnel-certificates/{certificate_id}/scan-url",
    "/api/v1/personnel-certificates/{certificate_id}/verifications",
    "/api/v1/workers/{worker_id}/certificates",
    "/api/v1/projects/{project_id}/defects",
    "/api/v1/defects/{defect_id}/close",
    "/api/v1/incidents/{incident_id}/defect-prompt",
    "/api/v1/certification-bans",
    "/api/v1/certification-bans/{ban_id}/lift",
    "/api/v1/blacklist-register",
    "/api/v1/projects/{project_id}/cert-settings",
    "/api/v1/cert-catalogue",
    "/api/v1/cert-types",
    "/api/v1/projects/{project_id}/hook-policy",
    "/api/v1/projects/{project_id}/hook-policy/{kind}/switch",
    "/api/v1/projects/{project_id}/hook-policy/{kind}/deferral",
    "/api/v1/projects/{project_id}/hook-readiness",
    "/api/v1/projects/{project_id}/certificate-imports",
    "/api/v1/certificate-imports/template",
    "/api/v1/certificate-imports/{batch_id}/commit",
    "/api/v1/certification-checks",
    "/api/v1/kpi/certification",
}


def test_phase4_paths_in_contract() -> None:
    spec = create_app().openapi()
    assert spec["info"]["version"] == "0.5.0"
    assert set(spec["paths"]) >= PHASE4_PATHS
    schemas = spec["components"]["schemas"]
    qr = schemas["EquipmentStickerRead"]["properties"]["qr_payload"]
    assert qr["pattern"] == r"^HSE2:EQ:[A-Za-z0-9_-]{22}$"
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))
    # additive fields on earlier contracts
    assert "equipment" in schemas["GateCheckResponse"]["properties"]
    assert "cert_band" in schemas["DashboardResponse"]["properties"]
    assert "cert_limiting_factor" in schemas["ExpiringItem"]["properties"]
    eq_in = schemas["PermitEquipmentInput"]["properties"]
    assert {"equipment_item_id", "operator_worker_id"} <= set(eq_in)
    eq_out = schemas["PermitEquipmentRead"]["properties"]
    assert {"equipment_item", "operator", "operator_hooks", "conditions", "swl_t"} <= set(eq_out)
    assert {"hard_stop", "hook_reason_code", "conditions"} <= set(
        schemas["EligibilityItem"]["properties"]
    )
    assert "calibration_body_id" in schemas["DetectorCreate"]["properties"]
    assert "equipment_item_id" in schemas["ObstacleCreate"]["properties"]
    # PC-3: the typed ID is input-only and never in a read model
    assert "id_on_card" in schemas["PersonnelCertCreate"]["properties"]
    assert "id_on_card" not in schemas["PersonnelCertRead"]["properties"]


def test_phase4_stubs_raise_501() -> None:
    with pytest.raises(ApiError) as exc:
        cert_config.get_cert_catalogue(None, None)  # type: ignore[arg-type]
    assert exc.value.status_code == 501
    assert exc.value.code == ErrorCode.NOT_IMPLEMENTED


def test_phase4_enums_and_codes() -> None:
    assert {c.value for c in HookReasonCode} <= {c.value for c in ErrorCode}
    assert QrKind.EQ.value == "EQ"
    for code in (
        "EQUIPMENT_BLACKLISTED",
        "EQUIPMENT_NOT_DEPLOYED",
        "EQUIPMENT_NOT_APPROVED",
        "EQUIPMENT_OUT_OF_SERVICE",
        "EQUIPMENT_QUARANTINED",
    ):
        assert GateReasonCode(code) not in GATE_WARN_CODES
    for code in ("HOOK_NOT_MET_WARN", "ARRIVAL_INSPECTION_DUE", "ALSO_SCAN_VEHICLE_STICKER"):
        assert GateReasonCode(code) in GATE_WARN_CODES
    assert {f"K-{n}" for n in range(72, 82)} <= {m.value for m in KpiMetric}
    assert {"E10", "E11"} <= {c.value for c in LeadingWarningCode}
    assert {"C16", "C17", "C18"} <= {c.value for c in ChartId}
    assert AiTool.get_certification_kpis.value == "get_certification_kpis"
    assert CaSourceType.equipment_defect.value == "equipment_defect"
    assert {
        "equipment_cert_expiry",
        "personnel_cert_expiry",
        "scaffold_inspection_due",
        "defect_rectification_due",
        "tpi_accreditation_expiry",
        "tpi_client_approval_expiry",
        "certificate_verification_due",
        "hook_block_date",
    } <= {k.value for k in ExpiringItemKind}
    assert len(ActionPanelItem) >= 12
    assert len(PHASE4_METRICS) == 10
    for m in PHASE4_METRICS:
        assert not CATALOGUE[m].available  # Stage 1: catalogued, not computed yet
        assert CATALOGUE[m].spec_ref.startswith("4-third-party-cert §6.7")
    assert ExportDataset.equipment_certificates.value == "equipment_certificates"


def test_phase4_capabilities_in_matrix() -> None:
    officer = MATRIX[Role.hse_officer]
    for cap in (Capability.cert_blacklist, Capability.cert_settings_edit):
        assert cap in MATRIX[Role.hse_manager]
        assert cap not in MANAGER_EXCLUDED
        for role in Role:
            if role != Role.hse_manager:
                assert cap not in MATRIX[role], (role, cap)
    assert Capability.cert_review in officer
    assert Capability.cert_review not in MATRIX[Role.site_engineer]
    assert Capability.scaffold_inspect in MATRIX[Role.site_engineer]
    assert Capability.personnel_cert_view not in MATRIX[Role.viewer_client]
    assert Capability.cert_kpi_view in MATRIX[Role.viewer_client]
    assert Capability.personnel_cert_scan_view in MATRIX[Role.contractor_hse_rep]
    assert Capability.cert_import in MATRIX[Role.contractor_hse_rep]
    assert Capability.equipment_edit not in MATRIX[Role.permit_issuer]
    assert Capability.cert_check in MATRIX[Role.permit_receiver]
    assert Capability.defect_close not in MATRIX[Role.contractor_hse_rep]
