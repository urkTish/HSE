"""T9 compare_groups (spec 1-dashboard §5.9): counts and exposure per group of a dimension,
then `stats.compare`. Exposure is man-hours where the dimension can be attributed to workforce
returns (site, zone type, contractor, weekday, heat season, Ramadan), else none."""

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.hse_enums import RECORDABLE, BreakdownDimension, CaseCategory, CompareDimension
from app.kpi import breakdowns
from app.kpi.engine import Engine
from app.kpi.periods import Window
from app.kpi.scope import Scope
from app.kpi.stats import Comparison, Group, compare

CD = CompareDimension
D = BreakdownDimension
AS_BREAKDOWN = {
    CD.heat_season: D.heat_season,
    CD.shift: D.shift,
    CD.hour_band: D.hour_band,
    CD.weekday: D.weekday,
    CD.contractor: D.contractor,
    CD.activity: D.activity,
    CD.site: D.site,
    CD.zone_type: D.zone_type,
    CD.ramadan: D.ramadan,
}
EXPOSED = {CD.heat_season, CD.weekday, CD.contractor, CD.site, CD.zone_type, CD.ramadan}
REFERENCE = {
    CD.heat_season: "out",
    CD.ramadan: "out",
    CD.new_starter: "experienced",
    CD.ptw_involved: "no",
    CD.ca_overdue_at_event: "no",
}
NONE_KEY = breakdowns.NONE_KEY


@dataclass
class Unit:
    d: date
    site: uuid.UUID
    zone: uuid.UUID | None
    eng: uuid.UUID | None
    attrs: dict[str, object]


def _units(
    engine: Engine, w: Window, measure: str, categories: list[CaseCategory], event_type: str | None
) -> list[Unit]:
    out: list[Unit] = []
    if measure in ("injury_cases", "recordable_cases"):
        for c in engine.cases_in(w):
            if c.d > engine.as_of:
                continue
            if measure == "recordable_cases" and c.category not in RECORDABLE:
                continue
            if categories and c.category not in categories:
                continue
            out.append(
                Unit(
                    c.d,
                    c.site,
                    c.zone,
                    c.eng,
                    {
                        "shift": c.shift,
                        "hour": c.hour,
                        "activity": c.activity,
                        "days_on_site": c.days_on_site,
                        "ptw": c.ptw_involved,
                    },
                )
            )
    else:
        for ev in engine.events_in(w):
            if ev.d > engine.as_of or (event_type and event_type not in ev.types):
                continue
            out.append(
                Unit(
                    ev.d,
                    ev.site,
                    ev.zone,
                    ev.eng,
                    {
                        "shift": ev.shift,
                        "hour": ev.hour,
                        "activity": ev.activity,
                        "ptw": ev.ptw_involved,
                    },
                )
            )
    return out


def _ca_overdue(engine: Engine, eng: uuid.UUID | None, d: date) -> bool:
    for ca in engine.cas:
        if ca.eng != eng or ca.created > d or ca.due >= d:
            continue
        done = ca.completed or ca.verified
        if (done is None or done > d) and (ca.cancelled is None or ca.cancelled > d):
            return True
    return False


def _key(scope: Scope, engine: Engine, dim: CompareDimension, u: Unit) -> str:
    if dim == CD.new_starter:
        days = u.attrs.get("days_on_site")
        if days is None:
            return NONE_KEY
        limit = scope.settings().new_starter_days
        return "new_starter" if int(str(days)) <= limit else "experienced"
    if dim == CD.ptw_involved:
        v = u.attrs.get("ptw")
        return NONE_KEY if v is None else ("yes" if v else "no")
    if dim == CD.ca_overdue_at_event:
        return "yes" if _ca_overdue(engine, u.eng, u.d) else "no"
    attrs = {k: v for k, v in u.attrs.items() if k != "ptw"}
    return breakdowns._keys(
        scope, AS_BREAKDOWN[dim], d=u.d, site=u.site, zone=u.zone, eng=u.eng, attrs=attrs
    )[0]


def compare_groups(
    db: Session,
    scope: Scope,
    dim: CompareDimension,
    measure: str,
    categories: list[CaseCategory] | None = None,
    event_type: str | None = None,
    reference: str | None = None,
) -> tuple[Comparison, str, dict[str, str]]:
    """Returns (comparison, exposure basis, labels)."""
    engine = scope.engine
    w = scope.window
    counts: Counter[str] = Counter()
    for u in _units(engine, w, measure, categories or [], event_type):
        counts[_key(scope, engine, dim, u)] += 1
    counts.pop(NONE_KEY, None)
    exposure: dict[str, Decimal] | None = None
    basis = "none"
    if dim in EXPOSED:
        exposure = defaultdict(Decimal)
        for r in engine.wf_in(w):
            k = breakdowns._keys(
                scope, AS_BREAKDOWN[dim], d=r.d, site=r.site, zone=r.zone, eng=r.eng, attrs={}
            )[0]
            exposure[k] += r.mh
        exposure.pop(NONE_KEY, None)
        basis = "man_hours"
    elif dim in (CD.new_starter, CD.ptw_involved, CD.ca_overdue_at_event):
        for k in ("yes", "no") if dim != CD.new_starter else ("new_starter", "experienced"):
            counts.setdefault(k, 0)
    keys = sorted(set(counts) | set(exposure or {}))
    groups = [
        Group(k, counts.get(k, 0), float(exposure.get(k, 0)) if exposure is not None else None)
        for k in keys
    ]
    ref = reference or REFERENCE.get(dim)
    result = compare(groups, scope.config.rate_base, ref)
    if dim in AS_BREAKDOWN:
        lm = breakdowns.label_map(db, scope, AS_BREAKDOWN[dim], set(keys))
        labels = {k: lm.get(k, (k, k))[0] for k in keys}
    else:
        labels = {
            "new_starter": f"≤ {scope.settings().new_starter_days} days on site",
            "experienced": f"> {scope.settings().new_starter_days} days on site",
            "yes": "Yes",
            "no": "No",
        }
    return result, basis, labels
