"""Phase 6e enumerations — environmental management (spec 6e-environmental v1.0, §3.17 lists and
§4 states). Exported into the OpenAPI contract so the frontend gets typed unions. EN/AR labels of
every list are served by GET /env-reference (services/env/reference.py)."""

from enum import StrEnum


class AspectCode(StrEnum):
    """List AS."""

    dust_emission = "dust_emission"
    exhaust_emission = "exhaust_emission"
    noise_vibration = "noise_vibration"
    waste_generation = "waste_generation"
    hazardous_material_storage = "hazardous_material_storage"
    fuel_spill_risk = "fuel_spill_risk"
    wastewater_discharge = "wastewater_discharge"
    water_consumption = "water_consumption"
    land_disturbance = "land_disturbance"
    wildlife_attraction = "wildlife_attraction"
    fod_generation = "fod_generation"
    light_spill = "light_spill"
    odour = "odour"


class ImpactCode(StrEnum):
    """List IM."""

    air_quality = "air_quality"
    community_nuisance = "community_nuisance"
    soil_contamination = "soil_contamination"
    groundwater_contamination = "groundwater_contamination"
    resource_depletion = "resource_depletion"
    aviation_safety = "aviation_safety"
    ecology = "ecology"
    climate = "climate"


class AspectCondition(StrEnum):
    normal = "normal"
    abnormal = "abnormal"
    emergency = "emergency"


class AspectStatus(StrEnum):
    """§4.1."""

    draft = "draft"
    active = "active"
    archived = "archived"


class AspectAction(StrEnum):
    activate = "activate"
    archive = "archive"
    review = "review"


class EnvPermitType(StrEnum):
    """List PT."""

    ncec_env_permit_construction = "ncec_env_permit_construction"
    ncec_env_permit_operation = "ncec_env_permit_operation"
    eia_approval = "eia_approval"
    mwan_producer_registration = "mwan_producer_registration"
    municipal_construction_permit = "municipal_construction_permit"
    dewatering_discharge_permit = "dewatering_discharge_permit"
    sewer_discharge_permit = "sewer_discharge_permit"
    cemp_approval = "cemp_approval"
    mwan_licence = "mwan_licence"
    facility_authorisation = "facility_authorisation"
    lab_accreditation = "lab_accreditation"
    other = "other"


class Issuer(StrEnum):
    """List IS."""

    ncec = "ncec"
    mwan = "mwan"
    momrah_municipality = "momrah_municipality"
    nwc = "nwc"
    mewa = "mewa"
    airport_operator = "airport_operator"
    gaca = "gaca"
    client = "client"
    saac = "saac"
    other = "other"


class EnvPermitStatus(StrEnum):
    """§4.2 (derived daily, plus the manual states pending / suspended / cancelled)."""

    pending = "pending"
    valid = "valid"
    expiring = "expiring"
    expired = "expired"
    suspended = "suspended"
    superseded = "superseded"
    cancelled = "cancelled"


class EnvPermitAction(StrEnum):
    suspend = "suspend"
    reinstate = "reinstate"
    cancel = "cancel"


class ProviderKind(StrEnum):
    """List PK."""

    transporter = "transporter"
    recycler = "recycler"
    treatment_facility = "treatment_facility"
    landfill = "landfill"
    sewage_tanker = "sewage_tanker"
    environmental_lab = "environmental_lab"


class ProviderStatus(StrEnum):
    approved = "approved"
    suspended = "suspended"
    blacklisted = "blacklisted"


class ProviderAction(StrEnum):
    approve = "approve"
    suspend = "suspend"
    blacklist = "blacklist"


class LicenceActivity(StrEnum):
    """List LA."""

    collection_transport = "collection_transport"
    storage = "storage"
    sorting = "sorting"
    treatment = "treatment"
    recycling = "recycling"
    disposal = "disposal"


