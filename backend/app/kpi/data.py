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


def _mark_write(session: Session, *_: Any) -> None:
    session.info["kpi_wrote"] = True


def _mark_statement(state: ORMExecuteState) -> None:
    if not state.is_select:
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
    with _CACHE_LOCK:
        _CACHE.clear()


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
    at = time.monotonic()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        gen = _GENERATION
    if hit is not None and hit[1] == gen and at - hit[0] < ttl:
        shared = hit[2]
        facts = copy.copy(shared)  # own lazy loader on this request's session
        if shared._access is None:
            facts.access_loader = _access_loader(db, key, shared)
        if shared._ptw is None:
            facts.ptw_loader = _ptw_loader(db, key, shared)
        return facts
    facts = _load(db, plist, hse)
    with _CACHE_LOCK:
        if gen == _GENERATION:
            if len(_CACHE) > 64:
                _CACHE.clear()
            _CACHE[key] = (at, gen, facts)
    return facts


def _access_loader(db: Session, pids: tuple[uuid.UUID, ...], shared: Facts) -> Any:
    def run() -> Any:
        acc = load_access(db, list(pids))
        shared.access = acc
        return acc

    return run


def _ptw_loader(db: Session, pids: tuple[uuid.UUID, ...], shared: Facts) -> Any:
    def run() -> Any:
        from app.kpi.ptw_facts import load_ptw  # noqa: PLC0415

        pf = load_ptw(db, list(pids))
        shared.ptw = pf
        return pf

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
        ).where(I.project_id.in_(pids))
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
    facts.access_loader = lambda: load_access(db, pids)
    facts.ptw_loader = _ptw_loader(db, tuple(pids), facts)
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
