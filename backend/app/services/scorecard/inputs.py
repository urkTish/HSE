"""Scorecard line inputs (spec 6g §6.1, SN-1…SN-6, SP-4, caps CP-1…CP-3).

Every value is read from the KPI engine (the only place rates are computed) for the engagement
("this contractor only" for `own`, "with descendants" for `tree`, K-R5), the month window and
as_of = the month's last day. Rates are converted to the canonical bases. Nothing is redefined."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.hse_enums import CaseCategory, KpiMetric, PermanentDisability
from app.core.scorecard_enums import ScCap, ScGrade, ScLineStatus, ScScope, ScWindow
from app.kpi import data
from app.kpi.engine import Agg, Engine, EngineConfig, Result
from app.kpi.facts import Facts, Filter
from app.kpi.periods import Window
from app.models import HseSettings, Project, ScProfile
from app.services import hse_settings
from app.services.scorecard import calc
from app.services.scorecard import common as cm

D = Decimal
ZERO = D(0)
M = KpiMetric
KPI = {x.value: x for x in KpiMetric}


@dataclass
class Ctx:
    project: Project
    hse: HseSettings
    facts: Facts
    cfg: cm.Cfg
    config: EngineConfig
    engines: dict[Any, Engine] = field(default_factory=dict)
    aggs: dict[Any, Agg] = field(default_factory=dict)


def context(db: Session, project: Project) -> Ctx:
    cache: dict[uuid.UUID, Ctx] = db.info.setdefault("sc_ctx", {})
    if project.id not in cache:
        hse = hse_settings.get(db, project.id)
        facts = data.load(db, [project], {project.id: hse})
        st = project.settings
        config = EngineConfig(
            st.ltifr_base_hours if st else 1_000_000,
            st.rate_base_hours if st else 200_000,
            hse.low_exposure_hours,
        )
        cache[project.id] = Ctx(project, hse, facts, cm.cfg(db, project.id), config)
    return cache[project.id]


def reset(db: Session) -> None:
    db.info.pop("sc_ctx", None)


def engine(ctx: Ctx, engs: frozenset[uuid.UUID] | None, as_of: date) -> Engine:
    key = (engs, as_of)
    if key not in ctx.engines:
        ctx.engines[key] = Engine(ctx.facts, Filter(engs=engs), as_of, ctx.config)
    return ctx.engines[key]


def agg(ctx: Ctx, e: Engine, w: Window) -> Agg:
    key = (id(e), w.start, w.end)
    if key not in ctx.aggs:
        ctx.aggs[key] = e.aggregate(w)
    return ctx.aggs[key]


def result(ctx: Ctx, e: Engine, kpi: str, w: Window) -> Result:
    return e.result(KPI[kpi], agg(ctx, e, w))


def comp(r: Result, key: str) -> Decimal | None:
    for c in r.components:
        if c.key == key:
            return c.value
    return None


def engs_of(ctx: Ctx, eng_id: uuid.UUID, scope: ScScope) -> frozenset[uuid.UUID]:
    if scope == ScScope.tree:
        return frozenset(ctx.facts.descendants(eng_id))
    return frozenset({eng_id})


def in_heat_season(ctx: Ctx, month: date) -> bool:
    """SN-4: at least one day of the month inside the Phase 1 heat season."""
    s, e = ctx.hse.heat_season_start, ctx.hse.heat_season_end
    first = month.strftime("%m-%d")
    last = cm.month_end(month).strftime("%m-%d")
    if s <= e:
        return not (last < s or first > e)
    return True


def month_mh(ctx: Ctx, engs: frozenset[uuid.UUID], month: date) -> Decimal:
    e = engine(ctx, engs, cm.month_end(month))
    return D(agg(ctx, e, Window(month, cm.month_end(month))).mh)


@dataclass
class CardInputs:
    month_mh: Decimal
    r12_mh: Decimal
    z: Decimal
    lines: list[calc.Line]
    caps: list[tuple[ScCap, ScGrade, list[str]]]
    trir_used: Decimal | None

    def hash(self) -> str:
        payload = {
            "mh": str(self.month_mh), "r12": str(self.r12_mh),
            "lines": [[ln.metric_code, ln.status.value, str(ln.value), ln.extra.get("numerator"),
                       ln.extra.get("denominator")] for ln in self.lines],
            "caps": [[c.value, refs] for c, _g, refs in self.caps],
        }  # fmt: skip
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _rate_line(
    ctx: Ctx, md: dict[str, Any], own: Engine, proj: Engine, r12: Window, z: Decimal
) -> calc.Line:
    """SN-1 / SN-2: R12 rate in the canonical base, blended with the project rate."""
    code = md["metric_code"]
    defn = cm.METRIC_BY_CODE[code]
    base = D(defn.canonical_base or 200_000)
    a_own, a_proj = agg(ctx, own, r12), agg(ctx, proj, r12)

    def count(e: Engine, a: Agg) -> Decimal:
        r = e.result(KPI[defn.kpi], a)
        return D(r.numerator or 0)

    n_own, n_proj = count(own, a_own), count(proj, a_proj)
    own_v = n_own * base / D(a_own.mh) if a_own.mh else ZERO
    proj_v = n_proj * base / D(a_proj.mh) if a_proj.mh else ZERO
    used = calc.blend(z, own_v, proj_v)
    return calc.Line(
        code, md["pillar_code"], D(md["weight"]), D(md["good"]), D(md["bad"]),
        ScLineStatus.scored, used,
        extra={"numerator": str(n_own), "denominator": str(a_own.mh), "base": int(base),
               "own_value": own_v, "project_value": proj_v},
    )  # fmt: skip


def _status_for(window: ScWindow, volume: Decimal | None, min_volume: int) -> ScLineStatus | None:
    """SN-3: month_end with denominator 0 → not_applicable; below min_volume → insufficient."""
    v = volume or ZERO
    if window == ScWindow.month_end and v == 0:
        return ScLineStatus.not_applicable
    if v <= 0 or v < min_volume:
        return ScLineStatus.insufficient_volume
    return None


def _month_line(
    ctx: Ctx, md: dict[str, Any], e: Engine, month: date
) -> tuple[ScLineStatus | None, Decimal | None, dict[str, Any]]:
    code = md["metric_code"]
    defn = cm.METRIC_BY_CODE[code]
    mw = Window(month, cm.month_end(month))
    w = Window(cm.add_months(month, -2), mw.end) if defn.window == ScWindow.latest_3m else mw
    r = result(ctx, e, defn.kpi, w)
    extra: dict[str, Any] = {
        "numerator": None if r.numerator is None else str(r.numerator),
        "denominator": None if r.denominator is None else str(r.denominator),
    }
    value: Decimal | None = r.value
    volume: Decimal | None = None if r.denominator is None else D(r.denominator)
    if defn.kpi == "K-32":  # observation rate in the canonical base (SP-4)
        mh = D(r.denominator or 0)
        value = D(r.numerator or 0) * 200_000 / mh if mh else None
        volume = mh
        extra["base"] = 200_000
    elif defn.kpi == "K-42":  # overdue CAs per 100 average workers
        k03 = result(ctx, e, "K-03", mw).value
        volume = D(k03 or 0)
        value = D(r.value or 0) * 100 / volume if volume else None
        extra["denominator"] = None if k03 is None else str(k03)
    elif defn.kpi == "K-61":  # volume = field audits (K-64 denominator)
        volume = D(result(ctx, e, "K-64", mw).denominator or 0)
    elif defn.kpi == "K-64":
        value = comp(r, "rate")
    elif defn.kpi == "K-100":
        value = comp(r, "rate_per_100_patrols")
        volume = comp(r, "patrols")
    elif defn.kpi == "K-110":
        volume = comp(r, "inspections")
    status = _status_for(defn.window, volume, int(md["min_volume"]))
    if status is None and value is None:
        status = ScLineStatus.insufficient_volume
    return status, value, extra


def _caps(
    ctx: Ctx, engs: frozenset[uuid.UUID], month: date, e: Engine
) -> list[tuple[ScCap, list[str]]]:
    """CP-1…CP-3 conditions of the month (record refs, never names)."""
    end = cm.month_end(month)
    mw = Window(month, end)
    cp1: list[str] = []
    cp2: list[str] = []
    for c in ctx.facts.cases:
        if c.eng not in engs or not (month <= c.d <= end) or not c.eligible:
            continue
        if c.fatal or c.category == CaseCategory.FAT or c.permanent != PermanentDisability.none:
            cp1.append(c.incident_ref)
        elif c.category == CaseCategory.LTI:
            cp2.append(c.incident_ref)
    cp3: list[str] = []
    k64 = result(ctx, e, "K-64", mw)
    if (comp(k64, "unpermitted_work") or 0) > 0:
        cp3.append(f"K-64 unpermitted_work × {comp(k64, 'unpermitted_work')}")
    k100 = result(ctx, e, "K-100", mw)
    if (k100.numerator or 0) > 0:
        cp3.append(f"K-100 midday-ban violation × {k100.numerator}")
    k128 = result(ctx, e, "K-128", mw)
    if (comp(k128, "statutory") or 0) > 0:
        cp3.append(f"K-128 statutory overdue × {comp(k128, 'statutory')}")
    cp3 += sorted(
        ev.ref for ev in ctx.facts.events if ev.late and ev.eng in engs and month <= ev.d <= end
    )
    out: list[tuple[ScCap, list[str]]] = []
    if cp1:
        out.append((ScCap.CP1, sorted(set(cp1))))
    if cp2:
        out.append((ScCap.CP2, sorted(set(cp2))))
    if cp3:
        out.append((ScCap.CP3, cp3))
    return out


def card_inputs(
    ctx: Ctx,
    profile: ScProfile,
    eng_id: uuid.UUID,
    month: date,
    scope: ScScope,
    excluded: list[str] | None = None,
) -> CardInputs:
    engs = engs_of(ctx, eng_id, scope)
    end = cm.month_end(month)
    own = engine(ctx, engs, end)
    proj = engine(ctx, None, end)
    mw = Window(month, end)
    r12 = Window(cm.add_months(month, -11), end)
    mh = D(agg(ctx, own, mw).mh)
    r12_mh = D(agg(ctx, own, r12).mh)
    z = calc.credibility(r12_mh, D(ctx.cfg["scorecard_min_exposure_hours"]))
    heat = in_heat_season(ctx, month)
    lines: list[calc.Line] = []
    trir: Decimal | None = None
    for md in profile.metrics:
        code = md["metric_code"]
        defn = cm.METRIC_BY_CODE.get(code)
        if defn is None:
            continue
        base = calc.Line(code, md["pillar_code"], D(md["weight"]), D(md["good"]), D(md["bad"]),
                         ScLineStatus.not_applicable)  # fmt: skip
        if not md.get("enabled", True):
            lines.append(base)
            continue
        if not ctx.cfg.live(defn.module, month):
            base.status = ScLineStatus.source_not_live
            lines.append(base)
            continue
        if defn.pillar.value == "HEAT" and not heat:
            lines.append(base)
            continue
        if defn.window == ScWindow.r12_rate:
            ln = _rate_line(ctx, md, own, proj, r12, z)
            if code == "SM-TRIR":
                trir = ln.value
        else:
            status, value, extra = _month_line(ctx, md, own, month)
            ln = base
            ln.extra = extra
            ln.value = value
            ln.status = status or ScLineStatus.scored
        if excluded and code in excluded:
            ln.status = ScLineStatus.excluded_by_manager
        lines.append(ln)
    grades = {c["cap_code"]: ScGrade(c["max_grade"]) for c in profile.caps if c.get("enabled")}
    caps = [(c, grades[c.value], refs) for c, refs in _caps(ctx, engs, month, own)
            if c.value in grades]  # fmt: skip
    return CardInputs(mh, r12_mh, z, lines, caps, trir)


def compute(ctx: Ctx, profile: ScProfile, inp: CardInputs) -> calc.CardResult:
    return calc.compute(
        inp.lines,
        {p["pillar_code"]: D(p["weight"]) for p in profile.pillars},
        [(ScGrade(b["grade"]), D(b["min_score"])) for b in profile.bands],
        [g for _c, g, _r in inp.caps],
        ctx.cfg.dec("scorecard_min_coverage_pct"),
    )
