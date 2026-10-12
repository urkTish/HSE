"""Option 7b enumerations — Site Vehicle & Plant Readiness, **Prototype** (spec
7b-fleet-driver v2.0, §3.1–§3.6 lists and §4 states). Every class carries the `SiteVeh` prefix so
no name clashes with earlier modules in the OpenAPI contract (DECISIONS D-202). EN/AR labels of
the lists are in `app.services.site_vehicle.reference` and the frontend message files
(`p7-site-vehicle.py`)."""

from enum import StrEnum


class SiteVehScope(StrEnum):
    """§3.1 site_scope. Existing Phase 2 rows default to `airside_only` (SV-1)."""

    airside_only = "airside_only"
    site = "site"
    both = "both"


SITE_SCOPES = frozenset({SiteVehScope.site, SiteVehScope.both})


class SiteVehUseClass(StrEnum):
    """List SU (§3.6): site use class → driver group."""

    pool_car = "pool_car"
    crew_pickup = "crew_pickup"
    crew_bus = "crew_bus"
    tipper = "tipper"
    goods_heavy = "goods_heavy"
    water_tanker = "water_tanker"
    earthmoving_plant = "earthmoving_plant"
    other_plant = "other_plant"


class SiteVehDriverGroup(StrEnum):
    """List DG (§3.6). light / bus / heavy are road groups (licence class per LCV); plant needs
    no road licence (Phase 4 operator certificate or a practical assessment)."""

    light = "light"
    bus = "bus"
    heavy = "heavy"
    plant = "plant"


ROAD_GROUPS = frozenset(
    {SiteVehDriverGroup.light, SiteVehDriverGroup.bus, SiteVehDriverGroup.heavy}
)

USE_CLASS_GROUP: dict[SiteVehUseClass, SiteVehDriverGroup] = {
    SiteVehUseClass.pool_car: SiteVehDriverGroup.light,
    SiteVehUseClass.crew_pickup: SiteVehDriverGroup.light,
    SiteVehUseClass.crew_bus: SiteVehDriverGroup.bus,
    SiteVehUseClass.tipper: SiteVehDriverGroup.heavy,
    SiteVehUseClass.goods_heavy: SiteVehDriverGroup.heavy,
    SiteVehUseClass.water_tanker: SiteVehDriverGroup.heavy,
    SiteVehUseClass.earthmoving_plant: SiteVehDriverGroup.plant,
    SiteVehUseClass.other_plant: SiteVehDriverGroup.plant,
}
# §3.1: seats required for crew_bus and crew_pickup (2–60)
SEATED_CLASSES = frozenset({SiteVehUseClass.crew_bus, SiteVehUseClass.crew_pickup})
# §3.1 / R2: operating card required for crew_bus, tipper and goods_heavy (plated, public roads)
OPERATING_CARD_CLASSES = frozenset(
    {SiteVehUseClass.crew_bus, SiteVehUseClass.tipper, SiteVehUseClass.goods_heavy}
)


class SiteVehReadiness(StrEnum):
    """§4.1, in precedence order (first matching state wins)."""

    withdrawn = "withdrawn"
    idle = "idle"
    defect_hold = "defect_hold"
    not_certified = "not_certified"
    docs_expired = "docs_expired"
    ready = "ready"


NOT_READY_FOR_JOURNEY = frozenset(
    {SiteVehReadiness.defect_hold, SiteVehReadiness.not_certified, SiteVehReadiness.withdrawn}
)


class SiteVehDocsFilter(StrEnum):
    """Register filter on the vehicle documents."""

    expired = "expired"
    expiring_30d = "expiring_30d"
    unverified = "unverified"


class SiteVehAuthStatus(StrEnum):
    """§4.2 driver / operator authorisation."""

    draft = "draft"
    active = "active"
    suspended = "suspended"
    expired = "expired"
    revoked = "revoked"


LIVE_AUTH = frozenset(
    {SiteVehAuthStatus.draft, SiteVehAuthStatus.active, SiteVehAuthStatus.suspended}
)


class SiteVehHookResult(StrEnum):
    """DA-2 result of one hook: met; warn (not met under policy warn); not_met."""

    met = "met"
    warn = "warn"
    not_met = "not_met"


class SiteVehLimitingFactor(StrEnum):
    """§6.1: the term that gives effective_valid_until."""

    own_validity = "own_validity"
    licence = "licence"
    worker_id = "worker_id"
    deployment_end = "deployment_end"
    training = "training"
    medical = "medical"
    operator_certificate = "operator_certificate"


class SiteVehCheckSource(StrEnum):
    """PU-5: `paper` = answers transcribed from a signed paper card (photo attached)."""

    app = "app"
    paper = "paper"


class SiteVehJourneyStatus(StrEnum):
    """§4.3 (prototype). Overdue is a display flag only."""

    planned = "planned"
    arrived = "arrived"
    cancelled = "cancelled"


class SiteVehPolicy(StrEnum):
    """§3.5 driver_hook_policy / driver_auth_policy."""

    warn = "warn"
    block = "block"


class SiteVehWarning(StrEnum):
    """Non-blocking warning codes returned in `warnings[]` (§5.9)."""

    VEHICLE_DOCS_UNVERIFIED = "VEHICLE_DOCS_UNVERIFIED"
    DRIVER_NOT_AUTHORISED_WARN = "DRIVER_NOT_AUTHORISED_WARN"
    HOOK_NOT_MET_WARN = "HOOK_NOT_MET_WARN"
    JOURNEY_PLAN_RECOMMENDED = "JOURNEY_PLAN_RECOMMENDED"


class SiteVehKpiGroupBy(StrEnum):
    """GET /kpi/site-vehicles breakdowns."""

    contractor = "contractor"
    month = "month"
