"""KPI engine worked examples W1-W8 (spec 1-dashboard §6.10), to the decimal, half-up."""

import itertools
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.hse_enums import (
    CaseCategory,
    CaStatus,
    ComparisonKind,
    ControlLevel,
    InjuryNature,
    KpiMetric,
    KpiWarning,
    NullReason,
    PeriodPreset,
    PermanentDisability,
    TreatedAt,
    Treatment,
)
from app.kpi import fmt, periods, present
from app.kpi.cases import CaseDates, day_counts, derive_category, lost_days_charged
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine, EngineConfig
from app.kpi.facts import CaFact, Facts, Filter, InspFact, WfFact, ZoneFact
from app.kpi.periods import Window
from tests import kpi_world as w
from tests.kpi_world import GULFPAVE, NAJD, RAWABI, SAHARA, SEP_END, SEP_START

M = KpiMetric
SEP = Window(SEP_START, SEP_END)


@pytest.fixture(autouse=True)
def _fresh_data() -> None:
    """Pure tests: no database reset needed."""


def show(e: Engine, metric: KpiMetric, window: Window = SEP) -> str:
    res = e.result(metric, e.aggregate(window))
    return present.display(CATALOGUE[metric], res.value)


def val(e: Engine, metric: KpiMetric, window: Window = SEP) -> Decimal | None:
    return e.result(metric, e.aggregate(window)).value


# ---- W1 -----------------------------------------------------------------------------------


def test_AC1_W1_exposure() -> None:
    e = w.engine(w.w1_facts())
    assert show(e, M.K01) == "870,000"
    k02 = e.result(M.K02, e.aggregate(SEP))
    shares = {c.key: present.display_kind(c.kind, c.share and c.share, 1) for c in k02.components}
    assert fmt.percent(k02.components[0].share or Decimal(0)) == "41.4 %"
    assert fmt.percent(k02.components[1].share or Decimal(0)) == "58.6 %"
    assert shares  # direct/subcontractor/tier components exist
    assert show(e, M.K02) == "41.4 %"
    assert show(e, M.K03) == "2,900"
    assert show(e, M.K04) == "2,900"


def test_AC44_W1_lagging_values() -> None:
    e = w.engine(w.w1_facts())
    expected = {
        M.K06: "1", M.K10: "4", M.K11: "2", M.K12: "6", M.K13: "24", M.K14: "1",
        M.K15: "2", M.K16: "1", M.K17: "20", M.K18: "5", M.K20: "1.15", M.K21: "0.92",
        M.K22: "0.46", M.K23: "4.60", M.K24: "1.38", M.K25: "5.52", M.K27: "2.4 : 1",
        M.K28: "22", M.K29: "638,000",
    }  # fmt: skip
    got = {m: show(e, m) for m in expected}
    assert got == expected


def test_AC21_W1_excluded_case_never_counted() -> None:
    e = w.engine(w.w1_facts())
    a = e.aggregate(SEP)
    assert a.cats[CaseCategory.FAC] == 6  # #39 (not work related) is not a 7th FAC
    assert a.nm == 24  # voided #40 is not loaded as a counted event


def test_AC45_W1_ltifr_base_200k() -> None:
    e = w.engine(w.w1_facts(), ltifr_base=200_000)
    res = e.result(M.K20, e.aggregate(SEP))
    assert present.display(CATALOGUE[M.K20], res.value) == "0.23"
    assert res.base == 200_000
    assert fmt.hours_label(res.base)[0] == "per 200,000 h"


def test_AC38_W1_leading_values() -> None:
    e = w.engine(w.w1_facts())
    a = e.aggregate(SEP)
    assert (a.obs_total, a.obs_safe, a.obs_unsafe) == (600, 420, 180)
    expected = {
        M.K31: "70.0 %", M.K32: "137.93", M.K34: "85.0 %", M.K35: "92.5 %", M.K35b: "42",
        M.K37: "1.50", M.K41: "82.0 %", M.K42: "7",
    }  # fmt: skip
    assert {m: show(e, m) for m in expected} == expected


