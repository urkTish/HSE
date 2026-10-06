"""Request scope for every KPI read: role scoping (D-3) first, then the user's filters
(K-R5 roll-up, tiers, sites, zones), the period (K-R10), comparisons (K-R11) and the bases
(K-R12). Builds the engine once per request."""

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.kpi_params import KpiQuery
from app.core.clock import today
from app.core.enums import Capability, EntityType, WeekStart
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import ComparisonKind
from app.kpi import data
from app.kpi.engine import Engine, EngineConfig
from app.kpi.facts import Facts, Filter
from app.kpi.periods import Period, Window, comparison, month_end, month_key, resolve
from app.models import HseSettings, Project, ProjectEngagement, Site
from app.services import hse_settings
from app.services.permissions import Principal, deny

DEFAULT_LTIFR = 1_000_000
DEFAULT_RATE = 200_000


@dataclass
class Scope:
    p: Principal
    projects: list[Project]
    hse: dict[uuid.UUID, HseSettings]
    facts: Facts
    flt: Filter
    engine: Engine
    period: Period
    as_of: date
    comparisons: list[tuple[ComparisonKind, Window]]
    query: KpiQuery
    config: EngineConfig
    mixed_bases: bool
    narrowed: bool  # an explicit request was reduced by the role scope
    role_scoped: bool  # an unfiltered request was limited to the role scope
    restated: list[date] = field(default_factory=list)
    role_engs: frozenset[uuid.UUID] | None = None
    role_sites: frozenset[uuid.UUID] | None = None
    project_sites: dict[uuid.UUID, frozenset[uuid.UUID]] = field(default_factory=dict)

    @property
    def window(self) -> Window:
        return self.period.window

    @property
    def single_project(self) -> Project | None:
        return self.projects[0] if len(self.projects) == 1 else None

    def settings(self) -> HseSettings:
        return self.hse[self.projects[0].id]

    def sub_engine(self, flt: Filter) -> Engine:
        return Engine(self.facts, flt, self.as_of, self.config)

    def narrowed_filter(
        self,
        engs: frozenset[uuid.UUID] | None = None,
        sites: frozenset[uuid.UUID] | None = None,
    ) -> Filter:
        """The current filter further restricted (engagement and/or site sets)."""
        f = self.flt
        e = f.engs if engs is None else (engs if f.engs is None else f.engs & engs)
        s = f.sites if sites is None else (sites if f.sites is None else f.sites & sites)
        return Filter(sites=s, zones=f.zones, zone_type=f.zone_type, engs=e)

    def restated_in(self, w: Window) -> list[str]:
        return [month_key(m) for m in self.restated if m <= w.end and month_end(m) >= w.start]

    def engagement_label(self, eng_id: uuid.UUID | None) -> str:
        e = self.facts.engagements.get(eng_id) if eng_id else None
        return e.code if e else "—"


def _role_scope(
    db: Session, p: Principal, projects: list[Project], cap: Capability
) -> tuple[
    frozenset[uuid.UUID] | None,
    frozenset[uuid.UUID] | None,
    dict[uuid.UUID, frozenset[uuid.UUID]],
]:
    """Union of the caller's grants across the selected projects as global site/engagement
    sets (``None`` = unrestricted)."""
    site_rows = db.execute(
        select(Site.id, Site.project_id).where(Site.project_id.in_([x.id for x in projects]))
    ).all()
    project_sites: dict[uuid.UUID, set[uuid.UUID]] = {}
    for sid, pid in site_rows:
        project_sites.setdefault(pid, set()).add(sid)
    sites: set[uuid.UUID] = set()
    engs: set[uuid.UUID] = set()
    sites_restricted = engs_restricted = False
    eng_rows = db.execute(
        select(ProjectEngagement.id, ProjectEngagement.project_id).where(
            ProjectEngagement.project_id.in_([x.id for x in projects])
        )
    ).all()
    project_engs: dict[uuid.UUID, set[uuid.UUID]] = {}
    for eid, pid in eng_rows:
        project_engs.setdefault(pid, set()).add(eid)
    for proj in projects:
        g = p.grant(proj.id, cap)
        if g is None:
            continue
        if g.site_ids is not None:
            sites_restricted = True
            sites |= set(g.site_ids) & project_sites.get(proj.id, set())
        else:
            sites |= project_sites.get(proj.id, set())
        if g.engagement_ids is not None:
            engs_restricted = True
            engs |= set(g.engagement_ids) & project_engs.get(proj.id, set())
        else:
            engs |= project_engs.get(proj.id, set())
    return (
        frozenset(sites) if sites_restricted else None,
        frozenset(engs) if engs_restricted else None,
        {k: frozenset(v) for k, v in project_sites.items()},
    )


