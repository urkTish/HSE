"""Option 7a pure rules (spec 7a-vehicle-accident-details §3, §5): the VA-1 vehicle signal, the
VA-3 licence check (list LCV), VA-4 documents at the time, VA-6 plate normalisation, VA-13
recorded-not-counted. No database access here."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.core.access_enums import LicenceClass
from app.core.hse_enums import (
    Agency,
    AirsideFlag,
    AssetType,
    DangerousOccurrenceCategory,
    Mechanism,
)
from app.core.vehicle_enums import (
    COMMUTING_PURPOSES,
    VehCategory,
    VehDocState,
    VehDriverKind,
    VehJourneyPurpose,
    VehLicenceCheck,
    VehSpeedBand,
)

C = VehCategory
SIGNAL_MECHANISMS = frozenset({Mechanism.vehicle_plant_collision, Mechanism.vehicle_overturn})
SIGNAL_AGENCIES = frozenset({Agency.light_vehicle, Agency.heavy_vehicle, Agency.airside_gse})

_PRIVATE = frozenset({C.light_vehicle, C.pickup, C.van, C.private_car})
_PUBLIC = _PRIVATE | {C.bus}
_HEAVY_TRANSPORT = _PUBLIC | {
    C.truck,
    C.tipper,
    C.water_tanker,
    C.fuel_bowser,
    C.concrete_mixer,
    C.trailer,
}
_PLANT = frozenset(
    {
        C.mobile_crane,
        C.crawler_crane,
        C.mewp,
        C.forklift,
        C.telehandler,
        C.excavator,
        C.wheel_loader,
        C.grader,
        C.roller,
        C.paver,
        C.milling_machine,
        C.line_marking_vehicle,
        C.sweeper,
        C.lighting_tower,
    }
)
LCV: dict[LicenceClass, frozenset[VehCategory]] = {
    LicenceClass.private: _PRIVATE,
    LicenceClass.public_transport: _PUBLIC,
    LicenceClass.heavy_transport: _HEAVY_TRANSPORT,
    LicenceClass.heavy_equipment: _PLANT,
    LicenceClass.motorcycle: frozenset({C.motorcycle}),
}
# Categories no licence class judges (ASSUMPTION, DECISIONS): treated as covered.
NOT_JUDGED = frozenset({C.bicycle_pedestrian, C.other})

# VA-6: Saudi plate letters, Arabic → Latin pair (Phase 2 rule; ASSUMPTION per the KSA plate set)
AR_TO_LATIN = {
    "ا": "A",
    "أ": "A",
    "ب": "B",
    "ح": "J",
    "د": "D",
    "ر": "R",
    "س": "S",
    "ص": "X",
    "ط": "T",
    "ع": "E",
    "ق": "G",
    "ك": "K",
    "ل": "L",
    "م": "Z",
    "ن": "N",
    "ه": "H",
    "و": "U",
    "ى": "V",
    "ي": "V",
}


def vehicle_signal(
    case_mechanisms: Iterable[Any],
    case_agencies: Iterable[Any],
    pd_asset_type: Any,
    do_category: Any,
    airside_flags: Iterable[str],
) -> bool:
    """VA-1: the incident is a vehicle incident (vehicle_involved forced true)."""
    if any(m in SIGNAL_MECHANISMS for m in case_mechanisms):
        return True
    if any(a in SIGNAL_AGENCIES for a in case_agencies):
        return True
    if pd_asset_type == AssetType.vehicle:
        return True
    if do_category == DangerousOccurrenceCategory.vehicle_overturn:
        return True
    return AirsideFlag.airside_vehicle_incident.value in set(airside_flags or [])


def recorded_not_counted(purpose: VehJourneyPurpose | None) -> bool:
    """VA-13."""
    return purpose in COMMUTING_PURPOSES


def class_covers(
    cls: LicenceClass | None, category: VehCategory | None, adp_classes: Sequence[str] = ()
) -> bool:
    if category is None or category in NOT_JUDGED:
        return True
    if category.value in set(adp_classes):  # airside GSE without plate: ADP class check
        return True
    return cls is not None and category in LCV[cls]


def licence_check(
    driver_kind: VehDriverKind | None,
    licence_class: LicenceClass | None,
    licence_expiry: date | None,
    category: VehCategory | None,
    occurred: date,
    adp_classes: Sequence[str] = (),
) -> VehLicenceCheck:
    """VA-3. A row without a driver (parked) or without a driver kind → not_checked."""
    if driver_kind == VehDriverKind.worker:
        if licence_class is None and licence_expiry is None:
            return VehLicenceCheck.no_licence
    elif driver_kind == VehDriverKind.external:
        if licence_class is None and licence_expiry is None:
            return VehLicenceCheck.not_checked
    else:
        return VehLicenceCheck.not_checked
    if licence_expiry is not None and licence_expiry < occurred:
        return VehLicenceCheck.expired
    if not class_covers(licence_class, category, adp_classes):
        return VehLicenceCheck.wrong_class
    return VehLicenceCheck.valid


def doc_state(expiry: date | None, occurred: date) -> VehDocState:
    if expiry is None:
        return VehDocState.unknown
    return VehDocState.valid if expiry >= occurred else VehDocState.expired


def normalise_letters(ar: str | None, en: str | None) -> str | None:
    """VA-6: the Latin form of the plate letters (Arabic mapped, spaces dropped)."""
    if ar:
        out = "".join(AR_TO_LATIN.get(ch, ch) for ch in ar if not ch.isspace())
        return out.upper() or None
    if en:
        return "".join(ch for ch in en.upper() if not ch.isspace()) or None
    return None


def plate_key(ar: str | None, en: str | None, digits: str | None) -> str | None:
    letters = normalise_letters(ar, en)
    if not letters or not digits:
        return None
    return f"{letters}{digits.lstrip('0') or '0'}"


def speed_band(speed: int | None) -> VehSpeedBand:
    """P7a-2: the AI receives a band, never the exact speed."""
    if speed is None:
        return VehSpeedBand.unknown
    if speed < 30:
        return VehSpeedBand.lt_30
    if speed < 60:
        return VehSpeedBand.b30_59
    if speed < 90:
        return VehSpeedBand.b60_89
    if speed < 120:
        return VehSpeedBand.b90_119
    return VehSpeedBand.ge_120


@dataclass(frozen=True)
class RowGaps:
    """VA-2: what a vehicle row still lacks before the investigation is submitted."""

    seq: int
    missing: list[str]


def row_missing(row: Any, *, occurred: date) -> list[str]:
    """Fields of §3.2 marked Y / cond. that a row must carry before investigation submit.
    Licence fields are not required: a missing licence is a finding (no_licence)."""
    _ = occurred
    out: list[str] = []
    company = row.ownership.value in ("own_company", "contractor", "hired")
    if company and row.engagement_id is None:
        out.append("engagement_id")
    plated = row.ownership.value != "unknown" and (
        row.plate_type is None or row.plate_type.value != "none"
    )
    if row.vehicle_id is None and plated and not row.plate_digits:
        out.append("plate")
    for f in ("category", "damage", "driver_kind"):
        if getattr(row, f) is None:
            out.append(f)
    if row.seat_belt is None and row.driver_kind != VehDriverKind.none:
        out.append("seat_belt")
    if row.driver_kind == VehDriverKind.worker and row.worker_id is None:
        out.append("worker_id")
    if row.driver_kind == VehDriverKind.external and not row.external_driver_name:
        out.append("external_driver_name")
    return out