# ---- W2 -----------------------------------------------------------------------------------

W2_ROWS = [
    # scope, MH, LTIFR, TRIR, DART, LTISR, FA, NM ratio, LTI-free days, LTI-free MH
    ("RAWABI+subs", w.tree(RAWABI), "870,000", "1.15", "0.92", "0.46", "4.60", "1.38",
     "2.4 : 1", "22", "638,000"),
    ("NAJD+subs", w.tree(NAJD), "330,000", "3.03", "1.21", "1.21", "12.12", "1.21",
     "2.3 : 1", "22", "242,000"),
    ("NAJD only", {NAJD}, "240,000", "4.17", "0.83", "0.83", "16.67", "0.83", "3.0 : 1",
     "22", "176,000"),
    ("RAWABI only", {RAWABI}, "360,000", "0.00", "0.56", "0.00", "0.00", "1.67", "2.5 : 1",
     "579", "360,000"),
    ("GULFPAVE", {GULFPAVE}, "180,000", "0.00", "1.11", "0.00", "0.00", "1.11", "2.5 : 1",
     "534", "180,000"),
    ("SAHARA", {SAHARA}, "90,000", "0.00", "2.22", "2.22", "0.00", "2.22", "1.5 : 1",
     "487", "90,000"),
]  # fmt: skip


@pytest.mark.parametrize("row", W2_ROWS, ids=[r[0] for r in W2_ROWS])
def test_AC46_W2_contractor_filters(row: tuple) -> None:  # type: ignore[type-arg]
    _, engs, *cells = row
    e = w.engine(w.w1_facts(), engs=engs)
    metrics = [M.K01, M.K20, M.K21, M.K22, M.K23, M.K24, M.K27, M.K28, M.K29]
    assert [show(e, m) for m in metrics] == cells


def test_AC47_W2_rawabi_with_subs_equals_project() -> None:
    whole = w.engine(w.w1_facts())
    rawabi = w.engine(w.w1_facts(), engs=w.tree(RAWABI))
    for m in KpiMetric:
        assert show(whole, m) == show(rawabi, m), m


def test_W2_non_injury_events_do_not_change_injury_rates() -> None:
    f = w.w1_facts()
    with_events = w.engine(f)
    f.events = [ev for ev in f.events if ev.types <= {"near_miss", "injury_illness"}]
    without = w.engine(f)
    for m in (M.K20, M.K21, M.K22, M.K23, M.K24):
        assert show(with_events, m) == show(without, m)


# ---- W3 -----------------------------------------------------------------------------------

W3_EXPECTED = {
    # window: MH, LTI, TRI, DART, FAC, NM, lost, LTIFR, TRIR, DART, LTISR, FA, NM rate, ratio
    "R12 Sep": (Window(date(2025, 10, 1), date(2026, 9, 30)), "9,030,000", "3", "30", "11",
                "74", "239", "44", "0.33", "0.66", "0.24", "0.97", "1.64", "5.29", "2.3 : 1"),
    "R12 Aug": (Window(date(2025, 9, 1), date(2026, 8, 31)), "8,770,000", "3", "28", "10",
                "73", "229", "36", "0.34", "0.64", "0.23", "0.82", "1.66", "5.22", "2.3 : 1"),
    "YTD 2026": (Window(date(2026, 1, 1), date(2026, 9, 30)), "7,030,000", "2", "24", "9",
                 "59", "185", "35", "0.28", "0.68", "0.26", "1.00", "1.68", "5.26", "2.2 : 1"),
}  # fmt: skip
W3_METRICS = [
    M.K01, M.K06, M.K10, M.K11, M.K12, M.K13, M.K17, M.K20, M.K21, M.K22, M.K23, M.K24,
    M.K25, M.K27,
]  # fmt: skip