def resolve_projects(
    db: Session, p: Principal, q: KpiQuery, cap: Capability = Capability.dashboard_view
) -> list[Project]:
    if q.all_projects:
        if not p.is_manager:
            raise ApiError(
                403,
                ErrorCode.MIXED_PROJECT_SCOPE,
                "Only the HSE Manager may aggregate all projects.",
                "تجميع كل المشاريع متاح لمدير الصحة والسلامة فقط.",
            )
        return list(db.scalars(select(Project).order_by(Project.code)).all())
    if not q.project_ids:
        raise validation_error("project_id", "Give a project_id (or all_projects=true).")
    out = []
    for pid in dict.fromkeys(q.project_ids):
        proj = db.get(Project, pid)
        if proj is None or p.grant(pid, cap) is None:
            raise deny(db, p, EntityType.project, pid, pid if proj else None, "Project")
        out.append(proj)
    return out


def build(
    db: Session,
    p: Principal,
    q: KpiQuery,
    cap: Capability = Capability.dashboard_view,
    facts: Facts | None = None,
) -> Scope:
    projects = resolve_projects(db, p, q, cap)
    hse = {proj.id: hse_settings.get(db, proj.id) for proj in projects}
    if facts is None:
        facts = data.load(db, projects, hse)
    role_sites, role_engs, project_sites = _role_scope(db, p, projects, cap)
    narrowed = False

    # engagements: requested (+ descendants) ∩ tiers ∩ role scope
    engs: set[uuid.UUID] | None = None
    if q.engagement_ids:
        engs = set()
        for e in q.engagement_ids:
            if e not in facts.engagements:
                narrowed = True
                continue
            engs |= facts.descendants(e) if q.include_subcontractors else {e}
    if q.tiers:
        tiered = {e.id for e in facts.engagements.values() if e.tier in q.tiers}
        engs = tiered if engs is None else engs & tiered
    # an unfiltered request ("all contractors") from a role-scoped caller is reduced too (D-3);
    # reported to the dashboard as scope_narrowed, but not to the AI (it is the caller's scope)
    role_scoped = False
    if role_engs is not None:
        if engs is None:
            role_scoped = True
            engs = set(role_engs)
        else:
            if not engs <= role_engs:
                narrowed = True
            engs &= role_engs
    sites: set[uuid.UUID] | None = set(q.site_ids) if q.site_ids else None
    if role_sites is not None:
        if sites is None:
            role_scoped = True
            sites = set(role_sites)
        else:
            if not sites <= role_sites:
                narrowed = True
            sites &= role_sites
    flt = Filter(
        sites=frozenset(sites) if sites is not None else None,
        zones=frozenset(q.zone_ids) if q.zone_ids else None,
        zone_type=q.zone_type.value if q.zone_type else None,
        engs=frozenset(engs) if engs is not None else None,
    )

    first = projects[0] if projects else None
    tz = first.settings.timezone if first and first.settings else "Asia/Riyadh"
    as_of = q.as_of or today(tz)
    try:
        period = resolve(
            q.period,
            as_of=as_of,
            anchor=q.anchor,
            start=q.start,
            end=q.end,
            week_starts=first.settings.week_start if first and first.settings else WeekStart.sunday,
            project_start=facts.project_start,
        )
    except ValueError as exc:
        raise validation_error("period", str(exc)) from exc
    bases = {
        (x.settings.ltifr_base_hours, x.settings.rate_base_hours) if x.settings else
        (DEFAULT_LTIFR, DEFAULT_RATE)
        for x in projects
    }  # fmt: skip
    mixed = len(bases) > 1
    ltifr, rate = (DEFAULT_LTIFR, DEFAULT_RATE) if mixed or not bases else next(iter(bases))
    low = min((s.low_exposure_hours for s in hse.values()), default=200_000)
    config = EngineConfig(ltifr, rate, low)
    engine = Engine(facts, flt, as_of, config)
    comps = [(k, comparison(k, q.period, period.window)) for k in dict.fromkeys(q.compare)]
    return Scope(
        p=p,
        projects=projects,
        hse=hse,
        facts=facts,
        flt=flt,
        engine=engine,
        period=period,
        as_of=as_of,
        comparisons=comps,
        query=q,
        config=config,
        mixed_bases=mixed,
        narrowed=narrowed,
        role_scoped=role_scoped,
        restated=data.restated_months(db, [x.id for x in projects]),
        role_engs=role_engs,
        role_sites=role_sites,
        project_sites=project_sites,
    )
