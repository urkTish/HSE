"""Medical requirement engine (spec 6a-occupational-health §3.4, §6.3, MR-2…MR-4, WP-1).

Computed on read for any as_of from the plan versions, health profiles, deployments, Phase 2
ADPs and the HK6-6 check, so the requirements view, the gap register and the KPIs (K-89…K-96)
share one implementation (MK-1). Deployments without a stored health profile get the trade
defaults from their mobilisation date (WP-1), evaluated in memory."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import WorkerPersonType
from app.core.cert_enums import HookReasonCode
from app.core.med_enums import FitnessRequirementState, MedicalAppliesTo, MedicalLineSource
from app.models import Adp, Deployment, HealthProfile, MedicalPlanLine, Worker, Zone
from app.services.med import common, engine

A = MedicalAppliesTo
RS = FitnessRequirementState
EXPIRING_KPI_DAYS = 30
ENFORCEMENT = (A.crew_role, A.operator_binding)


@dataclass(frozen=True)
class Line:
    row: MedicalPlanLine
    since: date

    @property
    def enforcement(self) -> bool:
        return self.row.applies_to_kind in ENFORCEMENT


def lines_at(db: Session, project_id: uuid.UUID, d: date) -> list[Line]:
    rows = list(
        db.scalars(
            select(MedicalPlanLine).where(
                MedicalPlanLine.project_id == project_id, MedicalPlanLine.effective_from <= d
            )
        )
    )
    by_line: dict[uuid.UUID, list[MedicalPlanLine]] = defaultdict(list)
    for r in rows:
        by_line[r.line_id].append(r)
    out = []
    for versions in by_line.values():
        versions.sort(key=lambda x: x.effective_from)
        cur = next(
            (x for x in reversed(versions) if x.effective_to is None or x.effective_to >= d), None
        )
        if cur is None or cur.effective_from > d:
            continue
        since = min(x.effective_from for x in versions if x.code == cur.code)
        out.append(Line(cur, since))
    out.sort(key=lambda x: x.row.line_no)
    return out


def hook_codes(db: Session, project_id: uuid.UUID) -> set[str]:
    """Codes used by any attach point of the project (derived H / E lines in force)."""
    return set(
        db.scalars(
            select(MedicalPlanLine.code).where(
                MedicalPlanLine.project_id == project_id,
                MedicalPlanLine.source != MedicalLineSource.manual,
                MedicalPlanLine.effective_to.is_(None),
            )
        )
    )


@dataclass
class Req:
    dep: Deployment
    code: str
    lines: list[Line]
    kpi_counted: bool
    hook_code: bool
    critical: bool
    applies_from: date
    due_date: date
    state: FitnessRequirementState = RS.gap
    counted: bool = False
    check: engine.Check | None = None

    @property
    def line_nos(self) -> list[str]:
        return [ln.row.line_no for ln in self.lines]

    @property
    def reason(self) -> HookReasonCode | None:
        return self.check.reason if self.check is not None and not self.check.ok else None


@dataclass
class Facts:
    project_id: uuid.UUID
    d: date
    at: datetime
    lines: list[Line]
    deps: list[Deployment]
    workers: dict[uuid.UUID, Worker]
    groups: dict[uuid.UUID, dict[str, date]]  # deployment → exposure group → since
    adps: dict[uuid.UUID, dict[str, date]]  # worker → ADP category → since
    zone_sites: dict[str, uuid.UUID]
    facts: dict[uuid.UUID, engine.WorkerFacts]
    ctx: engine.Ctx
    hook_codes: set[str]
    critical: set[str] = field(default_factory=set)


def _history_since(history: list[dict[str, Any]], d: date) -> dict[str, date]:
    spans = []
    for h in history or []:
        f = date.fromisoformat(h["from_date"])
        t = date.fromisoformat(h["to_date"]) if h.get("to_date") else None
        spans.append((f, t, set(h.get("value") or [])))
    spans.sort(key=lambda x: x[0])
    idx = next((i for i, (f, t, _) in enumerate(spans) if f <= d and (t is None or t >= d)), None)
    if idx is None:
        return {}
    out: dict[str, date] = {}
    for x in spans[idx][2]:
        since = spans[idx][0]
        j = idx - 1
        while j >= 0 and x in spans[j][2]:
            since = spans[j][0]
            j -= 1
        out[x] = since
    return out


def default_groups(s: Any, trade: str) -> list[str]:
    return sorted(
        g for g, trades in (s.exposure_group_trade_defaults or {}).items() if trade in trades
    )


def _chunked(db: Session, model: Any, col: Any, ids: Iterable[uuid.UUID]) -> list[Any]:
    ids = list(ids)
    out: list[Any] = []
    for i in range(0, len(ids), 5000):
        out.extend(db.scalars(select(model).where(col.in_(ids[i : i + 5000]))))
    return out


def load(
    db: Session,
    project_id: uuid.UUID,
    d: date,
    deployment_ids: Iterable[uuid.UUID] | None = None,
    mobilised_only: bool = True,
    at: datetime | None = None,
) -> Facts:
    from app.services.train.requirements import _active_cred  # noqa: PLC0415

    at = at or common.day_end_utc(d)
    lines = lines_at(db, project_id, d)
    q = select(Deployment).where(Deployment.project_id == project_id)
    if deployment_ids is not None:
        q = q.where(Deployment.id.in_(list(deployment_ids)))
    deps = [x for x in db.scalars(q) if not mobilised_only or common.mobilised_on(x, d)]
    if not lines:
        deps = deps if deployment_ids is not None else []
    wids = {x.worker_id for x in deps}
    workers = {w.id: w for w in _chunked(db, Worker, Worker.id, wids)}
    s = common.settings(db, project_id)
    groups: dict[uuid.UUID, dict[str, date]] = {}
    stored = {
        pr.deployment_id: pr
        for pr in _chunked(db, HealthProfile, HealthProfile.deployment_id, [x.id for x in deps])
    }
    for dep in deps:
        pr = stored.get(dep.id)
        if pr is not None:
            groups[dep.id] = _history_since(pr.history, d)
        elif dep.mobilised_on <= d:
            groups[dep.id] = dict.fromkeys(default_groups(s, dep.trade.value), dep.mobilised_on)
    adps: dict[uuid.UUID, dict[str, date]] = defaultdict(dict)
    if any(ln.row.applies_to_kind == A.adp_category for ln in lines):
        for adp in db.scalars(select(Adp).where(Adp.project_id == project_id)):
            if adp.worker_id in wids and adp.issued_on is not None and _active_cred(adp, d):
                cat = adp.category.value
                cur = adps[adp.worker_id].get(cat)
                adps[adp.worker_id][cat] = min(cur or adp.issued_on, adp.issued_on)
    zone_sites = {
        str(z.id): z.site_id for z in db.scalars(select(Zone).where(Zone.project_id == project_id))
    }
    return Facts(
        project_id=project_id,
        d=d,
        at=at,
        lines=lines,
        deps=deps,
        workers=workers,
        groups=groups,
        adps=adps,
        zone_sites=zone_sites,
        facts=engine.load(db, wids) if wids else {},
        ctx=engine.ctx_for(db, project_id),
        hook_codes=hook_codes(db, project_id),
        critical=common.critical_codes(s),
    )


def _applies(f: Facts, ln: Line, dep: Deployment) -> date | None:
    r = ln.row
    vals = set(r.applies_to_values or [])
    k = r.applies_to_kind
    if k in (A.all_workers, A.project_hook):
        return dep.mobilised_on
    if k == A.trade:
        return dep.mobilised_on if dep.trade.value in vals else None
    if k == A.exposure_group:
        got = [s for x, s in f.groups.get(dep.id, {}).items() if x in vals]
        return min(got) if got else None
    if k == A.adp_category:
        got = [s for x, s in f.adps.get(dep.worker_id, {}).items() if x in vals]
        return min(got) if got else None
    if k == A.zone:
        if r.trades and dep.trade.value not in r.trades:
            return None
        sites = {f.zone_sites.get(z) for z in vals}
        return dep.mobilised_on if sites & set(dep.site_ids or []) else None
    return None  # enforcement-only lines (crew roles, operator binding) are never counted


def evaluate_dep(f: Facts, dep: Deployment) -> list[Req]:
    d = f.d
    grouped: dict[str, list[tuple[Line, date]]] = defaultdict(list)
    for ln in f.lines:
        if ln.enforcement or not ln.row.kpi_counted:
            continue
        since = _applies(f, ln, dep)
        if since is None:
            continue
        grouped[ln.row.code].append((ln, max(dep.mobilised_on, ln.since, since)))
    w = f.workers.get(dep.worker_id)
    contractor = w is not None and w.person_type == WorkerPersonType.contractor_worker
    mobilised = common.mobilised_on(dep, d)
    out: list[Req] = []
    wf = f.facts.get(dep.worker_id) or engine.WorkerFacts(w)
    for code, items in grouped.items():
        due_date, applies_from = min(
            (af + timedelta(days=ln.row.due_within_days), af) for ln, af in items
        )
        req = Req(
            dep=dep,
            code=code,
            lines=[x[0] for x in items],
            kpi_counted=True,
            hook_code=code in f.hook_codes,
            critical=code in f.critical,
            applies_from=applies_from,
            due_date=due_date,
        )
        chk = engine.check(f.ctx, wf, code, f.at)
        req.check = chk
        if chk.ok:
            exp = chk.valid_until is not None and chk.valid_until <= d + timedelta(
                days=EXPIRING_KPI_DAYS
            )
            req.state = RS.expiring if exp else RS.met
        elif d < due_date:
            req.state = RS.due
        else:
            req.state = RS.gap
        req.counted = contractor and mobilised and req.state in (RS.met, RS.expiring, RS.gap)
        out.append(req)
    out.sort(key=lambda r: (r.line_nos[0] if r.line_nos else "", r.code))
    return out


@dataclass
class ProjectEval:
    f: Facts
    reqs: list[Req]

    @property
    def counted(self) -> list[Req]:
        return [r for r in self.reqs if r.counted]


def evaluate_project(
    db: Session, project_id: uuid.UUID, d: date, engagement_ids: set[uuid.UUID] | None = None
) -> ProjectEval:
    f = load(db, project_id, d)
    reqs: list[Req] = []
    for dep in f.deps:
        if engagement_ids is not None and dep.engagement_id not in engagement_ids:
            continue
        reqs.extend(evaluate_dep(f, dep))
    return ProjectEval(f, reqs)
