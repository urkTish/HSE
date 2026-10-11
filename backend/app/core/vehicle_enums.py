"""Option 7a enumerations — vehicle accident details on Phase 1 incidents (spec
7a-vehicle-accident-details v1.1, §3.1–§3.3 and §5.3). Every class carries the `Veh` prefix so no
name clashes with earlier modules in the OpenAPI contract (DECISIONS D-202). EN/AR labels live in
the frontend message files (`p7-vehicle.py`)."""

from enum import StrEnum


class VehRoadType(StrEnum):
    site_road = "site_road"
    airside = "airside"
    public_road = "public_road"


class VehJourneyPurpose(StrEnum):
    """List JP. The two `commuting_*` codes make the incident "Recorded, not counted" (VA-13)."""

    work_task = "work_task"
    material_delivery = "material_delivery"
    crew_transport = "crew_transport"
    commuting_company_transport = "commuting_company_transport"
    commuting_own = "commuting_own"
    personal = "personal"
    other = "other"


COMMUTING_PURPOSES = frozenset(
    {VehJourneyPurpose.commuting_company_transport, VehJourneyPurpose.commuting_own}
)


class VehLight(StrEnum):
    daylight = "daylight"
    dusk_dawn = "dusk_dawn"
    dark_lit = "dark_lit"
    dark_unlit = "dark_unlit"


class VehSurface(StrEnum):
    dry = "dry"
    wet = "wet"
    sand_on_road = "sand_on_road"
    gravel_unpaved = "gravel_unpaved"
    other = "other"


class VehReportAuthority(StrEnum):
    """`none_internal` only for site_road / airside (VA-5)."""

    najm = "najm"
    traffic_police = "traffic_police"
    airport_operator = "airport_operator"
    none_internal = "none_internal"


class VehOwnership(StrEnum):
    own_company = "own_company"
    contractor = "contractor"
    hired = "hired"
    third_party = "third_party"
    unknown = "unknown"


COMPANY_OWNERSHIP = frozenset(
    {VehOwnership.own_company, VehOwnership.contractor, VehOwnership.hired}
)


class VehCategory(StrEnum):
    """Phase 2 list VC + private_car, motorcycle, bicycle_pedestrian (§3.2)."""

    light_vehicle = "light_vehicle"
    pickup = "pickup"
    van = "van"
    bus = "bus"
    truck = "truck"
    tipper = "tipper"
    water_tanker = "water_tanker"
    fuel_bowser = "fuel_bowser"
    concrete_mixer = "concrete_mixer"
    mobile_crane = "mobile_crane"
    crawler_crane = "crawler_crane"
    mewp = "mewp"
    forklift = "forklift"
    telehandler = "telehandler"
    excavator = "excavator"
    wheel_loader = "wheel_loader"
    grader = "grader"
    roller = "roller"
    paver = "paver"
    milling_machine = "milling_machine"
    line_marking_vehicle = "line_marking_vehicle"
    sweeper = "sweeper"
    lighting_tower = "lighting_tower"
    trailer = "trailer"
    other = "other"
    private_car = "private_car"
    motorcycle = "motorcycle"
    bicycle_pedestrian = "bicycle_pedestrian"


class VehRole(StrEnum):
    striking = "striking"
    struck = "struck"
    single_vehicle = "single_vehicle"
    parked = "parked"


class VehDamage(StrEnum):
    none = "none"
    minor = "minor"
    major = "major"
    total_loss = "total_loss"


class VehDocState(StrEnum):
    valid = "valid"
    expired = "expired"
    unknown = "unknown"


class VehSeatBelt(StrEnum):
    worn = "worn"
    not_worn = "not_worn"
    unknown = "unknown"
    not_fitted = "not_fitted"


class VehSpeedSource(StrEnum):
    vehicle_recorder = "vehicle_recorder"
    report = "report"
    estimate = "estimate"
    unknown = "unknown"


class VehDriverKind(StrEnum):
    worker = "worker"
    external = "external"
    none = "none"


class VehLicenceCheck(StrEnum):
    """VA-3, computed when the row is saved."""

    valid = "valid"
    expired = "expired"
    wrong_class = "wrong_class"
    no_licence = "no_licence"
    not_checked = "not_checked"


class VehSpeedBand(StrEnum):
    """Speed band given to the AI (P7a-2) instead of the exact speed."""

    lt_30 = "lt_30"
    b30_59 = "30_59"
    b60_89 = "60_89"
    b90_119 = "90_119"
    ge_120 = "ge_120"
    unknown = "unknown"


class VehWarning(StrEnum):
    """Non-blocking warning codes (§5.3), returned in `warnings[].code`."""

    COMMUTING_PURPOSE_MISMATCH = "COMMUTING_PURPOSE_MISMATCH"
    VEHICLE_DOCS_EXPIRED_AT_TIME = "VEHICLE_DOCS_EXPIRED_AT_TIME"
    LICENCE_NOT_VALID_AT_TIME = "LICENCE_NOT_VALID_AT_TIME"