@pytest.mark.parametrize("name", list(W3_EXPECTED))
def test_AC48_W3_aggregates(name: str) -> None:
    window, *cells = W3_EXPECTED[name]
    e = w.engine(w.w3_facts())
    assert [show(e, m, window) for m in W3_METRICS] == cells


def test_AC48_W3_monthly_values() -> None:
    e = w.engine(w.w3_facts())
    monthly = [
        "0.66", "0.63", "0.61", "0.57", "0.56", "0.29", "0.31", "0.79", "0.50", "0.96",
        "0.71", "0.93", "0.92",
    ]  # fmt: skip
    ltifr = [
        "1.64", "0.00", "0.00", "1.43", "0.00", "0.00", "0.00", "0.00", "1.25", "0.00",
        "0.00", "0.00", "1.15",
    ]  # fmt: skip
    months = periods.months_between(date(2025, 9, 1), date(2026, 9, 30))
    assert [show(e, M.K21, m) for m in months] == monthly
    assert [show(e, M.K20, m) for m in months] == ltifr


def _delta(e: Engine, metric: KpiMetric, cur: Window, comp: Window) -> tuple[str, str]:
    c = val(e, metric, cur)
    p = val(e, metric, comp)
    _, abs_d, _, pct_d, _ = present.delta(CATALOGUE[metric], c, p)
    return abs_d, pct_d


def test_AC48_W3_trir_comparisons() -> None:
    e = w.engine(w.w3_facts())
    prev = periods.comparison(ComparisonKind.previous, PeriodPreset.month, SEP)
    sply = periods.comparison(ComparisonKind.sply, PeriodPreset.month, SEP)
    r12 = periods.comparison(ComparisonKind.r12, PeriodPreset.month, SEP)
    assert prev == Window(date(2026, 8, 1), date(2026, 8, 31))
    assert sply == Window(date(2025, 9, 1), date(2025, 9, 30))
    assert r12 == Window(date(2025, 10, 1), date(2026, 9, 30))
    assert str(val(e, M.K21, prev))[:8] == "0.930232"
    assert _delta(e, M.K21, SEP, prev) == ("−0.01", "−1.1 %")
    assert _delta(e, M.K21, SEP, sply) == ("+0.26", "+40.2 %")
    assert _delta(e, M.K21, SEP, r12) == ("+0.26", "+38.4 %")
    assert _delta(e, M.K20, SEP, sply) == ("−0.49", "−29.9 %")
    assert _delta(e, M.K01, SEP, prev)[1] == "+1.2 %"
    assert _delta(e, M.K01, SEP, sply)[1] == "+42.6 %"
    r12_aug = periods.r12_ending(date(2026, 8, 31))
    assert _delta(e, M.K21, r12, r12_aug) == ("+0.03", "+4.1 %")
    # direction: TRIR down vs previous is better, up vs SPLY is worse
    assert present.delta(CATALOGUE[M.K21], val(e, M.K21), val(e, M.K21, prev))[4] == "better"
    assert present.delta(CATALOGUE[M.K21], val(e, M.K21), val(e, M.K21, sply))[4] == "worse"


# ---- W4 -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scope", "engs", "last", "days"),
    [
        ("ANIA-EXP", None, date(2026, 9, 8), 22),
        ("NAJD+subs", w.tree(NAJD), date(2026, 9, 8), 22),
        ("RAWABI only", {RAWABI}, date(2025, 12, 14), 290),
        ("GULFPAVE", {GULFPAVE}, date(2026, 5, 19), 134),
        ("SAHARA", {SAHARA}, None, 487),
    ],
)
def test_AC49_W4_lti_free_days(
    scope: str, engs: set[uuid.UUID] | None, last: date | None, days: int
) -> None:
    lf = w.engine(w.w3_facts(), engs=engs).lti_free()
    assert lf.last_lti_date == last
    assert lf.days == days
    assert lf.basis == ("since_last_lti" if last else "since_start")


