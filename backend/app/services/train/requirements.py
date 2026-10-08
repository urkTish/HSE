"""Requirement engine (spec 5-training §3.10, §6.2, MX-4…MX-6, MX-10, CC-6, CC-7).

Computed on read for any as_of from the matrix versions, the training-profile history,
deployments, Phase 2 credentials and records. One pass loads everything a project needs, so the
gap register, the KPIs (K-82…K-85) and a single deployment's competence profile share it."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    DeploymentStatus,
    InductionResult,
    InductionType,
    ValidityStatus,
    WorkerPersonType,
)
from app.core.cert_enums import HookReasonCode
from app.core.ptw_enums import PERMIT_TERMINAL, AppointmentStatus, CrewLineStatus
from app.core.train_enums import (
    CourseCategory,
    ExemptionStatus,
    MatrixAppliesTo,
    MatrixLevel,
    MatrixLineSource,
    RequirementState,
    SessionStatus,
)
from app.models import (
    Adp,
    AirportPass,
    Deployment,
    InductionCourse,
    InductionRecord,
    Permit,
    PermitCrew,
    PtwAppointment,
    TrainingExemption,
    TrainingMatrixLine,
    TrainingNomination,
    TrainingProfile,
    TrainingRecord,
    TrainingSession,
    Worker,
)
from app.services.access import common as acommon
from app.services.train import common
from app.services.train import hook as thook
from app.services.train import reference as ref
from app.services.train import validity as v

A = MatrixAppliesTo
RS = RequirementState
IND_OK = thook.IND_OK
EXPIRING_DAYS = 30


# ---- matrix lines at a date --------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    row: TrainingMatrixLine
    since: date  # first effective_from of this requirement on the line (MX-5)

    @property
    def key(self) -> str:
        return req_key(self.row.course_code, self.row.any_of)

    @property
    def codes(self) -> tuple[str, ...]:
        r = self.row
        return (r.course_code,) if r.course_code else tuple(r.any_of or ())

    @property
    def enforcement(self) -> bool:
        return self.row.applies_to_kind in (A.crew_role, A.appointment_function)


def req_key(course_code: str | None, any_of: Iterable[str] | None) -> str:
    if course_code:
        return course_code
    return "any:" + ",".join(sorted(any_of or ()))


def lines_at(db: Session, project_id: uuid.UUID, d: date) -> list[Line]:
    rows = list(
        db.scalars(
            select(TrainingMatrixLine).where(
                TrainingMatrixLine.project_id == project_id,
                TrainingMatrixLine.effective_from <= d,
            )
        )
    )
    by_line: dict[uuid.UUID, list[TrainingMatrixLine]] = defaultdict(list)
    for r in rows:
        by_line[r.line_id].append(r)
    out = []
    for versions in by_line.values():
        cur = next(
            (x for x in versions if x.effective_to is None or x.effective_to >= d),
            None,
        )
        if cur is None:
            continue
        k = req_key(cur.course_code, cur.any_of)
        since = min(x.effective_from for x in versions if req_key(x.course_code, x.any_of) == k)
        out.append(Line(cur, since))
    out.sort(key=lambda x: x.row.line_no)
    return out


# ---- result rows -------------------------------------------------------------------------------


@dataclass
class Req:
    dep: Deployment
    key: str
    codes: tuple[str, ...]
    lines: list[Line]
    level: MatrixLevel
    kpi_counted: bool
    hook_code: bool
    critical: bool
    applies_from: date
    due_date: date
    state: RS = RS.gap
    counted: bool = False
    record: TrainingRecord | None = None
    valid_until: date | None = None
    induction: InductionRecord | None = None
    exemption_id: uuid.UUID | None = None
    reason: HookReasonCode | None = None
    booked: TrainingSession | None = None

    @property
    def line_nos(self) -> list[str]:
        return [ln.row.line_no for ln in self.lines]

    @property
    def course_code(self) -> str | None:
        return self.codes[0] if len(self.codes) == 1 and not self.key.startswith("any:") else None


@dataclass
class Facts:
    """Everything loaded for one project at one date."""

    project_id: uuid.UUID
    d: date
    lines: list[Line]
    deps: list[Deployment]
    workers: dict[uuid.UUID, Worker]
    roles: dict[uuid.UUID, dict[str, date]]  # deployment → matrix role → since
    zones: dict[uuid.UUID, dict[str, date]]  # deployment → zone id (str) → since
    passes: dict[uuid.UUID, dict[str, date]]  # worker → pass category → since
    adps: dict[uuid.UUID, dict[str, date]]  # worker → ADP category → since
    exemptions: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID]  # (dep, line) → exemption id
    records: dict[uuid.UUID, list[TrainingRecord]]
    inductions: dict[uuid.UUID, list[tuple[InductionRecord, str]]]  # worker → (record, course)
    ctx: v.EvalCtx
    hook_codes: set[str]
    critical: set[str]
    enforcement: dict[uuid.UUID, dict[str, date]] = field(default_factory=dict)
    bookings: dict[uuid.UUID, list[tuple[TrainingNomination, TrainingSession]]] = field(
        default_factory=dict
    )


def _active_cred(c: Any, d: date) -> bool:
    """Phase 2 pass / ADP active at d (suspended counts as not active, DECISIONS)."""
    if c.issued_on is None or c.issued_on > d:
        return False
    if c.validity_status in (ValidityStatus.pending, ValidityStatus.withdrawn):
        return False
    if c.validity_status == ValidityStatus.suspended:
        return False
    if c.effective_valid_until is not None and c.effective_valid_until < d:
        return False
    if c.revoked_at is not None and acommon.local_day(c.revoked_at) <= d:
        return False
    return not (c.expired_on is not None and c.expired_on <= d)


def _history_since(
    history: list[dict[str, Any]], fld: str, d: date, current: list[str], created: date
) -> dict[str, date]:
    """MX-9: values of `fld` at d with the date each value started to apply (a value kept
    across consecutive history rows keeps its first start)."""
    rows = [h for h in history or [] if h.get("field") == fld]
    if not rows:
        return {str(x): created for x in current} if created <= d else {}
    spans = []
    for h in rows:
        f = date.fromisoformat(h["from_date"])
        t = date.fromisoformat(h["to_date"]) if h.get("to_date") else None
        if t is not None and t < f:
            continue
        spans.append((f, t, {str(x) for x in h.get("value") or []}))
    spans.sort(key=lambda x: x[0])
    idx = next((i for i, (f, t, _) in enumerate(spans) if f <= d and (t is None or t >= d)), None)
    if idx is None:
        return {}
    out: dict[str, date] = {}
    for x in spans[idx][2]:
        since = spans[idx][0]
        j = idx - 1
        while j >= 0 and x in spans[j][2]:
            pt = spans[j][1]
            if pt is not None and pt < since - timedelta(days=1):
                break
            since = spans[j][0]
            j -= 1
        out[x] = since
    return out


def project_hook_codes(db: Session, project_id: uuid.UUID) -> set[str]:
    """HK5-2 first list plus codes of the project's hook-derived lines."""
    codes = set(ref.HOOK_CODES_TODAY)
    for r in db.scalars(
        select(TrainingMatrixLine).where(
            TrainingMatrixLine.project_id == project_id,
            TrainingMatrixLine.source == MatrixLineSource.hook,
            TrainingMatrixLine.effective_to.is_(None),
        )
    ):
        if r.course_code:
            codes.add(r.course_code)
    return codes


