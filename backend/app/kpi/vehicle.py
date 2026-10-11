"""Vehicle incident KPIs K-136, K-137 (spec 7a-vehicle-accident-details §6.1, VA-13).

K-136 counts every vehicle incident (status ∉ {Draft, Voided}) occurred in the period, commuting
and not-work-related ones included, with chips by road type, primary type, with injury and
"Recorded, not counted". K-137 = crashes (injury/illness or property damage) with ≥ 1 own /
contractor / hired vehicle, not recorded-not-counted and work related, × B ÷ MH; it ignores
`include_commuting_in_rates` (VA-13). Contractor filter = responsible engagement (K-R5)."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from decimal import Decimal

from app.core.hse_enums import IncidentType, KpiKind, KpiMetric
from app.kpi import engine as engine_mod
from app.kpi.engine import Agg, Component, Engine, Result
from app.kpi.facts import VehFact
from app.kpi.periods import Window

M = KpiMetric
CRASH = frozenset({IncidentType.injury_illness.value, IncidentType.property_damage.value})
ROAD_LABELS = {
    "site_road": ("Site road", "طريق داخل الموقع"),
    "airside": ("Airside", "الجانب الجوي"),
    "public_road": ("Public road", "طريق عام"),
}
TYPE_LABELS = {
    "injury_illness": ("Injury / illness", "إصابة / مرض"),
    "near_miss": ("Near miss", "حادث وشيك"),
    "property_damage": ("Property damage", "أضرار ممتلكات"),
    "environmental": ("Environmental", "بيئي"),
    "dangerous_occurrence": ("Dangerous occurrence", "حدث خطير"),
}
RNC_LABEL = ("Recorded, not counted — commuting (OSHA)", "مسجل، غير محتسب — تنقل (OSHA)")


def vehicles_in(e: Engine, w: Window) -> list[VehFact]:
    end = min(e.as_of, w.end)
    return [v for v in e.vehicles if w.start <= v.d <= end]


def counted(v: VehFact) -> bool:
    """K-137 numerator rule."""
    return bool(v.types & CRASH) and v.company and not v.rnc and v.work_related


def with_injury(v: VehFact) -> bool:
    return IncidentType.injury_illness.value in v.types


def vehicle_ids(e: Engine, w: Window, rate: bool = False) -> list[uuid.UUID]:
    return [v.id for v in vehicles_in(e, w) if not rate or counted(v)]


def chips(vs: Sequence[VehFact]) -> list[Component]:
    k = KpiKind.count_
    out = []
    roads = Counter(v.road_type for v in vs if v.road_type)
    for code, (en, ar) in ROAD_LABELS.items():
        out.append(Component(f"road_type:{code}", en, ar, Decimal(roads.get(code, 0)), k))
    prim = Counter(v.primary for v in vs)
    for code, (en, ar) in TYPE_LABELS.items():
        if prim.get(code):
            out.append(Component(f"primary_type:{code}", en, ar, Decimal(prim[code]), k))
    out.append(
        Component(
            "with_injury",
            "With injury",
            "مع إصابة",
            Decimal(sum(1 for v in vs if with_injury(v))),
            k,
        )
    )
    out.append(
        Component("recorded_not_counted", *RNC_LABEL, Decimal(sum(1 for v in vs if v.rnc)), k)
    )
    return out


def _k136(e: Engine, a: Agg) -> Result:
    vs = vehicles_in(e, a.window)
    res = e._count(M.K136, len(vs))
    res.components = chips(vs)
    return res


def _k137(e: Engine, a: Agg) -> Result:
    n = sum(1 for v in vehicles_in(e, a.window) if counted(v))
    return e._rate(M.K137, n, a, e.config.rate_base)


engine_mod._DISPATCH.update({M.K136: _k136, M.K137: _k137})
