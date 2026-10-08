"""Phase 5 contract surface: paths, schemas, enums, error codes, capability matrix and the
former stage-1 stubs now answering (spec 5-training)."""

from app.core.access_enums import HookKind, QrKind
from app.core.cert_enums import HookReasonCode
from app.core.enums import Capability, EntityType, ExportDataset, NotificationKind, Role
from app.core.errors import ErrorCode
from app.core.hse_enums import (
    ActionPanelItem,
    AiTool,
    ChartId,
    ExpiringItemKind,
    KpiMetric,
    KpiWarning,
    LeadingWarningCode,
)
from app.core.train_enums import ProviderUnacceptableReason
from app.kpi.catalogue import CATALOGUE, PHASE5_METRICS
from app.main import create_app
from app.services.permissions import MANAGER_EXCLUDED, MATRIX
from tests.cert_helpers import API, project
from tests.conftest import Api

PHASE5_PATHS = {
    "/api/v1/training-courses",
    "/api/v1/training-courses/{code}",
    "/api/v1/training-providers",
    "/api/v1/training-providers/{provider_id}",
    "/api/v1/training-providers/{provider_id}/transitions",
    "/api/v1/training-providers/{provider_id}/affected",
    "/api/v1/training-providers/{provider_id}/acceptability",
    "/api/v1/training-providers/{provider_id}/accreditations",
    "/api/v1/training-provider-accreditations/{accreditation_id}",
    "/api/v1/training-provider-accreditations/{accreditation_id}/register-check",
    "/api/v1/projects/{project_id}/trainer-authorisations",
    "/api/v1/trainer-authorisations/{authorisation_id}",
    "/api/v1/trainer-authorisations/{authorisation_id}/transitions",
    "/api/v1/projects/{project_id}/training-matrix",
    "/api/v1/projects/{project_id}/training-matrix/lines",
    "/api/v1/training-matrix-lines/{line_id}",
    "/api/v1/training-matrix-lines/{line_id}/remove",
    "/api/v1/training-matrix-lines/{line_id}/versions",
    "/api/v1/deployments/{deployment_id}/training-profile",
    "/api/v1/deployments/{deployment_id}/training-requirements",
    "/api/v1/projects/{project_id}/training-exemptions",
    "/api/v1/training-exemptions/{exemption_id}/withdraw",
    "/api/v1/projects/{project_id}/training-gaps",
    "/api/v1/projects/{project_id}/training-gaps/summary",
    "/api/v1/projects/{project_id}/refresher-plan",
    "/api/v1/workers/{worker_id}/training-retraining-notes",
    "/api/v1/projects/{project_id}/training-sessions",
    "/api/v1/projects/{project_id}/training-sessions/from-plan",
    "/api/v1/training-sessions/{session_id}",
    "/api/v1/training-sessions/{session_id}/transitions",
    "/api/v1/training-sessions/{session_id}/close",
    "/api/v1/training-sessions/{session_id}/void",
    "/api/v1/training-sessions/{session_id}/nominations",
    "/api/v1/training-sessions/{session_id}/attendance",
    "/api/v1/training-sessions/{session_id}/assessments",
    "/api/v1/training-nominations/{nomination_id}/withdraw",
    "/api/v1/training-nominations/{nomination_id}/signature",
    "/api/v1/projects/{project_id}/training-records",
    "/api/v1/projects/{project_id}/training-records/preview",
    "/api/v1/training-records/{record_id}",
    "/api/v1/training-records/{record_id}/transitions",
    "/api/v1/training-records/{record_id}/verifications",
    "/api/v1/training-records/{record_id}/scan-url",
    "/api/v1/training-records/{record_id}/certificate",
    "/api/v1/training-records/{record_id}/certificate/reissue",
    "/api/v1/projects/{project_id}/training-verification-log",
    "/api/v1/workers/{worker_id}/training-records",
    "/api/v1/workers/{worker_id}/training-report",
    "/api/v1/projects/{project_id}/training-settings",
    "/api/v1/projects/{project_id}/training-hooks/enable",
    "/api/v1/projects/{project_id}/training-hours",
    "/api/v1/training-imports/template",
    "/api/v1/projects/{project_id}/training-imports",
    "/api/v1/training-imports/{batch_id}",
    "/api/v1/training-imports/{batch_id}/commit",
    "/api/v1/training-imports/{batch_id}/discard",
    "/api/v1/kpi/training",
}


def test_phase5_paths_in_contract() -> None:
    spec = create_app().openapi()
    assert spec["info"]["version"] == "0.6.0"
    assert set(spec["paths"]) >= PHASE5_PATHS
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))
    schemas = spec["components"]["schemas"]
    qr = schemas["TrainingCertificatePrint"]["properties"]["qr_payload"]
    assert qr["pattern"] == r"^HSE2:TR:[A-Za-z0-9_-]{22}$"
    # additive fields on earlier contracts
    assert "training_band" in schemas["DashboardResponse"]["properties"]
    assert {"data_source", "notes"} <= set(schemas["KpiValue"]["properties"])
    assert "training_register_from" in schemas["HseSettingsRead"]["properties"]
    assert "training_register_from" in schemas["HseSettingsUpdate"]["properties"]
    assert "training_enabled" in schemas["HookPolicyRead"]["properties"]
    assert "training_record" in schemas["CertCheckResponse"]["properties"]
    assert "training" in schemas["PersonCheckCard"]["properties"]
    # TR-6: the typed ID is input-only and never in a read model
    assert "id_on_card" in schemas["TrainingRecordCreate"]["properties"]
    assert "id_on_card" not in schemas["TrainingRecordRead"]["properties"]
    kpi_params = {p["name"] for p in spec["paths"]["/api/v1/kpi/training"]["get"]["parameters"]}
    assert {"trade", "course_code", "course_category", "group_by"} <= kpi_params


