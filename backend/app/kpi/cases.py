"""Per-case rules: lost-day counting (§6.3, I-7, I-8) and category derivation (I-5)."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.hse_enums import (
    MEDICAL_TREATMENTS,
    SIGNIFICANT_NATURES,
    CaseCategory,
    InjuryNature,
    PermanentDisability,
    TreatedAt,
    Treatment,
)


@dataclass(frozen=True, slots=True)
class CaseDates:
    """The inputs of §6.3 for one case (dates are project-local)."""

    injury_date: date
    away_start_date: date | None = None
    rtw_date: date | None = None
    restricted_start: date | None = None
    restricted_end: date | None = None
    transfer_start: date | None = None
    transfer_end: date | None = None

    @property
    def has_absence(self) -> bool:
        return self.away_start_date is not None or self.rtw_date is not None

    @property
    def away_start(self) -> date:
        """Default: injury date + 1 (the day of injury is never counted, I-7)."""
        return self.away_start_date or self.injury_date + timedelta(days=1)


@dataclass(frozen=True, slots=True)
class DayCounts:
    days_away: int
    restricted_days: int
    transfer_days: int
    capped: bool
    open_absence: bool


def _span(start: date | None, end: date | None, as_of: date) -> int:
    if start is None:
        return 0
    last = min(end or as_of, as_of)
    return max(0, (last - start).days + 1)


def day_counts(c: CaseDates, as_of: date, cap: int) -> DayCounts:
    """§6.3: calendar days; days_away = rtw − away_start, or every day from away_start to as_of
    while still away; restricted/transfer inclusive; combined cap (0 = no cap)."""
    days_away = 0
    open_absence = False
    if c.has_absence:
        start = c.away_start
        if c.rtw_date is not None and c.rtw_date <= as_of:
            days_away = max(0, (c.rtw_date - start).days)
        else:
            open_absence = c.rtw_date is None
            days_away = max(0, (as_of + timedelta(days=1) - start).days)
    restricted = _span(c.restricted_start, c.restricted_end, as_of)
    transfer = _span(c.transfer_start, c.transfer_end, as_of)
    capped = False
    if cap > 0:
        if days_away >= cap:
            capped = True
            days_away = cap
        room = cap - days_away
        if restricted + transfer > room:
            capped = True
            restricted = min(restricted, room)
            transfer = min(transfer, room - restricted)
    return DayCounts(days_away, restricted, transfer, capped, open_absence)


def lost_days_charged(
    category: CaseCategory,
    counts: DayCounts,
    fatal: bool,
    permanent: PermanentDisability,
    fatality_charge: int,
) -> int:
    """K-17 contribution: LTI/FAT days away; FAT or permanent total disability use the
    fatality charge when it is > 0 (§6.3.6)."""
    if (fatal or permanent == PermanentDisability.total) and fatality_charge > 0:
        return fatality_charge
    if category in (CaseCategory.FAT, CaseCategory.LTI):
        return counts.days_away
    return 0


def derive_category(
    *,
    dates: CaseDates,
    fatal: bool,
    permanent: PermanentDisability,
    treatments: Iterable[Treatment | str],
    loss_of_consciousness: bool,
    nature: InjuryNature | str,
    treated_at: TreatedAt | str,
    as_of: date,
) -> CaseCategory:
    """I-5, first match wins. An absence/restriction/transfer that has started but not ended
    counts as at least one day (the case is classified as soon as it is recorded)."""
    probe = max(
        [as_of]
        + [
            d
            for d in (
                dates.away_start if dates.has_absence else None,
                dates.restricted_start,
                dates.transfer_start,
            )
            if d is not None
        ]
    )
    counts = day_counts(dates, probe, cap=0)
    if fatal:
        return CaseCategory.FAT
    if counts.days_away >= 1 or permanent != PermanentDisability.none:
        return CaseCategory.LTI
    if counts.restricted_days >= 1:
        return CaseCategory.RWC
    if counts.transfer_days >= 1:
        return CaseCategory.JTC
    treatment_set = {Treatment(t) for t in treatments}
    if (
        treatment_set & MEDICAL_TREATMENTS
        or loss_of_consciousness
        or InjuryNature(nature) in SIGNIFICANT_NATURES
        or TreatedAt(treated_at) == TreatedAt.hospital_admitted
    ):
        return CaseCategory.MTC
    return CaseCategory.FAC
