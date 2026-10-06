"""Breakdowns of a measure by a dimension (spec 1-dashboard §6.8, C7, AI tool T3).

Counts come from the engine's filtered facts for the window; exposure (man-hours) is
available for dimensions that workforce returns carry (site, zone, contractor, tier, month,
weekday, heat season, Ramadan). Person-level cells of 1-2 are suppressed to "<3" for roles
without capability 39 (D-7, AI-6); age band / nationality need capability 39 outright.
"""

import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import (
    RECORDABLE,
    RESTRICTED_DIMENSIONS,
    BreakdownDimension,
    BreakdownMeasure,
    ReferenceList,
)
from app.kpi import calendar, fmt
from app.kpi.engine import CONTROL_LABELS, OBS_LABELS, Engine
from app.kpi.periods import Window, fmt_month, month_key
from app.kpi.scope import Scope
from app.models import Site, Zone
from app.services import hse_settings

D = BreakdownDimension
MS = BreakdownMeasure
PERSON_MEASURES = frozenset({MS.injury_cases, MS.recordable_cases})
RATE_MEASURES = frozenset(
    {MS.injury_cases, MS.recordable_cases, MS.events_by_type, MS.observations,
     MS.unsafe_observations}
)  # fmt: skip
EXPOSURE_DIMS = frozenset(
    {D.site, D.zone, D.zone_type, D.airside_area, D.contractor, D.tier, D.month, D.weekday,
     D.heat_season, D.ramadan}
)  # fmt: skip
COMMON = {D.site, D.zone, D.zone_type, D.airside_area, D.contractor, D.tier, D.month, D.weekday,
          D.heat_season, D.ramadan}  # fmt: skip
SUPPORTED: dict[BreakdownMeasure, frozenset[BreakdownDimension]] = {
    MS.injury_cases: frozenset(COMMON | {
        D.activity, D.mechanism, D.agency, D.body_part, D.nature, D.case_category,
        D.incident_type, D.root_cause_level, D.root_cause_code, D.shift, D.hour_band,
        D.days_on_site_band, D.trade, D.age_band, D.nationality}),
    MS.events_by_type: frozenset(COMMON | {
        D.activity, D.incident_type, D.root_cause_level, D.root_cause_code, D.shift,
        D.hour_band}),
    MS.observations: frozenset(COMMON | {D.observation_category, D.observation_type}),
    MS.cas: frozenset(COMMON | {D.control_level, D.ca_priority}),
    MS.inspections: frozenset(COMMON | {D.inspection_type}),
}  # fmt: skip
SUPPORTED[MS.recordable_cases] = SUPPORTED[MS.injury_cases]
SUPPORTED[MS.unsafe_observations] = SUPPORTED[MS.observations]

