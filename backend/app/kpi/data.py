"""Loader: fills ``Facts`` for a set of projects with aggregated SQL (no N+1).

One query per fact type per call, grouped where the engine only needs sums (workforce rows by
date × engagement × site × zone; observations by date × engagement × site × zone × type ×
closure). Eligibility of injury cases for rates (I-4) and of events (status ∉ {draft, voided},
work related) is decided here from the project settings; the engine never sees settings.
"""

import copy
import hashlib
import threading
import time
import uuid
from collections.abc import Iterable
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, event, func, or_, select
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql.elements import TextClause

from app.core.access_enums import InductionResult, InductionType
from app.core.config import get_settings
from app.core.hse_enums import (
    CaStatus,
    IncidentStatus,
    InspectionStatus,
    ObservationStatus,
    PersonType,
    WorkforceStatus,
)
from app.kpi.access_facts import load_access
from app.kpi.cases import CaseDates
from app.kpi.facts import (
    CaFact,
    CaseFact,
    EngFact,
    EventFact,
    Facts,
    IndFact,
    InspFact,
    MeetingFact,
    ObsFact,
    TbtFact,
    WfFact,
    ZoneFact,
)
from app.models import (
    CorrectiveAction,
    Deployment,
    HseMeeting,
    HseSettings,
    Incident,
    InductionRecord,
    InjuryCase,
    Inspection,
    Investigation,
    Observation,
    PeriodLock,
    Project,
    ProjectEngagement,
    WorkforceReturn,
    Zone,
)

COUNTED_RETURN = (WorkforceStatus.submitted, WorkforceStatus.verified, WorkforceStatus.locked)
EXCLUDED_INCIDENT = (IncidentStatus.draft, IncidentStatus.voided)
SAFE_TYPES = ("safe_behaviour", "safe_condition")


def case_eligible(incident: Incident, c: InjuryCase, s: HseSettings) -> tuple[bool, str | None]:
    """I-4. Returns (counts in rates, exclusion reason)."""
    if incident.status == IncidentStatus.draft:
        return False, "incident_draft"
    if incident.status == IncidentStatus.voided:
        return False, "incident_voided"
    if not incident.work_related:
        return False, "not_work_related"
    allowed = {PersonType.contractor_worker}
    if s.include_non_contractor_cases_in_rates:
        allowed.add(PersonType.client_pmc_staff)
    if c.person_type not in allowed:
        return False, "non_contractor_person"
    if c.commuting and not s.include_commuting_in_rates:
        return False, "commuting"
    return True, None


# ---- per-process facts cache --------------------------------------------------------------------

_CACHE: dict[tuple[uuid.UUID, ...], tuple[float, int, Facts]] = {}
_CACHE_LOCK = threading.Lock()
_GENERATION = 0


# Writes that never change a KPI fact; the 30-second session heartbeat (deps.py) would
# otherwise invalidate every scope's cache on each request. No KPI reads the audit log, and
# reads are audited too (logins, sensitive medical reads in the 6a readiness behind the action
# panel), so an audit row must not invalidate the cache either.
_NO_KPI_TABLES = frozenset({"user_sessions", "gate_device_sessions", "audit_log"})


def _table_of(obj: Any) -> str | None:
    t = getattr(type(obj), "__tablename__", None)
    return t if isinstance(t, str) else None


def _mark_write(session: Session, *_: Any) -> None:
    rows = [*session.new, *session.dirty, *session.deleted]
    if not rows or any(_table_of(o) not in _NO_KPI_TABLES for o in rows):
        session.info["kpi_wrote"] = True


def _mark_statement(state: ORMExecuteState) -> None:
    if state.is_select:
        return
    if isinstance(state.statement, TextClause) and state.statement.text.lstrip()[:7].upper() == (
        "SELECT "
    ):
        return  # e.g. the audit chain's pg_advisory_xact_lock
    table = getattr(getattr(state.statement, "table", None), "name", None)
    if table not in _NO_KPI_TABLES:
        state.session.info["kpi_wrote"] = True


