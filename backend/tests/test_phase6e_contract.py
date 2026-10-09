"""Phase 6e contract surface: paths, enums, error codes and the capability matrix (spec
6e-environmental)."""

from app.core.emergency_enums import AssetType, NotReadyReason
from app.core.enums import Capability, Role
from app.core.errors import ErrorCode
from app.core.hse_enums import CaSourceType, ExternalBody, KpiMetric, LeadingWarningCode
from app.kpi.catalogue import CATALOGUE, PHASE6E_METRICS
from app.main import create_app
from app.services.permissions import MATRIX

PHASE6E_PATHS = {
    "/api/v1/env-reference",
    "/api/v1/projects/{project_id}/env-settings",
    "/api/v1/projects/{project_id}/env-aspects",
    "/api/v1/env-aspects/{aspect_id}",
    "/api/v1/env-aspects/{aspect_id}/transitions",
    "/api/v1/env-providers",
    "/api/v1/env-providers/{provider_id}",
    "/api/v1/env-providers/{provider_id}/transitions",
    "/api/v1/env-providers/{provider_id}/licences",
    "/api/v1/projects/{project_id}/env-permits",
    "/api/v1/env-permits/{permit_id}",
    "/api/v1/env-permits/{permit_id}/transitions",
    "/api/v1/projects/{project_id}/waste-streams",
    "/api/v1/projects/{project_id}/waste-streams/{stream_code}",
    "/api/v1/projects/{project_id}/waste-storage-areas",
    "/api/v1/waste-storage-areas/{area_id}",
    "/api/v1/projects/{project_id}/waste-consignments",
    "/api/v1/waste-consignments/{consignment_id}",
    "/api/v1/waste-consignments/{consignment_id}/receipt",
    "/api/v1/waste-consignments/{consignment_id}/transitions",
    "/api/v1/projects/{project_id}/env-instruments",
    "/api/v1/env-instruments/{instrument_id}",
    "/api/v1/env-instruments/{instrument_id}/transitions",
    "/api/v1/env-instruments/{instrument_id}/devices",
    "/api/v1/env-instruments/{instrument_id}/devices/{device_pk}/revoke",
    "/api/v1/env/station-session",
    "/api/v1/env/station-readings",
    "/api/v1/projects/{project_id}/env-points",
    "/api/v1/env-points/{point_id}",
    "/api/v1/projects/{project_id}/env-readings",
    "/api/v1/env-readings/{reading_id}",
    "/api/v1/env-readings/{reading_id}/void",
    "/api/v1/projects/{project_id}/background-declarations",
    "/api/v1/projects/{project_id}/env-exceedances",
    "/api/v1/env-exceedances/{exceedance_id}",
    "/api/v1/env-exceedances/{exceedance_id}/review",
    "/api/v1/env-exceedances/{exceedance_id}/void",
    "/api/v1/projects/{project_id}/spills",
    "/api/v1/spills/{spill_id}",
    "/api/v1/spills/{spill_id}/transitions",
    "/api/v1/projects/{project_id}/water-entries",
    "/api/v1/water-entries/{entry_id}",
    "/api/v1/water-entries/{entry_id}/void",
    "/api/v1/projects/{project_id}/discharge-days",
    "/api/v1/projects/{project_id}/env-complaints",
    "/api/v1/env-complaints/{complaint_id}",
    "/api/v1/env-complaints/{complaint_id}/transitions",
    "/api/v1/env-complaints/{complaint_id}/nearby-readings",
    "/api/v1/projects/{project_id}/env-action-panel",
    "/api/v1/projects/{project_id}/env-band",
    "/api/v1/kpi/environmental",
}


def test_phase6e_paths_in_contract() -> None:
    spec = create_app().openapi()
    assert spec["info"]["version"] == "0.11.0"
    assert set(spec["paths"]) >= PHASE6E_PATHS
    ops = [op["operationId"] for v in spec["paths"].values() for op in v.values()]
    assert len(ops) == len(set(ops))


def test_phase6e_enums_and_matrix() -> None:
    codes = {c.value for c in ErrorCode}
    assert {
        "ASPECT_CONTROL_REQUIRED", "CONTROL_LEVEL_TOO_LOW", "PRODUCER_REGISTRATION_INVALID",
        "PROVIDER_LICENCE_INVALID", "LICENCE_SCOPE_MISMATCH", "PROVIDER_NOT_APPROVED",
        "STREAM_NOT_ACCEPTED", "CONTAINMENT_INSUFFICIENT", "AIRSIDE_STORAGE_NOT_SECURED",
        "MANIFEST_REF_REQUIRED", "DISCREPANCY_REASON_REQUIRED", "INSTRUMENT_CALIBRATION_EXPIRED",
        "FIELD_CALIBRATION_REQUIRED", "BACKDATED_READING", "VALUE_OUT_OF_RANGE", "LIMIT_LOOSENING",
        "ENGAGEMENT_REQUIRED", "INCIDENT_FIELDS_REQUIRED", "INCIDENT_NOT_ENVIRONMENTAL",
        "CLEANUP_WASTE_UNTRACKED", "DUPLICATE_WATER_ENTRY", "SETTING_LOOSENING",
        "CONSIGNMENT_CLOSED", "PERMIT_NOT_VALID", "AVP_NOT_FOUND",
    } <= codes  # fmt: skip
    assert {f"K-{n}" for n in range(118, 127)} <= {m.value for m in KpiMetric}
    assert {"E22", "E23"} <= {c.value for c in LeadingWarningCode}
    assert CaSourceType.environmental.value == "environmental"
    assert ExternalBody.ncec.value == "ncec"
    assert AssetType.spill_kit.value == "spill_kit"
    assert NotReadyReason.USED_REPLENISH in NotReadyReason
    for m in PHASE6E_METRICS:
        assert CATALOGUE[m].spec_ref.startswith("6e-environmental §6.7")
    # §5.17: 213 is HSE Manager only; viewers only read
    for role, caps in MATRIX.items():
        if role != Role.hse_manager:
            assert Capability.env_settings not in caps, role
    assert set(MATRIX[Role.viewer_client]) & {c for c in Capability if c.value.startswith(
        ("env", "waste", "consignment", "spill"))} == {Capability.env_view}  # fmt: skip
    assert Capability.consignment_close not in MATRIX[Role.contractor_hse_rep]
    assert Capability.env_void not in MATRIX[Role.site_engineer]
    assert Capability.spill_record in MATRIX[Role.permit_receiver]
