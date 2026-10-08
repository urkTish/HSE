"""Certification KPIs K-72…K-81 (4-third-party-cert §6.7, KC-1…KC-3).

Pure functions over ``CertFacts`` and the engine's filter / window / as_of, registered into the
engine dispatch at import. Point-in-time metrics are evaluated at min(as_of, window end) (KC-2);
period metrics use the window up to that day. Filters: site (any of the deployment's sites), zone
(equipment deployment / scaffold zone), engagement (tree already expanded by the scope) and the
certification-only `equipment_category` / `cert_type`, read from ``engine.equipment_categories`` /
``engine.cert_types`` when set.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from decimal import Decimal

from app.core.cert_enums import (
    DefectCategory,
    DefectStatus,
    ScaffoldStatus,
    ScaffoldTagStatus,
    ServiceStatus,
    VerificationOutcome,
)
from app.core.hse_enums import KpiKind, KpiMetric, NullReason
from app.kpi import engine as _engine
from app.kpi.cert_facts import (
    FAILED,
    CertFacts,
    DefectFact,
    EqDepFact,
    ScaffoldFact,
    SubFact,
    VerFact,
    WorkerDepFact,
)
from app.kpi.engine import Agg, Component, Engine, Result

UUID = uuid.UUID
M = KpiMetric
HUNDRED = Decimal(100)
SCAFFOLD = "scaffold"

def label(cat: str) -> tuple[str, str]:
    from app.core.cert_enums import EquipmentCertCategory  # noqa: PLC0415
    from app.services.cert.reference import EQC  # noqa: PLC0415

    try:
        e = EQC.get(EquipmentCertCategory(cat))
    except ValueError:
        e = None
    if e is None:
        return ("Scaffold", "سقالة") if cat == SCAFFOLD else (cat, cat)
    return e.label_en, e.label_ar


# ---- helpers ----


def facts(e: Engine) -> CertFacts:
    cf = getattr(e.facts, "cert", None)
    return cf if isinstance(cf, CertFacts) else CertFacts()


def day(e: Engine, a: Agg) -> date:
    return min(e.as_of, a.window.end)


def _in(e: Engine, a: Agg, d: date | None) -> bool:
    return d is not None and a.window.start <= d <= day(e, a)


def _cats(e: Engine) -> frozenset[str] | None:
    return getattr(e, "equipment_categories", None)


def _types(e: Engine) -> frozenset[str] | None:
    return getattr(e, "cert_types", None)


def _sites_ok(e: Engine, sites: frozenset[UUID], project: UUID | None) -> bool:
    want = e.flt.sites
    if want is None:
        return True
    if sites:
        return bool(sites & want)
    sp = facts(e).site_project
    return project is not None and any(sp.get(s) == project for s in want)


def _zone_ok(e: Engine, zone: UUID | None) -> bool:
    return e.flt.zone_ok(zone, e.facts.zones)


def dep_ok(e: Engine, x: EqDepFact, *, scaffold_cat: bool = False) -> bool:
    if not e.flt.eng_ok(x.eng) or not _sites_ok(e, x.sites, x.project) or not _zone_ok(e, x.zone):
        return False
    cats = _cats(e)
    if cats is not None and x.category not in cats:
        return False
    return scaffold_cat or x.category != SCAFFOLD


def scaffold_ok(e: Engine, s: ScaffoldFact) -> bool:
    cats = _cats(e)
    if cats is not None and SCAFFOLD not in cats:
        return False
    if not e.flt.eng_ok(s.eng) or not _zone_ok(e, s.zone):
        return False
    z = e.facts.zones.get(s.zone)
    return e.flt.sites is None or (z is not None and z.site in e.flt.sites)


def worker_ok(e: Engine, w: WorkerDepFact) -> bool:
    return e.flt.eng_ok(w.eng) and _sites_ok(e, w.sites, w.project)


def _attr_ok(
    e: Engine,
    eng: UUID | None,
    sites: frozenset[UUID],
    project: UUID,
    category: str | None,
    cert_type: str | None,
) -> bool:
    if not e.flt.eng_ok(eng) or not _sites_ok(e, sites, project):
        return False
    cats, types = _cats(e), _types(e)
    if cats is not None and category not in cats:
        return False
    return types is None or cert_type in types


def sub_ok(e: Engine, s: SubFact | VerFact) -> bool:
    return _attr_ok(e, s.eng, s.sites, s.project, s.category, s.cert_type)


def defect_ok(e: Engine, x: DefectFact) -> bool:
    if not e.flt.eng_ok(x.eng) or not _sites_ok(e, x.sites, x.project):
        return False
    if e.flt.zone_filtered and not _zone_ok(e, x.zone):
        return False
    cats = _cats(e)
    return cats is None or x.equipment_category in cats


def _comp(
    key: str, en: str, ar: str, v: int | Decimal | None, kind: KpiKind = KpiKind.count_, dp: int = 0
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


def pct(metric: KpiMetric, num: int, den: int) -> Result:
    if den == 0:
        return _res(metric, None, num, den, NullReason.NO_DENOMINATOR)
    return _res(metric, Decimal(num) / Decimal(den) * HUNDRED, num, den)


def _pct_val(num: int, den: int) -> Decimal | None:
    return Decimal(num) / Decimal(den) * HUNDRED if den else None


def _unique(rows: Iterable[EqDepFact]) -> list[EqDepFact]:
    """One row per item (an item On Site twice on the scoped projects counts once per project)."""
    seen: set[tuple[UUID, UUID]] = set()
    out = []
    for x in rows:
        k = (x.project, x.item)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def on_site(e: Engine, a: Agg) -> list[EqDepFact]:
    d = day(e, a)
    return _unique(x for x in facts(e).eq_deps if x.on_site(d) and dep_ok(e, x))


def mobilised(e: Engine, a: Agg) -> list[tuple[WorkerDepFact, str]]:
    """Mobilised deployments at day whose trade maps to a certificate type (K-76)."""
    cf = facts(e)
    d = day(e, a)
    types = _types(e)
    out = []
    seen: set[tuple[UUID, UUID]] = set()
    for w in cf.worker_deps:
        if not w.mobilised(d) or not worker_ok(e, w):
            continue
        s = cf.settings.get(w.project)
        code = (s.trade_cert_requirements or {}).get(w.trade) if s is not None else None
        if not code or (types is not None and code not in types):
            continue
        k = (w.project, w.worker)
        if k in seen:
            continue
        seen.add(k)
        out.append((w, code))
    return out


def in_use(e: Engine, a: Agg) -> list[ScaffoldFact]:
    d = day(e, a)
    return [s for s in facts(e).scaffolds if s.in_use(d) and scaffold_ok(e, s)]


# ---- metrics ----


def k72(e: Engine, a: Agg) -> Result:
    cf = facts(e)
    d = day(e, a)
    rows = on_site(e, a)
    ok = [x for x in rows if cf.item_valid(x.item, d)]
    res = pct(M.K72, len(ok), len(rows))
    tot = Counter(x.category for x in rows)
    good = Counter(x.category for x in ok)
    res.components = [
        _comp(f"category:{c}", *label(c), _pct_val(good[c], n), KpiKind.percentage, 1)
        for c, n in sorted(tot.items())
    ]
    return res


def k73(e: Engine, a: Agg) -> Result:
    cf = facts(e)
    d = day(e, a)
    by: Counter[str] = Counter()
    for x in on_site(e, a):
        vu = cf.item_valid_until(x.item, d)
        if vu is not None and d <= vu <= d + timedelta(days=30):
            by[x.category] += 1
    n = sum(by.values())
    res = _res(M.K73, Decimal(n), n)
    res.components = [_comp(f"category:{c}", *label(c), v) for c, v in sorted(by.items())]
    return res


def a_defects(e: Engine, a: Agg) -> list[DefectFact]:
    return [
        x
        for x in facts(e).defects
        if x.category == DefectCategory.A
        and x.status != DefectStatus.cancelled
        and _in(e, a, x.raised)
        and defect_ok(e, x)
    ]


def k74(e: Engine, a: Agg) -> Result:
    cf = facts(e)
    d = day(e, a)
    rows = [
        x
        for x in on_site(e, a)
        if x.item in cf.items and cf.items[x.item].status_on(d) == ServiceStatus.out_of_service
    ]
    n = len(rows)
    res = _res(M.K74, Decimal(n), n)
    res.components = [
        _comp("out_of_service", "Out of service", "خارج الخدمة", n),
        _comp(
            "a_defects", "A defects raised in period", "عيوب فئة A في الفترة", len(a_defects(e, a))
        ),
    ]
    return res


def overdue_equipment(e: Engine, a: Agg) -> list[EqDepFact]:
    cf = facts(e)
    d = day(e, a)
    out = []
    for x in on_site(e, a):
        latest = cf.latest_line(x.item, d)
        if latest is None or latest.valid_until is None:
            continue
        if latest.valid_until < d and not cf.item_valid(x.item, d):
            out.append(x)
    return out


def overdue_scaffolds(e: Engine, a: Agg) -> list[ScaffoldFact]:
    d = day(e, a)
    return [s for s in in_use(e, a) if s.tag_on(d) == ScaffoldTagStatus.expired]


def k75(e: Engine, a: Agg) -> Result:
    eq = len(overdue_equipment(e, a))
    sc = len(overdue_scaffolds(e, a))
    res = _res(M.K75, Decimal(eq + sc), eq + sc)
    res.components = [
        _comp("equipment", "Equipment", "المعدات", eq),
        _comp("scaffolds", "Scaffolds", "السقالات", sc),
    ]
    return res


def k76(e: Engine, a: Agg) -> Result:
    cf = facts(e)
    d = day(e, a)
    rows = mobilised(e, a)
    ok = [(w, c) for w, c in rows if cf.worker_holds(w.worker, c, d)]
    res = pct(M.K76, len(ok), len(rows))
    tot = Counter(c for _w, c in rows)
    good = Counter(c for _w, c in ok)
    res.components = [
        _comp(f"cert_type:{c}", c, c, _pct_val(good[c], n), KpiKind.percentage, 1)
        for c, n in sorted(tot.items())
    ]
    return res


def expiring_pcs(e: Engine, a: Agg) -> list[tuple[WorkerDepFact, str]]:
    """In-force certificates of Mobilised workers with valid_until ∈ [d, d + 30] (K-77)."""
    cf = facts(e)
    d = day(e, a)
    types = _types(e)
    out: list[tuple[WorkerDepFact, str]] = []
    seen: set[tuple[UUID, UUID]] = set()
    for w in cf.worker_deps:
        if not w.mobilised(d) or not worker_ok(e, w) or (w.project, w.worker) in seen:
            continue
        seen.add((w.project, w.worker))
        for pc in cf.pcs.get(w.worker, []):
            if types is not None and pc.cert_type not in types:
                continue
            if cf.banned(w.worker, d, pc.cert_type) or not pc.in_force(d):
                continue
            if pc.valid_until is not None and d <= pc.valid_until <= d + timedelta(days=30):
                out.append((w, pc.cert_type))
    return out


def k77(e: Engine, a: Agg) -> Result:
    rows = expiring_pcs(e, a)
    by = Counter(c for _w, c in rows)
    res = _res(M.K77, Decimal(len(rows)), len(rows))
    res.components = [_comp(f"cert_type:{c}", c, c, v) for c, v in sorted(by.items())]
    return res


def k78_parts(e: Engine, a: Agg) -> tuple[int, int, int]:
    cf = facts(e)
    d = day(e, a)
    items = {
        x.item
        for x in cf.eq_deps
        if x.start is not None and x.start <= d and dep_ok(e, x, scaffold_cat=True)
    }
    eq = sum(1 for i in items if cf.blacklisted_on(i, d))
    workers = {w.worker for w in cf.worker_deps if worker_ok(e, w) and (w.start or d) <= d}
    persons = sum(1 for w in workers if cf.banned(w, d))
    tpis = sum(1 for _code, since in cf.tpis_blacklisted if since <= d)
    return eq, persons, tpis


def k78(e: Engine, a: Agg) -> Result:
    eq, persons, tpis = k78_parts(e, a)
    n = eq + persons + tpis
    res = _res(M.K78, Decimal(n), n)
    res.components = [
        _comp("equipment", "Equipment", "المعدات", eq),
        _comp("persons", "Persons", "الأشخاص", persons),
        _comp("tpis", "TPIs", "جهات الفحص", tpis),
    ]
    return res


def subs(e: Engine, a: Agg) -> list[SubFact]:
    return [s for s in facts(e).subs if _in(e, a, s.submitted) and sub_ok(e, s)]


def failed_verifications(
    e: Engine, a: Agg, outcomes: frozenset[VerificationOutcome] = FAILED
) -> list[VerFact]:
    return [v for v in facts(e).vers if v.outcome in outcomes and _in(e, a, v.d) and sub_ok(e, v)]


def k79(e: Engine, a: Agg) -> Result:
    d = day(e, a)
    num = den = 0
    for s in subs(e, a):
        done = s.conclusive is not None and s.conclusive <= d
        if not done and s.due >= d:
            continue  # window not ended and still unverified
        den += 1
        if done and s.conclusive is not None and s.conclusive <= s.due:
            num += 1
    res = pct(M.K79, num, den)
    res.components = [
        _comp("failed", "Failed verifications", "تحقق فاشل", len(failed_verifications(e, a)))
    ]
    return res


def b_due(e: Engine, a: Agg) -> list[DefectFact]:
    d = day(e, a)
    return [
        x
        for x in facts(e).defects
        if x.category == DefectCategory.B
        and x.status != DefectStatus.cancelled
        and x.due is not None
        and a.window.start <= x.due <= d
        and defect_ok(e, x)
    ]


def k80(e: Engine, a: Agg) -> Result:
    rows = b_due(e, a)
    ok = [
        x
        for x in rows
        if x.status == DefectStatus.closed and x.closed is not None and x.due is not None
        and x.closed <= x.due
    ]  # fmt: skip
    return pct(M.K80, len(ok), len(rows))


def k81(e: Engine, a: Agg) -> Result:
    d = day(e, a)
    rows = [
        s
        for s in in_use(e, a)
        if s.status not in (ScaffoldStatus.closed_red, ScaffoldStatus.under_erection,
                            ScaffoldStatus.under_alteration)
    ]  # fmt: skip
    ok = [s for s in rows if s.tag_on(d) in (ScaffoldTagStatus.green, ScaffoldTagStatus.yellow)]
    return pct(M.K81, len(ok), len(rows))


CERT_DISPATCH: dict[KpiMetric, Callable[[Engine, Agg], Result]] = {
    M.K72: k72,
    M.K73: k73,
    M.K74: k74,
    M.K75: k75,
    M.K76: k76,
    M.K77: k77,
    M.K78: k78,
    M.K79: k79,
    M.K80: k80,
    M.K81: k81,
}

_engine._DISPATCH.update(CERT_DISPATCH)
