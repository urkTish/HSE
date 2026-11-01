"""Statistical process control (spec 8-quality §E.5, Q-SPC-01…08): X-bar / R, I-MR and p-charts
with ISO 7870-2 constants, provisional limits below `spc_min_subgroups`, Western Electric signals,
short-term capability, and the data sources of list SPCS read from Q1 / Q2 / Q3 records (only
verified, not-voided results; an amended result plots its latest version, marked)."""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, not_found
from app.core.quality.q1 import DECIDED_RESULTS, QIrResult, QIrStatus
from app.core.quality.q2 import QTestVerdict
from app.core.quality.q3 import QLineDecision, QReadingTarget, QReceiptStatus
from app.core.quality.q4 import SPC_SOURCE_TYPES, QSpcBaseline, QSpcSource, QSpcType
from app.models import Project
from app.models.quality.q1 import QIr, QIrRound
from app.models.quality.q2 import QTestRequest, QTestSpecimen
from app.models.quality.q3 import (
    QMonitoringPoint,
    QReading,
    QReceipt,
    QReceiptLine,
)
from app.models.quality.q4 import QSpcChart
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality.q4 import base as b

C = b.C
D = Decimal
# n: (A2, D3, D4, d2)
CONST: dict[int, tuple[float, float, float, float]] = {
    2: (1.880, 0, 3.267, 1.128),
    3: (1.023, 0, 2.574, 1.693),
    4: (0.729, 0, 2.282, 2.059),
    5: (0.577, 0, 2.114, 2.326),
    6: (0.483, 0, 2.004, 2.534),
    7: (0.419, 0.076, 1.924, 2.704),
    8: (0.373, 0.136, 1.864, 2.847),
    9: (0.337, 0.184, 1.816, 2.970),
    10: (0.308, 0.223, 1.777, 3.078),
}
MIN_DRAW = 8


@dataclass
class Point:
    key: str  # subgroup key (test id, day, week)
    label: str
    values: list[float] = field(default_factory=list)  # X-bar / R subgroup, or [x] for I-MR
    defectives: int = 0  # p-chart
    n: int = 0  # p-chart sample size
    amended: bool = False


def r4(x: float | None) -> str | None:
    return None if x is None else str(D(str(x)).quantize(D("0.001"), ROUND_HALF_UP))


def r2(x: float | None) -> str | None:
    return None if x is None else str(D(str(x)).quantize(D("0.01"), ROUND_HALF_UP))


# ---- limits (Q-SPC-01…04) -----------------------------------------------------------------------


def xbar_r(groups: list[list[float]]) -> dict[str, float]:
    n = len(groups[0])
    a2, d3, d4, d2 = CONST[n]
    xbb = sum(sum(g) / len(g) for g in groups) / len(groups)
    rbar = sum(max(g) - min(g) for g in groups) / len(groups)
    return {
        "cl": xbb,
        "ucl": xbb + a2 * rbar,
        "lcl": xbb - a2 * rbar,
        "r_cl": rbar,
        "r_ucl": d4 * rbar,
        "r_lcl": d3 * rbar,
        "sigma": rbar / d2,
    }


def imr(xs: list[float]) -> dict[str, float]:
    xbar = sum(xs) / len(xs)
    mrs = [abs(xs[i] - xs[i - 1]) for i in range(1, len(xs))]
    mrbar = sum(mrs) / len(mrs) if mrs else 0.0
    return {
        "cl": xbar,
        "ucl": xbar + 2.66 * mrbar,
        "lcl": xbar - 2.66 * mrbar,
        "r_cl": mrbar,
        "r_ucl": 3.267 * mrbar,
        "r_lcl": 0.0,
        "sigma": mrbar / 1.128,
    }


def p_bar(defectives: list[int], ns: list[int]) -> float:
    return sum(defectives) / sum(ns) if sum(ns) else 0.0


def p_limits(pbar: float, n: int) -> tuple[float, float]:
    """Q-SPC-03: p̄ ± 3·√(p̄(1 − p̄) ÷ n), LCL floored at 0, UCL capped at 1."""
    s = 3 * math.sqrt(pbar * (1 - pbar) / n) if n else 0.0
    return min(pbar + s, 1.0), max(pbar - s, 0.0)