def test_AC49_W4_longest_run() -> None:
    """Spec W4/AC49 states 112 days (2026-05-19 → 2026-09-08). Applying §6.4.6 to the W3 LTI
    dates gives longer runs: 156 days (2025-12-14 → 2026-05-19) between LTIs and 200 days
    from the project start (2025-03-01) to the first LTI (2025-09-17). The engine implements
    the definition; the discrepancy is reported to the HSE Manager (see docs/PROGRESS.md)."""
    lf = w.engine(w.w3_facts()).lti_free()
    assert (lf.longest_days, lf.longest_start, lf.longest_end) == (
        200,
        date(2025, 3, 1),
        date(2025, 9, 17),
    )
    lti_dates = sorted(v[0] for v in w.W3_LTIS.values())
    between = [(b - a).days for a, b in itertools.pairwise(lti_dates)]
    assert max(x for x in between) == 156
    assert (date(2026, 9, 8) - date(2026, 5, 19)).days == 112


# ---- W5 -----------------------------------------------------------------------------------


def _counts(dates: CaseDates, as_of: date, cap: int = 180) -> tuple[int, int, bool]:
    c = day_counts(dates, as_of, cap)
    return c.days_away, c.restricted_days, c.capped


def _derive(dates: CaseDates, treatments: list[Treatment] | None = None, **kw: object) -> str:
    args: dict[str, object] = {
        "fatal": False,
        "permanent": PermanentDisability.none,
        "treatments": treatments or [Treatment.wound_cleaning],
        "loss_of_consciousness": False,
        "nature": InjuryNature.laceration,
        "treated_at": TreatedAt.site_clinic,
    }
    args.update(kw)
    return derive_category(dates=dates, as_of=date(2026, 10, 31), **args).value  # type: ignore[arg-type]


def test_AC17_W5_day_counts() -> None:
    a = CaseDates(date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 29))
    assert _counts(a, date(2026, 9, 29))[0] == 20
    assert _counts(a, date(2027, 1, 1))[0] == 20
    b = CaseDates(date(2026, 9, 22), date(2026, 9, 23))
    assert _counts(b, date(2026, 9, 30))[0] == 8
    assert _counts(b, date(2026, 10, 31))[0] == 39
    b2 = CaseDates(date(2026, 9, 22), date(2026, 9, 23), date(2026, 10, 12))
    assert _counts(b2, date(2026, 12, 31))[0] == 19
    c = CaseDates(date(2026, 1, 5), date(2026, 1, 6))
    assert _counts(c, date(2026, 9, 30)) == (180, 0, True)
    assert day_counts(c, date(2026, 9, 30), 0).days_away == 268
    g = CaseDates(date(2026, 9, 24), restricted_start=date(2026, 9, 25))
    assert _counts(g, date(2026, 9, 30))[1] == 6


def test_W5_b2_attributed_to_injury_month() -> None:
    f = Facts(engagements=dict(w.ENGAGEMENTS), project_start=w.PROJECT_START)
    f.cases = [
        w.case(date(2026, 9, 22), NAJD, CaseCategory.LTI, away=date(2026, 9, 23),
               rtw=date(2026, 10, 12))
    ]  # fmt: skip
    e = w.engine(f, as_of=date(2026, 12, 31))
    assert val(e, M.K17, SEP) == 19
    assert val(e, M.K17, Window(date(2026, 10, 1), date(2026, 10, 31))) == 0


def test_AC15_W5_case_d() -> None:
    d = CaseDates(
        date(2026, 6, 1),
        date(2026, 6, 2),
        date(2026, 6, 12),
        restricted_start=date(2026, 6, 12),
        restricted_end=date(2026, 7, 11),
    )
    assert _counts(d, date(2026, 7, 11)) == (10, 30, False)
    assert _derive(d) == "LTI"


def test_AC16_W5_case_e() -> None:
    e = CaseDates(date(2026, 9, 10), rtw_date=date(2026, 9, 11))
    assert _counts(e, date(2026, 9, 30))[0] == 0
    assert _derive(e, [Treatment.sutures_staples_glue]) == "MTC"