def test_phase5_enums_and_codes() -> None:
    codes = {c.value for c in ErrorCode}
    assert {c.value for c in HookReasonCode} <= codes
    assert {r.value for r in ProviderUnacceptableReason} <= codes
    assert {
        "TRAINING_MISSING",
        "TRAINING_EXPIRED",
        "TRAINING_PENDING_REVIEW",
        "TRAINING_UNVERIFIED",
        "TRAINING_SUSPENDED",
        "TRAINING_REVOKED",
        "TRAINING_VERIFICATION_FAILED",
        "INDUCTION_NOT_VALID",
        "HOLDER_NOT_LINKED",
    } <= {c.value for c in HookReasonCode}
    assert QrKind.TR.value == "TR"
    assert HookKind.training_course.value == "training_course"
    assert {f"K-{n}" for n in range(82, 89)} <= {m.value for m in KpiMetric}
    assert {"E12", "E13"} <= {c.value for c in LeadingWarningCode}
    assert {"C19", "C20", "C21"} <= {c.value for c in ChartId}
    assert {"TRAINING_REGISTER_DIFFERS", "SESSIONS_NOT_CLOSED"} <= {w.value for w in KpiWarning}
    assert AiTool.get_training_kpis.value == "get_training_kpis"
    assert {
        "training_record_expiry",
        "training_refresher_due",
        "trainer_authorisation_expiry",
        "training_provider_accreditation_expiry",
        "training_verification_due",
        "training_session_close_due",
    } <= {k.value for k in ExpiringItemKind}
    assert sum(1 for a in ActionPanelItem if a.value.startswith("training_")) == 10
    assert sum(1 for k in NotificationKind if "training" in k.value or "trainer" in k.value) >= 20
    assert EntityType.training_record.value == "training_record"
    assert len(PHASE5_METRICS) == 7
    for m in PHASE5_METRICS:
        assert CATALOGUE[m].available  # computed since stage 2
        assert CATALOGUE[m].spec_ref.startswith("5-training §6.8")
    assert ExportDataset.training_records.value == "training_records"


def test_phase5_capabilities_in_matrix() -> None:
    p5 = [c for c in Capability if c.value.startswith(("training", "trainer", "export.training"))]
    assert len(p5) == 21
    for cap in p5:
        assert cap in MATRIX[Role.hse_manager]
        assert cap not in MANAGER_EXCLUDED
    for cap in (
        Capability.training_course_edit,
        Capability.training_provider_decide,
        Capability.training_settings_edit,
    ):
        for role in Role:
            if role != Role.hse_manager:
                assert cap not in MATRIX[role], (role, cap)
    officer = MATRIX[Role.hse_officer]
    assert Capability.training_session_close in officer
    assert Capability.training_record_review in officer
    rep = MATRIX[Role.contractor_hse_rep]
    assert Capability.training_session_manage in rep
    assert Capability.training_scan_view in rep
    assert Capability.training_record_review not in rep
    assert Capability.training_session_close not in rep
    site = MATRIX[Role.site_engineer]
    assert Capability.training_nominate in site
    assert Capability.training_profile_edit in site
    assert Capability.export_training in site
    assert Capability.export_training not in MATRIX[Role.permit_issuer]
    viewer = MATRIX[Role.viewer_client]
    assert set(viewer) & set(p5) == {
        Capability.training_catalogue_view,
        Capability.training_kpi_view,
        Capability.export_training,
    }
    assert Capability.training_check in MATRIX[Role.permit_receiver]


def test_phase5_endpoints_implemented(train_seed: None, clock: None, db: object, api: Api) -> None:
    from sqlalchemy.orm import Session

    assert isinstance(db, Session)
    c = api.as_("faisal.harbi")
    pid = project(db, "ANIA-EXP").id
    for url in (
        "/training-courses",
        "/training-providers",
        f"/projects/{pid}/training-matrix",
        f"/projects/{pid}/training-sessions",
        f"/projects/{pid}/training-records",
        f"/projects/{pid}/training-settings",
        f"/projects/{pid}/training-gaps/summary",
        f"/kpi/training?project_id={pid}",
        f"/kpi/charts/C19?project_id={pid}",
        f"/exports/training_records?project_id={pid}",
        f"/projects/{pid}/hook-readiness?kind=training_course",
    ):
        res = c.get(API + url)
        assert res.status_code < 500, (url, res.text)
        assert res.status_code in (200, 409), (url, res.text)
    # earlier contracts keep working: null training_register_from is accepted (ignored; the
    # seeded date stays, since the date may only move earlier, TH-6)
    res = c.patch(f"{API}/projects/{pid}/hse-settings", json={"training_register_from": None})
    assert res.status_code == 200, res.text
    assert res.json()["training_register_from"] == "2026-09-01"