@dataclass
class Base:
    """Date-independent rows of one project, loaded once and reused for several dates by the
    read-only KPI engine (sparklines evaluate the same project at many dates)."""

    deps: list[Deployment]
    workers: dict[uuid.UUID, Worker]
    records: dict[uuid.UUID, list[TrainingRecord]]
    bookings: list[tuple[TrainingNomination, TrainingSession]]


def load_base(db: Session, project_id: uuid.UUID) -> Base:
    deps = list(db.scalars(select(Deployment).where(Deployment.project_id == project_id)))
    wids = {x.worker_id for x in deps}
    workers = {w.id: w for w in _chunked(db, Worker, Worker.id, wids)}
    records: dict[uuid.UUID, list[TrainingRecord]] = defaultdict(list)
    for r in _chunked(db, TrainingRecord, TrainingRecord.worker_id, wids):
        records[r.worker_id].append(r)
    bookings = [
        (n, s)
        for n, s in db.execute(
            select(TrainingNomination, TrainingSession)
            .join(TrainingSession, TrainingSession.id == TrainingNomination.session_id)
            .where(TrainingSession.scheduled_at.is_not(None))
        ).all()
        if n.worker_id in wids
    ]
    return Base(deps, workers, records, bookings)


def load(
    db: Session,
    project_id: uuid.UUID,
    d: date,
    deployment_ids: Iterable[uuid.UUID] | None = None,
    worker_ids: Iterable[uuid.UUID] | None = None,
    mobilised_only: bool = True,
    enforcement: bool = False,
    bookings: bool = False,
    base: Base | None = None,
) -> Facts:
    lines = lines_at(db, project_id, d)
    if not lines and base is not None and deployment_ids is None and worker_ids is None:
        # no matrix line in force at d (e.g. KPI sparkline months before the matrix existed):
        # nothing to evaluate, so skip loading deployments, records and bookings
        s0 = common.settings(db, project_id)
        return Facts(
            project_id=project_id, d=d, lines=[], deps=[], workers={}, roles={}, zones={},
            passes={}, adps={}, exemptions={}, records={}, inductions={},
            ctx=v.EvalCtx(courses=common.courses(db), settings=s0, providers=thook.providers(db)),
            hook_codes=project_hook_codes(db, project_id), critical=common.critical_codes(s0),
        )  # fmt: skip
    if base is not None and deployment_ids is None and worker_ids is None:
        all_deps: list[Deployment] = base.deps
    else:
        base = None
        q = select(Deployment).where(Deployment.project_id == project_id)
        if deployment_ids is not None:
            q = q.where(Deployment.id.in_(list(deployment_ids)))
        if worker_ids is not None:
            q = q.where(Deployment.worker_id.in_(list(worker_ids)))
        all_deps = list(db.scalars(q))
    deps = [
        x
        for x in all_deps
        if not mobilised_only
        or common.mobilised_on(x, d)
        or (deployment_ids is not None and x.status != DeploymentStatus.demobilised)
    ]
    wids = {x.worker_id for x in deps}
    dids = [x.id for x in deps]
    if base is not None:
        workers = {w: base.workers[w] for w in wids if w in base.workers}
    else:
        workers = {w.id: w for w in _chunked(db, Worker, Worker.id, wids)}
    roles: dict[uuid.UUID, dict[str, date]] = {}
    zones: dict[uuid.UUID, dict[str, date]] = {}
    kinds = {ln.row.applies_to_kind for ln in lines}
    if kinds & {A.matrix_role, A.zone}:
        for pr in _chunked(db, TrainingProfile, TrainingProfile.deployment_id, dids):
            created = acommon.local_day(pr.created_at) if pr.created_at else d
            roles[pr.deployment_id] = _history_since(
                pr.history, "matrix_roles", d, list(pr.matrix_roles or []), created
            )
            zones[pr.deployment_id] = _history_since(
                pr.history, "work_zone_ids", d, [str(z) for z in pr.work_zone_ids or []], created
            )
    passes: dict[uuid.UUID, dict[str, date]] = defaultdict(dict)
    adps: dict[uuid.UUID, dict[str, date]] = defaultdict(dict)
    if A.pass_category in kinds:
        for ap in db.scalars(select(AirportPass).where(AirportPass.project_id == project_id)):
            if ap.worker_id in wids and _active_cred(ap, d):
                cur = passes[ap.worker_id].get(ap.pass_category)
                passes[ap.worker_id][ap.pass_category] = min(cur or ap.issued_on, ap.issued_on)
    if A.adp_category in kinds:
        for adp in db.scalars(select(Adp).where(Adp.project_id == project_id)):
            if adp.worker_id in wids and adp.issued_on is not None and _active_cred(adp, d):
                cat = adp.category.value
                cur = adps[adp.worker_id].get(cat)
                adps[adp.worker_id][cat] = min(cur or adp.issued_on, adp.issued_on)
    exemptions: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    for ex in db.scalars(
        select(TrainingExemption).where(
            TrainingExemption.project_id == project_id,
            TrainingExemption.valid_from <= d,
            TrainingExemption.valid_until >= d,
        )
    ):
        if ex.status == ExemptionStatus.withdrawn and (
            ex.withdrawn_at is None or acommon.local_day(ex.withdrawn_at) <= d
        ):
            continue
        exemptions[(ex.deployment_id, ex.line_id)] = ex.id
    records: dict[uuid.UUID, list[TrainingRecord]] = defaultdict(list)
    if base is not None:
        for w in wids:
            if w in base.records:
                records[w] = base.records[w]
    else:
        for r in _chunked(db, TrainingRecord, TrainingRecord.worker_id, wids):
            records[r.worker_id].append(r)
    inductions: dict[uuid.UUID, list[tuple[InductionRecord, str]]] = defaultdict(list)
    courses = common.courses(db)
    if any(
        courses.get(c) is not None and courses[c].category == CourseCategory.induction_link
        for ln in lines
        for c in ln.codes
    ):
        rows = db.execute(
            select(InductionRecord, InductionCourse.code)
            .join(InductionCourse, InductionCourse.id == InductionRecord.course_id)
            .where(
                InductionRecord.project_id == project_id,
                InductionRecord.result == InductionResult.passed,
                InductionRecord.status.in_(IND_OK),
                or_(InductionRecord.valid_from.is_(None), InductionRecord.valid_from <= d),
                or_(InductionRecord.valid_until.is_(None), InductionRecord.valid_until >= d),
            )
        )
        for ir, code in rows:
            if ir.worker_id in wids:
                inductions[ir.worker_id].append((ir, code))
    s = common.settings(db, project_id)
    ctx = v.EvalCtx(courses=courses, settings=s, providers=thook.providers(db))
    f = Facts(
        project_id=project_id,
        d=d,
        lines=lines,
        deps=deps,
        workers=workers,
        roles=roles,
        zones=zones,
        passes=passes,
        adps=adps,
        exemptions=exemptions,
        records=records,
        inductions=inductions,
        ctx=ctx,
        hook_codes=project_hook_codes(db, project_id),
        critical=common.critical_codes(s),
    )
    if enforcement:
        f.enforcement = enforcement_keys(db, project_id, d, workers)
    if bookings:
        f.bookings = load_bookings(
            db, project_id, wids, d, base.bookings if base is not None else None
        )
    return f


