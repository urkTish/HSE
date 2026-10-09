"""Environmental KPIs K-118…K-126 (spec 6e-environmental §6.3–§6.7, EK-1).

Computed from the 6e registers on the request's session, reached through the per-request heat
facts (same session and project list), as the 6c / 6d KPIs. as_of = the period end or today,
whichever is earlier. Attribution (EK-1): consignments → local dispatch date and the generator;
readings and exceedances → `day` (local date of window_end) and, for exceedances, the responsible
engagement once reviewed; spills → occurred date and the responsible engagement; water → month;
permits → as_of (project level only: "—" with a contractor filter). Monitoring slots (K-122),
spill kits (K-125, owner engagement as K-107) and water (K-126) follow the site filter."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.hse_enums import KpiKind, KpiMetric, NullReason
from app.kpi import engine as engine_mod
from app.kpi.engine import Agg, Component, Engine, Result
from app.kpi.periods import Window

UUID = uuid.UUID
M = KpiMetric
D = Decimal
ZERO = Decimal(0)


@dataclass
class EFacts:
    db: Session
    pids: list[UUID]
    memo: dict[Any, Any] = field(default_factory=dict)


def efacts(e: Engine) -> EFacts | None:
    m: EFacts | None = getattr(e, "_env_facts", None)
    if m is None:
        hf = getattr(e.facts, "heat", None)
        if hf is None:
            return None
        m = EFacts(hf.db, list(hf.pids))
        e._env_facts = m  # type: ignore[attr-defined]
    return m


def _end(e: Engine, w: Window) -> date:
    return min(e.as_of, w.end)


def _memo(f: EFacts, key: Any, fn: Any) -> Any:
    if key not in f.memo:
        f.memo[key] = fn()
    return f.memo[key]


def _q(v: Decimal | None, places: str = "0.01") -> Decimal | None:
    return None if v is None else v.quantize(D(places), rounding=ROUND_HALF_UP)


# ---- K-118 permits (PRM-2) -----------------------------------------------------------------------


def permit_stats(db: Session, pids: list[UUID], as_of: date) -> tuple[int, int, int]:
    """(requirements in force, requirements applicable, required records expiring)."""
    from app.core.env_enums import PermitStatus  # noqa: PLC0415
    from app.services.env import common as ec  # noqa: PLC0415

    num = den = exp = 0
    for pid in pids:
        for code, pms in ec.requirements(db, pid).items():
            if not ec.applicable(pms, as_of):
                continue
            den += 1
            num += ec.requirement_in_force(db, pid, code, as_of)
            exp += any(ec.permit_status(db, pm, as_of) == PermitStatus.expiring for pm in pms)
    return num, den, exp


def _k118(e: Engine, a: Agg) -> Result:
    f = efacts(e)
    if f is None or e.flt.engs is not None:
        return Result(M.K118, None, null_reason=NullReason.NO_DENOMINATOR)
    num, den, exp = permit_stats(f.db, f.pids, _end(e, a.window))
    res = e._pct(M.K118, num, den)
    res.components = [
        Component("expiring", "Expiring ≤ 30 days", "تنتهي خلال 30 يوماً", D(exp), KpiKind.count_)
    ]
    return res


# ---- K-119…K-121 waste (§6.3, §6.4) --------------------------------------------------------------


@dataclass(frozen=True)
class Con:
    id: UUID
    no: str
    pid: UUID
    d: date
    due: date
    site: UUID | None
    eng: UUID
    stream: str
    wclass: str
    route: str
    t: Decimal | None
    sewage_m3: Decimal
    status: str
    received: date | None
    transporter: UUID
    facility: UUID


def consignments(f: EFacts) -> list[Con]:
    from app.core.env_enums import QuantityUnit, WasteClass  # noqa: PLC0415
    from app.models import WasteConsignment  # noqa: PLC0415
    from app.services.env import common as ec  # noqa: PLC0415
    from app.services.env import reference as rf  # noqa: PLC0415
    from app.services.env import waste  # noqa: PLC0415

    def load() -> list[Con]:
        out = []
        for c in f.db.scalars(
            select(WasteConsignment).where(WasteConsignment.project_id.in_(f.pids))
        ):
            wc = rf.stream_class(c.stream_code)
            m3 = ZERO
            if wc == WasteClass.liquid_sewage:
                q = D(c.quantity)
                m3 = q / 1000 if c.unit == QuantityUnit.L else q
            out.append(
                Con(
                    c.id, c.consignment_no, c.project_id, c.dispatched_date, c.due_on, c.site_id,
                    c.generator_engagement_id, c.stream_code, wc.value, c.route.value,
                    waste.tonnes(c), m3, c.status.value,
                    ec.local_day(c.receipt_recorded_at) if c.receipt_recorded_at else None,
                    c.transporter_id, c.facility_provider_id,
                )
            )  # fmt: skip
        return out

    return _memo(f, "cons", load)  # type: ignore[no-any-return]


def _con_ok(e: Engine, c: Con) -> bool:
    return (c.site is None or e.flt.site_ok(c.site)) and e.flt.eng_ok(c.eng)


def dispatched(e: Engine, w: Window) -> list[Con]:
    """§6.3: dispatched in the window (≤ as_of); voided and rejected excluded."""
    f = efacts(e)
    if f is None:
        return []
    end = _end(e, w)
    return [
        c
        for c in consignments(f)
        if w.start <= c.d <= end and c.status not in ("voided", "rejected") and _con_ok(e, c)
    ]


def tonnage(cs: list[Con]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """(total t, diverted t, hazardous t, sewage m³)."""
    from app.services.env import reference as rf  # noqa: PLC0415

    tot = div = haz = m3 = ZERO
    for c in cs:
        m3 += c.sewage_m3
        if c.t is None:
            continue
        tot += c.t
        div += c.t if c.route in {r.value for r in rf.DIVERTED} else ZERO
        haz += c.t if c.wclass == "hazardous" else ZERO
    return tot, div, haz, m3


def _k119(e: Engine, a: Agg) -> Result:
    tot, _div, haz, m3 = tonnage(dispatched(e, a.window))
    res = e._count(M.K119, tot)
    inten = tot * 100000 / a.mh if a.mh else None
    res.components = [
        Component("hazardous_t", "Hazardous", "خطرة", haz, KpiKind.count_, 1),
        Component("intensity", "t per 100,000 h", "طن لكل 100,000 ساعة", inten, KpiKind.rate, 2),
        Component("sewage_m3", "Sewage m³", "صرف صحي م³", m3, KpiKind.count_, 0),
    ]
    return res


def _k120(e: Engine, a: Agg) -> Result:
    tot, div, _haz, _m3 = tonnage(dispatched(e, a.window))
    return e._pct(M.K120, div, tot)


def custody(e: Engine, w: Window) -> tuple[int, int, list[str]]:
    """K-121: (on time, due, late numbers) for due_on in the window and ≤ as_of."""
    f = efacts(e)
    if f is None:
        return 0, 0, []
    end = _end(e, w)
    on = n = 0
    late: list[str] = []
    for c in consignments(f):
        if not (w.start <= c.due <= end) or c.status == "voided" or not _con_ok(e, c):
            continue
        n += 1
        if c.received is not None and c.received <= c.due:
            on += 1
        else:
            late.append(c.no)
    return on, n, late


def _k121(e: Engine, a: Agg) -> Result:
    on, n, _late = custody(e, a.window)
    return e._pct(M.K121, on, n)


# ---- K-122 monitoring slots (§6.5) ---------------------------------------------------------------


def slots(e: Engine, w: Window) -> list[tuple[str, str, bool]]:
    """(point code, slot key, met) per (point, schedule) unit (DECISIONS: one slot per point and
    schedule, whatever the number of parameters)."""
    from app.core.env_enums import Averaging, RecordState  # noqa: PLC0415
    from app.models import EnvPoint, EnvReading  # noqa: PLC0415
    from app.services.field import common as fc  # noqa: PLC0415
    from app.services.heat import common as hc  # noqa: PLC0415

    f = efacts(e)
    if f is None:
        return []
    end = _end(e, w)
    if end < w.start:
        return []
    out: list[tuple[str, str, bool]] = []
    for pid in f.pids:
        work = hc.days_with_work(f.db, pid, w.start - timedelta(days=6), end)
        pts = [
            p
            for p in f.db.scalars(
                select(EnvPoint)
                .where(EnvPoint.project_id == pid, EnvPoint.active.is_(True))
                .order_by(EnvPoint.point_code)
            )
            if e.flt.site_ok(p.site_id)
        ]
        if not pts:
            continue
        rows = f.db.execute(
            select(EnvReading.point_id, EnvReading.parameter, EnvReading.averaging, EnvReading.day)
            .where(
                EnvReading.point_id.in_([p.id for p in pts]),
                EnvReading.status == RecordState.valid,
                EnvReading.averaging != Averaging.min15,
                EnvReading.day >= w.start - timedelta(days=6),
                EnvReading.day <= end,
            )
            .distinct()
        )
        have: dict[UUID, set[tuple[str, str, date]]] = defaultdict(set)
        for pt_id, par, avg, d in rows:
            have[pt_id].add((par.value, avg.value, d))
        weeks = fc.weeks_in(f.db, pid, w.start, end, e.as_of)
        for p in pts:
            sched: dict[str, set[str]] = defaultdict(set)
            for r in p.requirements or []:
                if r["schedule"] != "campaign":
                    sched[r["schedule"]].add(r["parameter"])
            days = work.get(p.site_id, set())
            h = have.get(p.id, set())
            for s, params in sched.items():
                if s in ("continuous", "daily"):
                    for d in sorted(x for x in days if w.start <= x <= end):
                        if s == "continuous":
                            met = any((pa, "24h", d) in h for pa in params)
                        else:
                            met = any(x[2] == d and x[0] in params for x in h)
                        out.append((p.point_code, f"{s}:{d.isoformat()}", met))
                elif s == "weekly":
                    for ws in weeks:
                        wd = {ws + timedelta(days=i) for i in range(7)}
                        if not (wd & days):
                            continue
                        met = any(x[2] in wd and x[0] in params for x in h)
                        out.append((p.point_code, f"weekly:{ws.isoformat()}", met))
                elif s == "monthly":
                    months = sorted({(d.year, d.month) for d in days if w.start <= d <= end})
                    for y, m in months:
                        met = any(x[2].year == y and x[2].month == m and x[0] in params for x in h)
                        out.append((p.point_code, f"monthly:{y}-{m:02d}", met))
    return out


def _k122(e: Engine, a: Agg) -> Result:
    ss = slots(e, a.window)
    return e._pct(M.K122, sum(1 for s in ss if s[2]), len(ss))


# ---- K-123 exceedances, K-124 spills -------------------------------------------------------------


def exceedances(e: Engine, w: Window) -> list[Any]:
    from app.models import EnvExceedance  # noqa: PLC0415

    f = efacts(e)
    if f is None:
        return []
    end = _end(e, w)
    rows = _memo(f, "exd", lambda: list(f.db.scalars(
        select(EnvExceedance).where(EnvExceedance.project_id.in_(f.pids)))))  # fmt: skip
    return [
        x
        for x in rows
        if w.start <= x.day <= end
        and x.status.value != "voided"
        and e.flt.site_ok(x.site_id)
        and (e.flt.engs is None or e.flt.eng_ok(x.responsible_engagement_id))
    ]


def _k123(e: Engine, a: Agg) -> Result:
    from app.services.env.exceedances import project_caused  # noqa: PLC0415

    xs = exceedances(e, a.window)
    proj = [x for x in xs if project_caused(x)]
    res = e._count(M.K123, len(proj))
    by: dict[str, int] = defaultdict(int)
    for x in proj:
        by[x.parameter.value] += 1
    res.components = [
        Component("background", "Background", "خلفية طبيعية", D(len(xs) - len(proj)),
                  KpiKind.count_),
        *[Component(k, k, k, D(v), KpiKind.count_) for k, v in sorted(by.items())],
    ]  # fmt: skip
    return res


def spills(e: Engine, w: Window) -> list[Any]:
    from app.models import Spill  # noqa: PLC0415

    f = efacts(e)
    if f is None:
        return []
    end = _end(e, w)
    rows = _memo(f, "spills", lambda: list(f.db.scalars(
        select(Spill).where(Spill.project_id.in_(f.pids)))))  # fmt: skip
    return [
        s
        for s in rows
        if w.start <= s.occurred_date <= end
        and s.status.value != "voided"
        and e.flt.site_ok(s.site_id)
        and e.flt.eng_ok(s.responsible_engagement_id)
    ]


def _k124(e: Engine, a: Agg) -> Result:
    ss = spills(e, a.window)
    res = e._count(M.K124, len(ss))
    res.components = [
        Component("reportable", "Reportable", "واجب الإبلاغ", D(sum(s.reportable for s in ss)),
                  KpiKind.count_)
    ]  # fmt: skip
    return res


# ---- K-125 spill kits, K-126 water ---------------------------------------------------------------


def kit_stats(e: Engine, w: Window) -> tuple[int, int, dict[str, int]]:
    from app.core.emergency_enums import AssetType  # noqa: PLC0415
    from app.models import EmergencyAsset  # noqa: PLC0415
    from app.services.emergency import assets  # noqa: PLC0415

    f = efacts(e)
    if f is None:
        return 0, 0, {}
    end = _end(e, w)
    ready = n = 0
    reasons: dict[str, int] = defaultdict(int)
    for pid in f.pids:
        rows = [
            x
            for x in f.db.scalars(
                select(EmergencyAsset).where(
                    EmergencyAsset.project_id == pid,
                    EmergencyAsset.asset_type == AssetType.spill_kit,
                )
            )
            if e.flt.site_ok(x.site_id) and e.flt.eng_ok(x.owner_engagement_id)
        ]
        for r in assets.ready_map(f.db, pid, end, rows).values():
            n += 1
            ready += r.ready
            if not r.ready and r.reasons:
                reasons[r.reasons[0].value] += 1
    return ready, n, reasons


def _k125(e: Engine, a: Agg) -> Result:
    ready, n, reasons = kit_stats(e, a.window)
    res = e._pct(M.K125, ready, n)
    res.components = [Component(k, k, k, D(v), KpiKind.count_) for k, v in sorted(reasons.items())]
    return res


def water(e: Engine, w: Window) -> tuple[Decimal, Decimal]:
    """(m³ of the months in the window, of which treated effluent)."""
    from app.core.env_enums import RecordState, WaterSource  # noqa: PLC0415
    from app.models import WaterEntry  # noqa: PLC0415

    f = efacts(e)
    if f is None:
        return ZERO, ZERO
    end = _end(e, w)
    tot = tre = ZERO
    for x in f.db.scalars(
        select(WaterEntry).where(
            WaterEntry.project_id.in_(f.pids), WaterEntry.status == RecordState.valid
        )
    ):
        first = date(int(x.month[:4]), int(x.month[5:7]), 1)
        if not (w.start <= first <= end) or not e.flt.site_ok(x.site_id):
            continue
        tot += D(x.volume_m3)
        tre += D(x.volume_m3) if x.source == WaterSource.treated_effluent else ZERO
    return tot, tre


def _k126(e: Engine, a: Agg) -> Result:
    tot, tre = water(e, a.window)
    res = e._count(M.K126, tot)
    lph = tot * 1000 / a.mh if a.mh else None
    res.components = [
        Component("l_per_mh", "L per man-hour", "لتر لكل ساعة عمل", lph, KpiKind.rate, 2),
        Component("treated_pct", "Treated effluent", "مياه معالجة",
                  tre * 100 / tot if tot else None, KpiKind.percentage, 1),
    ]  # fmt: skip
    return res


engine_mod._DISPATCH.update(
    {
        M.K118: _k118,
        M.K119: _k119,
        M.K120: _k120,
        M.K121: _k121,
        M.K122: _k122,
        M.K123: _k123,
        M.K124: _k124,
        M.K125: _k125,
        M.K126: _k126,
    }
)
