"""Scorecard arithmetic (spec 6g §6.2-§6.6): points between anchors, weight redistribution within
and across pillars, score, coverage, band grade, caps and the ranking order. Pure functions on
exact decimals; nothing is rounded before output (K-R8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.core.scorecard_enums import ScGrade, ScLineStatus

D = Decimal
ZERO = D(0)
HUNDRED = D(100)
GRADE_ORDER = {ScGrade.A: 4, ScGrade.B: 3, ScGrade.C: 2, ScGrade.D: 1}


@dataclass
class Line:
    metric_code: str
    pillar_code: str
    weight: Decimal
    good: Decimal
    bad: Decimal
    status: ScLineStatus
    value: Decimal | None = None
    points: Decimal | None = None
    effective_weight: Decimal = ZERO
    contribution: Decimal = ZERO
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PillarResult:
    pillar_code: str
    weight: Decimal
    effective_weight: Decimal
    score: Decimal | None
    redistributed: bool


@dataclass
class CardResult:
    lines: list[Line]
    pillars: list[PillarResult]
    score: Decimal | None
    coverage: Decimal
    band_grade: ScGrade | None
    grade: ScGrade | None
    indicative: bool


def points(v: Decimal, good: Decimal, bad: Decimal) -> Decimal:
    """§6.2: linear between the anchors, clipped to 0-100."""
    if good > bad:  # higher is better
        if v >= good:
            return HUNDRED
        if v <= bad:
            return ZERO
        return (v - bad) / (good - bad) * HUNDRED
    if v <= good:
        return HUNDRED
    if v >= bad:
        return ZERO
    return (bad - v) / (bad - good) * HUNDRED


def band(score: Decimal, bands: list[tuple[ScGrade, Decimal]]) -> ScGrade:
    """§6.5: the highest grade whose min_score ≤ score; D otherwise."""
    for g, mn in sorted(bands, key=lambda b: -b[1]):
        if score >= mn:
            return g
    return ScGrade.D


def lower(a: ScGrade, b: ScGrade) -> ScGrade:
    return a if GRADE_ORDER[a] <= GRADE_ORDER[b] else b


def compute(
    lines: list[Line],
    pillar_weights: dict[str, Decimal],
    bands: list[tuple[ScGrade, Decimal]],
    cap_grades: list[ScGrade],
    min_coverage: Decimal,
) -> CardResult:
    """§6.3 / WR-1…WR-4 / §6.5. `lines` carry their pre-scoring status; scored lines need a
    value. Effective weights of a card always sum to 100 (when anything is scored)."""
    for ln in lines:
        if ln.status == ScLineStatus.scored:
            assert ln.value is not None  # noqa: S101
            ln.points = points(ln.value, ln.good, ln.bad)
        ln.effective_weight = ZERO
        ln.contribution = ZERO
    by_pillar: dict[str, list[Line]] = {}
    for ln in lines:
        by_pillar.setdefault(ln.pillar_code, []).append(ln)
    included = {
        p: [ln for ln in by_pillar.get(p, []) if ln.status == ScLineStatus.scored]
        for p in pillar_weights
    }
    total_w = sum((w for p, w in pillar_weights.items() if included[p]), ZERO)
    pillars: list[PillarResult] = []
    score: Decimal | None = None
    acc = ZERO
    for p, wp in pillar_weights.items():
        scored = included[p]
        if not scored or total_w == 0:
            pillars.append(PillarResult(p, wp, ZERO, None, True))
            continue
        sw = sum((ln.weight for ln in scored), ZERO)
        sp = sum((ln.weight * (ln.points or ZERO) for ln in scored), ZERO) / sw
        wpe = wp * HUNDRED / total_w
        for ln in scored:
            ln.effective_weight = wpe * ln.weight / sw
            ln.contribution = ln.effective_weight * (ln.points or ZERO) / HUNDRED
        acc += wpe * sp / HUNDRED
        all_lines = by_pillar.get(p, [])
        pillars.append(PillarResult(p, wp, wpe, sp, len(scored) != len(all_lines)))
    if total_w > 0:
        score = acc
    coverage = sum((ln.weight for ln in lines if ln.status == ScLineStatus.scored), ZERO)
    indicative = coverage < min_coverage
    band_grade = band(score, bands) if score is not None else None
    grade: ScGrade | None = band_grade
    if grade is not None:
        for g in cap_grades:
            grade = lower(grade, g)
    if indicative:
        grade = None
    return CardResult(lines, pillars, score, coverage, band_grade, grade, indicative)


def blend(z: Decimal, own: Decimal, project: Decimal) -> Decimal:
    """§6.4 credibility blending."""
    return z * own + (1 - z) * project


def credibility(r12_mh: Decimal, min_exposure: Decimal) -> Decimal:
    return min(D(1), r12_mh / min_exposure) if min_exposure else D(1)


def median(xs: list[Decimal]) -> Decimal | None:
    ys = sorted(xs)
    n = len(ys)
    if n == 0:
        return None
    if n % 2:
        return ys[n // 2]
    return (ys[n // 2 - 1] + ys[n // 2]) / 2


def trend(
    score: Decimal | None, prev: Decimal | None, prior3: list[Decimal], points_: Decimal
) -> tuple[Decimal | None, str | None]:
    """§6.6: delta to M − 1 and the label against the mean of M−3…M−1 (needs 3 Final months)."""
    delta = score - prev if score is not None and prev is not None else None
    if score is None or len(prior3) < 3:
        return delta, None
    diff = score - sum(prior3, ZERO) / 3
    if diff >= points_:
        return delta, "improving"
    if diff <= -points_:
        return delta, "declining"
    return delta, "stable"