def _chunked(db: Session, model: Any, col: Any, ids: Iterable[uuid.UUID]) -> list[Any]:
    ids = list(ids)
    out: list[Any] = []
    for i in range(0, len(ids), 5000):
        out.extend(db.scalars(select(model).where(col.in_(ids[i : i + 5000]))))
    return out


# ---- enforcement lines (MX-2) ------------------------------------------------------------------


def enforcement_keys(
    db: Session, project_id: uuid.UUID, d: date, workers: dict[uuid.UUID, Worker]
) -> dict[uuid.UUID, dict[str, date]]:
    """worker → hook keys that apply now: `crew:<type|*>:<role|*>` for non-terminal permit crews,
    `appointment:<function>` for Active appointments, `appointment:receiver` for receivers."""
    out: dict[uuid.UUID, dict[str, date]] = defaultdict(dict)
    by_user = {w.user_id: w.id for w in workers.values() if w.user_id}
    permits = {
        pm.id: pm
        for pm in db.scalars(
            select(Permit).where(
                Permit.project_id == project_id, Permit.status.notin_(list(PERMIT_TERMINAL))
            )
        )
    }
    for line in _chunked(db, PermitCrew, PermitCrew.permit_id, permits):
        if line.status == CrewLineStatus.removed or line.worker_id not in workers:
            continue
        pm = permits[line.permit_id]
        start = acommon.local_day(pm.valid_from_at)
        for t in pm.work_types or [pm.primary_type.value]:
            for k in (
                f"crew:{t}:{line.crew_role.value}",
                f"crew:*:{line.crew_role.value}",
                f"crew:{t}:*",
            ):
                out[line.worker_id].setdefault(k, start)
    for pm in permits.values():
        wid = by_user.get(pm.receiver_user_id)
        if wid is not None:
            out[wid].setdefault("appointment:receiver", acommon.local_day(pm.valid_from_at))
    for a in db.scalars(
        select(PtwAppointment).where(
            PtwAppointment.project_id == project_id,
            PtwAppointment.status == AppointmentStatus.active,
            PtwAppointment.valid_from <= d,
            PtwAppointment.valid_to >= d,
        )
    ):
        wid = a.holder_worker_id or (by_user.get(a.holder_user_id) if a.holder_user_id else None)
        if wid is not None and wid in workers:
            out[wid].setdefault(f"appointment:{a.function.value}", a.valid_from)
    return out


