"""Access KPIs K-48…K-60 and K-53b (spec 2-access-permits §6.8, KA-1…KA-4).

Pure functions over ``AccessFacts`` and the engine's filter / window / as_of, registered into
the engine dispatch at import. Worker-based metrics (K-48…K-51, K-54…K-57) have no zone and
ignore a zone filter; gate, WAP, NOTAM and obstacle metrics apply it.
"""

import statistics
import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from decimal import Decimal

from app.core.hse_enums import KpiKind, KpiMetric, NullReason
from app.kpi import engine as _engine
from app.kpi.access_facts import AccessFacts, DepFact, GateAgg
from app.kpi.engine import Agg, Component, Engine, Result

UUID = uuid.UUID
M = KpiMetric
HUNDRED = Decimal(100)


# ---- helpers -------------------------------------------------------------------------------------


def _facts(e: Engine) -> AccessFacts:
    af = getattr(e.facts, "access", None)
    return af if isinstance(af, AccessFacts) else AccessFacts()


def _sites_ok(e: Engine, sites: Iterable[UUID]) -> bool:
    f = e.flt
    if f.sites is None:
        return True
    return any(s in f.sites for s in sites)


def _zones_ok(e: Engine, zones: Iterable[UUID | None]) -> bool:
    return any(e.flt.zone_ok(z, e.facts.zones) for z in zones)


def _end(e: Engine, a: Agg) -> date:
    return min(e.as_of, a.window.end)


def _in(a: Agg, d: date | None, e: Engine) -> bool:
    return d is not None and a.window.start <= d <= _end(e, a)


def mobilised(d: DepFact, day: date) -> bool:
    return d.start is not None and d.start <= day and (d.end is None or d.end > day)


def deployed(e: Engine, day: date) -> list[DepFact]:
    return [
        d
        for d in _facts(e).deps
        if d.worker and mobilised(d, day) and e.flt.eng_ok(d.eng) and _sites_ok(e, d.sites)
    ]


def gen_valid(d: DepFact, day: date) -> bool:
    return any(vf <= day <= vu for vf, vu in d.gen)


def _comp(
    key: str, en: str, ar: str, v: int | Decimal | None, kind: KpiKind = KpiKind.count_
) -> Component:
    return Component(key, en, ar, None if v is None else Decimal(v), kind, 0)


def _res(
    metric: KpiMetric,
    value: Decimal | None,
    num: int | Decimal | None = None,
    den: int | Decimal | None = None,
    reason: NullReason | None = None,
) -> Result:
    return Result(metric, value, num, den, reason)


def _pct(metric: KpiMetric, num: int, den: int) -> Result:
    if den == 0:
        return _res(metric, None, num, den, NullReason.NO_DENOMINATOR)
    return _res(metric, Decimal(num) / Decimal(den) * HUNDRED, num, den)


# ---- metrics -------------------------------------------------------------------------------------


def k48(e: Engine, a: Agg) -> Result:
    n = len(deployed(e, _end(e, a)))
    return _res(M.K48, Decimal(n), n)


def k49_counts(e: Engine, day: date) -> tuple[int, int]:
    deps = deployed(e, day)
    return sum(1 for d in deps if gen_valid(d, day)), len(deps)


def k49(e: Engine, a: Agg) -> Result:
    num, den = k49_counts(e, _end(e, a))
    return _pct(M.K49, num, den)


def k50(e: Engine, a: Agg) -> Result:
    first = passed = 0
    for x in _facts(e).attempts:
        if x.first and _in(a, x.d, e) and e.flt.eng_ok(x.eng):
            first += x.n
            passed += x.n if x.passed else 0
    return _pct(M.K50, passed, first)


K51_KINDS = (
    ("induction", "Inductions", "التعريفات"),
    ("airport_pass", "Airport passes", "تصاريح المطار"),
    ("adp", "ADPs", "تصاريح القيادة"),
    ("avp", "AVPs", "تصاريح المركبات"),
    ("worker_id", "Worker IDs", "هويات العمال"),
    ("vehicle_document", "Vehicle documents", "وثائق المركبات"),
    ("bg_recheck", "Background rechecks", "إعادة التحقق الأمني"),
    ("obstacle_clearance", "Obstacle clearances", "موافقات العوائق"),
)


def k51_counts(e: Engine, day: date, within: int = 30) -> Counter[str]:
    c: Counter[str] = Counter()
    last = day + timedelta(days=within)
    for x in _facts(e).creds:
        if day <= x.eff <= last and e.flt.eng_ok(x.eng) and (not x.sites or _sites_ok(e, x.sites)):
            c[x.kind] += 1
    return c


def k51(e: Engine, a: Agg) -> Result:
    c = k51_counts(e, _end(e, a))
    res = _res(M.K51, Decimal(sum(c.values())), sum(c.values()))
    res.components = [_comp(k, en, ar, c.get(k, 0)) for k, en, ar in K51_KINDS]
    return res


