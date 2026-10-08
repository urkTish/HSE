"""PTW KPIs K-46, K-46b, K-61…K-71 (3-ptw §6.11, KP-1…KP-6).

Pure functions over ``PtwFacts`` and the engine's filter / window / as_of, registered into the
engine dispatch at import. Filters: site, zone (any of the permit's zones), engagement (tree
already expanded by the scope) and the PTW-only `permit_type` (any of the permit's types),
read from ``engine.permit_types`` when set.
"""

from __future__ import annotations

import statistics
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from app.core.hse_enums import KpiKind, KpiMetric, NullReason
from app.core.ptw_enums import PermitType, PtwAuditType, ShiftEndType
from app.kpi import engine as _engine
from app.kpi.engine import Agg, Component, Engine, Result
from app.kpi.ptw_facts import AuditFact, PermitFact, PtwFacts, ShiftFact, SuspFact

UUID = uuid.UUID
M = KpiMetric
HUNDRED = Decimal(100)

TYPE_LABELS: dict[str, tuple[str, str]] = {
    "general": ("General work", "أعمال عامة"),
    "hot_work": ("Hot work", "أعمال ساخنة"),
    "confined_space": ("Confined space", "أماكن محصورة"),
    "work_at_height": ("Work at height", "العمل على ارتفاع"),
    "excavation": ("Excavation", "الحفر"),
    "electrical_isolation": ("Electrical / isolation", "الكهرباء والعزل"),
    "lifting": ("Lifting", "الرفع"),
    "radiography": ("Radiography", "التصوير الإشعاعي"),
    "airside_works": ("Airside works", "أعمال الجانب الجوي"),
}


# ---- helpers -------------------------------------------------------------------------------------


def facts(e: Engine) -> PtwFacts:
    pf = getattr(e.facts, "ptw", None)
    return pf if isinstance(pf, PtwFacts) else PtwFacts()


def _end(e: Engine, a: Agg) -> date:
    return min(e.as_of, a.window.end)


def _in(e: Engine, a: Agg, d: date | None) -> bool:
    return d is not None and a.window.start <= d <= _end(e, a)


def permit_ok(e: Engine, p: PermitFact | None) -> bool:
    if p is None:
        return False
    f = e.flt
    if not f.eng_ok(p.eng) or not f.site_ok(p.site):
        return False
    if f.zone_filtered and not any(f.zone_ok(z, e.facts.zones) for z in p.zones):
        return False
    types = getattr(e, "permit_types", None)
    return not types or bool(p.types & types)


def audit_ok(e: Engine, x: AuditFact) -> bool:
    pf = facts(e)
    if x.permit is not None:
        return permit_ok(e, pf.permits.get(x.permit))
    f = e.flt
    if not f.eng_ok(x.eng) or not f.site_ok(x.site):
        return False
    if f.zone_filtered and not f.zone_ok(x.zone, e.facts.zones):
        return False
    return not getattr(e, "permit_types", None)


def _comp(
    key: str,
    en: str,
    ar: str,
    v: int | Decimal | None,
    kind: KpiKind = KpiKind.count_,
    dp: int = 0,
) -> Component:
    return Component(key, en, ar, None if v is None else Decimal(v), kind, dp)


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


def field_audits(e: Engine, a: Agg) -> list[AuditFact]:
    return [
        x
        for x in facts(e).audits
        if x.counted and x.audit_type == PtwAuditType.field and _in(e, a, x.d) and audit_ok(e, x)
    ]


def _shifts(e: Engine) -> list[tuple[PermitFact, ShiftFact]]:
    pf = facts(e)
    out = []
    for s in pf.shifts:
        p = pf.permits.get(s.permit)
        if permit_ok(e, p):
            assert p is not None  # noqa: S101
            out.append((p, s))
    return out


# ---- metrics -------------------------------------------------------------------------------------


def k46(e: Engine, a: Agg) -> Result:
    n = len(field_audits(e, a))
    res = _res(M.K46, Decimal(n), n)
    k46b_ = k46b(e, a)
    res.components = [
        _comp(
            "coverage",
            "Audit coverage (K-46b)",
            "تغطية التدقيق",
            k46b_.value,
            KpiKind.percentage,
            1,
        )
    ]
    return res


