"""Phase 2 contract surface (stage 1): paths, schemas, enums and capability matrix."""

from app.core.access_enums import GateReasonCode
from app.core.enums import Capability, Role
from app.core.hse_enums import ExpiringItemKind, KpiMetric, LeadingWarningCode
from app.main import create_app
from app.services.permissions import MATRIX

PHASE2_PATHS = {
    "/api/v1/workers",
    "/api/v1/workers/lookup",
    "/api/v1/workers/{worker_id}/id-number/unmask",
    "/api/v1/projects/{project_id}/deployments",
    "/api/v1/deployments/{deployment_id}/access-card",
    "/api/v1/projects/{project_id}/induction-courses",
    "/api/v1/projects/{project_id}/inductions",
    "/api/v1/zones/{zone_id}/access-profile",
    "/api/v1/workers/{worker_id}/eligibility",
    "/api/v1/projects/{project_id}/pass-applications",
    "/api/v1/pass-applications/{application_id}/issue",
    "/api/v1/projects/{project_id}/airport-passes",
    "/api/v1/projects/{project_id}/adps",
    "/api/v1/projects/{project_id}/airside-offences",
    "/api/v1/projects/{project_id}/vehicles",
    "/api/v1/projects/{project_id}/avps",
    "/api/v1/projects/{project_id}/notam-requests",
    "/api/v1/projects/{project_id}/obstacle-clearances",
    "/api/v1/projects/{project_id}/waps",
    "/api/v1/projects/{project_id}/ops-events",
    "/api/v1/credentials/{kind}/{credential_id}/suspend",
    "/api/v1/credentials/{kind}/{credential_id}/loss",
    "/api/v1/projects/{project_id}/gates",
    "/api/v1/gate-device/login",
    "/api/v1/gate-checks",
    "/api/v1/projects/{project_id}/gate-log",
    "/api/v1/projects/{project_id}/access-settings",
    "/api/v1/kpi/access",
}


def test_phase2_paths_in_contract() -> None:
    spec = create_app().openapi()
    assert set(spec["paths"]) >= PHASE2_PATHS
    schemas = spec["components"]["schemas"]
    qr = schemas["AccessCardRead"]["properties"]["qr_payload"]
    assert qr["pattern"] == r"^HSE2:AC:[A-Za-z0-9_-]{22}$"
    assert "gateSessionCookie" in spec["components"]["securitySchemes"]


def test_phase2_enums() -> None:
    assert {"K-48", "K-53b", "K-60"} <= {m.value for m in KpiMetric}
    assert {"E5", "E6", "E7"} <= {c.value for c in LeadingWarningCode}
    assert ExpiringItemKind.pass_return_due.value == "pass_return_due"
    assert next(iter(GateReasonCode)) == GateReasonCode.TOKEN_UNKNOWN


def test_phase2_capabilities_in_matrix() -> None:
    assert Capability.worker_unmask_id not in MATRIX[Role.site_engineer]
    assert Capability.worker_view not in MATRIX[Role.viewer_client]
    assert Capability.access_kpi_view in MATRIX[Role.viewer_client]
    assert Capability.access_settings_edit not in MATRIX[Role.hse_officer]
    assert Capability.worker_ban not in MATRIX[Role.hse_officer]
    assert Capability.wap_approve in MATRIX[Role.permit_issuer]
