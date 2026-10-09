"""Phase 6a contract surface: paths, enums, error codes and the capability matrix (spec
6a-occupational-health)."""

from app.core.cert_enums import HookReasonCode
from app.core.enums import Capability, Role
from app.core.errors import ErrorCode
from app.core.hse_enums import AiTool, KpiMetric, LeadingWarningCode
from app.kpi.catalogue import CATALOGUE, PHASE6A_METRICS
from app.main import create_app
from app.services.permissions import MANAGER_EXCLUDED, MATRIX

PHASE6A_PATHS = {
    "/api/v1/fitness-reference",
    "/api/v1/fitness-codes",
    "/api/v1/fitness-codes/{code}",
    "/api/v1/medical-providers",
    "/api/v1/medical-providers/{provider_id}",
    "/api/v1/medical-providers/{provider_id}/transitions",
    "/api/v1/medical-providers/{provider_id}/affected",
    "/api/v1/medical-examiners",
    "/api/v1/medical-examiners/{examiner_id}",
    "/api/v1/medical-examiners/{examiner_id}/transitions",
    "/api/v1/projects/{project_id}/medical-plan",
    "/api/v1/projects/{project_id}/medical-plan/lines",
    "/api/v1/medical-plan-lines/{line_id}",
    "/api/v1/medical-plan-lines/{line_id}/remove",
    "/api/v1/medical-plan-lines/{line_id}/versions",
    "/api/v1/projects/{project_id}/medical-exemptions",
    "/api/v1/deployments/{deployment_id}/health-profile",
    "/api/v1/deployments/{deployment_id}/fitness-requirements",
    "/api/v1/projects/{project_id}/fitness-gaps",
    "/api/v1/projects/{project_id}/fitness-assessments",
    "/api/v1/fitness-assessments/{assessment_id}",
    "/api/v1/fitness-assessments/{assessment_id}/transitions",
    "/api/v1/fitness-assessments/{assessment_id}/verifications",
    "/api/v1/fitness-assessments/{assessment_id}/scan-url",
    "/api/v1/workers/{worker_id}/fitness",
    "/api/v1/workers/{worker_id}/fitness-report",
    "/api/v1/projects/{project_id}/fitness-holds",
    "/api/v1/fitness-holds/{hold_id}",
    "/api/v1/fitness-holds/{hold_id}/cancel",
    "/api/v1/fitness-holds/{hold_id}/release",
    "/api/v1/projects/{project_id}/fitness-referrals",
    "/api/v1/fitness-referrals/{referral_id}",
    "/api/v1/fitness-referrals/{referral_id}/cancel",
    "/api/v1/projects/{project_id}/medical-settings",
    "/api/v1/projects/{project_id}/medical-hooks/enable",
    "/api/v1/medical-imports/template",
    "/api/v1/projects/{project_id}/medical-imports",
    "/api/v1/medical-imports/{batch_id}",
    "/api/v1/medical-imports/{batch_id}/commit",
    "/api/v1/medical-imports/{batch_id}/discard",
    "/api/v1/kpi/occupational-health",
}


def test_phase6a_paths_in_contract() -> None:
    spec = create_app().openapi()
    assert set(spec["paths"]) >= PHASE6A_PATHS
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))
    schemas = spec["components"]["schemas"]
    assert "medical_enabled" in schemas["HookPolicyRead"]["properties"]
    assert "band" in schemas["ReadinessSubject"]["properties"]
    assert "fitness" in schemas["PersonCheckCard"]["properties"]
    # P6-1 / FA-9: the typed ID is input-only; no clinical fields exist anywhere
    assert "id_on_card" in schemas["FitnessAssessmentCreate"]["properties"]
    assert "id_on_card" not in schemas["FitnessAssessmentRead"]["properties"]
    for name, schema in schemas.items():
        props = set(schema.get("properties", {}))
        assert not props & {"diagnosis", "test_results", "clinical_notes"}, name


def test_phase6a_enums_and_matrix() -> None:
    codes = {c.value for c in ErrorCode}
    assert {c.value for c in HookReasonCode} <= codes
    assert {"MEDICAL_HOLD", "MEDICAL_UNFIT", "MEDICAL_MISSING", "RESTRICTION_CONFLICT"} <= codes
    assert {f"K-{n}" for n in range(89, 97)} <= {m.value for m in KpiMetric}
    assert {"E14", "E15"} <= {c.value for c in LeadingWarningCode}
    assert AiTool.get_occupational_health_kpis.value == "get_occupational_health_kpis"
    for m in PHASE6A_METRICS:
        assert CATALOGUE[m].spec_ref.startswith("6a-occupational-health §6.6")
    # §5.15: capability 152 (site-clinic record) is never the HSE Manager's
    assert Capability.fitness_record_clinic in MANAGER_EXCLUDED
    oh = MATRIX[Role.oh_practitioner]
    assert Capability.fitness_record_clinic in oh
    assert Capability.fitness_clinical_view in oh
    viewer = MATRIX[Role.viewer_client]
    assert Capability.fitness_status_view not in viewer
    assert Capability.medical_kpi_view in viewer
    for role in (Role.permit_issuer, Role.permit_receiver):
        assert Capability.fitness_clinical_view not in MATRIX[role]