def _after_commit(session: Session) -> None:
    global _GENERATION  # noqa: PLW0603
    if session.info.pop("kpi_wrote", False):
        with _CACHE_LOCK:
            _GENERATION += 1
            _CACHE.clear()


event.listen(Session, "after_flush", _mark_write)
event.listen(Session, "do_orm_execute", _mark_statement)
event.listen(Session, "after_commit", _after_commit)


def clear_cache() -> None:
    from app.kpi import train_facts  # noqa: PLC0415

    with _CACHE_LOCK:
        _CACHE.clear()
    with train_facts._SHARED_LOCK:
        train_facts._SHARED.clear()


def load(
    db: Session,
    projects: Iterable[Project],
    hse: dict[uuid.UUID, HseSettings],
) -> Facts:
    """Facts for these projects, cached for `kpi_cache_seconds` (see Settings). The cached
    Facts are read-only for every consumer; the lazy access facts load at most once."""
    plist = list(projects)
    ttl = get_settings().kpi_cache_seconds
    if ttl <= 0:
        return _load(db, plist, hse)
    key = tuple(sorted(p.id for p in plist))
    hit = _cached(db, key, ttl)
    if hit is not None:
        return hit
    # Single flight: concurrent requests for the same scope (the dashboard fires the tiles and
    # every chart at once) wait for one build instead of each rebuilding the facts.
    with _flight(key, "base"):
        hit = _cached(db, key, ttl)
        if hit is not None:
            return hit
        at = time.monotonic()
        with _CACHE_LOCK:
            gen = _GENERATION
        facts = _load(db, plist, hse)
        with _CACHE_LOCK:
            if gen == _GENERATION:
                if len(_CACHE) > 64:
                    _CACHE.clear()
                _CACHE[key] = (at, gen, facts)
        return facts


def _cached(db: Session, key: tuple[uuid.UUID, ...], ttl: float) -> Facts | None:
    at = time.monotonic()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        gen = _GENERATION
    if hit is None or hit[1] != gen or at - hit[0] >= ttl:
        return None
    shared = hit[2]
    facts = copy.copy(shared)  # own lazy loader on this request's session
    if shared._access is None:
        facts.access_loader = _access_loader(db, key, shared)
    if shared._ptw is None:
        facts.ptw_loader = _ptw_loader(db, key, shared)
    if shared._cert is None:
        facts.cert_loader = _cert_loader(db, key, shared)
    if shared._train is None:
        facts.train_loader = _train_loader(db, key, shared)
    else:
        facts._train = shared._train.with_db(db)
    if shared._med is None:
        facts.med_loader = _med_loader(db, key, shared)
    else:
        facts._med = shared._med.with_db(db)
    facts._heat = None  # per request (own session)
    facts.heat_loader = _heat_loader(db, key)
    return facts


_FLIGHTS: dict[tuple[tuple[uuid.UUID, ...], str], threading.RLock] = {}


def _flight(key: tuple[uuid.UUID, ...], part: str) -> threading.RLock:
    with _CACHE_LOCK:
        if len(_FLIGHTS) > 512:
            _FLIGHTS.clear()
        return _FLIGHTS.setdefault((key, part), threading.RLock())


def _lazy(db: Session, pids: tuple[uuid.UUID, ...], shared: Facts, part: str, fn: Any) -> Any:
    """A lazy fact section loaded once per shared Facts, other requests waiting for it."""

    def run() -> Any:
        with _flight(pids, part):
            cur = getattr(shared, f"_{part}")
            if cur is not None:
                return cur
            val = fn(db, list(pids))
            setattr(shared, f"_{part}", val)
            return val

    return run


def _access_loader(db: Session, pids: tuple[uuid.UUID, ...], shared: Facts) -> Any:
    return _lazy(db, pids, shared, "access", load_access)