# ---- bookings (§6.7) ---------------------------------------------------------------------------


def _booking_rows(
    db: Session,
    worker_ids: Iterable[uuid.UUID],
    d: date,
    pre: list[tuple[TrainingNomination, TrainingSession]] | None,
) -> Iterable[tuple[TrainingNomination, TrainingSession]]:
    wids = list(worker_ids)
    if pre is not None:
        ws = set(wids)
        yield from ((n, s) for n, s in pre if s.last_day > d and n.worker_id in ws)
        return
    q = (
        select(TrainingNomination, TrainingSession)
        .join(TrainingSession, TrainingSession.id == TrainingNomination.session_id)
        .where(TrainingSession.last_day > d, TrainingSession.scheduled_at.is_not(None))
    )
    for i in range(0, len(wids), 5000):
        rows = db.execute(q.where(TrainingNomination.worker_id.in_(wids[i : i + 5000]))).all()
        yield from ((n, s) for n, s in rows)


def load_bookings(
    db: Session,
    project_id: uuid.UUID | None,
    worker_ids: Iterable[uuid.UUID],
    d: date,
    pre: list[tuple[TrainingNomination, TrainingSession]] | None = None,
) -> dict[uuid.UUID, list[tuple[TrainingNomination, TrainingSession]]]:
    """Nominations not withdrawn by d to sessions scheduled by d, not cancelled by d, whose last
    day is after d (i.e. Scheduled / In Progress at d)."""
    end = common.day_end_utc(d)
    out: dict[uuid.UUID, list[tuple[TrainingNomination, TrainingSession]]] = defaultdict(list)
    for n, s in _booking_rows(db, worker_ids, d, pre):
        if s.scheduled_at is None or s.scheduled_at > end or n.nominated_at > end:
            continue
        if s.status == SessionStatus.draft:
            continue
        if s.cancelled_at is not None and s.cancelled_at <= end:
            continue
        if s.voided_at is not None and s.voided_at <= end:
            continue
        if n.withdrawn_at is not None and n.withdrawn_at <= end:
            continue
        out[n.worker_id].append((n, s))
    return out