NONE_KEY = "none"
MEASURE_LABELS = {
    MS.injury_cases: ("Injury cases", "حالات الإصابة"),
    MS.recordable_cases: ("Recordable cases", "الحالات المسجلة"),
    MS.events_by_type: ("Events", "الأحداث"),
    MS.observations: ("Observations", "الملاحظات"),
    MS.unsafe_observations: ("Unsafe observations", "الملاحظات غير الآمنة"),
    MS.cas: ("Corrective actions", "الإجراءات التصحيحية"),
    MS.inspections: ("Inspections", "عمليات التفتيش"),
}
DIMENSION_LABELS = {d: (d.value.replace("_", " ").capitalize(), d.value) for d in D}
FIXED: dict[BreakdownDimension, dict[str, tuple[str, str]]] = {
    D.zone_type: {"airside": ("Airside", "الجانب الجوي"), "landside": ("Landside", "الجانب الأرضي"),
                  "other": ("Other", "أخرى"), NONE_KEY: ("No zone", "بدون منطقة")},
    D.heat_season: {"in": ("Heat season", "موسم الحرارة"), "out": ("Outside heat season",
                                                                   "خارج موسم الحرارة")},
    D.ramadan: {"in": ("Ramadan", "رمضان"), "out": ("Outside Ramadan", "خارج رمضان")},
    D.shift: {"day": ("Day", "نهارية"), "night": ("Night", "ليلية"),
              "all": ("All day", "كامل اليوم")},
    D.root_cause_level: {"AD": ("Absent/failed defences", "دفاعات غائبة/فاشلة"),
                         "IT": ("Individual/team actions", "تصرفات فردية/جماعية"),
                         "TE": ("Task/environmental conditions", "ظروف المهمة/البيئة"),
                         "OF": ("Organisational factors", "عوامل تنظيمية")},
    D.incident_type: {"injury_illness": ("Injury / illness", "إصابة/مرض"),
                      "near_miss": ("Near miss", "حادث وشيك"),
                      "property_damage": ("Property damage", "أضرار ممتلكات"),
                      "environmental": ("Environmental", "حادث بيئي"),
                      "dangerous_occurrence": ("Dangerous occurrence", "حدث خطير")},
    D.ca_priority: {"critical": ("Critical", "حرجة"), "high": ("High", "عالية"),
                    "medium": ("Medium", "متوسطة"), "low": ("Low", "منخفضة")},
    D.weekday: {k: (en, ar) for k, en, ar in calendar.WEEKDAYS},
    D.control_level: {k.value: v for k, v in CONTROL_LABELS.items()},
    D.observation_type: {k.value: v for k, v in OBS_LABELS.items()},
}  # fmt: skip
REF_LISTS = {
    D.activity: ReferenceList.activity, D.mechanism: ReferenceList.mechanism,
    D.agency: ReferenceList.agency, D.body_part: ReferenceList.body_part,
    D.nature: ReferenceList.nature, D.trade: ReferenceList.trade,
    D.observation_category: ReferenceList.observation_category,
    D.inspection_type: ReferenceList.inspection_type, D.root_cause_code: ReferenceList.root_cause,
}  # fmt: skip


@dataclass
class Row:
    key: str
    label_en: str
    label_ar: str
    count: int
    man_hours: Decimal | None = None


@dataclass
class Breakdown:
    measure: BreakdownMeasure
    dimension: BreakdownDimension
    rows: list[Row]
    total: int
    exposure_available: bool
    rate_base: int
    persons: bool


def check_dimension(scope: Scope, measure: BreakdownMeasure, dim: BreakdownDimension) -> None:
    if dim in RESTRICTED_DIMENSIONS and not all(
        scope.p.grant(x.id, Capability.breakdown_sensitive_view) for x in scope.projects
    ):
        raise ApiError(
            403,
            ErrorCode.RESTRICTED_DIMENSION,
            "Nationality and age-band analyses are restricted to the HSE Manager and Officers.",
            "تحليلات الجنسية والفئة العمرية متاحة لمدير ومسؤولي الصحة والسلامة فقط.",
        )
    if dim not in SUPPORTED[measure]:
        raise validation_error(
            "dimension", f"Dimension {dim.value} is not available for {measure.value}."
        )


def can_see_small_cells(scope: Scope) -> bool:
    return all(scope.p.grant(x.id, Capability.breakdown_sensitive_view) for x in scope.projects)