def test_AC18_W5_case_f_fatality() -> None:
    f = Facts(engagements=dict(w.ENGAGEMENTS), project_start=w.PROJECT_START)
    fat = w.case(date(2026, 3, 3), NAJD, CaseCategory.FAT, fatal=True)
    f.cases = [fat]
    march = Window(date(2026, 3, 1), date(2026, 3, 31))
    e = w.engine(f)
    assert (val(e, M.K06, march), val(e, M.K10, march), val(e, M.K11, march)) == (1, 1, 0)
    assert val(e, M.K17, march) == 0
    f.cases = [w.case(date(2026, 3, 3), NAJD, CaseCategory.FAT, fatal=True, charge=6000)]
    assert val(w.engine(f), M.K17, march) == 6000
    assert (
        lost_days_charged(
            CaseCategory.FAT,
            day_counts(fat.dates, date(2026, 9, 30), 180),
            True,
            PermanentDisability.none,
            6000,
        )
        == 6000
    )
    assert _derive(CaseDates(date(2026, 3, 3)), fatal=True) == "FAT"


def test_AC13_classification_first_aid_vs_medical() -> None:
    d = CaseDates(date(2026, 9, 10))
    fa = [Treatment.wound_cleaning, Treatment.wound_covering_steristrips]
    assert _derive(d, fa) == "FAC"
    assert _derive(d, [*fa, Treatment.sutures_staples_glue]) == "MTC"


def test_AC14_classification_significant_injury() -> None:
    d = CaseDates(date(2026, 9, 10))
    tx = [Treatment.temporary_immobilisation_transport]
    assert _derive(d, tx, nature=InjuryNature.fracture) == "MTC"
    assert _derive(d, tx) == "FAC"
    assert _derive(d, tx, loss_of_consciousness=True) == "MTC"
    assert _derive(d, tx, treated_at=TreatedAt.hospital_admitted) == "MTC"
    assert _derive(d, [Treatment.x_ray_diagnosis]) == "FAC"
    assert _derive(d, tx, permanent=PermanentDisability.partial) == "LTI"
    assert _derive(CaseDates(date(2026, 9, 10), transfer_start=date(2026, 9, 11))) == "JTC"
    assert _derive(CaseDates(date(2026, 9, 10), restricted_start=date(2026, 9, 11))) == "RWC"


# ---- W6 -----------------------------------------------------------------------------------


def test_AC50_W6_half_up() -> None:
    q = uuid.UUID(int=99)
    site = uuid.UUID(int=98)
    f = Facts(
        engagements={q: w.EngFact(q, "QIMMA", "Qimma", "القمة", 1, None, frozenset({site}),
                                  date(2025, 1, 15))},
        project_start=date(2025, 1, 15),
    )  # fmt: skip
    monthly = [120, 125, 130, 130, 135, 135, 135, 140, 140, 140, 135, 135]
    for i, k in enumerate(monthly):
        d = periods.add_months(date(2025, 10, 15), i)
        f.wf.append(WfFact(d, q, site, None, Decimal(k * 1000), 100))
    mtc = w.case(date(2026, 3, 10), RAWABI, CaseCategory.MTC)
    f.cases = [
        w.CaseFact(**{**{s: getattr(mtc, s) for s in mtc.__slots__}, "eng": q, "site": site})
    ]
    f.sort()
    r12 = periods.r12_ending(date(2026, 9, 30))
    e = Engine(f, Filter(), date(2026, 9, 30), EngineConfig(200_000, 200_000))
    assert show(e, M.K01, r12) == "1,600,000"
    assert val(e, M.K21, r12) == Decimal("0.125")
    assert show(e, M.K21, r12) == "0.13"
    assert show(e, M.K20, r12) == "0.00"
    assert fmt.number(Decimal("0.125"), 2) == "0.13"


# ---- W7 -----------------------------------------------------------------------------------