def booking_for(
    f: Facts, worker_id: uuid.UUID, codes: Iterable[str], valid_until: date | None
) -> tuple[TrainingSession | None, bool]:
    """(session, in_time): the earliest booked session of the code or its renewal course."""
    wanted = set(codes)
    for c in list(wanted):
        crs = f.ctx.courses.get(c)
        if crs is not None and crs.renewal_course_code:
            wanted.add(crs.renewal_course_code)
    best_s: TrainingSession | None = None
    for _n, s in f.bookings.get(worker_id, []):
        if s.course_code not in wanted:
            continue
        if best_s is None or s.last_day < best_s.last_day:
            best_s = s
    if best_s is None:
        return None, False
    return best_s, valid_until is None or best_s.last_day <= valid_until


# ---- evaluation --------------------------------------------------------------------------------


def _applies(f: Facts, ln: Line, dep: Deployment) -> date | None:
    """MX-4: the date the line began to apply to the deployment (None = not applicable)."""
    r = ln.row
    vals = set(r.applies_to_values or [])
    k = r.applies_to_kind
    if k == A.all_workers:
        return dep.mobilised_on
    if k == A.trade:
        return dep.mobilised_on if dep.trade.value in vals else None
    if k == A.matrix_role:
        got = [s for x, s in f.roles.get(dep.id, {}).items() if x in vals]
        return min(got) if got else None
    if k == A.zone:
        got = [s for x, s in f.zones.get(dep.id, {}).items() if x in vals]
        return min(got) if got else None
    if k == A.pass_category:
        got = [s for x, s in f.passes.get(dep.worker_id, {}).items() if x in vals]
        return min(got) if got else None
    if k == A.adp_category:
        got = [s for x, s in f.adps.get(dep.worker_id, {}).items() if x in vals]
        return min(got) if got else None
    if r.hook_key:
        mine = f.enforcement.get(dep.worker_id, {})
        hits = [mine[k] for k in r.hook_key.split("|") if k in mine]
        return min(hits) if hits else None
    return None


