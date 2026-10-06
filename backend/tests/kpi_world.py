"""In-memory fixtures for the KPI engine worked examples (spec 1-dashboard §6.10 W1-W8).

No database: these build ``Facts`` directly so the engine is tested exactly as specified.
"""

import itertools
import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.core.hse_enums import CaseCategory, CaStatus, ControlLevel, ObservationType
from app.kpi.cases import CaseDates
from app.kpi.engine import Engine, EngineConfig
from app.kpi.facts import (
    CaFact,
    CaseFact,
    EngFact,
    EventFact,
    Facts,
    Filter,
    InspFact,
    ObsFact,
    WfFact,
)

S_AIR = uuid.UUID(int=1)
S_LAND = uuid.UUID(int=2)
RAWABI = uuid.UUID(int=11)
NAJD = uuid.UUID(int=12)
GULFPAVE = uuid.UUID(int=13)
SAHARA = uuid.UUID(int=14)
PROJECT_START = date(2025, 3, 1)
SEP_START = date(2026, 9, 1)
SEP_END = date(2026, 9, 30)

ENGAGEMENTS = {
    RAWABI: EngFact(RAWABI, "RAWABI", "Rawabi", "الروابي", 1, None,
                    frozenset({S_AIR, S_LAND}), date(2025, 3, 1)),
    NAJD: EngFact(NAJD, "NAJD", "Najd", "نجد", 2, RAWABI, frozenset({S_LAND}), date(2025, 5, 1)),
    GULFPAVE: EngFact(GULFPAVE, "GULFPAVE", "Gulf Pave", "الخليج", 2, RAWABI,
                      frozenset({S_AIR}), date(2025, 4, 15)),
    SAHARA: EngFact(SAHARA, "SAHARA", "Sahara", "الصحراء", 3, NAJD, frozenset({S_LAND}),
                    date(2025, 6, 1)),
}  # fmt: skip
SITE_OF = {RAWABI: S_AIR, NAJD: S_LAND, GULFPAVE: S_AIR, SAHARA: S_LAND}
DAILY = {RAWABI: (1200, 12000), NAJD: (800, 8000), GULFPAVE: (600, 6000), SAHARA: (300, 3000)}

_COUNTER = itertools.count(10_001)


def _id() -> uuid.UUID:
    return uuid.UUID(int=next(_COUNTER))


def case(
    d: date,
    eng: uuid.UUID,
    category: CaseCategory,
    *,
    away: date | None = None,
    rtw: date | None = None,
    restricted: tuple[date, date | None] | None = None,
    eligible: bool = True,
    fatal: bool = False,
    charge: int = 0,
) -> CaseFact:
    dates = CaseDates(
        injury_date=d,
        away_start_date=away,
        rtw_date=rtw,
        restricted_start=restricted[0] if restricted else None,
        restricted_end=restricted[1] if restricted else None,
    )
    iid = _id()
    return CaseFact(
        id=_id(),
        incident_id=iid,
        incident_ref=f"INC-{iid.int}",
        d=d,
        eng=eng,
        site=SITE_OF[eng],
        zone=None,
        category=category,
        dates=dates,
        eligible=eligible,
        fatal=fatal,
        fatality_charge=charge,
    )


def event(d: date, eng: uuid.UUID, *types: str, hipo: bool = False) -> EventFact:
    i = _id()
    return EventFact(i, f"INC-{i.int}", d, eng, SITE_OF[eng], None, frozenset(types), hipo=hipo)


def w1_workforce(days: int = 30, start: date = SEP_START, trn_total: int = 4350) -> list[WfFact]:
    rows = []
    per_day_trn = Decimal(trn_total) / Decimal(days) / 4
    for i in range(days):
        d = start + timedelta(days=i)
        for eng, (hc, mh) in DAILY.items():
            rows.append(WfFact(d, eng, SITE_OF[eng], None, Decimal(mh), hc, trn=per_day_trn))
    return rows