def live_in(e: Engine, a: Agg, p: PermitFact) -> bool:
    if p.issued_d is None:
        return False
    hi = _end(e, a)
    return p.issued_d <= hi and (p.end_d is None or p.end_d >= a.window.start)


def k46b(e: Engine, a: Agg) -> Result:
    pf = facts(e)
    live = {p.id for p in pf.permits.values() if permit_ok(e, p) and live_in(e, a, p)}
    audited = {x.permit for x in field_audits(e, a) if x.permit in live}
    return _pct(M.K46b, len(audited), len(live))


def k61(e: Engine, a: Agg) -> Result:
    rows = field_audits(e, a)
    return _pct(M.K61, sum(x.compliant for x in rows), sum(x.applicable for x in rows))


def k62(e: Engine, a: Agg) -> Result:
    rows = [p for p in facts(e).permits.values() if permit_ok(e, p) and _in(e, a, p.issued_d)]
    res = _res(M.K62, Decimal(len(rows)), len(rows))
    by = Counter(p.primary for p in rows)
    comps = [
        _comp(t.value, *TYPE_LABELS[t.value], by.get(t.value, 0))
        for t in PermitType
        if by.get(t.value, 0)
    ]
    comps.append(
        _comp(
            "critical_lifts",
            "Critical lifts",
            "رفعات حرجة",
            sum(1 for p in rows if p.critical_lift),
        )
    )
    comps.append(
        _comp(
            "high_risk",
            "High-risk permits",
            "تصاريح عالية الخطورة",
            sum(1 for p in rows if p.high_risk),
        )
    )
    res.components = comps
    return res


def k62_any_type(e: Engine, a: Agg) -> Counter[str]:
    c: Counter[str] = Counter()
    for p in facts(e).permits.values():
        if permit_ok(e, p) and _in(e, a, p.issued_d):
            for t in p.types:
                c[t] += 1
    return c


def k63_count(e: Engine, a: Agg) -> int:
    return sum(1 for _p, s in _shifts(e) if _in(e, a, s.started))


def k63(e: Engine, a: Agg) -> Result:
    n = k63_count(e, a)
    return _res(M.K63, Decimal(n), n)


def critical_items(e: Engine, a: Agg) -> Counter[str]:
    c: Counter[str] = Counter()
    for x in field_audits(e, a):
        for code, answer, sev in x.items:
            if answer == "non_compliant" and sev == "critical":
                c[code] += 1
    for x in facts(e).audits:
        if (
            x.counted
            and x.audit_type == PtwAuditType.unpermitted_work
            and _in(e, a, x.d)
            and audit_ok(e, x)
        ):
            c["A00"] += 1
    return c


def k64(e: Engine, a: Agg) -> Result:
    field_n = sum(x.critical for x in field_audits(e, a))
    unpermitted = sum(
        1
        for x in facts(e).audits
        if x.counted
        and x.audit_type == PtwAuditType.unpermitted_work
        and _in(e, a, x.d)
        and audit_ok(e, x)
    )
    n = field_n + unpermitted
    den = len(field_audits(e, a))
    rate = Decimal(n) * HUNDRED / Decimal(den) if den else None
    res = _res(M.K64, Decimal(n), n, den)
    res.components = [
        _comp("rate", "Per 100 field audits", "لكل 100 تدقيق ميداني", rate, KpiKind.rate, 2),
        _comp("field", "Critical items in field audits", "بنود حرجة في التدقيق الميداني", field_n),
        _comp("unpermitted_work", "Unpermitted work", "عمل دون تصريح", unpermitted),
    ]
    return res


def suspensions(e: Engine, a: Agg) -> list[tuple[PermitFact, SuspFact]]:
    pf = facts(e)
    out = []
    for s in pf.susps:
        p = pf.permits.get(s.permit)
        if permit_ok(e, p) and _in(e, a, s.d):
            assert p is not None  # noqa: S101
            out.append((p, s))
    return out


