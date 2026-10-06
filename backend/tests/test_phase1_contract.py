"""Phase 1 contract surface: paths, SSE schema and capability matrix."""

from app.core.enums import Capability
from app.main import create_app
from app.services.permissions import MATRIX, Role

PHASE1_PATHS = {
    "/api/v1/projects/{project_id}/workforce-returns",
    "/api/v1/projects/{project_id}/workforce-imports",
    "/api/v1/workforce-imports/{batch_id}/commit",
    "/api/v1/projects/{project_id}/incidents",
    "/api/v1/injury-cases/{case_id}",
    "/api/v1/incidents/{incident_id}/investigation",
    "/api/v1/projects/{project_id}/observations",
    "/api/v1/projects/{project_id}/inspection-plans",
    "/api/v1/projects/{project_id}/inspections",
    "/api/v1/projects/{project_id}/corrective-actions",
    "/api/v1/corrective-actions/{ca_id}/transitions",
    "/api/v1/projects/{project_id}/hse-meetings",
    "/api/v1/kpi/metrics/{metric}",
    "/api/v1/kpi/dashboard",
    "/api/v1/kpi/trends",
    "/api/v1/kpi/breakdowns",
    "/api/v1/kpi/pyramid",
    "/api/v1/kpi/leading-indicators",
    "/api/v1/kpi/comparisons",
    "/api/v1/dashboard/action-panel",
    "/api/v1/dashboard/expiring-items",
    "/api/v1/ai/ask",
    "/api/v1/ai/insights",
    "/api/v1/ai/monthly-report",
}


def test_phase1_paths_and_sse_schema_in_contract() -> None:
    spec = create_app().openapi()
    assert set(spec["paths"]) >= PHASE1_PATHS
    assert "AiStreamEvent" in spec["components"]["schemas"]
    sse = spec["paths"]["/api/v1/ai/ask"]["post"]["responses"]["200"]["content"]
    assert "text/event-stream" in sse


def test_phase1_capabilities_in_matrix() -> None:
    assert Capability.ai_ask in MATRIX[Role.viewer_client]
    assert Capability.injury_medical_view not in MATRIX[Role.contractor_hse_rep]
    assert Capability.hse_settings_edit not in MATRIX[Role.hse_officer]