def _insp_engine(completed: date | None, as_of: date) -> Engine:
    f = Facts(engagements=dict(w.ENGAGEMENTS), project_start=w.PROJECT_START)
    f.insp = [InspFact(uuid.uuid4(), date(2026, 9, 9), completed, False, RAWABI, w.S_AIR, None)]
    return w.engine(f, as_of=as_of)


def test_AC37_W7_inspection_pending_exclusion() -> None:
    mtd = Window(date(2026, 9, 1), date(2026, 9, 10))
    e = _insp_engine(None, date(2026, 9, 10))
    assert e.aggregate(mtd).d_insp == 0
    assert show(e, M.K34, mtd) == "—"
    e = _insp_engine(None, date(2026, 9, 12))
    assert show(e, M.K34, SEP) == "0.0 %"
    e = _insp_engine(date(2026, 9, 11), date(2026, 9, 12))
    assert (show(e, M.K34, SEP), show(e, M.K35, SEP)) == ("100.0 %", "100.0 %")
    e = _insp_engine(date(2026, 9, 12), date(2026, 9, 12))
    assert (show(e, M.K34, SEP), show(e, M.K35, SEP)) == ("0.0 %", "100.0 %")


# ---- W8 -----------------------------------------------------------------------------------


def test_AC39_W8_corrective_actions() -> None:
    s = SEP_START.replace

    def ca(due: date, status: CaStatus, completed: date | None = None,
           verified: date | None = None, cancelled: date | None = None) -> CaFact:  # fmt: skip
        return CaFact(uuid.uuid4(), date(2026, 8, 20), due, status, ControlLevel.engineering,
                      RAWABI, w.S_AIR, None, completed, verified, cancelled)  # fmt: skip

    f = Facts(engagements=dict(w.ENGAGEMENTS), project_start=w.PROJECT_START)
    f.cas = [
        ca(s(day=10), CaStatus.closed, s(day=9), s(day=9)),
        ca(s(day=15), CaStatus.closed, s(day=18), s(day=19)),
        ca(s(day=20), CaStatus.in_progress),
        ca(s(day=25), CaStatus.pending_verification, s(day=24)),
        ca(s(day=28), CaStatus.cancelled, cancelled=s(day=26)),
        ca(date(2026, 10, 5), CaStatus.open),
        ca(date(2026, 8, 31), CaStatus.open),
    ]
    e = w.engine(f)
    assert show(e, M.K41) == "25.0 %"
    k42 = e.result(M.K42, e.aggregate(SEP))
    assert k42.value == 2
    assert {c.key: c.value for c in k42.components}["8-30"] == 2
    assert show(e, M.K42b) == "1"


# ---- edge rules -------------------------------------------------------------------------------


def test_AC51_zero_exposure_rates_dash() -> None:
    f = w.w1_facts()
    f.wf = []
    e = w.engine(f)
    for m in (M.K20, M.K21, M.K22, M.K23, M.K24, M.K25, M.K32):
        res = e.result(m, e.aggregate(SEP))
        assert res.value is None and res.null_reason == NullReason.NO_EXPOSURE
        assert present.display(CATALOGUE[m], res.value) == "—"
    assert show(e, M.K10) == "4"  # counts still returned


def test_AC52_zone_without_zoned_man_hours() -> None:
    f = w.w1_facts()
    zone = uuid.UUID(int=500)
    f.zones = {zone: ZoneFact(zone, w.S_AIR, "airside", "apron", "Z-APR-21")}
    e = Engine(f, Filter(zones=frozenset({zone})), SEP_END, EngineConfig())
    res = e.result(M.K21, e.aggregate(SEP))
    assert res.value is None and res.null_reason == NullReason.NO_ZONE_EXPOSURE
    # partial exposure: some zoned rows exist next to unzoned ones on the same site
    f.wf.append(WfFact(date(2026, 9, 5), RAWABI, w.S_AIR, zone, Decimal(5000), 50))
    f.sort()
    e = Engine(f, Filter(zones=frozenset({zone})), SEP_END, EngineConfig())
    res = e.result(M.K21, e.aggregate(SEP))
    assert res.value is not None and KpiWarning.PARTIAL_EXPOSURE in res.warnings


