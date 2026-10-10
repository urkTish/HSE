"""Phase 6g contract surface: paths, enums, error codes, the capability matrix and the schema
names of earlier phases (spec 6g-scorecard-reports; DECISIONS D-202 `Sc` / `Rp` / `Xp`)."""

import inspect
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.core import scorecard_enums
from app.core.enums import Capability, Role
from app.core.errors import ErrorCode
from app.core.hse_enums import CaSourceType, KpiMetric, LeadingWarningCode
from app.kpi.catalogue import CATALOGUE, PHASE6G_METRICS
from app.main import create_app
from app.schemas import scorecard as schemas
from app.services.permissions import MATRIX

PHASE6G_PATHS = {
    "/api/v1/scorecard-reference",
    "/api/v1/projects/{project_id}/scorecard-settings",
    "/api/v1/projects/{project_id}/scorecard-settings/confirm-sources",
    "/api/v1/scorecard-profiles",
    "/api/v1/scorecard-profiles/{profile_id}",
    "/api/v1/scorecard-profiles/{profile_id}/activate",
    "/api/v1/projects/{project_id}/scorecards",
    "/api/v1/scorecards/{card_id}",
    "/api/v1/scorecards/{card_id}/lines/{metric_code}",
    "/api/v1/projects/{project_id}/scorecard-ranking",
    "/api/v1/projects/{project_id}/scorecards/finalise",
    "/api/v1/scorecards/{card_id}/reissue",
    "/api/v1/scorecards/{card_id}/remarks",
    "/api/v1/projects/{project_id}/scorecard-remarks",
    "/api/v1/scorecard-remarks/{remark_id}/resolve",
    "/api/v1/scorecard-remarks/{remark_id}/withdraw",
    "/api/v1/projects/{project_id}/watch-list",
    "/api/v1/watch-list/{entry_id}",
    "/api/v1/watch-list/{entry_id}/transitions",
    "/api/v1/watch-list/{entry_id}/suspension-form",
    "/api/v1/contractors/{contractor_id}/performance-summary",
    "/api/v1/projects/{project_id}/report-packs",
    "/api/v1/report-packs",
    "/api/v1/report-packs/{pack_id}",
    "/api/v1/report-packs/{pack_id}/transitions",
    "/api/v1/report-packs/{pack_id}/reissue",
    "/api/v1/report-packs/{pack_id}/files/{kind}/url",
    "/api/v1/report-packs/{pack_id}/deliveries",
    "/api/v1/projects/{project_id}/distribution-lists/{report_type}",
    "/api/v1/export-datasets",
    "/api/v1/exports",
    "/api/v1/export-jobs",
    "/api/v1/export-jobs/{job_id}",
    "/api/v1/export-jobs/{job_id}/file-url",
    "/api/v1/export-subscriptions",
    "/api/v1/export-subscriptions/{subscription_id}",
    "/api/v1/dashboard-print",
    "/api/v1/kpi/scorecards",
}
CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "openapi.yaml"
PREFIXES = ("Sc", "Rp", "Xp")


def test_phase6g_paths_and_schema_names() -> None:
    spec = create_app().openapi()
    assert tuple(map(int, spec["info"]["version"].split("."))) >= (0, 13, 0)
    assert set(spec["paths"]) >= PHASE6G_PATHS
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))
    names = set(spec["components"]["schemas"])
    # every 6g schema and enum class carries a 6g prefix (D-202) and is exported under its name
    ours = {n for n, c in inspect.getmembers(schemas, inspect.isclass)
            if issubclass(c, BaseModel) and c.__module__ == schemas.__name__}  # fmt: skip
    ours |= {n for n, c in inspect.getmembers(scorecard_enums, inspect.isclass)
             if c.__module__ == scorecard_enums.__name__}  # fmt: skip
    assert ours and all(n.startswith(PREFIXES) for n in ours)
    assert {"ScCardRead", "RpPackDetail", "XpJobRead", "ScPillar"} <= names
    # every schema name exported before 6g is still present (no clash renamed an older one)
    committed = set(yaml.safe_load(CONTRACT.read_text())["components"]["schemas"])
    assert committed - names == set()


def test_phase6g_enums_and_matrix() -> None:
    codes = {c.value for c in ErrorCode}
    assert {
        "WEIGHTS_NOT_100", "LAGGING_WEIGHT_OUT_OF_RANGE", "CAP_REQUIRED", "PROFILE_BACKDATED",
        "SOURCES_NOT_CONFIRMED", "COMMENT_WINDOW_CLOSED", "COMMENT_WINDOW_OPEN", "DISPUTES_OPEN",
        "CORRECTION_NOT_FOUND", "CAP_NOT_EXCLUDABLE", "WATCH_ENTRY_OPEN", "PIP_INCOMPLETE",
        "SOURCE_REPORT_NOT_PUBLISHED", "SELF_REVIEW", "RECIPIENT_SCOPE", "EXTERNAL_NOT_ALLOWED",
        "PACK_TOO_LARGE_FOR_EMAIL", "COLUMN_NOT_EXPORTABLE", "PURPOSE_REQUIRED",
        "EXPORT_TOO_LARGE", "SUBSCRIPTION_PERSONAL_DATA", "IDENTITY_IN_TEXT",
        "SETTING_OUT_OF_RANGE", "COLUMN_NOT_PERMITTED", "PACK_ISSUED_IMMUTABLE",
        "SCORECARD_FINAL", "EXPORT_RATE_LIMIT",
    } <= codes  # fmt: skip
    assert {f"K-{n}" for n in range(132, 136)} <= {m.value for m in KpiMetric}
    assert "E25" in {c.value for c in LeadingWarningCode}
    assert CaSourceType.scorecard.value == "scorecard"
    for m in PHASE6G_METRICS:
        assert CATALOGUE[m].spec_ref.startswith("6g-scorecard-reports §6.7")
    manager_only = {Capability.scorecard_settings, Capability.scorecard_manage,
                    Capability.report_pack_issue}  # fmt: skip
    for role, caps in MATRIX.items():
        if role != Role.hse_manager:
            assert not manager_only & set(caps), role
        assert Capability.export_log in caps, role
    assert Capability.scorecard_view in MATRIX[Role.contractor_hse_rep]
    assert Capability.scorecard_resolve not in MATRIX[Role.contractor_hse_rep]
    assert Capability.scorecard_comment not in MATRIX[Role.viewer_client]
    assert Capability.report_pack_prepare in MATRIX[Role.hse_officer]
