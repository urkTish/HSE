"""Phase 6g arithmetic on the worked examples (6g §6.9 SG1 / SG2; AC 3-8, 12). Pure functions:
the engine's values on the seed differ from the SG1 fixture (DECISIONS D-226)."""

from __future__ import annotations

from decimal import Decimal

from app.core.scorecard_enums import ScGrade, ScLineStatus
from app.services.scorecard import calc
from app.services.scorecard import common as cm
from tests.sc_helpers import sg1

D = Decimal


def test_sg1_card_ac3_ac4() -> None:
    r = sg1()
    q = D("0.000000000001")
    assert r.score is not None and r.score.quantize(q) == (D(54903) / D(679)).quantize(q)
    assert cm.d1(r.score) == "80.9" and r.coverage == D(90)
    assert r.band_grade == ScGrade.B and r.grade == ScGrade.C
    by = {ln.metric_code: ln for ln in r.lines}
    assert cm.d1(by["SM-TRIR"].points) == "76.0" and cm.d1(by["SM-LTIFR"].points) == "80.0"
    assert cm.d1(by["SM-LTISR"].points) == "92.0" and cm.d1(by["SM-HIPO"].points) == "84.0"
    assert cm.d1(by["SM-CA-ONTIME"].points) == "42.9" and by["SM-CA-OVERDUE"].points == D("81.25")
    assert cm.d1(by["SM-PTW-AUDIT"].points) == "50.0" and cm.d1(by["SM-PTW-CRIT"].points) == "16.7"
    assert cm.d1(by["SM-TBT"].points) == "85.7"
    pil = {p.pillar_code: p for p in r.pillars}
    assert (
        pil["LAG"].score is not None
        and pil["LAG"].score.quantize(q) == (D(2432) / 30).quantize(q)
        and cm.d1(pil["LAG"].effective_weight) == "30.9"
    )
    assert (
        cm.d1(pil["CA"].score) == "58.2"
        and pil["PTW"].score == D(50)
        and pil["CERT"].score == D("87.5")
    )
    assert pil["INS"].score == D(91) and pil["NOT"].score is None
    for code in ("SM-SCAF-TAG", "SM-EMG-EQUIP", "SM-WASTE-COC"):
        assert by[code].status == ScLineStatus.not_applicable
    assert by["SM-AUDIT"].status == ScLineStatus.insufficient_volume
    assert by["SM-NOTIF"].status == by["SM-LESSON-ACK"].status == ScLineStatus.source_not_live
    assert sum(ln.effective_weight for ln in r.lines).quantize(D("0.000001")) == D(100)


def test_sg2_credibility_ac5() -> None:
    z = calc.credibility(D(60000), D(100000))
    assert z == D("0.6")
    trir = calc.blend(z, D(1) * 200000 / D(60000), D("0.50"))
    assert cm.d2(trir) == "2.20" and calc.points(trir, D(0), D(1)) == 0
    assert calc.blend(z, D(0), D("0.40")) == D("0.160")
    assert calc.points(D("0.16"), D(0), D(2)) == D(92)
    assert calc.points(calc.blend(z, D(0), D("1.00")), D(0), D(20)) == D(98)
    assert calc.points(calc.blend(z, D(0), D("0.20")), D(0), D(1)) == D(92)
    lag = (0 + 8 * D(92) + 5 * D(98) + 5 * D(92)) / 30
    assert cm.d1(lag) == "56.2"
    # SP-4: a 1,000,000 base gives 5x larger stored rates but the same canonical value and points
    assert calc.points(D("0.80") * 200000 / 1000000, D(0), D(2)) == D(92)


def test_redistribution_ac6_ac7_ac8() -> None:
    r = sg1(status={"SM-CA-ONTIME": ScLineStatus.insufficient_volume})
    by = {ln.metric_code: ln for ln in r.lines}
    assert by["SM-CA-ONTIME"].effective_weight == 0
    ca = {p.pillar_code: p for p in r.pillars}["CA"]
    assert by["SM-CA-OVERDUE"].effective_weight == ca.effective_weight and ca.score == D("81.25")
    r = sg1(
        status={
            "SM-HEAT-WELF": ScLineStatus.not_applicable,
            "SM-HEAT-BAN": ScLineStatus.not_applicable,
        }
    )
    pil = {p.pillar_code: p for p in r.pillars}
    assert pil["HEAT"].effective_weight == 0 and pil["LAG"].effective_weight.quantize(
        D("0.0001")
    ) == (D(3000) / 93).quantize(D("0.0001"))
    # scored weight 55 < 60 % → grade "—", score indicative, never ranked
    off = {
        m.code.value: ScLineStatus.insufficient_volume
        for m in cm.METRICS
        if m.pillar.value == "LAG" or m.code.value == "SM-TRAIN"
    }
    r = sg1(status=off)
    assert r.coverage == D(55) and r.grade is None and r.indicative and r.score is not None


def test_caps_ac9() -> None:
    assert sg1(caps=[ScGrade.B]).grade == ScGrade.B
    assert sg1(values={"SM-TRIR": "0"}, caps=[ScGrade.D]).grade == ScGrade.D
