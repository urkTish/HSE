"""Phase 6b contract surface: paths, enums, error codes and the capability matrix (spec
6b-heat-stress)."""

from app.core.enums import Capability, Role
from app.core.errors import ErrorCode
from app.core.hse_enums import AiTool, CaSourceType, KpiMetric, LeadingWarningCode
from app.core.ptw_enums import ROUTINE_REASONS, PauseReason, PermitBlocker, StatusReason
from app.kpi.catalogue import CATALOGUE, PHASE6B_METRICS
from app.main import create_app
from app.services.permissions import MATRIX

PHASE6B_PATHS = {
    "/api/v1/heat-reference",
    "/api/v1/projects/{project_id}/heat-settings",
    "/api/v1/heat-regime-table",
    "/api/v1/projects/{project_id}/heat-instruments",
    "/api/v1/heat-instruments/{instrument_id}",
    "/api/v1/heat-instruments/{instrument_id}/transitions",
    "/api/v1/heat-instruments/{instrument_id}/devices",
    "/api/v1/heat-instruments/{instrument_id}/devices/{device_pk}/revoke",
    "/api/v1/projects/{project_id}/monitoring-points",
    "/api/v1/monitoring-points/{point_id}",
    "/api/v1/projects/{project_id}/rest-stations",
    "/api/v1/rest-stations/{station_id}",
    "/api/v1/projects/{project_id}/wbgt-readings",
    "/api/v1/wbgt-readings/{reading_id}/void",
    "/api/v1/projects/{project_id}/wbgt-imports",
    "/api/v1/heat/station-session",
    "/api/v1/heat/station-readings",
    "/api/v1/projects/{project_id}/heat-board",
    "/api/v1/zones/{zone_id}/heat-state",
    "/api/v1/projects/{project_id}/heat-duty-list",
    "/api/v1/workers/{worker_id}/acclimatisation-status",
    "/api/v1/projects/{project_id}/acclimatisation-plans",
    "/api/v1/acclimatisation-plans/{plan_id}",
    "/api/v1/acclimatisation-plans/{plan_id}/prior-experience",
    "/api/v1/acclimatisation-plans/{plan_id}/days/{day_no}/confirm",
    "/api/v1/acclimatisation-plans/{plan_id}/cancel",
    "/api/v1/projects/{project_id}/heat-welfare-checks",
    "/api/v1/heat-welfare-checks/{check_id}/void",
    "/api/v1/projects/{project_id}/ban-patrols",
    "/api/v1/ban-patrols/{patrol_id}/void",
    "/api/v1/projects/{project_id}/ban-exemptions",
    "/api/v1/ban-exemptions/{exemption_id}/revoke",
    "/api/v1/projects/{project_id}/heat-illness-log",
    "/api/v1/heat-illness-log/{entry_id}",
    "/api/v1/heat-illness-log/{entry_id}/review",
    "/api/v1/heat-illness-log/{entry_id}/reopen",
    "/api/v1/projects/{project_id}/heat-action-panel",
    "/api/v1/projects/{project_id}/heat-season-reports",
    "/api/v1/permits/{permit_id}/heat-resume",
    "/api/v1/kpi/heat-stress",
}


def test_phase6b_paths_in_contract() -> None:
    spec = create_app().openapi()
    assert tuple(map(int, spec["info"]["version"].split("."))) >= (0, 8, 0)
    assert set(spec["paths"]) >= PHASE6B_PATHS
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))
    schemas = spec["components"]["schemas"]
    assert {"heat_workload", "heat_clothing", "heat_hood"} <= set(
        schemas["PermitRead"]["properties"]
    )
    assert "wbgt_reading_id" in schemas["PermitShiftRead"]["properties"]
    # §3.11: the log stores no clinical data
    assert not {"nature", "category", "diagnosis"} & set(schemas["HeatLogRead"]["properties"])


def test_phase6b_enums_and_matrix() -> None:
    codes = {c.value for c in ErrorCode}
    assert {
        "REGIME_LOOSENING", "PERIOD_TOO_SHORT", "HEAT_COVERAGE_INCOMPLETE", "WBGT_REQUIRED",
        "BACKDATED_READING", "NOT_IN_BAN_WINDOW", "NO_ACTIVE_EXEMPTION", "TOO_LATE_TO_CHANGE",
    } <= codes  # fmt: skip
    assert {f"K-{n}" for n in range(97, 104)} <= {m.value for m in KpiMetric}
    assert {"E16", "E17"} <= {c.value for c in LeadingWarningCode}
    assert AiTool.get_heat_stress_kpis.value == "get_heat_stress_kpis"
    assert CaSourceType.heat_check.value == "heat_check"
    assert StatusReason.heat_stress_stop in ROUTINE_REASONS
    assert PauseReason.heat_rest.value == "heat_rest"
    assert {PermitBlocker.HEAT_STOP, PermitBlocker.WBGT_READING_REQUIRED} <= set(PermitBlocker)
    for m in PHASE6B_METRICS:
        assert CATALOGUE[m].spec_ref.startswith("6b-heat-stress §6.6")
    # §5.13: 171 and 175 are HSE Manager only; contractors never record patrols (MB-1)
    for role, caps in MATRIX.items():
        if role != Role.hse_manager:
            assert Capability.heat_exemption_grant not in caps, role
            assert Capability.heat_settings_edit not in caps, role
    assert Capability.heat_patrol_record not in MATRIX[Role.contractor_hse_rep]
    assert Capability.heat_patrol_record not in MATRIX[Role.permit_receiver]
    assert Capability.heat_log_view not in MATRIX[Role.permit_receiver]
    assert Capability.heat_void in MATRIX[Role.hse_officer]