def evaluate_dep(f: Facts, dep: Deployment, include_enforcement: bool = False) -> list[Req]:
    """All de-duplicated requirements of one deployment at f.d (MX-6, §6.2)."""
    d = f.d
    groups: dict[str, list[tuple[Line, date]]] = defaultdict(list)
    for ln in f.lines:
        if ln.enforcement and not include_enforcement:
            continue
        since = _applies(f, ln, dep)
        if since is None:
            continue
        applies_from = max(dep.mobilised_on, ln.since, since)
        groups[ln.key].append((ln, applies_from))
    w = f.workers.get(dep.worker_id)
    contractor = w is not None and w.person_type == WorkerPersonType.contractor_worker
    mobilised = common.mobilised_on(dep, d)
    out: list[Req] = []
    for key, items in groups.items():
        lns = [x[0] for x in items]
        codes = lns[0].codes
        due_pairs = [(af + timedelta(days=ln.row.due_within_days), af) for ln, af in items]
        due_date, applies_from = min(due_pairs)
        mandatory = [ln for ln in lns if ln.row.level == MatrixLevel.mandatory]
        kpi = any(ln.row.kpi_counted and not ln.enforcement for ln in mandatory)
        req = Req(
            dep=dep,
            key=key,
            codes=codes,
            lines=lns,
            level=MatrixLevel.mandatory if mandatory else MatrixLevel.recommended,
            kpi_counted=any(ln.row.kpi_counted for ln in lns),
            hook_code=any(c in ref.HOOK_CODES_TODAY for c in codes),
            critical=any(c in f.critical for c in codes),
            applies_from=applies_from,
            due_date=due_date,
        )
        ex = next((f.exemptions[(dep.id, ln.row.line_id)] for ln in lns
                   if (dep.id, ln.row.line_id) in f.exemptions), None)  # fmt: skip
        _satisfy(f, req, dep.worker_id)
        if ex is not None:
            req.state = RS.exempt
            req.exemption_id = ex
        elif req.state in (RS.met, RS.expiring):
            pass
        elif d < due_date:
            req.state = RS.due
        else:
            req.state = RS.gap
        req.counted = (
            kpi and contractor and mobilised and req.state in (RS.met, RS.expiring, RS.gap)
        )
        if f.bookings:
            req.booked, _ = booking_for(f, dep.worker_id, codes, req.valid_until)
        out.append(req)
    out.sort(key=lambda r: (r.line_nos[0] if r.line_nos else "", r.key))
    return out


