"""Pure cold-chain calculations (spec 8-quality §D.3, §D.4): worked examples QX12, QX13, QX15 and
AC-Q3-11, -12, -14, -15, -20 on the engine without a database."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.quality.q3 import QExcursionSeverity
from app.services.quality.q3 import engine as eng

SEV = QExcursionSeverity

D = Decimal
P1, P2 = uuid.uuid4(), uuid.uuid4()
T0 = datetime(2026, 9, 17, 4, 0, tzinfo=UTC)  # 07:00 Riyadh
CHILLED = (eng.Limits(D(0), D(4)), eng.Bands(15, D(2), D(5), 60, 240))
FROZEN = (eng.Limits(D(-30), D(-18)), eng.Bands(30, D(3), D(6), 120, 480))


def series(
    values: list[float], start: datetime = T0, step: int = 15, point: uuid.UUID = P1
) -> list[eng.Reading]:
    return [
        eng.Reading(point, start + timedelta(minutes=step * i), D(str(v)))
        for i, v in enumerate(values)
    ]


def run(
    readings: list[eng.Reading], lim: eng.Limits, bands: eng.Bands, hours: int = 6
) -> tuple[eng.Grid, list[eng.Run]]:
    g = eng.grid(readings, {P1: 15, P2: 15}, D("2.0"), lim, T0, T0 + timedelta(hours=hours))
    return g, eng.runs(g, bands, lim)


def test_ac11_qx12_minor_excursion() -> None:
    # 07:00 … 08:00 in range, 08:00 3.6 · 08:15 4.4 · 08:30 5.1 · 08:45 5.6 · 09:00 4.8 · 09:15 3.9
    vals = [3.0, 3.1, 3.2, 3.3, 3.6, 4.4, 5.1, 5.6, 4.8, 3.9, 3.5, 3.2]
    g, rs = run(series(vals), *CHILLED)
    exc = [r for r in rs if not r.transient]
    assert len(exc) == 1
    r = exc[0]
    assert g.at(r.start) == T0 + timedelta(hours=1, minutes=15)  # 08:15 Riyadh
    assert r.duration == 60 and r.max_deviation == D("1.6")
    assert r.degree_minutes == D("58.50")
    assert r.severity == SEV.minor and not r.data_gap


def test_ac12_transient_ten_minutes() -> None:
    rs_in = series([3.0, 3.0, 4.6, 3.0, 3.0])
    cut = eng.Reading(P1, T0 + timedelta(minutes=40), D("3.2"))  # manual reading cuts the run
    g, rs = run([*rs_in, cut], *CHILLED, hours=2)
    assert len(rs) == 1 and rs[0].transient and rs[0].duration == 10
    assert eng.coverage(g)[2] == 10  # counted in TOR


def test_qx13_major_and_ac14_critical() -> None:
    vals = (
        [-22.0] * 4
        + [
            -17.6,
            -17.0,
            -16.4,
            -15.8,
            -15.1,
            -14.6,
            -14.2,
            -13.8,
            -14.0,
            -14.5,
            -15.2,
            -16.0,
            -16.9,
            -17.6,
        ]
        + [-19.2, -21.0]
    )
    _, rs = run(series(vals), *FROZEN, hours=8)
    r = next(x for x in rs if not x.transient)
    assert r.duration == 210 and r.max_deviation == D("4.2") and r.severity == SEV.major
    _, rs = run(series([-22.0, -11.5, -11.5, -12.0, -20.0, -21.0]), *FROZEN)
    r = next(x for x in rs if not x.transient)
    assert r.duration == 45 and r.max_deviation == D("6.5") and r.severity == SEV.critical


def test_ac15_data_gap_counts_as_out_time() -> None:
    # 08:00 out, then nothing until 09:05 (65 min > 2 × 15): 08:15–09:05 unmonitored inside the run
    rs = [
        *series([3.0, 3.0, 3.0, 3.0, 4.8]),
        eng.Reading(P1, T0 + timedelta(minutes=125), D("4.9")),
        eng.Reading(P1, T0 + timedelta(minutes=140), D("3.0")),
    ]
    g, out = run(rs, *CHILLED, hours=4)
    r = next(x for x in out if not x.transient)
    assert r.data_gap and r.duration == 80  # 08:00 → 09:20
    assert eng.coverage(g)[1] == 105  # 0–75, 125–155 monitored; 75–125 is the gap inside
    assert (75, 125) in eng.gaps(g, 30)


def test_any_point_out_makes_the_zone_out() -> None:
    a = series([3.0] * 8)
    b = series([3.0, 3.0, 4.5, 4.5, 3.0, 3.0, 3.0, 3.0], point=P2)
    g, rs = run([*a, *b], *CHILLED, hours=2)
    assert eng.coverage(g)[2] == 30 and rs[0].points == {P2}


def test_runs_closer_than_alarm_delay_merge() -> None:
    vals = [3.0, 4.5, 4.5, 3.0, 4.5, 4.5, 3.0, 3.0]  # out 15–45, in 45–60, out 60–90
    _, rs = run(series(vals), CHILLED[0], eng.Bands(30, D(2), D(5), 60, 240), hours=2)
    assert len(rs) == 1 and rs[0].duration == 75 and rs[0].out_minutes == 60
    _, rs = run(series(vals), *CHILLED, hours=2)  # 15 in-range minutes is not fewer than 15
    assert len(rs) == 2


def test_ac20_qx15_mean_kinetic_temperature() -> None:
    vals = [21.5, 22.0, 23.0, 24.5, 26.0, 27.5, 24.0]
    assert eng.mkt(vals) == D("24.29")
    assert eng.mkt([v + 2 for v in vals]) > D(25)  # MKT_ABOVE_RANGE for a 15–25 °C zone
    mean = sum(vals) / len(vals)
    assert round(mean, 2) == 24.07


def test_severity_bands_inclusive() -> None:
    b = CHILLED[1]
    assert eng.severity(D(2), 60, b) == SEV.minor
    assert eng.severity(D("2.01"), 60, b) == SEV.major
    assert eng.severity(D(1), 241, b) == SEV.critical