def _keys(
    scope: Scope, dim: BreakdownDimension, *, d: date, site: uuid.UUID, zone: uuid.UUID | None,
    eng: uuid.UUID | None, attrs: dict[str, object],
) -> list[str]:  # fmt: skip
    facts = scope.facts
    z = facts.zones.get(zone) if zone else None
    e = facts.engagements.get(eng) if eng else None
    hs = scope.settings()
    simple: dict[BreakdownDimension, Callable[[], object]] = {
        D.site: lambda: str(site),
        D.zone: lambda: str(zone) if zone else NONE_KEY,
        D.zone_type: lambda: z.zone_type if z else NONE_KEY,
        D.airside_area: lambda: (z.airside_area or NONE_KEY) if z else NONE_KEY,
        D.contractor: lambda: str(eng) if eng else NONE_KEY,
        D.tier: lambda: str(e.tier) if e else NONE_KEY,
        D.month: lambda: month_key(d),
        D.weekday: lambda: calendar.weekday(d),
        D.heat_season: lambda: (
            "in" if calendar.in_heat_season(d, hs.heat_season_start, hs.heat_season_end) else "out"
        ),
        D.ramadan: lambda: "in" if calendar.in_ramadan(d) else "out",
    }
    if dim in simple:
        return [str(simple[dim]())]
    if dim == D.hour_band:
        return [calendar.hour_band(attrs.get("hour")) or NONE_KEY]  # type: ignore[arg-type]
    if dim == D.days_on_site_band:
        return [calendar.days_on_site_band(attrs.get("days_on_site")) or NONE_KEY]  # type: ignore[arg-type]
    if dim == D.root_cause_code:
        return list(attrs.get("root_causes") or ()) or [NONE_KEY]  # type: ignore[call-overload]
    if dim == D.root_cause_level:
        codes = attrs.get("root_causes") or ()
        return sorted({c.split("-")[0] for c in codes}) or [NONE_KEY]  # type: ignore[attr-defined]
    if dim == D.incident_type:
        types = attrs.get("types")
        return sorted(types) if types else ["injury_illness"]  # type: ignore[call-overload]
    v = attrs.get(dim.value)
    return [str(v) if v not in (None, "") else NONE_KEY]


def _items(
    scope: Scope, engine: Engine, measure: BreakdownMeasure, w: Window
) -> Iterable[tuple[dict[str, object], int]]:
    """(attributes, weight) for each counted unit of the measure in the window."""
    as_of = engine.as_of
    if measure in PERSON_MEASURES:
        for c in engine.cases_in(w):
            if c.d > as_of or (measure == MS.recordable_cases and c.category not in RECORDABLE):
                continue
            yield ({"d": c.d, "site": c.site, "zone": c.zone, "eng": c.eng,
                    "activity": c.activity, "mechanism": c.mechanism, "agency": c.agency,
                    "body_part": c.body_part, "nature": c.nature,
                    "case_category": c.category.value, "root_causes": c.root_causes,
                    "shift": c.shift, "hour": c.hour, "days_on_site": c.days_on_site,
                    "trade": c.trade, "age_band": c.age_band,
                    "nationality": c.nationality}, 1)  # fmt: skip
    elif measure == MS.events_by_type:
        for ev in engine.events_in(w):
            if ev.d <= as_of:
                yield ({"d": ev.d, "site": ev.site, "zone": ev.zone, "eng": ev.eng,
                        "activity": ev.activity, "root_causes": ev.root_causes,
                        "shift": ev.shift, "hour": ev.hour, "types": ev.types}, 1)  # fmt: skip
    elif measure in (MS.observations, MS.unsafe_observations):
        for o in engine.obs_in(w):
            if o.d > as_of or (measure == MS.unsafe_observations and o.safe):
                continue
            yield ({"d": o.d, "site": o.site, "zone": o.zone, "eng": o.eng,
                    "observation_category": o.category,
                    "observation_type": o.obs_type}, o.n)  # fmt: skip
    elif measure == MS.cas:
        for ca in engine.cas:
            if w.contains(ca.created) and ca.created <= as_of:
                yield ({"d": ca.created, "site": ca.site, "zone": ca.zone, "eng": ca.eng,
                        "control_level": ca.control.value,
                        "ca_priority": ca.priority}, 1)  # fmt: skip
    elif measure == MS.inspections:
        for i in engine.insp:
            d = i.planned or i.completed
            if d is None or i.cancelled or not w.contains(d) or d > as_of:
                continue
            yield ({"d": d, "site": i.site, "zone": i.zone, "eng": i.eng,
                    "inspection_type": i.inspection_type}, 1)  # fmt: skip