def gate_rows(e: Engine, a: Agg, gate: UUID | None = None) -> list[GateAgg]:
    out = []
    for r in _facts(e).gate:
        if not _in(a, r.d, e):
            continue
        if r.site is not None and not e.flt.site_ok(r.site):
            continue
        if not e.flt.eng_ok(r.eng) and e.flt.engs is not None:
            continue
        if e.flt.zone_filtered and not e.flt.zone_ok(r.zone, e.facts.zones):
            continue
        if gate is not None and r.gate != gate:
            continue
        out.append(r)
    return out


def k52(e: Engine, a: Agg) -> Result:
    n = sum(r.n for r in gate_rows(e, a, getattr(e, "gate_id", None)))
    return _res(M.K52, Decimal(n), n)


def k53(e: Engine, a: Agg) -> Result:
    rows = gate_rows(e, a, getattr(e, "gate_id", None))
    total = sum(r.n for r in rows)
    denied = sum(r.n for r in rows if r.denied)
    res = _pct(M.K53, denied, total)
    by: Counter[str] = Counter()
    for r in rows:
        if r.denied:
            by[r.reason or "OTHER"] += r.n
    res.components = [
        _comp(k, *reason_label(k), v) for k, v in sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return res


def reason_label(code: str) -> tuple[str, str]:
    from app.core.access_enums import GateReasonCode  # noqa: PLC0415
    from app.services.access.reasons import GATE_TEXT  # noqa: PLC0415 (services import kpi)

    try:
        return GATE_TEXT[GateReasonCode(code)]
    except (ValueError, KeyError):
        return code, code


def k53b(e: Engine, a: Agg) -> Result:
    gate = getattr(e, "gate_id", None)
    n = 0
    for r in _facts(e).admitted:
        if not _in(a, r.d, e) or (gate is not None and r.gate != gate):
            continue
        if r.site is not None and not e.flt.site_ok(r.site):
            continue
        if e.flt.engs is not None and not e.flt.eng_ok(r.eng):
            continue
        if e.flt.zone_filtered and not e.flt.zone_ok(r.zone, e.facts.zones):
            continue
        n += r.n
    return _res(M.K53b, Decimal(n), n)


def k54(e: Engine, a: Agg) -> Result:
    due = on_time = 0
    for c in _facts(e).custody:
        if _in(a, c.due, e) and e.flt.eng_ok(c.eng):
            due += 1
            if c.returned is not None and c.returned <= c.due:
                on_time += 1
    return _pct(M.K54, on_time, due)


def k55(e: Engine, a: Agg) -> Result:
    day = _end(e, a)
    buckets = {"1-7": 0, "8-30": 0, "31+": 0}
    n = 0
    for c in _facts(e).custody:
        if not e.flt.eng_ok(c.eng) or c.lost:
            continue
        if day > c.due and (c.returned is None or c.returned > day):
            n += 1
            late = (day - c.due).days
            buckets["1-7" if late <= 7 else "8-30" if late <= 30 else "31+"] += 1
    res = _res(M.K55, Decimal(n), n)
    res.components = [
        _comp("d1_7", "1-7 days", "1-7 أيام", buckets["1-7"]),
        _comp("d8_30", "8-30 days", "8-30 يوماً", buckets["8-30"]),
        _comp("d31_plus", "> 30 days", "أكثر من 30 يوماً", buckets["31+"]),
    ]
    return res


def k56(e: Engine, a: Agg) -> Result:
    day = _end(e, a)
    leads = [
        (x.issued - x.submitted).days
        for x in _facts(e).apps
        if x.issued and x.submitted and _in(a, x.issued, e) and e.flt.eng_ok(x.eng)
    ]
    stale = sum(
        1
        for x in _facts(e).apps
        if x.lodged is not None
        and x.lodged + timedelta(days=x.stale_days) < day
        and (x.decided is None or x.decided > day)
        and e.flt.eng_ok(x.eng)
    )
    value = Decimal(str(statistics.median(leads))) if leads else None
    res = _res(M.K56, value, len(leads), None, None if leads else NullReason.NO_DENOMINATOR)
    res.components = [_comp("stale", "Lodged and stale", "طلبات متأخرة", stale)]
    return res


def active_adps(e: Engine, day: date) -> int:
    n = 0
    for x in _facts(e).adps:
        if not e.flt.eng_ok(x.eng) or x.issued is None or x.issued > day:
            continue
        if x.until is not None and x.until < day:
            continue
        if x.ended is not None and x.ended <= day:
            continue
        if any(s <= day and (t is None or t > day) for s, t in x.susp):
            continue
        n += 1
    return n


def k57(e: Engine, a: Agg) -> Result:
    offs = [
        o for o in _facts(e).offences
        if o.counted and _in(a, o.d, e) and e.flt.eng_ok(o.eng)
        and (not e.flt.zone_filtered or e.flt.zone_ok(o.zone, e.facts.zones))
    ]  # fmt: skip
    den = active_adps(e, _end(e, a))
    value = Decimal(len(offs)) * HUNDRED / Decimal(den) if den else None
    res = _res(M.K57, value, len(offs), den, None if den else NullReason.NO_DENOMINATOR)
    susp = sum(1 for d, eng in _facts(e).adp_susp if _in(a, d, e) and e.flt.eng_ok(eng))
    res.components = [
        _comp("suspensions", "ADP suspensions", "إيقافات تصاريح القيادة", susp),
        _comp(
            "off05", "OFF-05 offences", "مخالفات OFF-05", sum(1 for o in offs if o.code == "OFF-05")
        ),
    ]
    return res


def _wap_ok(e: Engine, eng: UUID, site: UUID, zones: frozenset[UUID]) -> bool:
    return (
        e.flt.eng_ok(eng)
        and e.flt.site_ok(site)
        and (not e.flt.zone_filtered or _zones_ok(e, zones))
    )


def k58(e: Engine, a: Agg) -> Result:
    day = _end(e, a)
    waps = [w for w in _facts(e).waps if _wap_ok(e, w.eng, w.site, w.zones)]
    approved = sum(1 for w in waps if _in(a, w.approved, e))
    active = sum(
        1
        for w in waps
        if w.activated is not None
        and w.activated <= day
        and (w.ended is None or w.ended > day)
        and w.valid_from <= day <= w.valid_to
    )
    by: Counter[str] = Counter(
        s.reason
        for s in _facts(e).wap_susp
        if _in(a, s.d, e) and _wap_ok(e, s.eng, s.site, s.zones)
    )
    blocked = 0
    lo, hi = a.window.start, day
    for w in waps:
        if w.approved is None:
            continue
        start = max(lo, w.valid_from, w.approved)
        stop = min(hi, w.valid_to, (w.activated - timedelta(days=1)) if w.activated else hi)
        if w.ended is not None and w.activated is None:
            stop = min(stop, w.ended - timedelta(days=1))
        if stop >= start:
            blocked += (stop - start).days + 1
    res = _res(M.K58, Decimal(approved), approved)
    res.components = [
        _comp("active", "Active at as of", "سارية", active),
        _comp("susp_ops", "Suspensions — operational", "إيقافات تشغيلية", by.get("ops", 0)),
        _comp(
            "susp_violation", "Suspensions — violation", "إيقافات مخالفة", by.get("violation", 0)
        ),
        _comp(
            "susp_dependency",
            "Suspensions — dependency",
            "إيقافات اعتمادية",
            by.get("dependency", 0),
        ),
        _comp("susp_other", "Suspensions — other", "إيقافات أخرى", by.get("other", 0)),
        _comp("blocked_days", "WAP-days blocked", "أيام التصاريح المعطلة", blocked),
    ]
    return res


def k59(e: Engine, a: Agg) -> Result:
    rows = [
        n for n in _facts(e).ntms
        if _in(a, n.d, e) and e.flt.eng_ok(n.eng)
        and (not e.flt.zone_filtered or _zones_ok(e, n.zones))
    ]  # fmt: skip
    return _pct(M.K59, sum(1 for n in rows if not n.late), len(rows))


def k60(e: Engine, a: Agg) -> Result:
    day = _end(e, a)
    rows = [
        o for o in _facts(e).obstacles
        if e.flt.eng_ok(o.eng) and (not e.flt.zone_filtered or e.flt.zone_ok(o.zone, e.facts.zones))
    ]  # fmt: skip
    act = [
        o for o in rows
        if o.approved and o.valid_from is not None and o.valid_to is not None
        and o.valid_from <= day <= o.valid_to
    ]  # fmt: skip
    expiring = sum(
        1 for o in act if o.valid_to is not None and o.valid_to <= day + timedelta(days=7)
    )
    rejected = sum(1 for o in rows if _in(a, o.rejected_on, e))
    res = _res(M.K60, Decimal(len(act)), len(act))
    res.components = [
        _comp("expiring_7d", "Expiring ≤ 7 days", "تنتهي خلال 7 أيام", expiring),
        _comp("rejected", "Rejected in period", "مرفوضة في الفترة", rejected),
        _comp(
            "penetration",
            "Active with OLS penetration",
            "سارية مع اختراق OLS",
            sum(1 for o in act if o.penetration),
        ),
    ]
    return res


ACCESS_DISPATCH: dict[KpiMetric, Callable[[Engine, Agg], Result]] = {
    M.K48: k48,
    M.K49: k49,
    M.K50: k50,
    M.K51: k51,
    M.K52: k52,
    M.K53: k53,
    M.K53b: k53b,
    M.K54: k54,
    M.K55: k55,
    M.K56: k56,
    M.K57: k57,
    M.K58: k58,
    M.K59: k59,
    M.K60: k60,
}

_engine._DISPATCH.update(ACCESS_DISPATCH)
