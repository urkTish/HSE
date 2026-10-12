"""Option 7b contract surface (spec 7b-fleet-driver v2.0, Prototype): paths, schema names, enums,
error codes, KPIs, datasets, capabilities and the version (DECISIONS D-202 prefix `SiteVeh`)."""

from pathlib import Path

import yaml

from app.core.enums import Capability, EntityType, ExportDataset, NotificationKind, Role
from app.core.errors import ErrorCode
from app.core.field_enums import ResponseOwnerType
from app.core.hse_enums import CaSourceType, ExpiringItemKind, KpiMetric
from app.kpi.catalogue import CATALOGUE, PHASE7B_METRICS
from app.main import create_app
from app.services.permissions import MATRIX

P = "/api/v1"
PHASE7B_PATHS = {
    f"{P}/projects/{{project_id}}/site-vehicle-settings",
    f"{P}/site-vehicles/reference",
    f"{P}/projects/{{project_id}}/site-vehicles",
    f"{P}/projects/{{project_id}}/site-vehicles/summary",
    f"{P}/site-vehicles/{{vehicle_id}}",
    f"{P}/site-vehicles/{{vehicle_id}}/verify-documents",
    f"{P}/site-vehicles/{{vehicle_id}}/clear-hold",
    f"{P}/site-vehicles/{{vehicle_id}}/withdraw",
    f"{P}/projects/{{project_id}}/driver-authorisations",
    f"{P}/projects/{{project_id}}/driver-authorisations/prefill",
    f"{P}/driver-authorisations/{{auth_id}}",
    f"{P}/driver-authorisations/{{auth_id}}/transition",
    f"{P}/projects/{{project_id}}/pre-use-checks",
    f"{P}/projects/{{project_id}}/pre-use-checks/form",
    f"{P}/projects/{{project_id}}/pre-use-checks/missing",
    f"{P}/pre-use-checks/{{check_id}}",
    f"{P}/projects/{{project_id}}/journey-plans",
    f"{P}/projects/{{project_id}}/journey-plans/hint",
    f"{P}/journey-plans/{{plan_id}}",
    f"{P}/journey-plans/{{plan_id}}/arrive",
    f"{P}/journey-plans/{{plan_id}}/cancel",
    f"{P}/kpi/site-vehicles",
}
CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "openapi.yaml"


def test_phase7b_paths_and_schema_names() -> None:
    spec = create_app().openapi()
    assert tuple(map(int, spec["info"]["version"].split("."))) >= (0, 15, 0)
    assert set(spec["paths"]) >= PHASE7B_PATHS
    names = set(spec["components"]["schemas"])
    assert {
        "SiteVehSettingsRead", "SiteVehSettingsUpdate", "SiteVehReference", "SiteVehRead",
        "SiteVehCreate", "SiteVehUpdate", "SiteVehSummary", "SiteVehAuthRead", "SiteVehAuthCreate",
        "SiteVehAuthTransition", "SiteVehCheckRead", "SiteVehCheckCreate", "SiteVehCheckForm",
        "SiteVehMissingRead", "SiteVehJourneyRead", "SiteVehJourneyCreate", "SiteVehJourneyHint",
        "SiteVehKpiResponse",
    } <= names  # fmt: skip
    committed = yaml.safe_load(CONTRACT.read_text())
    assert committed["info"]["version"] == spec["info"]["version"]
    assert set(committed["components"]["schemas"]) - names == set()
    veh = spec["components"]["schemas"]["VehicleRead"]["properties"]
    assert {"site_scope", "use_class", "readiness"} <= set(veh)
    iv = spec["components"]["schemas"]["VehIncidentVehicleRead"]["properties"]
    assert {"pre_use_check_id", "journey_plan_id"} <= set(iv)


def test_phase7b_enums_codes_and_matrix() -> None:
    codes = {c.value for c in ErrorCode}
    assert {
        "SITE_VEHICLES_NOT_LIVE", "OPERATING_CARD_REQUIRED", "LICENCE_CLASS_NOT_COVERING",
        "ASSESSMENT_TOO_OLD", "DRIVER_NOT_AUTHORISED", "PRE_USE_CHECK_EXISTS",
        "PASSENGERS_EXCEED_SEATS", "JOURNEY_TIMES_INVALID", "JOURNEY_CONTACT_IS_DRIVER",
        "VEHICLE_DEFECT_HOLD", "VEHICLE_NOT_READY", "HOOK_NOT_MET",
    } <= codes  # fmt: skip
    assert {"K-138", "K-139", "K-140"} <= {m.value for m in KpiMetric}
    for m in PHASE7B_METRICS:
        assert CATALOGUE[m].spec_ref.startswith("7b-fleet-driver §6.4")
    assert CaSourceType.site_vehicle.value == "site_vehicle"
    assert ResponseOwnerType.vehicle_check.value == "vehicle_check"
    assert {"site_vehicle_doc_expiry", "driver_auth_expiry"} <= {k.value for k in ExpiringItemKind}
    assert {"site_vehicle_doc_expiry", "driver_auth_expiry"} <= {k.value for k in NotificationKind}
    assert {"driver_authorisation", "vehicle_check", "journey_plan"} <= {
        e.value for e in EntityType
    }
    assert {"site_vehicles", "driver_authorisations", "pre_use_checks", "journey_plans"} <= {
        d.value for d in ExportDataset
    }
    caps = [
        Capability.site_vehicle_view, Capability.site_vehicle_manage,
        Capability.driver_auth_manage, Capability.pre_use_record, Capability.site_vehicle_settings,
    ]  # fmt: skip
    assert MATRIX[Role.viewer_client].get(Capability.site_vehicle_view) is not None
    assert Capability.site_vehicle_manage not in MATRIX[Role.viewer_client]
    assert Capability.site_vehicle_settings not in MATRIX[Role.hse_officer]
    assert all(c not in MATRIX[Role.permit_issuer] for c in caps[1:])