def w1_facts() -> Facts:
    s = SEP_START.replace
    cases = [
        case(s(day=8), NAJD, CaseCategory.LTI, away=s(day=9), rtw=s(day=29)),
        case(s(day=15), SAHARA, CaseCategory.RWC, restricted=(s(day=16), s(day=20))),
        case(s(day=20), RAWABI, CaseCategory.MTC),
        case(s(day=22), GULFPAVE, CaseCategory.MTC),
        *[case(s(day=3 + i), e, CaseCategory.FAC)
          for i, e in enumerate([RAWABI, RAWABI, RAWABI, NAJD, GULFPAVE, SAHARA])],
        case(s(day=17), RAWABI, CaseCategory.FAC, eligible=False),  # #39 not work related
    ]  # fmt: skip
    nm_split = [RAWABI] * 10 + [NAJD] * 6 + [GULFPAVE] * 5 + [SAHARA] * 3
    events = [event(s(day=1 + i), e, "near_miss") for i, e in enumerate(nm_split)]
    events += [
        event(s(day=4), RAWABI, "property_damage"),
        event(s(day=12), GULFPAVE, "property_damage"),
        event(s(day=25), GULFPAVE, "environmental"),
        event(s(day=11), NAJD, "dangerous_occurrence"),
        *[event(c.d, c.eng, "injury_illness") for c in cases if c.eligible and c.eng],
    ]
    # leading fixture: observations
    obs = [
        ObsFact(s(day=10), RAWABI, S_AIR, None, ObservationType.safe_behaviour, True, n=300),
        ObsFact(s(day=11), NAJD, S_LAND, None, ObservationType.safe_condition, True, n=120),
        ObsFact(s(day=12), GULFPAVE, S_AIR, None, ObservationType.unsafe_act, False, n=60),
        ObsFact(s(day=13), SAHARA, S_LAND, None, ObservationType.unsafe_condition, False, n=120),
    ]
    insp: list[InspFact] = []
    for i in range(34):  # on time
        p = s(day=1 + i % 25)
        insp.append(InspFact(_id(), p, p + timedelta(days=1), False, RAWABI, S_AIR, None))
    for i in range(3):  # late
        p = s(day=2 + i)
        insp.append(InspFact(_id(), p, p + timedelta(days=5), False, NAJD, S_LAND, None))
    for i in range(3):  # missed
        insp.append(InspFact(_id(), s(day=5 + i), None, False, GULFPAVE, S_AIR, None))
    for i in range(2):  # cancelled
        insp.append(InspFact(_id(), s(day=6 + i), None, True, SAHARA, S_LAND, None))
    for i in range(5):  # unplanned
        insp.append(InspFact(_id(), None, s(day=10 + i), False, RAWABI, S_AIR, None))
    cas: list[CaFact] = []
    for i in range(41):  # closed on time
        due = s(day=1 + i % 28)
        cas.append(CaFact(_id(), due - timedelta(days=7), due, CaStatus.closed,
                          ControlLevel.engineering, RAWABI, S_AIR, None,
                          completed=due, verified=due + timedelta(days=1)))  # fmt: skip
    for i in range(2):  # closed late
        due = s(day=3 + i)
        cas.append(CaFact(_id(), due - timedelta(days=7), due, CaStatus.closed,
                          ControlLevel.administrative, NAJD, S_LAND, None,
                          completed=due + timedelta(days=4),
                          verified=due + timedelta(days=5)))  # fmt: skip
    for i in range(7):  # still open, overdue at 09-30
        due = s(day=10 + i)
        cas.append(CaFact(_id(), due - timedelta(days=7), due, CaStatus.in_progress,
                          ControlLevel.ppe, GULFPAVE, S_AIR, None))  # fmt: skip
    return Facts(
        wf=w1_workforce(),
        cases=cases,
        events=events,
        obs=obs,
        insp=insp,
        cas=cas,
        engagements=dict(ENGAGEMENTS),
        project_start=PROJECT_START,
    ).sort()


# ---- W3 / W4 monthly fixture ----------------------------------------------------------------

W3 = [
    # month, MH, LTI, RWC, JTC, MTC, FAC, NM
    ((2025, 9), 610_000, 1, 0, 0, 1, 5, 14),
    ((2025, 10), 640_000, 0, 1, 0, 1, 4, 16),
    ((2025, 11), 660_000, 0, 0, 0, 2, 6, 18),
    ((2025, 12), 700_000, 1, 0, 0, 1, 5, 20),
    ((2026, 1), 720_000, 0, 0, 1, 1, 7, 21),
    ((2026, 2), 690_000, 0, 1, 0, 0, 4, 19),
    ((2026, 3), 650_000, 0, 0, 0, 1, 5, 17),
    ((2026, 4), 760_000, 0, 1, 0, 2, 6, 22),
    ((2026, 5), 800_000, 1, 0, 0, 1, 7, 23),
    ((2026, 6), 830_000, 0, 1, 0, 3, 8, 20),
    ((2026, 7), 850_000, 0, 0, 1, 2, 9, 18),
    ((2026, 8), 860_000, 0, 1, 0, 3, 7, 21),
    ((2026, 9), 870_000, 1, 1, 0, 2, 6, 24),
]
W3_LTIS = {
    (2025, 9): (date(2025, 9, 17), RAWABI, 12),
    (2025, 12): (date(2025, 12, 14), RAWABI, 9),
    (2026, 5): (date(2026, 5, 19), GULFPAVE, 15),
    (2026, 9): (date(2026, 9, 8), NAJD, 20),
}


def w3_facts() -> Facts:
    wf: list[WfFact] = []
    cases: list[CaseFact] = []
    events: list[EventFact] = []
    for (y, m), mh, lti, rwc, jtc, mtc, fac, nm in W3:
        d = date(y, m, 10)
        wf.append(WfFact(d, RAWABI, S_AIR, None, Decimal(mh), 1000))
        if lti:
            ld, eng, days = W3_LTIS[(y, m)]
            away = ld + timedelta(days=1)
            cases.append(case(ld, eng, CaseCategory.LTI, away=away, rtw=away + timedelta(days)))
        for cat, n in ((CaseCategory.RWC, rwc), (CaseCategory.JTC, jtc),
                       (CaseCategory.MTC, mtc), (CaseCategory.FAC, fac)):  # fmt: skip
            cases += [case(date(y, m, 2 + i), SAHARA, cat) for i in range(n)]
        events += [event(date(y, m, 1 + i % 28), RAWABI, "near_miss") for i in range(nm)]
    return Facts(
        wf=wf,
        cases=cases,
        events=events,
        engagements=dict(ENGAGEMENTS),
        project_start=PROJECT_START,
    ).sort()


def engine(
    facts: Facts,
    as_of: date = SEP_END,
    engs: set[uuid.UUID] | None = None,
    ltifr_base: int = 1_000_000,
    rate_base: int = 200_000,
) -> Engine:
    flt = Filter(engs=frozenset(engs) if engs is not None else None)
    return Engine(facts, flt, as_of, EngineConfig(ltifr_base, rate_base, 200_000))


def tree(eng: uuid.UUID) -> set[uuid.UUID]:
    return Facts(engagements=dict(ENGAGEMENTS)).descendants(eng)