def test_rate_with_zero_count_is_zero() -> None:
    e = w.engine(w.w1_facts(), engs={RAWABI})
    assert show(e, M.K20) == "0.00"


def test_AC53_custom_period_comparisons() -> None:
    p = periods.resolve(
        PeriodPreset.custom, as_of=date(2026, 9, 30), start=date(2026, 9, 5),
        end=date(2026, 9, 14),
    )  # fmt: skip
    assert periods.previous(PeriodPreset.custom, p.window) == Window(
        date(2026, 8, 26), date(2026, 9, 4)
    )
    assert periods.sply(p.window) == Window(date(2025, 9, 5), date(2025, 9, 14))


def test_AC54_leap_day_sply() -> None:
    p = periods.resolve(PeriodPreset.day, as_of=date(2024, 2, 29))
    assert periods.sply(p.window) == Window(date(2023, 2, 28), date(2023, 2, 28))
    feb = periods.resolve(PeriodPreset.month, as_of=date(2024, 2, 10)).window
    assert periods.sply(feb) == Window(date(2023, 2, 1), date(2023, 2, 28))


def test_period_presets() -> None:
    as_of = date(2026, 9, 30)
    r = periods.resolve(PeriodPreset.r12, as_of=as_of)
    assert (r.window, r.label_en) == (Window(date(2025, 10, 1), as_of), "R12 to Sep 2026")
    assert periods.resolve(PeriodPreset.ytd, as_of=as_of).window.start == date(2026, 1, 1)
    q = periods.resolve(PeriodPreset.quarter, as_of=as_of)
    assert (q.window, q.label_en) == (Window(date(2026, 7, 1), as_of), "Q3 2026")
    itd = periods.resolve(PeriodPreset.itd, as_of=as_of, project_start=date(2025, 3, 1))
    assert itd.window.start == date(2025, 3, 1)
    m = periods.resolve(PeriodPreset.month, as_of=as_of)
    assert (m.label_en, m.label_ar) == ("Sep 2026", "سبتمبر 2026")


def test_AC57_completeness_threshold() -> None:
    eng = uuid.UUID(int=700)
    sites = [uuid.UUID(int=701), uuid.UUID(int=702), uuid.UUID(int=703), uuid.UUID(int=704)]
    start = date(2026, 6, 1)
    f = Facts(
        engagements={eng: w.EngFact(eng, "X", "X", "X", 1, None, frozenset(sites), start)},
        project_start=start,
    )
    june = Window(start, date(2026, 6, 30))  # 4 sites × 30 days = 120 cells

    def make(missing: int) -> Engine:
        f.wf = [
            WfFact(start + timedelta(days=d), eng, s, None, Decimal(100), 10)
            for s in sites
            for d in range(30)
        ][missing:]
        f.sort()
        return Engine(f, Filter(), date(2026, 7, 5), EngineConfig())

    e = make(3)
    a = e.aggregate(june)
    assert (a.expected, a.reported) == (120, 117)
    assert show(e, M.K45, june) == "97.5 %"
    assert show(make(7), M.K45, june) == "94.2 %"


def test_rag_rules() -> None:
    trir = CATALOGUE[M.K21]
    assert present.rag(trir, Decimal("0.50"), Decimal("0.50")) == "green"
    assert present.rag(trir, Decimal("0.60"), Decimal("0.50")) == "amber"
    assert present.rag(trir, Decimal("0.61"), Decimal("0.50")) == "red"
    comp = CATALOGUE[M.K34]
    assert present.rag(comp, Decimal("95.0"), Decimal("95")) == "green"
    assert present.rag(comp, Decimal("76.0"), Decimal("95")) == "amber"
    assert present.rag(comp, Decimal("75.9"), Decimal("95")) == "red"
    assert present.rag(CATALOGUE[M.K01], Decimal(1), Decimal(1)) is None