def _ptw_loader(db: Session, pids: tuple[uuid.UUID, ...], shared: Facts) -> Any:
    from app.kpi.ptw_facts import load_ptw  # noqa: PLC0415

    return _lazy(db, pids, shared, "ptw", load_ptw)


def _cert_loader(db: Session, pids: tuple[uuid.UUID, ...], shared: Facts) -> Any:
    from app.kpi.cert_facts import load_cert  # noqa: PLC0415

    return _lazy(db, pids, shared, "cert", load_cert)


def _med_loader(db: Session, pids: tuple[uuid.UUID, ...], shared: Facts) -> Any:
    from app.kpi.medical import load_med  # noqa: PLC0415

    def run() -> Any:
        with _flight(pids, "med"):
            cur = shared._med
            if cur is None:
                cur = load_med(db, list(pids))
                shared._med = cur
            return cur.with_db(db)

    return run


def _heat_loader(db: Session, pids: tuple[uuid.UUID, ...]) -> Any:
    def run() -> Any:
        from app.kpi.heat import load_heat  # noqa: PLC0415

        return load_heat(db, list(pids))

    return run


def _train_loader(db: Session, pids: tuple[uuid.UUID, ...], shared: Facts) -> Any:
    from app.kpi.train_facts import load_train  # noqa: PLC0415

    def run() -> Any:
        with _flight(pids, "train"):
            cur = shared._train
            if cur is None:
                cur = load_train(db, list(pids), shared)
                shared._train = cur
            return cur.with_db(db)

    return run