def capability(cl: float, sigma: float, lsl: float | None, usl: float | None) -> dict[str, Any]:
    """Q-SPC-07: Cp = (USL − LSL) ÷ 6σ̂; Cpk = min(USL − μ, μ − LSL) ÷ 3σ̂ (one-sided with one
    limit); labelled short-term (within-subgroup)."""
    if sigma <= 0 or (lsl is None and usl is None):
        return {"cp": None, "cpk": None}
    cp = (usl - lsl) / (6 * sigma) if lsl is not None and usl is not None else None
    parts = [
        x
        for x in ((usl - cl) if usl is not None else None, (cl - lsl) if lsl is not None else None)
        if x is not None
    ]
    cpk = min(parts) / (3 * sigma)
    return {"cp": r2(cp), "cpk": r2(cpk), "label": "short-term (within-subgroup)"}


# ---- signals (Q-SPC-05) ----------------------------------------------------------------------


def signals(
    xs: list[float],
    cl: float,
    sig: list[float],
    ucl: list[float],
    lcl: list[float],
    rule1_only: bool = False,
) -> list[tuple[int, int]]:
    """Western Electric rules on the centre-line chart (per-point σ for p-charts). Returns
    (index, rule) with the index of the point that completes the pattern."""
    out: list[tuple[int, int]] = []
    for i, x in enumerate(xs):
        if x > ucl[i] or x < lcl[i]:
            out.append((i, 1))
    if rule1_only:
        return out
    side = [1 if x > cl else -1 if x < cl else 0 for x in xs]
    for i in range(len(xs)):
        for s in (1, -1):
            w3 = range(max(0, i - 2), i + 1)
            if (
                len(w3) == 3
                and sum(1 for j in w3 if s * (xs[j] - cl) > 2 * sig[j]) >= 2
                and s * (xs[i] - cl) > 2 * sig[i]
            ):
                out.append((i, 2))
            w5 = range(max(0, i - 4), i + 1)
            if (
                len(w5) == 5
                and sum(1 for j in w5 if s * (xs[j] - cl) > sig[j]) >= 4
                and s * (xs[i] - cl) > sig[i]
            ):
                out.append((i, 3))
        if i >= 7 and all(side[j] == side[i] != 0 for j in range(i - 7, i + 1)):
            out.append((i, 4))
    return sorted(set(out))


def evaluate(
    ctype: QSpcType,
    points: list[Point],
    baseline_keys: list[str] | None,
    min_subgroups: int,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Any]:
    """Limits from the baseline (frozen keys, else the last 25 points), signals on every point."""
    keys = set(baseline_keys or [])
    base = [x for x in points if x.key in keys] if keys else points[-25:]
    k = len(base)
    out: dict[str, Any] = {
        "type": ctype.value,
        "baseline_subgroups": k,
        "provisional": False,
        "limits_drawn": k >= MIN_DRAW,
        "points": [],
        "signals": [],
    }
    if k >= MIN_DRAW and k < min_subgroups:
        out["provisional"] = True
    if ctype == QSpcType.p:
        pb = p_bar([x.defectives for x in base], [x.n for x in base]) if base else 0.0
        out["cl"] = r4(pb) if k >= MIN_DRAW else None
        ps, ucl, lcl, sig = [], [], [], []
        for x in points:
            p = x.defectives / x.n if x.n else 0.0
            u, lo = p_limits(pb, x.n)
            ps.append(p)
            ucl.append(u)
            lcl.append(lo)
            sig.append((u - pb) / 3 if u > pb else 0.0)
            out["points"].append(
                {
                    "key": x.key,
                    "label": x.label,
                    "value": r4(p),
                    "n": x.n,
                    "defectives": x.defectives,
                    "ucl": r4(u) if k >= MIN_DRAW else None,
                    "lcl": r4(lo) if k >= MIN_DRAW else None,
                }
            )
        if k >= MIN_DRAW:
            for i, rule in signals(ps, pb, sig, ucl, lcl):
                out["signals"].append(
                    {"index": i, "key": points[i].key, "rule": rule, "chart": "p"}
                )
        return out
    if ctype == QSpcType.xbar_r:
        n = len(points[0].values) if points else 0
        if not 2 <= n <= 10:
            return {**out, "limits_drawn": False}
        groups = [x.values for x in points if len(x.values) == n]
        lim = xbar_r([x.values for x in base if len(x.values) == n]) if k >= MIN_DRAW else None
        centre = [sum(g) / len(g) for g in groups]
        disp = [max(g) - min(g) for g in groups]
    else:
        xs = [x.values[0] for x in points]
        lim = imr([x.values[0] for x in base]) if k >= MIN_DRAW else None
        centre = xs
        disp = [0.0] + [abs(xs[i] - xs[i - 1]) for i in range(1, len(xs))]
    for i, x in enumerate(points[: len(centre)]):
        out["points"].append(
            {
                "key": x.key,
                "label": x.label,
                "value": r4(centre[i]),
                "range": r4(disp[i]),
                "amended": x.amended,
            }
        )
    if lim is None:
        return out
    out.update(
        {
            "cl": r4(lim["cl"]),
            "ucl": r4(lim["ucl"]),
            "lcl": r4(lim["lcl"]),
            "r_cl": r4(lim["r_cl"]),
            "r_ucl": r4(lim["r_ucl"]),
            "r_lcl": r4(lim["r_lcl"]),
            "sigma_hat": r4(lim["sigma"]),
        }
    )
    m = len(centre)
    sig = [(lim["ucl"] - lim["cl"]) / 3] * m
    for i, rule in signals(centre, lim["cl"], sig, [lim["ucl"]] * m, [lim["lcl"]] * m):
        out["signals"].append({"index": i, "key": points[i].key, "rule": rule, "chart": "x"})
    rs = disp if ctype == QSpcType.xbar_r else disp[1:]
    off = 0 if ctype == QSpcType.xbar_r else 1
    for i, rule in signals(
        rs,
        lim["r_cl"],
        [0.0] * len(rs),
        [lim["r_ucl"]] * len(rs),
        [lim["r_lcl"]] * len(rs),
        rule1_only=True,
    ):
        out["signals"].append(
            {
                "index": i + off,
                "key": points[i + off].key,
                "rule": rule,
                "chart": "r" if ctype == QSpcType.xbar_r else "mr",
            }
        )
    base_rule1 = any(s["rule"] == 1 and s["key"] in {x.key for x in base} for s in out["signals"])
    if k >= min_subgroups and not base_rule1 and (lsl is not None or usl is not None):
        out["capability"] = capability(lim["cl"], lim["sigma"], lsl, usl)
    return out