def k65(e: Engine, a: Agg) -> Result:
    rows = suspensions(e, a)
    non = [s for _p, s in rows if not s.routine]
    routine = [s for _p, s in rows if s.routine]
    shifts = k63_count(e, a)
    rate = Decimal(len(non)) * HUNDRED / Decimal(shifts) if shifts else None
    res = _res(M.K65, Decimal(len(non)), len(non), shifts)
    by = Counter(s.reason.value for s in non)
    res.components = [
        _comp("rate", "Per 100 permit-shifts", "لكل 100 وردية", rate, KpiKind.rate, 2),
        _comp("routine", "Routine (shift end, midday ban)", "اعتيادية", len(routine)),
        *[
            _comp(f"reason:{k}", k, k, v)
            for k, v in sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    ]
    return res


def k66(e: Engine, a: Agg) -> Result:
    rows = [s for _p, s in _shifts(e) if s.gas_required and _in(e, a, s.ended)]
    return _pct(M.K66, sum(1 for s in rows if s.gas_compliant), len(rows))


def k67(e: Engine, a: Agg) -> Result:
    day = _end(e, a)
    pf = facts(e)
    n = lt = 0
    types = getattr(e, "permit_types", None)
    for x in pf.isos:
        if x.isolated is None or x.isolated > day or (x.ended is not None and x.ended <= day):
            continue
        if x.eng is not None and not e.flt.eng_ok(x.eng):
            continue
        if x.eng is None and e.flt.engs is not None:
            continue
        linked = [pf.permits[i] for i in x.permits if i in pf.permits]
        if (e.flt.sites is not None or e.flt.zone_filtered or types) and not any(
            permit_ok(e, p) for p in linked
        ):
            continue
        n += 1
        if x.verified_at is not None and (day - x.verified_at.date()).days > x.long_term_days:
            lt += 1
    res = _res(M.K67, Decimal(n), n)
    res.components = [_comp("long_term", "Long-term", "طويلة الأمد", lt)]
    return res


def _conflict_ok(e: Engine, pf: PtwFacts, pair: tuple[UUID, UUID]) -> bool:
    return any(permit_ok(e, pf.permits.get(i)) for i in pair)


def k68(e: Engine, a: Agg) -> Result:
    pf = facts(e)
    day = _end(e, a)
    rows = [c for c in pf.conflicts if _in(e, a, c.d) and _conflict_ok(e, pf, c.permits)]
    open_n = sum(
        1
        for c in pf.conflicts
        if c.d <= day
        and (c.open_until is None or c.open_until > day)
        and _conflict_ok(e, pf, c.permits)
    )
    by = Counter(c.result for c in rows)
    res = _res(M.K68, Decimal(len(rows)), len(rows))
    res.components = [
        _comp("prohibited", "Prohibited", "محظورة", by.get("prohibited", 0)),
        _comp("conditional", "Conditional", "مشروطة", by.get("conditional", 0)),
        _comp("open", "Open at as of", "مفتوحة", open_n),
    ]
    return res


def k69(e: Engine, a: Agg) -> Result:
    rows = [p for p in facts(e).permits.values() if permit_ok(e, p)]
    closed = sum(1 for p in rows if _in(e, a, p.closed_d))
    expired = sum(1 for p in rows if _in(e, a, p.expired_d))
    res = _pct(M.K69, closed, closed + expired)
    res.components = [_comp("expired", "Expired", "منتهية", expired)]
    return res


def k70(e: Engine, a: Agg) -> Result:
    n = sum(1 for _p, s in _shifts(e) if s.end_type == ShiftEndType.lapsed and _in(e, a, s.ended))
    return _res(M.K70, Decimal(n), n)


def k71(e: Engine, a: Agg) -> Result:
    hours = [
        Decimal((p.first_issued_at - p.first_requested_at).total_seconds()) / Decimal(3600)
        for p in facts(e).permits.values()
        if permit_ok(e, p)
        and _in(e, a, p.issued_d)
        and p.first_issued_at is not None
        and p.first_requested_at is not None
    ]
    if not hours:
        return _res(M.K71, None, 0, None, NullReason.NO_DENOMINATOR)
    return _res(M.K71, Decimal(str(statistics.median(hours))), len(hours))


PTW_DISPATCH: dict[KpiMetric, Callable[[Engine, Agg], Result]] = {
    M.K46: k46,
    M.K46b: k46b,
    M.K61: k61,
    M.K62: k62,
    M.K63: k63,
    M.K64: k64,
    M.K65: k65,
    M.K66: k66,
    M.K67: k67,
    M.K68: k68,
    M.K69: k69,
    M.K70: k70,
    M.K71: k71,
}

_engine._DISPATCH.update(PTW_DISPATCH)
