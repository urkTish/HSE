"""Option 7a contract surface: paths, schema names, enums and error codes (spec
7a-vehicle-accident-details; DECISIONS D-202 `Veh` prefix)."""

from pathlib import Path

import yaml

from app.core.enums import EntityType, ExportDataset, NotificationKind
from app.core.errors import ErrorCode
from app.core.hse_enums import KpiMetric
from app.kpi.catalogue import CATALOGUE, LAGGING_TILES, PHASE7A_METRICS
from app.main import create_app

PHASE7A_PATHS = {
    "/api/v1/incidents/{incident_id}/vehicles",
    "/api/v1/incident-vehicles/{vehicle_row_id}",
    "/api/v1/incidents/{incident_id}/vehicle-prefill",
    "/api/v1/incidents/{incident_id}/accident-report",
    "/api/v1/incidents/{incident_id}/accident-report/files",
}
CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "openapi.yaml"


def test_phase7a_paths_and_schema_names() -> None:
    spec = create_app().openapi()
    assert tuple(map(int, spec["info"]["version"].split("."))) >= (0, 14, 0)
    assert set(spec["paths"]) >= PHASE7A_PATHS
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))
    names = set(spec["components"]["schemas"])
    assert {
        "VehIncidentVehicleRead", "VehIncidentVehicleCreate", "VehIncidentVehicleUpdate",
        "VehAccidentReportRead", "VehAccidentReportUpdate", "VehSectionRead", "VehPrefillRead",
    } <= names  # fmt: skip
    assert not {n for n in names if n.startswith("Vehicle") and "Incident" in n}
    committed = set(yaml.safe_load(CONTRACT.read_text())["components"]["schemas"])
    assert committed - names == set()
    inc = spec["components"]["schemas"]["IncidentRead"]["properties"]
    assert {"vehicle_involved", "recorded_not_counted", "vehicle_section"} <= set(inc)
    sec = spec["components"]["schemas"]["VehSectionRead"]["properties"]
    assert {"road_type", "journey_purpose", "vehicles", "accident_report"} <= set(sec)


def test_phase7a_enums_and_codes() -> None:
    codes = {c.value for c in ErrorCode}
    assert {
        "VEHICLE_REQUIRED", "VEHICLE_SECTION_INCOMPLETE", "ACCIDENT_REPORT_AUTHORITY_REQUIRED",
        "ACCIDENT_REPORT_MISSING", "PLATE_IS_REGISTERED", "ACCIDENT_REPORT_LOCKED",
        "VEHICLE_INVOLVED_LOCKED",
    } <= codes  # fmt: skip
    assert {"K-136", "K-137"} <= {m.value for m in KpiMetric}
    for m in PHASE7A_METRICS:
        assert CATALOGUE[m].spec_ref.startswith("7a-vehicle-accident-details §6.1")
    assert KpiMetric.K136 in LAGGING_TILES
    assert EntityType.incident_vehicle.value == "incident_vehicle"
    assert {"vehicle_docs_not_valid", "accident_report_missing"} <= {
        k.value for k in NotificationKind
    }
    assert ExportDataset.incident_vehicles.value == "incident_vehicles"