class WasteClass(StrEnum):
    """List WC."""

    inert = "inert"
    non_hazardous = "non_hazardous"
    hazardous = "hazardous"
    liquid_sewage = "liquid_sewage"


class WasteRoute(StrEnum):
    """List TR (reuse, recycle and recovery count as diverted)."""

    reuse = "reuse"
    recycle = "recycle"
    recovery = "recovery"
    treatment = "treatment"
    disposal_landfill = "disposal_landfill"


class WasteStreamCode(StrEnum):
    """List WS."""

    inert_cd = "inert_cd"
    asphalt_planings = "asphalt_planings"
    surplus_excavated_soil = "surplus_excavated_soil"
    metal_scrap = "metal_scrap"
    wood = "wood"
    packaging = "packaging"
    general_mixed = "general_mixed"
    food_domestic = "food_domestic"
    used_oil = "used_oil"
    oily_absorbents = "oily_absorbents"
    chemical_containers = "chemical_containers"
    paint_solvent = "paint_solvent"
    batteries = "batteries"
    e_waste = "e_waste"
    contaminated_soil = "contaminated_soil"
    clinical_first_aid = "clinical_first_aid"
    sewage = "sewage"


class StorageAreaType(StrEnum):
    """List SA."""

    skip = "skip"
    segregated_bay = "segregated_bay"
    hazardous_store = "hazardous_store"
    liquid_store = "liquid_store"
    compactor = "compactor"
    sealed_bin_station = "sealed_bin_station"


class AreaStatus(StrEnum):
    active = "active"
    closed = "closed"


class QuantityUnit(StrEnum):
    t = "t"
    m3 = "m3"
    L = "L"


class ConsignmentStatus(StrEnum):
    """§4.3."""

    dispatched = "dispatched"
    received = "received"
    closed = "closed"
    rejected = "rejected"
    voided = "voided"


class ConsignmentAction(StrEnum):
    close = "close"
    reject = "reject"
    void = "void"


class EnvInstrumentKind(StrEnum):
    """List IK."""

    pm_station = "pm_station"
    pm_portable = "pm_portable"
    pm_sampler_24h = "pm_sampler_24h"
    sound_level_meter = "sound_level_meter"
    noise_station = "noise_station"
    water_quality_meter = "water_quality_meter"


class EnvInstrumentStatus(StrEnum):
    active = "active"
    quarantined = "quarantined"
    retired = "retired"


class InstrumentAction(StrEnum):
    activate = "activate"
    quarantine = "quarantine"
    retire = "retire"


class PointKind(StrEnum):
    """List MPK."""

    boundary = "boundary"
    sensitive_receptor = "sensitive_receptor"
    airside = "airside"
    background_upwind = "background_upwind"
    discharge = "discharge"
    work_area = "work_area"


class NoiseArea(StrEnum):
    """List NA (day / night LAeq limits)."""

    residential = "residential"
    mixed_commercial = "mixed_commercial"
    industrial = "industrial"
    sensitive = "sensitive"


class PointSource(StrEnum):
    manual = "manual"
    station = "station"
    visual = "visual"


class Parameter(StrEnum):
    """List PA."""

    pm10 = "pm10"
    pm2_5 = "pm2_5"
    visual_dust = "visual_dust"
    laeq = "laeq"
    ph = "ph"
    tss = "tss"
    oil_grease = "oil_grease"
    turbidity = "turbidity"


class Averaging(StrEnum):
    """List AV."""

    min15 = "15min"
    h1 = "1h"
    h24 = "24h"
    spot = "spot"
    measurement = "measurement"


class Schedule(StrEnum):
    continuous = "continuous"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    campaign = "campaign"


class NoisePeriod(StrEnum):
    any = "any"
    day = "day"
    night = "night"


class LimitSource(StrEnum):
    ncec = "ncec"
    municipality = "municipality"
    permit_condition = "permit_condition"
    client = "client"
    project_trigger = "project_trigger"