# ---- data sources (list SPCS) -------------------------------------------------------------------


def _week(d: date) -> date:
    return d - timedelta(days=(d.weekday() + 1) % 7)  # weeks Sunday–Saturday (KSA)


def source_points(db: Session, ch: QSpcChart, start: date | None, end: date | None) -> list[Point]:
    pid, f = ch.project_id, ch.filters or {}
    src = ch.source
    if src in (
        QSpcSource.conc_strength_28d,
        QSpcSource.slump,
        QSpcSource.dft_spot,
        QSpcSource.compaction_pct,
    ):
        codes = {
            QSpcSource.conc_strength_28d: ["CONC-CYL", "CONC-CUBE"],
            QSpcSource.slump: ["SLUMP"],
            QSpcSource.dft_spot: ["DFT"],
            QSpcSource.compaction_pct: ["FDT-SC", "FDT-NUC"],
        }[src]
        stmt = select(QTestRequest).where(
            QTestRequest.project_id == pid,
            QTestRequest.test_type_code.in_(codes),
            QTestRequest.verified_at.is_not(None),
            QTestRequest.status != "voided",
            QTestRequest.verdict != QTestVerdict.pending,
        )
        if f.get("mix"):
            stmt = stmt.where(QTestRequest.mix_key.ilike(f"%{f['mix']}"))
        out: list[Point] = []
        for t in db.scalars(
            stmt.order_by(QTestRequest.cast_date, QTestRequest.sampled_at, QTestRequest.test_no)
        ):
            day = t.cast_date or (b.local_day(t.sampled_at) if t.sampled_at else None)
            if day is None or (start and day < start) or (end and day > end):
                continue
            amended = int(t.result_version or 1) > 1
            if src == QSpcSource.conc_strength_28d:
                vals = [
                    float(s.values["strength"])
                    for s in db.scalars(
                        select(QTestSpecimen)
                        .where(
                            QTestSpecimen.test_request_id == t.id,
                            QTestSpecimen.age_days == 28,
                            QTestSpecimen.spare.is_(False),
                        )
                        .order_by(QTestSpecimen.position)
                    )
                    if (s.values or {}).get("strength")
                ]
                n = ch.subgroup_size or len(vals)
                if len(vals) >= 2:
                    out.append(Point(str(t.id), t.test_no or "", vals[:n], amended=amended))
            elif src == QSpcSource.slump and (t.results or {}).get("slump"):
                out.append(
                    Point(str(t.id), t.test_no or "", [float(t.results["slump"])], amended=amended)
                )
            elif src == QSpcSource.dft_spot and (t.results or {}).get("spot_readings"):
                vals = [float(x) for x in t.results["spot_readings"]][: ch.subgroup_size or 3]
                out.append(Point(str(t.id), t.test_no or "", vals, amended=amended))
            elif src == QSpcSource.compaction_pct and (t.results or {}).get("mdd"):
                r = t.results
                out.append(
                    Point(
                        str(t.id),
                        t.test_no or "",
                        [float(r["dry_density"]) / float(r["mdd"]) * 100],
                        amended=amended,
                    )
                )
        return out
    if src == QSpcSource.zone_daily_mean_temp:
        zone = f.get("zone_id")
        pts = list(
            db.scalars(
                select(QMonitoringPoint.id).where(
                    QMonitoringPoint.project_id == pid, QMonitoringPoint.zone_id == zone
                )
            )
        )
        day_ = func.date(func.timezone("Asia/Riyadh", QReading.measured_at))
        q = (
            select(day_, func.avg(QReading.temperature_c))
            .where(
                QReading.target_type == QReadingTarget.point,
                QReading.target_id.in_(pts or [uuid.uuid4()]),
                QReading.probe_fault.is_(False),
                QReading.temperature_c.is_not(None),
                QReading.voided.is_(False),
            )
            .group_by(day_)
            .order_by(day_)
        )
        if start:
            q = q.where(QReading.measured_at >= b.day_start(start))
        if end:
            q = q.where(QReading.measured_at < b.day_start(end + timedelta(days=1)))
        return [Point(d.isoformat(), d.isoformat(), [float(v)]) for d, v in db.execute(q)]
    if src == QSpcSource.ir_rejection_weekly:
        weeks: dict[date, list[int]] = defaultdict(lambda: [0, 0])
        for rnd in db.scalars(
            select(QIrRound)
            .join(QIr, QIr.id == QIrRound.ir_id)
            .where(
                QIr.project_id == pid,
                QIr.status != QIrStatus.voided,
                QIrRound.round_no >= 1,
                QIrRound.needs_confirmation.is_(False),
                QIrRound.decided_date.is_not(None),
                QIrRound.result.in_(list(DECIDED_RESULTS)),
            )
        ):
            dd = rnd.decided_date
            if dd is None or (start and dd < start) or (end and dd > end):
                continue
            w = weeks[_week(dd)]
            w[1] += 1
            w[0] += rnd.result in (QIrResult.rejected, QIrResult.not_ready)
        return [
            Point(k.isoformat(), k.isoformat(), defectives=v[0], n=v[1])
            for k, v in sorted(weeks.items())
        ]
    weeks2: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    rej = set(
        db.scalars(
            select(QReceiptLine.receipt_id).where(QReceiptLine.decision == QLineDecision.reject)
        )
    )
    for rc in db.scalars(
        select(QReceipt).where(
            QReceipt.project_id == pid,
            QReceipt.status == QReceiptStatus.decided,
            QReceipt.decided_at.is_not(None),
        )
    ):
        if rc.decided_at is None:
            continue
        dd = b.local_day(rc.decided_at)
        if (start and dd < start) or (end and dd > end):
            continue
        w = weeks2[_week(dd)]
        w[1] += 1
        w[0] += rc.id in rej
    return [
        Point(k.isoformat(), k.isoformat(), defectives=v[0], n=v[1])
        for k, v in sorted(weeks2.items())
    ]