def compute(
    db: Session,
    scope: Scope,
    measure: BreakdownMeasure,
    dim: BreakdownDimension,
    w: Window | None = None,
    engine: Engine | None = None,
) -> Breakdown:
    check_dimension(scope, measure, dim)
    eng = engine or scope.engine
    w = w or scope.window
    counts: Counter[str] = Counter()
    total = 0
    for attrs, n in _items(scope, eng, measure, w):
        total += n
        keys = _keys(
            scope,
            dim,
            d=attrs["d"],  # type: ignore[arg-type]
            site=attrs["site"],  # type: ignore[arg-type]
            zone=attrs["zone"],  # type: ignore[arg-type]
            eng=attrs["eng"],  # type: ignore[arg-type]
            attrs=attrs,
        )
        for k in keys:
            counts[k] += n
    exposure = dim in EXPOSURE_DIMS and measure in RATE_MEASURES
    mh: dict[str, Decimal] = defaultdict(Decimal)
    if exposure:
        for r in eng.wf_in(w):
            for k in _keys(scope, dim, d=r.d, site=r.site, zone=r.zone, eng=r.eng, attrs={}):
                mh[k] += r.mh
    labels = label_map(db, scope, dim, set(counts) | set(mh))
    keys = sorted(set(counts) | (set(mh) if exposure else set()),
                  key=lambda k: (-counts.get(k, 0), labels.get(k, (k, k))[0]))  # fmt: skip
    if dim in (D.month, D.hour_band, D.days_on_site_band):
        keys = sorted(keys)
    if dim == D.weekday:
        order = [k for k, _, _ in calendar.WEEKDAYS]
        keys = sorted(keys, key=lambda k: order.index(k) if k in order else 99)
    rows = [
        Row(k, *labels.get(k, (k, k)), counts.get(k, 0), mh.get(k) if exposure else None)
        for k in keys
    ]
    return Breakdown(
        measure, dim, rows, total, exposure, scope.config.rate_base, measure in PERSON_MEASURES
    )


def label_map(
    db: Session, scope: Scope, dim: BreakdownDimension, keys: set[str]
) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {NONE_KEY: ("Not recorded", "غير مسجل")}
    if dim in FIXED:
        out.update(FIXED[dim])
    elif dim in REF_LISTS:
        out.update(hse_settings.labels(db, REF_LISTS[dim]))
    elif dim == D.site:
        ids = [uuid.UUID(k) for k in keys if k != NONE_KEY]
        for sid, code, en, ar in db.execute(
            select(Site.id, Site.code, Site.name_en, Site.name_ar).where(Site.id.in_(ids))
        ):
            out[str(sid)] = (f"{code} · {en}", f"{code} · {ar}")
    elif dim == D.zone:
        ids = [uuid.UUID(k) for k in keys if k != NONE_KEY]
        for zid, code, en, ar in db.execute(
            select(Zone.id, Zone.code, Zone.name_en, Zone.name_ar).where(Zone.id.in_(ids))
        ):
            out[str(zid)] = (f"{code} · {en}", f"{code} · {ar}")
        out[NONE_KEY] = ("No zone", "بدون منطقة")
    elif dim == D.contractor:
        for k in keys:
            e = scope.facts.engagements.get(uuid.UUID(k)) if k != NONE_KEY else None
            if e:
                out[k] = (e.code, e.code)
        out[NONE_KEY] = ("Not assigned", "غير محدد")
    elif dim == D.tier:
        out.update({str(t): (f"Tier {t}", f"المستوى {t}") for t in (1, 2, 3)})
    elif dim == D.month:
        for k in keys:
            if k != NONE_KEY:
                y, m = (int(x) for x in k.split("-"))
                out[k] = fmt_month(date(y, m, 1))
    elif dim == D.airside_area:
        out.update({k: (k.replace("_", " ").capitalize(), k) for k in keys if k != NONE_KEY})
    elif dim == D.case_category:
        out.update({k: (k, k) for k in keys})
    else:
        out.update({k: (k, k) for k in keys if k != NONE_KEY})
    return out


def rate_display(count: int, mh: Decimal | None, base: int) -> tuple[str | None, str | None]:
    if mh is None or mh <= 0:
        return None, None if mh is None else fmt.DASH
    v = Decimal(count) * Decimal(base) / mh
    return fmt.dec_str(v, 2), fmt.number(v, 2)