def _satisfy(f: Facts, req: Req, worker_id: uuid.UUID) -> None:
    d = f.d
    courses = f.ctx.courses
    best_vu: date | None = None
    found = False
    reason: HookReasonCode | None = None
    for code in req.codes:
        c = courses.get(code)
        if c is not None and c.category == CourseCategory.induction_link:
            ir = _induction(f, worker_id, c)
            if ir is not None:
                vu = ir.valid_until
                if not found or (vu or date.max) > (best_vu or date.max):
                    req.induction, req.record, best_vu, found = ir, None, vu, True
            else:
                reason = reason or HookReasonCode.INDUCTION_NOT_VALID
            continue
        sat: list[str] = []
        for x in common_satisfiers(courses, code):
            sat.append(x)
        b = v.best(f.records.get(worker_id, []), sat, d, f.ctx)
        if b.met:
            vu = b.valid_until
            if not found or (vu or date.max) > (best_vu or date.max):
                req.record, req.induction, best_vu, found = b.record, None, vu, True
        elif reason is None or reason == HookReasonCode.TRAINING_MISSING:
            reason = b.reason
            if req.record is None and not found:
                req.record = b.record
    if found:
        req.valid_until = best_vu
        req.reason = None
        expiring = best_vu is not None and best_vu <= d + timedelta(days=EXPIRING_DAYS)
        req.state = RS.expiring if expiring else RS.met
    else:
        req.reason = reason or HookReasonCode.TRAINING_MISSING
        req.state = RS.gap


def common_satisfiers(courses: dict[str, Any], code: str) -> list[str]:
    out = [code]
    for c in courses.values():
        if code in (c.satisfies or []) and c.code not in out:
            out.append(c.code)
    return out


def _induction(f: Facts, worker_id: uuid.UUID, c: Any) -> InductionRecord | None:
    mapped = (c.induction_project_codes or {}).get(str(f.project_id))
    best_r: InductionRecord | None = None
    for ir, code in f.inductions.get(worker_id, []):
        if c.induction_type and ir.induction_type != InductionType(c.induction_type):
            continue
        if mapped and code != mapped:
            continue
        if best_r is None or (ir.valid_until or date.max) > (best_r.valid_until or date.max):
            best_r = ir
    return best_r


# ---- project-level summaries -------------------------------------------------------------------


@dataclass
class ProjectEval:
    f: Facts
    reqs: list[Req]

    @property
    def counted(self) -> list[Req]:
        return [r for r in self.reqs if r.counted]


def evaluate_project(
    db: Session,
    project_id: uuid.UUID,
    d: date,
    engagement_ids: set[uuid.UUID] | None = None,
    bookings: bool = False,
    enforcement: bool = False,
    mobilised_only: bool = True,
    base: Base | None = None,
) -> ProjectEval:
    f = load(
        db,
        project_id,
        d,
        bookings=bookings,
        enforcement=enforcement,
        mobilised_only=mobilised_only,
        base=base,
    )
    reqs: list[Req] = []
    for dep in f.deps:
        if engagement_ids is not None and dep.engagement_id not in engagement_ids:
            continue
        reqs.extend(evaluate_dep(f, dep, include_enforcement=enforcement))
    return ProjectEval(f, reqs)


def at_noon(d: date) -> datetime:
    return acommon.local_midnight_utc(d) + timedelta(hours=12)
