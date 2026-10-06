"""Group comparison statistics for T9 compare_groups (spec 1-dashboard §5.9 T9, AI-9).

Two groups: exact conditional binomial test (given n events, events in group 1 follow
Binomial(n, E1 / (E1 + E2)) under equal rates), Clopper-Pearson interval transformed to the
rate ratio. More than two groups: chi-square goodness of fit against exposure-proportional
expectation. Pure Python (no SciPy)."""

import math
from collections.abc import Callable
from dataclasses import dataclass

MIN_EVENTS = 10  # AI-9 ASSUMPTION: ≥ 10 events in total
MIN_HIGHER = 3  # and ≥ 3 in the higher group
ALPHA = 0.05


def _log_binom_pmf(k: int, n: int, p: float) -> float:
    if p <= 0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1:
        return 0.0 if k == n else -math.inf
    return (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )


def binom_pmf(k: int, n: int, p: float) -> float:
    return math.exp(_log_binom_pmf(k, n, p))


def binom_cdf(k: int, n: int, p: float) -> float:
    return min(1.0, sum(binom_pmf(i, n, p) for i in range(0, k + 1)))


def binom_test_two_sided(x: int, n: int, p: float) -> float:
    """Exact two-sided p-value (sum of outcomes no more likely than the observed one)."""
    if n == 0:
        return 1.0
    obs = binom_pmf(x, n, p)
    total = sum(q for i in range(n + 1) if (q := binom_pmf(i, n, p)) <= obs * (1 + 1e-7))
    return min(1.0, total)


def _bisect(f: Callable[[float], float], lo: float = 0.0, hi: float = 1.0) -> float:
    for _ in range(100):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(x: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    a = (1 - conf) / 2
    lower = 0.0 if x == 0 else _bisect(lambda p: a - (1 - binom_cdf(x - 1, n, p)))
    upper = 1.0 if x == n else _bisect(lambda p: binom_cdf(x, n, p) - a)
    return lower, upper


def gammaincc(s: float, x: float) -> float:
    """Regularised upper incomplete gamma Q(s, x) (Numerical Recipes gser/gcf)."""
    if x <= 0:
        return 1.0
    gln = math.lgamma(s)
    if x < s + 1:
        term = total = 1.0 / s
        ap = s
        for _ in range(500):
            ap += 1
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return max(0.0, 1.0 - total * math.exp(-x + s * math.log(x) - gln))
    b = x + 1 - s
    c = 1 / 1e-300
    d = 1 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - s)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return min(1.0, math.exp(-x + s * math.log(x) - gln) * h)


def chi2_sf(stat: float, df: int) -> float:
    return gammaincc(df / 2, stat / 2)


@dataclass
class Group:
    key: str
    count: int
    exposure: float | None  # None = no exposure basis


@dataclass
class GroupStat:
    key: str
    count: int
    exposure: float | None
    rate: float | None
    rate_ratio: float | None
    ci_low: float | None
    ci_high: float | None


@dataclass
class Comparison:
    groups: list[GroupStat]
    reference: str | None
    test: str  # "conditional_binomial" | "chi_square" | "none"
    p_value: float | None
    total_events: int
    higher_group: str | None
    sample_sufficient: bool

    @property
    def supports_association(self) -> bool:
        return self.sample_sufficient and self.p_value is not None and self.p_value < ALPHA


def _pair_ci(x1: int, e1: float, x2: int, e2: float) -> tuple[float | None, float | None]:
    n = x1 + x2
    if n == 0 or e1 <= 0 or e2 <= 0:
        return None, None
    lo, hi = clopper_pearson(x1, n)
    k = e2 / e1

    def rr(pi: float) -> float | None:
        return None if pi >= 1 else pi / (1 - pi) * k

    return rr(lo), rr(hi)


def compare(groups: list[Group], base: int, reference: str | None = None) -> Comparison:
    groups = [g for g in groups if g.count > 0 or (g.exposure or 0) > 0]
    total = sum(g.count for g in groups)
    exposed = all(g.exposure is not None and g.exposure > 0 for g in groups) and len(groups) >= 2
    if reference is None or reference not in {g.key for g in groups}:
        reference = max(groups, key=lambda g: (g.exposure or 0, g.count)).key if groups else None
    ref = next((g for g in groups if g.key == reference), None)
    stats: list[GroupStat] = []
    for g in groups:
        rate = g.count / g.exposure * base if exposed and g.exposure else None
        rr = lo = hi = None
        if exposed and ref is not None and ref.exposure and ref.count > 0 and g.exposure:
            rr = (g.count / g.exposure) / (ref.count / ref.exposure)
            if g.key != ref.key:
                lo, hi = _pair_ci(g.count, g.exposure, ref.count, ref.exposure)
            else:
                lo = hi = 1.0
        stats.append(GroupStat(g.key, g.count, g.exposure, rate, rr, lo, hi))
    p: float | None = None
    test = "none"
    if exposed and total > 0:
        e_total = sum(g.exposure or 0 for g in groups)
        if len(groups) == 2:
            g1 = groups[0]
            p = binom_test_two_sided(g1.count, total, (g1.exposure or 0) / e_total)
            test = "conditional_binomial"
        else:
            chi = 0.0
            for g in groups:
                exp_n = total * (g.exposure or 0) / e_total
                if exp_n > 0:
                    chi += (g.count - exp_n) ** 2 / exp_n
            p = chi2_sf(chi, len(groups) - 1)
            test = "chi_square"
    higher = None
    if stats:
        if exposed:
            top = max(stats, key=lambda s: (s.rate or 0, s.count))
        else:
            top = max(stats, key=lambda s: s.count)
        higher = top.key
    higher_count = next((s.count for s in stats if s.key == higher), 0)
    sufficient = total >= MIN_EVENTS and higher_count >= MIN_HIGHER
    return Comparison(stats, reference, test, p, total, higher, sufficient)