class EnvReadingSource(StrEnum):
    manual = "manual"
    station = "station"
    derived = "derived"
    lab = "lab"
    import_ = "import"


class ReadingResult(StrEnum):
    """§6.2."""

    ok = "ok"
    alert = "alert"
    exceedance = "exceedance"
    no_limit = "no_limit"


class RecordState(StrEnum):
    valid = "valid"
    voided = "voided"


class BackgroundSource(StrEnum):
    ncm_warning = "ncm_warning"
    aocc = "aocc"
    visual_regional = "visual_regional"
    other = "other"


class ExceedanceCause(StrEnum):
    """List EC."""

    project_activity = "project_activity"
    background_natural = "background_natural"
    third_party = "third_party"
    instrument_fault = "instrument_fault"
    unknown = "unknown"


class ExceedanceStatus(StrEnum):
    """§4.5."""

    open = "open"
    reviewed = "reviewed"
    closed = "closed"
    voided = "voided"


class SpillSubstance(StrEnum):
    """List SS."""

    diesel = "diesel"
    petrol = "petrol"
    hydraulic_oil = "hydraulic_oil"
    engine_oil = "engine_oil"
    bitumen_emulsion = "bitumen_emulsion"
    paint = "paint"
    solvent = "solvent"
    concrete_washout = "concrete_washout"
    sewage = "sewage"
    chemical_other = "chemical_other"
    other = "other"


class SpillSource(StrEnum):
    plant_leak = "plant_leak"
    refuelling = "refuelling"
    container_failure = "container_failure"
    tanker = "tanker"
    other = "other"


class SpillSurface(StrEnum):
    paved = "paved"
    unpaved_soil = "unpaved_soil"
    drain = "drain"
    water_body = "water_body"


class SpillStatus(StrEnum):
    """§4.6."""

    reported = "reported"
    cleaned_up = "cleaned_up"
    closed = "closed"
    voided = "voided"


class SpillAction(StrEnum):
    clean_up = "clean_up"
    close = "close"
    void = "void"


class WaterSource(StrEnum):
    network = "network"
    tanker = "tanker"
    groundwater_dewatering_reuse = "groundwater_dewatering_reuse"
    treated_effluent = "treated_effluent"


class ComplaintChannel(StrEnum):
    phone = "phone"
    email = "email"
    in_person = "in_person"
    via_client = "via_client"
    via_authority = "via_authority"


class ComplaintCategory(StrEnum):
    dust = "dust"
    noise = "noise"
    odour = "odour"
    waste = "waste"
    water = "water"
    mud_on_road = "mud_on_road"
    light = "light"
    other = "other"


class ComplaintStatus(StrEnum):
    """§4.7."""

    open = "open"
    responded = "responded"
    closed = "closed"
    voided = "voided"


class ComplaintAction(StrEnum):
    respond = "respond"
    close = "close"
    void = "void"


class EnvActionKind(StrEnum):
    """§8.2 action-panel items."""

    exceedances_awaiting_review = "exceedances_awaiting_review"
    requirements_not_in_force = "requirements_not_in_force"
    consignments_overdue = "consignments_overdue"
    consignments_rejected = "consignments_rejected"
    haz_storage_overdue = "haz_storage_overdue"
    discharge_without_permit = "discharge_without_permit"
    post_storm_checks_unmet = "post_storm_checks_unmet"
    spill_kit_coverage_gap = "spill_kit_coverage_gap"
    spills_not_closed = "spills_not_closed"
    complaints_past_due = "complaints_past_due"


class EnvKpiGroupBy(StrEnum):
    """EK-2 / §8.1 breakdowns (aggregates only; provider names are organisations)."""

    stream = "stream"
    waste_class = "class"
    route = "route"
    transporter = "transporter"
    facility = "facility"
    point = "point"
    parameter = "parameter"
    month = "month"
    contractor = "contractor"
    cause = "cause"
    substance = "substance"