def _load(
    db: Session,
    projects: Iterable[Project],
    hse: dict[uuid.UUID, HseSettings],
) -> Facts:
    plist = list(projects)
    pids = [p.id for p in plist]
    tz = {p.id: ZoneInfo(p.settings.timezone if p.settings else "Asia/Riyadh") for p in plist}
    facts = Facts(project_start=min((p.start_date for p in plist), default=None))

    # engagements & zones
    for e in db.scalars(select(ProjectEngagement).where(ProjectEngagement.project_id.in_(pids))):
        facts.engagements[e.id] = EngFact(
            id=e.id,
            code=e.contractor.short_code,
            name_en=e.contractor.legal_name_en,
            name_ar=e.contractor.legal_name_ar,
            tier=e.tier,
            parent=e.parent_engagement_id,
            site_ids=frozenset(e.site_ids or []),
            mobilisation=e.mobilisation_date,
            demobilisation=e.demobilisation_date,
            contractor_id=e.contractor_id,
            project=e.project_id,
        )
    for z in db.scalars(select(Zone).where(Zone.project_id.in_(pids))):
        facts.zones[z.id] = ZoneFact(
            z.id,
            z.site_id,
            z.zone_type.value,
            z.airside_area.value if z.airside_area else None,
            z.code,
        )

    # workforce (aggregated)
    W = WorkforceReturn  # noqa: N806
    wf_rows = db.execute(
        select(
            W.project_id,
            W.work_date,
            W.engagement_id,
            W.site_id,
            W.zone_id,
            W.shift,
            func.sum(W.man_hours),
            func.sum(W.headcount),
            func.sum(W.toolbox_talks),
            func.sum(W.toolbox_attendees),
            func.sum(W.inductions),
            func.sum(W.training_hours),
            func.bool_or(or_(W.no_work.is_(True), W.headcount > 0)),
            func.array_agg(W.id),
        )
        .where(W.project_id.in_(pids), W.status.in_(COUNTED_RETURN))
        .group_by(W.project_id, W.work_date, W.engagement_id, W.site_id, W.zone_id, W.shift)
    ).all()
    facts.wf = [
        WfFact(
            d=r[1],
            eng=r[2],
            site=r[3],
            zone=r[4],
            mh=Decimal(r[6] or 0),
            hc=int(r[7] or 0),
            tbt=int(r[8] or 0),
            tbt_att=int(r[9] or 0),
            ind=int(r[10] or 0),
            trn=Decimal(r[11] or 0),
            reported=bool(r[12]),
            project=r[0],
            ids=tuple(r[13]),
            shift=r[5].value,
        )
        for r in wf_rows
    ]

    # v1.1 K-38: from induction_register_from the passed general_site induction records replace
    # the daily-return inductions (KA-2)
    reg_from: dict[uuid.UUID, date] = {}
    for pid in pids:
        rf = hse[pid].induction_register_from if pid in hse else None
        if rf is not None:
            reg_from[pid] = rf
    if reg_from:
        facts.wf = [
            replace(r, ind=0)
            if r.project in reg_from and r.d >= reg_from[r.project] and r.ind
            else r
            for r in facts.wf
        ]
        ind_rows = db.execute(
            select(
                InductionRecord.project_id,
                InductionRecord.delivered_on,
                InductionRecord.engagement_id,
                Deployment.site_ids,
            )
            .join(Deployment, Deployment.id == InductionRecord.deployment_id)
            .where(
                InductionRecord.project_id.in_(list(reg_from)),
                InductionRecord.induction_type == InductionType.general_site,
                InductionRecord.result == InductionResult.passed,
            )
        ).all()
        facts.inds = [
            IndFact(d=r[1], eng=r[2], site=r[3][0] if r[3] else None, project=r[0])
            for r in ind_rows
            if r[1] >= reg_from[r[0]]
        ]

    _toolbox_register(db, facts, pids)

    # 5-training TH-6: from training_register_from the register replaces the daily-return
    # training_hours (kept in trn_reg for the TH-7 reconciliation)
    facts.train_from = {
        pid: rf
        for pid in pids
        if pid in hse and (rf := hse[pid].training_register_from) is not None
    }
    if facts.train_from:
        tf = facts.train_from
        facts.wf = [
            replace(r, trn=Decimal(0), trn_reg=r.trn)
            if r.project in tf and r.d >= tf[r.project] and r.trn
            else r
            for r in facts.wf
        ]

    # incidents (counted events) + their investigation attributes
    inc_rows = db.execute(
        select(Incident, Investigation.root_causes, Investigation.ptw_involved)
        .outerjoin(Investigation, Investigation.incident_id == Incident.id)
        .where(Incident.project_id.in_(pids), Incident.status.not_in(EXCLUDED_INCIDENT))
    ).all()
    inv_attrs: dict[uuid.UUID, tuple[tuple[str, ...], bool | None]] = {}
    for inc, rcs, ptw in inc_rows:
        codes = tuple(str(rc.get("code")) for rc in (rcs or []) if rc.get("code"))
        inv_attrs[inc.id] = (codes, ptw)
        if not inc.work_related:
            continue
        local = inc.occurred_at.astimezone(tz[inc.project_id])
        facts.events.append(
            EventFact(
                id=inc.id,
                ref=inc.ref,
                d=inc.occurred_date,
                eng=inc.responsible_engagement_id,
                site=inc.site_id,
                zone=inc.zone_id,
                types=frozenset(inc.incident_types or []),
                hipo=inc.hipo,
                late=inc.late_report,
                pd_cost=Decimal(inc.pd_estimated_cost_sar or 0),
                project=inc.project_id,
                hour=local.hour,
                shift=inc.shift.value if inc.shift else None,
                activity=inc.activity.value if inc.activity else None,
                ptw_involved=ptw,
                root_causes=codes,
                airside_flags=tuple(inc.airside_flags or []),
                title=inc.title,
            )
        )

    # injury cases (all non-draft/void incidents; eligibility decided here)
    case_rows = db.execute(
        select(InjuryCase, Incident)
        .join(Incident, Incident.id == InjuryCase.incident_id)
        .where(InjuryCase.project_id.in_(pids), Incident.status.not_in(EXCLUDED_INCIDENT))
    ).all()
    for c, inc in case_rows:
        s = hse[inc.project_id]
        eligible, _ = case_eligible(inc, c, s)
        local = inc.occurred_at.astimezone(tz[inc.project_id])
        codes, ptw = inv_attrs.get(inc.id, ((), None))
        facts.cases.append(
            CaseFact(
                id=c.id,
                incident_id=inc.id,
                incident_ref=inc.ref,
                d=inc.occurred_date,
                eng=c.employer_engagement_id,
                site=inc.site_id,
                zone=inc.zone_id,
                category=c.category,
                dates=CaseDates(
                    injury_date=inc.occurred_date,
                    away_start_date=c.away_start_date,
                    rtw_date=c.rtw_date,
                    restricted_start=c.restricted_start,
                    restricted_end=c.restricted_end,
                    transfer_start=c.transfer_start,
                    transfer_end=c.transfer_end,
                ),
                eligible=eligible,
                provisional=c.classification_status.value == "provisional",
                fatal=c.fatal,
                permanent=c.permanent_disability,
                cap=s.lost_days_cap,
                fatality_charge=s.fatality_lost_days_charge,
                project=inc.project_id,
                hour=local.hour,
                shift=inc.shift.value if inc.shift else None,
                activity=inc.activity.value if inc.activity else None,
                mechanism=c.mechanism.value,
                agency=c.agency.value,
                body_part=c.body_part.value,
                nature=c.nature.value,
                trade=c.trade.value,
                age_band=c.age_band.value if c.age_band else None,
                nationality=c.nationality,
                days_on_site=(inc.occurred_date - c.site_start_date).days
                if c.site_start_date
                else None,
                ptw_involved=ptw,
                root_causes=codes,
                person_no=c.person_no,
            )
        )

    # observations (aggregated)
    O = Observation  # noqa: E741, N806
    closed = case((O.status == ObservationStatus.closed, O.closed_date), else_=None)
    obs_rows = db.execute(
        select(
            O.project_id,
            O.observed_date,
            O.observed_engagement_id,
            O.site_id,
            O.zone_id,
            O.obs_type,
            closed,
            O.category,
            O.risk_rating,
            func.count(),
            func.array_agg(O.id),
        )
        .where(O.project_id.in_(pids))
        .group_by(
            O.project_id,
            O.observed_date,
            O.observed_engagement_id,
            O.site_id,
            O.zone_id,
            O.obs_type,
            closed,
            O.category,
            O.risk_rating,
        )
    ).all()
    facts.obs = [
        ObsFact(
            d=r[1],
            eng=r[2],
            site=r[3],
            zone=r[4],
            obs_type=r[5].value,
            safe=r[5].value in SAFE_TYPES,
            closed_date=r[6],
            n=int(r[9]),
            category=r[7].value,
            risk=r[8].value if r[8] else None,
            project=r[0],
            ids=tuple(r[10]),
        )
        for r in obs_rows
    ]

    # inspections
    I = Inspection  # noqa: E741, N806
    for row in db.execute(
        select(
            I.id,
            I.planned_date,
            I.completed_date,
            I.status,
            I.engagement_id,
            I.site_id,
            I.zone_id,
            I.inspection_type,
            I.project_id,
        ).where(I.project_id.in_(pids), I.status != InspectionStatus.voided)  # 6d SRC-1
    ):
        facts.insp.append(
            InspFact(
                id=row[0],
                planned=row[1],
                completed=row[2],
                cancelled=row[3] == InspectionStatus.cancelled,
                eng=row[4],
                site=row[5],
                zone=row[6],
                grace=hse[row[8]].inspection_grace_days,
                inspection_type=row[7].value,
                project=row[8],
            )
        )

    # corrective actions
    A = CorrectiveAction  # noqa: N806
    for ca_row in db.execute(
        select(
            A.id,
            A.created_date,
            A.due_date,
            A.status,
            A.control_level,
            A.responsible_engagement_id,
            A.site_id,
            A.zone_id,
            A.completed_date,
            A.verified_date,
            A.cancelled_date,
            A.priority,
            A.source_type,
            A.project_id,
        ).where(A.project_id.in_(pids))
    ):
        status = ca_row[3]
        facts.cas.append(
            CaFact(
                id=ca_row[0],
                created=ca_row[1],
                due=ca_row[2],
                status=status,
                control=ca_row[4],
                eng=ca_row[5],
                site=ca_row[6],
                zone=ca_row[7],
                completed=ca_row[8],
                verified=ca_row[9] if status == CaStatus.closed else None,
                cancelled=(ca_row[10] or ca_row[1]) if status == CaStatus.cancelled else None,
                priority=ca_row[11].value,
                source_type=ca_row[12].value,
                project=ca_row[13],
            )
        )

    # meetings
    for m in db.scalars(select(HseMeeting).where(HseMeeting.project_id.in_(pids))):
        facts.meetings.append(
            MeetingFact(
                m.id,
                m.planned_date,
                m.held_date,
                m.invited_count,
                m.attended_count,
                m.engagement_id,
                m.project_id,
            )
        )
    facts.access_loader = _access_loader(db, tuple(sorted(pids)), facts)
    facts.ptw_loader = _ptw_loader(db, tuple(sorted(pids)), facts)
    facts.cert_loader = _cert_loader(db, tuple(sorted(pids)), facts)
    facts.train_loader = _train_loader(db, tuple(sorted(pids)), facts)
    facts.med_loader = _med_loader(db, tuple(sorted(pids)), facts)
    facts.heat_loader = _heat_loader(db, tuple(sorted(pids)))
    return facts.sort()