# ---- charts --------------------------------------------------------------------------------------


def chart_read(
    db: Session, ch: QSpcChart, start: date | None = None, end: date | None = None
) -> dict[str, Any]:
    pts = source_points(db, ch, start, end)
    mins = int(b.setting(db, ch.project_id, "spc_min_subgroups"))
    res = evaluate(
        ch.chart_type,
        pts,
        list(ch.baseline_keys or []) if ch.baseline == QSpcBaseline.frozen else None,
        mins,
        float(ch.lsl) if ch.lsl is not None else None,
        float(ch.usl) if ch.usl is not None else None,
    )
    return {
        "id": ch.id,
        "project_id": ch.project_id,
        "code": ch.code,
        "title_en": ch.title_en,
        "title_ar": ch.title_ar,
        "chart_type": ch.chart_type,
        "source": ch.source,
        "filters": ch.filters,
        "subgroup_size": ch.subgroup_size,
        "baseline": ch.baseline,
        "lsl": ch.lsl,
        "usl": ch.usl,
        "owner_user_id": ch.owner_user_id,
        "active": ch.active,
        "result": res,
    }


def list_charts(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    b.viewer(db, p, project_id)
    rows = db.scalars(
        select(QSpcChart).where(QSpcChart.project_id == project_id).order_by(QSpcChart.code)
    )
    return [chart_read(db, ch) for ch in rows]


def read_chart(
    db: Session, p: Principal, chart_id: uuid.UUID, start: date | None, end: date | None
) -> dict[str, Any]:
    ch = db.get(QSpcChart, chart_id)
    if ch is None:
        raise not_found("SPC chart")
    b.viewer(db, p, ch.project_id)
    return chart_read(db, ch, start, end)


def save_chart(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    body: dict[str, Any],
    chart_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    project, _g = b.writer(db, p, project_id, C.quality_author)
    if chart_id:
        ch = db.get(QSpcChart, chart_id)
        if ch is None or ch.project_id != project.id:
            raise not_found("SPC chart")
    else:
        code = str(body.get("code") or "").strip().upper()
        if not code:
            raise qc.field_err("code", "Give the chart code.", "أدخل رمز المخطط.")
        if db.scalar(
            select(QSpcChart.id).where(QSpcChart.project_id == project.id, QSpcChart.code == code)
        ):
            raise qc.err(409, ErrorCode.DUPLICATE_VALUE, f"{code} exists.", "الرمز مستخدم.")
        ch = QSpcChart(
            id=uuid.uuid4(),
            project_id=project.id,
            code=code,
            created_by_user_id=p.user.id,
            owner_user_id=p.user.id,
            signals_sent=[],
        )
        db.add(ch)
    for k in (
        "title_en",
        "title_ar",
        "filters",
        "subgroup_size",
        "baseline",
        "baseline_keys",
        "lsl",
        "usl",
        "owner_user_id",
        "active",
        "chart_type",
        "source",
    ):
        if k in body and body[k] is not None:
            setattr(ch, k, body[k])
    src, typ = QSpcSource(ch.source), QSpcType(ch.chart_type)
    if SPC_SOURCE_TYPES[src] != typ:
        raise qc.err(
            422,
            ErrorCode.SPC_SOURCE_INVALID,
            f"{src.value} is plotted as {SPC_SOURCE_TYPES[src].value}, not {typ.value}.",
            "مصدر البيانات لا يناسب نوع المخطط.",
        )
    if typ == QSpcType.xbar_r and not 2 <= int(ch.subgroup_size or 0) <= 10:
        raise qc.field_err(
            "subgroup_size",
            "X-bar / R needs a subgroup size of 2–10.",
            "حجم المجموعة الفرعية من 2 إلى 10.",
        )
    if src == QSpcSource.zone_daily_mean_temp and not (ch.filters or {}).get("zone_id"):
        raise qc.err(
            422,
            ErrorCode.SPC_SOURCE_INVALID,
            "A zone temperature chart names the zone.",
            "حدد المنطقة لمخطط حرارة المنطقة.",
        )
    if not (ch.title_en or "").strip():
        ch.title_en = ch.code
    ch.updated_by_user_id = p.user.id
    db.flush()
    return chart_read(db, ch)


def signal_job(db: Session, at: Any) -> dict[str, int]:
    """Q-SPC-06: each new signal notifies the chart owner once (who may raise an observation);
    no NCR is opened."""
    n = 0
    for ch in db.scalars(select(QSpcChart).where(QSpcChart.active.is_(True))):
        project = db.get(Project, ch.project_id)
        if project is None or ch.owner_user_id is None:
            continue
        res = chart_read(db, ch)["result"]
        sent = set(ch.signals_sent or [])
        new = [
            s for s in res.get("signals", []) if f"{s['key']}:{s['rule']}:{s['chart']}" not in sent
        ]
        for s in new:
            sent.add(f"{s['key']}:{s['rule']}:{s['chart']}")
            n += b.send(
                db,
                project,
                [ch.owner_user_id],
                f"spc:{ch.id}:{s['key']}:{s['rule']}:{s['chart']}",
                f"SPC signal on {ch.code}: rule {s['rule']}",
                f"إشارة ضبط إحصائي على {ch.code}: القاعدة {s['rule']}",
                path="/quality/spc",
                email=False,
            )
        ch.signals_sent = sorted(sent)
    db.flush()
    return {"q4_spc": n}