def restated_months(db: Session, project_ids: Iterable[uuid.UUID]) -> list[date]:
    return sorted(
        set(
            db.scalars(
                select(PeriodLock.month).where(
                    PeriodLock.project_id.in_(list(project_ids)), PeriodLock.restated.is_(True)
                )
            ).all()
        )
    )


def snapshot_hash(parts: Iterable[object]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode())
        h.update(b"\x1f")
    return h.hexdigest()


def _toolbox_register(db: Session, facts: Facts, pids: list[uuid.UUID]) -> None:
    """6d SRC-2: from toolbox_register_from the register replaces the daily-return toolbox_talks /
    toolbox_attendees (kept on the WfFact as tbt_dr / tbt_att_dr for the SRC-3 reconciliation)."""
    from app.core.field_enums import TalkStatus  # noqa: PLC0415
    from app.models import FieldSettings, TalkAttendance, ToolboxTalk  # noqa: PLC0415

    reg: dict[uuid.UUID, date] = {
        r[0]: r[1]
        for r in db.execute(
            select(FieldSettings.project_id, FieldSettings.toolbox_register_from).where(
                FieldSettings.project_id.in_(pids),
                FieldSettings.toolbox_register_from.is_not(None),
            )
        )
        if r[1] is not None
    }
    if not reg:
        return
    facts.tbt_from = dict(reg)
    facts.wf = [
        replace(r, tbt=0, tbt_att=0, tbt_dr=r.tbt, tbt_att_dr=r.tbt_att)
        if r.project in reg and r.d >= reg[r.project] and (r.tbt or r.tbt_att)
        else r
        for r in facts.wf
    ]
    T = ToolboxTalk  # noqa: N806
    named = dict(
        db.execute(
            select(TalkAttendance.talk_id, func.count())
            .join(T, T.id == TalkAttendance.talk_id)
            .where(
                T.project_id.in_(list(reg)),
                TalkAttendance.counted_person_type == "contractor_worker",
            )
            .group_by(TalkAttendance.talk_id)
        ).all()
    )
    facts.tbts = [
        TbtFact(d=r[1], eng=r[2], site=r[3], project=r[0], att=int(named.get(r[4], 0)) + r[5])
        for r in db.execute(
            select(
                T.project_id, T.delivered_date, T.host_engagement_id, T.site_id, T.id,
                T.unnamed_count,
            ).where(
                T.project_id.in_(list(reg)),
                T.status.in_((TalkStatus.delivered, TalkStatus.locked)),
            )
        )
        if r[1] >= reg[r[0]]
    ]  # fmt: skip
