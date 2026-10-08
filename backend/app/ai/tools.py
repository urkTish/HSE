"""AI tools T1-T14 (spec 1-dashboard §5.9 v1.1) plus get_expiring_items and propose_chart.

Every tool is a thin read-only wrapper over the KPI engine or a query service, executed with
the asking user's principal: projects without capability 40 + 38 are dropped, filters outside
the role scope are narrowed (D-3) and the narrowing is reported (`scope_narrowed`). Outputs are
de-identified (AI-5): no person names, ID numbers, contacts, medical notes or observer
identities; free text is redacted server-side.
"""

import dataclasses
import hashlib
import json
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.masking import redact
from app.api.kpi_params import KpiQuery
from app.core.access_enums import AccessKpiGroupBy
from app.core.cert_enums import CertKpiGroupBy, EquipmentCertCategory
from app.core.enums import Capability, Role, ZoneType
from app.core.errors import ApiError
from app.core.hse_enums import (
    AiTool,
    BreakdownDimension,
    BreakdownMeasure,
    CaseCategory,
    CaStatus,
    ChartId,
    CompareDimension,
    ComparisonKind,
    ExpiringItemKind,
    ExtensionStatus,
    Granularity,
    IncidentStatus,
    InspectionTimeliness,
    KpiMetric,
    PeriodPreset,
)
from app.core.ptw_enums import PermitType, PtwKpiGroupBy
from app.kpi import access_views, cert_views, charts, fmt, groups, ptw_views, service, views
from app.kpi import scope as kscope
from app.kpi.facts import Facts
from app.kpi.periods import week_start
from app.models import (
    CaExtension,
    Contractor,
    CorrectiveAction,
    Gate,
    Incident,
    InjuryCase,
    Investigation,
    Observation,
    Project,
    ProjectEngagement,
    Site,
    User,
    Zone,
)
from app.schemas.ai import AiCitation
from app.schemas.kpi import ChartSpec, KpiContext, KpiValue
from app.services import corrective_actions as ca_svc
from app.services import dashboard as dash_svc
from app.services import hse_settings
from app.services import incidents as inc_svc
from app.services import inspections as ins_svc
from app.services import observations as obs_svc
from app.services.hse_common import user_roles
from app.services.permissions import Principal

EQC_VALUES = [c.value for c in EquipmentCertCategory]
NO_ACCESS = "No access to the requested data."
ACCESS_KINDS = frozenset(
    {
        ExpiringItemKind.induction_expiry, ExpiringItemKind.reinduction_due,
        ExpiringItemKind.worker_id_expiry, ExpiringItemKind.airport_pass_expiry,
        ExpiringItemKind.bg_recheck_due, ExpiringItemKind.adp_expiry,
        ExpiringItemKind.adp_suspension_end, ExpiringItemKind.avp_expiry,
        ExpiringItemKind.vehicle_document_expiry, ExpiringItemKind.wap_expiry,
        ExpiringItemKind.notam_expiry, ExpiringItemKind.obstacle_clearance_expiry,
        ExpiringItemKind.pass_return_due,
    }
)  # fmt: skip
PERSON_KINDS = frozenset({ExpiringItemKind.worker_id_expiry, ExpiringItemKind.bg_recheck_due})
ROLE_ORDER = [
    Role.hse_manager,
    Role.hse_officer,
    Role.site_engineer,
    Role.contractor_hse_rep,
    Role.permit_issuer,
    Role.permit_receiver,
    Role.viewer_client,
]

# ---- JSON schemas --------------------------------------------------------------------------------

PERIOD = {
    "type": "object",
    "description": "Period. preset with optional anchor (a date inside the wanted month/week/"
    "quarter/year; default today), or preset=custom with start and end (inclusive).",
    "properties": {
        "preset": {"type": "string", "enum": [p.value for p in PeriodPreset]},
        "anchor": {"type": "string", "format": "date"},
        "start": {"type": "string", "format": "date"},
        "end": {"type": "string", "format": "date"},
    },
}
FILTERS = {
    "type": "object",
    "description": "Optional filters. Codes as shown in tool results (e.g. S-AIR, Z-APR-21, "
    "RAWABI).",
    "properties": {
        "site_codes": {"type": "array", "items": {"type": "string"}},
        "zone_codes": {"type": "array", "items": {"type": "string"}},
        "zone_type": {"type": "string", "enum": [z.value for z in ZoneType]},
        "contractor_codes": {"type": "array", "items": {"type": "string"}},
        "include_subcontractors": {"type": "boolean", "default": True},
        "tiers": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 3}},
    },
}
PROJECTS = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Project codes; default = the project the user is asking about.",
}


def _tool(
    name: AiTool, description: str, props: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "name": name.value,
        "description": description,
        "input_schema": {"type": "object", "properties": props, "required": required},
    }


TOOL_DEFS: list[dict[str, Any]] = [
    _tool(
        AiTool.get_kpis,
        "KPI values from the platform KPI engine for a scope and period: value, numerator, "
        "denominator, base, comparisons (previous / sply / r12) with absolute and % deltas, "
        "data completeness, provisional cases, restated flag. Metric ids K-01..K-47.",
        {
            "project_codes": PROJECTS,
            "period": PERIOD,
            "filters": FILTERS,
            "metrics": {
                "type": "array",
                "items": {"type": "string", "enum": [m.value for m in KpiMetric]},
            },
            "compare": {
                "type": "array",
                "items": {"type": "string", "enum": [c.value for c in ComparisonKind]},
            },
        },
        ["metrics"],
    ),
    _tool(
        AiTool.get_kpi_timeseries,
        "Series of one KPI by week or month with numerator/denominator, the rolling-12-month "
        "series and the 3-period moving average. trend_established tells whether a trend may "
        "be stated (≥ 6 monthly points with man-hours).",
        {
            "project_codes": PROJECTS,
            "metric": {"type": "string", "enum": [m.value for m in KpiMetric]},
            "granularity": {"type": "string", "enum": [g.value for g in Granularity]},
            "start": {"type": "string", "format": "date"},
            "end": {"type": "string", "format": "date"},
            "filters": FILTERS,
        },
        ["metric"],
    ),
    _tool(
        AiTool.get_breakdown,
        "Counts (and rates where man-hours exist) of a measure by a dimension. Cells of 1-2 "
        "persons may be suppressed as '<3'.",
        {
            "project_codes": PROJECTS,
            "measure": {"type": "string", "enum": [m.value for m in BreakdownMeasure]},
            "dimension": {"type": "string", "enum": [d.value for d in BreakdownDimension]},
            "period": PERIOD,
            "filters": FILTERS,
            "top_n": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        ["measure", "dimension"],
    ),
    _tool(
        AiTool.search_incidents,
        "De-identified incident rows (no names) for a period and filters.",
        {
            "project_codes": PROJECTS,
            "period": PERIOD,
            "filters": FILTERS,
            "types": {"type": "array", "items": {"type": "string"}},
            "categories": {
                "type": "array",
                "items": {"type": "string", "enum": [c.value for c in CaseCategory]},
            },
            "activity": {"type": "string"},
            "mechanism": {"type": "string"},
            "agency": {"type": "string"},
            "hipo": {"type": "boolean"},
            "status": {"type": "string", "enum": [s.value for s in IncidentStatus]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        [],
    ),
    _tool(
        AiTool.get_incident,
        "De-identified detail of one incident by ref: description (names and IDs redacted), "
        "immediate actions, investigation (level, causes, root-cause codes, lessons) and linked "
        "corrective actions.",
        {"ref": {"type": "string"}},
        ["ref"],
    ),
    _tool(
        AiTool.list_corrective_actions,
        "Corrective actions: ref, title, priority, control level, contractor, owner role (never "
        "a name), due date, days overdue, extensions, status.",
        {
            "project_codes": PROJECTS,
            "status": {
                "type": "array",
                "items": {"type": "string", "enum": [s.value for s in CaStatus]},
            },
            "overdue": {"type": "boolean"},
            "priority": {"type": "string"},
            "control_level": {"type": "string"},
            "source_type": {"type": "string"},
            "contractor_codes": {"type": "array", "items": {"type": "string"}},
            "due_from": {"type": "string", "format": "date"},
            "due_to": {"type": "string", "format": "date"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        [],
    ),
    _tool(
        AiTool.list_observations_summary,
        "Observation counts with safe/unsafe split grouped by category, obs_type, contractor, "
        "site, zone or week.",
        {
            "project_codes": PROJECTS,
            "period": PERIOD,
            "filters": FILTERS,
            "group_by": {
                "type": "string",
                "enum": ["category", "obs_type", "contractor", "site", "zone", "week"],
            },
        },
        ["group_by"],
    ),
    _tool(
        AiTool.list_inspections_summary,
        "Inspections planned / on time / late / missed / cancelled / unplanned and average score, "
        "grouped by type, site, contractor or week.",
        {
            "project_codes": PROJECTS,
            "period": PERIOD,
            "filters": FILTERS,
            "group_by": {"type": "string", "enum": ["type", "site", "contractor", "week"]},
        },
        ["group_by"],
    ),
    _tool(
        AiTool.compare_groups,
        "Compares event rates between groups of a dimension with exposure, rate ratio vs a "
        "reference group, 95 % CI and p-value (exact conditional binomial for 2 groups, "
        "chi-square for more). sample_sufficient and supports_association say whether an "
        "association may be stated.",
        {
            "project_codes": PROJECTS,
            "measure": {"type": "string", "enum": ["injury_cases", "recordable_cases", "events"]},
            "categories": {
                "type": "array",
                "items": {"type": "string", "enum": [c.value for c in CaseCategory]},
            },
            "event_type": {"type": "string"},
            "dimension": {"type": "string", "enum": [d.value for d in CompareDimension]},
            "reference": {"type": "string"},
            "period": PERIOD,
            "filters": FILTERS,
        },
        ["measure", "dimension"],
    ),
    _tool(
        AiTool.get_data_quality,
        "Data completeness % and missing engagement-days, provisional cases, late reports, "
        "restated periods, overdue investigations.",
        {"project_codes": PROJECTS, "period": PERIOD, "filters": FILTERS},
        [],
    ),
    _tool(
        AiTool.get_lti_free,
        "LTI-free days and man-hours, last LTI date and ref, run basis, longest run.",
        {
            "project_codes": PROJECTS,
            "filters": FILTERS,
            "as_of": {"type": "string", "format": "date"},
        },
        [],
    ),
    _tool(
        AiTool.get_settings_and_targets,
        "Bases, thresholds, KPI targets, heat season and new-starter days of a project.",
        {"project_code": {"type": "string"}},
        [],
    ),
    _tool(
        AiTool.get_leading_warnings,
        "Backend-computed leading-indicator warnings E1-E11 (E5-E7 for airport access: induction "
        "coverage, gate denial spike, airside driving offences; E8-E9 permit to work; E10 "
        "certification compliance below threshold, E11 dangerous defects / failed verifications) "
        "with their inputs for the last complete months.",
        {
            "project_code": {"type": "string"},
            "months": {"type": "integer", "minimum": 1, "maximum": 12},
        },
        [],
    ),
    _tool(
        AiTool.get_expiring_items,
        "Corrective actions, investigations, notifications and (airport projects) credentials, "
        "permits and NOTAMs due soon or overdue. Access items carry no person identifiers.",
        {
            "project_code": {"type": "string"},
            "within_days": {"type": "integer", "minimum": 1, "maximum": 90},
            "include_overdue": {"type": "boolean"},
        },
        [],
    ),
    _tool(
        AiTool.get_access_kpis,
        "T14: airport access and permit KPIs (K-38, K-48..K-60, K-53b) for airport projects: "
        "value, numerator, denominator, comparisons and breakdown rows by kind, reason_code, "
        "contractor, zone, gate or month. Aggregates only — no names, ID numbers, worker numbers, "
        "photos or plates. Gate KPIs count in-direction checks under the first DENY reason.",
        {
            "project_codes": PROJECTS,
            "period": PERIOD,
            "filters": {
                **FILTERS,
                "properties": {
                    **FILTERS["properties"],  # type: ignore[dict-item]
                    "gate_codes": {"type": "array", "items": {"type": "string"}},
                },
            },
            "metrics": {
                "type": "array",
                "items": {"type": "string", "enum": [m.value for m in access_views.ACCESS_METRICS]},
            },
            "group_by": {
                "type": "array",
                "items": {"type": "string", "enum": [g.value for g in AccessKpiGroupBy]},
            },
        },
        [],
    ),
    _tool(
        AiTool.get_ptw_kpis,
        "T15: permit-to-work KPIs (K-46, K-46b, K-61..K-71): value, numerator, denominator, "
        "comparisons and breakdown rows by type, contractor, zone, month, week, "
        "suspension_reason, audit_item or simops_rule, plus the live PTW band. Aggregates only "
        "— no names, worker numbers, signatures or appointment holders.",
        {
            "project_codes": PROJECTS,
            "period": PERIOD,
            "filters": {
                **FILTERS,
                "properties": {
                    **FILTERS["properties"],  # type: ignore[dict-item]
                    "permit_types": {
                        "type": "array",
                        "items": {"type": "string", "enum": [t.value for t in PermitType]},
                    },
                },
            },
            "metrics": {
                "type": "array",
                "items": {"type": "string", "enum": [m.value for m in ptw_views.PTW_METRICS]},
            },
            "group_by": {
                "type": "array",
                "items": {"type": "string", "enum": [g.value for g in PtwKpiGroupBy]},
            },
        },
        [],
    ),
    _tool(
        AiTool.get_certification_kpis,
        "T16: third-party certification KPIs (K-72..K-81): value, numerator, denominator, "
        "components, comparisons and breakdown rows by category, cert_type, contractor, tpi, "
        "defect_category, reason_code or month, plus the certification band counts. Aggregates "
        "only — no names, worker numbers, certificate numbers, ID data, ban reasons or "
        "verification-failure details.",
        {
            "project_codes": PROJECTS,
            "period": PERIOD,
            "filters": {
                **FILTERS,
                "properties": {
                    **FILTERS["properties"],  # type: ignore[dict-item]
                    "equipment_categories": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [c.value for c in EquipmentCertCategory],
                        },
                    },
                    "cert_types": {"type": "array", "items": {"type": "string"}},
                },
            },
            "metrics": {
                "type": "array",
                "items": {"type": "string", "enum": [m.value for m in cert_views.CERT_METRICS]},
            },
            "group_by": {
                "type": "array",
                "items": {"type": "string", "enum": [g.value for g in CertKpiGroupBy]},
            },
        },
        [],
    ),
    _tool(
        AiTool.propose_chart,
        "Attach one dashboard chart (C1..C9) for the scope and period to the answer.",
        {
            "chart_id": {"type": "string", "enum": [c.value for c in ChartId]},
            "project_codes": PROJECTS,
            "period": PERIOD,
            "filters": FILTERS,
        },
        ["chart_id"],
    ),
]


# ---- context -------------------------------------------------------------------------------------


@dataclass
class ToolRun:
    name: str
    params: dict[str, Any]
    result: dict[str, Any]
    narrowed: bool
    result_hash: str


@dataclass
class ToolContext:
    db: Session
    p: Principal
    project: Project
    as_of: date
    default_query: KpiQuery | None = None
    runs: list[ToolRun] = field(default_factory=list)
    citations: list[AiCitation] = field(default_factory=list)
    chart: ChartSpec | None = None
    _facts: dict[tuple[uuid.UUID, ...], Facts] = field(default_factory=dict)
    _names: list[str] | None = None

    def cite(
        self,
        tool: AiTool,
        text_en: str,
        *,
        metric: KpiMetric | None = None,
        value: str | None = None,
        period: str | None = None,
        scope: str | None = None,
        base: str | None = None,
        refs: list[str] | None = None,
    ) -> str:
        cid = f"S{len(self.citations) + 1}"
        self.citations.append(
            AiCitation(
                id=cid,
                tool=tool,
                metric=metric,
                value_display=value,
                period_label_en=period,
                scope_label_en=scope,
                base_label_en=base,
                refs=refs or [],
                text_en=text_en,
                text_ar=text_en,
            )
        )
        return cid

    def names(self) -> list[str]:
        """Person names to redact from free text (users and injured persons)."""
        if self._names is None:
            users = self.db.execute(select(User.full_name_en, User.full_name_ar)).all()
            people = self.db.scalars(
                select(InjuryCase.person_name).where(InjuryCase.project_id == self.project.id)
            ).all()
            self._names = [n for row in users for n in row if n] + [n for n in people if n]
        return self._names


class ToolError(Exception):
    pass


def _allowed_projects(ctx: ToolContext, codes: list[str] | None) -> tuple[list[Project], bool]:
    db, p = ctx.db, ctx.p
    wanted = [c.strip() for c in codes or [] if c and c.strip()]
    if not wanted:
        rows = [ctx.project]
    else:
        rows = list(db.scalars(select(Project).where(Project.code.in_(wanted))))
    ok = [
        x
        for x in rows
        if p.grant(x.id, Capability.ai_ask) is not None
        and p.grant(x.id, Capability.dashboard_view) is not None
    ]
    narrowed = len(ok) < max(len(wanted), 1)
    return ok, narrowed


def _date(v: Any) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as e:
        raise ToolError(f"Invalid date: {v}") from e


def _ids_by_code(
    db: Session, model: Any, codes: list[str], project_ids: list[uuid.UUID]
) -> tuple[list[uuid.UUID], bool]:
    if not codes:
        return [], False
    rows = db.execute(
        select(model.id, model.code).where(model.project_id.in_(project_ids), model.code.in_(codes))
    ).all()
    return [r[0] for r in rows], len({r[1] for r in rows}) < len(set(codes))


def _eng_ids(
    db: Session, codes: list[str], project_ids: list[uuid.UUID]
) -> tuple[list[uuid.UUID], bool]:
    if not codes:
        return [], False
    rows = db.execute(
        select(ProjectEngagement.id, Contractor.short_code)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(ProjectEngagement.project_id.in_(project_ids), Contractor.short_code.in_(codes))
    ).all()
    return [r[0] for r in rows], len({r[1] for r in rows}) < len(set(codes))


def _query(
    ctx: ToolContext, params: dict[str, Any], codes_key: str = "project_codes"
) -> tuple[KpiQuery | None, bool]:
    codes = params.get(codes_key)
    if isinstance(codes, str):
        codes = [codes]
    projects, narrowed = _allowed_projects(ctx, codes)
    if not projects:
        return None, True
    pids = [x.id for x in projects]
    flt = params.get("filters") or {}
    d = ctx.default_query
    use_default = not flt and d is not None and pids == [ctx.project.id]
    sites, n1 = _ids_by_code(ctx.db, Site, list(flt.get("site_codes") or []), pids)
    zones, n2 = _ids_by_code(ctx.db, Zone, list(flt.get("zone_codes") or []), pids)
    engs, n3 = _eng_ids(ctx.db, list(flt.get("contractor_codes") or []), pids)
    period = params.get("period") or {}
    preset = PeriodPreset(period.get("preset") or PeriodPreset.month)
    zt = flt.get("zone_type")
    q = KpiQuery(
        project_ids=pids,
        all_projects=False,
        site_ids=list(d.site_ids) if use_default and d else sites,
        zone_ids=list(d.zone_ids) if use_default and d else zones,
        zone_type=(d.zone_type if use_default and d else (ZoneType(zt) if zt else None)),
        engagement_ids=list(d.engagement_ids) if use_default and d else engs,
        include_subcontractors=bool(flt.get("include_subcontractors", True)),
        tiers=[int(t) for t in flt.get("tiers") or []],
        period=preset,
        anchor=_date(period.get("anchor")),
        start=_date(period.get("start")),
        end=_date(period.get("end")),
        as_of=_date(params.get("as_of")) or ctx.as_of,
        compare=[ComparisonKind(c) for c in params.get("compare") or ["previous", "sply"]],
    )
    return q, narrowed or n1 or n2 or n3


def _scope(ctx: ToolContext, q: KpiQuery) -> kscope.Scope:
    key = tuple(sorted(q.project_ids, key=str))
    facts = ctx._facts.get(key)
    sc = kscope.build(ctx.db, ctx.p, q, facts=facts)
    ctx._facts[key] = sc.facts
    return sc


def _codes_who(sc: kscope.Scope) -> tuple[str, str]:
    label = service.scope_label(sc)
    codes = ", ".join(x.code for x in sc.projects)
    return codes, label[len(codes) + 2 :] if label.startswith(codes + ", ") else label


def _context(c: KpiContext, sc: kscope.Scope) -> dict[str, Any]:
    low = sc.settings().low_exposure_hours if sc.single_project else None
    mh = sc.engine.aggregate(sc.window).mh
    return {
        "period": c.period.label_en,
        "start": c.period.start.isoformat(),
        "end": c.period.end.isoformat(),
        "as_of": c.period.as_of.isoformat(),
        "scope": service.scope_label(sc),
        "ltifr_base": c.bases.ltifr_label_en,
        "rate_base": c.bases.rate_label_en,
        "man_hours": fmt.number(mh, 0),
        "no_man_hours": mh <= 0,
        "low_exposure": bool(low and 0 < mh < low),
        "low_exposure_hours": fmt.number(low, 0) if low else None,
        "data_completeness": c.data_completeness_display,
        "completeness_below_threshold": c.completeness_below_threshold,
        "completeness_threshold_pct": service.threshold(sc),
        "provisional_cases": c.provisional_cases_count,
        "restated_months": c.restated_months,
        "scope_narrowed": sc.narrowed,
    }


def _kpi(v: KpiValue) -> dict[str, Any]:
    return {
        "metric": v.metric.value,
        "name": v.short_label_en,
        "label": v.label_en,
        "value": v.display,
        "null_reason": v.null_reason.value if v.null_reason else None,
        "numerator": v.numerator,
        "numerator_label": v.numerator_label_en,
        "denominator": v.denominator,
        "denominator_label": v.denominator_label_en,
        "base": v.base,
        "unit": v.unit_en,
        "comparisons": [
            {
                "kind": c.kind.value,
                "period": c.label_en,
                "value": c.display,
                "abs_delta": c.abs_delta_display,
                "pct_delta": c.pct_delta_display,
                "better_or_worse": c.direction.value,
            }
            for c in v.comparisons
        ],
        "target": v.target_display,
        "one_case_changes_rate_by": v.one_case_changes_rate_by,
        "warnings": [w.value for w in v.warnings],
        "components": [
            {"key": x.key, "label": x.label_en, "value": x.display, "share": x.share_display}
            for x in v.components
        ],
    }


# ---- tools ---------------------------------------------------------------------------------------


def t_get_kpis(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    sc = _scope(ctx, q)
    metrics = [KpiMetric(m) for m in params.get("metrics") or []] or None
    c = service.context(sc)
    values = service.metric_list(sc, metrics)
    codes, who = _codes_who(sc)
    out = []
    for v in values:
        row = _kpi(v)
        base = None
        if v.base:
            base = fmt.hours_label(v.base)[0]
        row["base_label"] = base
        text = f"{v.short_label_en} {v.display} — get_kpis, {codes}, {c.period.label_en}, {who}"
        row["cite"] = ctx.cite(
            AiTool.get_kpis,
            text + (f", {base}" if base else ""),
            metric=v.metric,
            value=v.display,
            period=c.period.label_en,
            scope=service.scope_label(sc),
            base=base,
        )
        out.append(row)
    return {"context": _context(c, sc), "kpis": out}, narrowed or sc.narrowed


def t_get_kpi_timeseries(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    q, narrowed = _query(
        ctx, {**params, "period": {"preset": "month", "anchor": params.get("end")}}
    )
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    sc = _scope(ctx, q)
    metric = KpiMetric(params["metric"])
    gran = Granularity(params.get("granularity") or Granularity.month)
    s = service.trend_series(sc, metric, gran, _date(params.get("start")), _date(params.get("end")))

    def pts(points: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "period": x.label_en,
                "value": x.display,
                "numerator": x.numerator,
                "denominator": x.denominator,
            }
            for x in points
        ]

    span = f"{s.points[0].label_en} – {s.points[-1].label_en}" if s.points else "—"
    cid = ctx.cite(
        AiTool.get_kpi_timeseries,
        f"{s.label_en} series — get_kpi_timeseries, {service.scope_label(sc)}, {span}",
        metric=metric,
        period=span,
        scope=service.scope_label(sc),
    )
    return {
        "metric": metric.value,
        "name": s.label_en,
        "granularity": gran.value,
        "scope": service.scope_label(sc),
        "points": pts(s.points),
        "r12": pts(s.r12),
        "moving_average_3": pts(s.ma3),
        "periods_with_exposure": s.periods_with_exposure,
        "trend_established": s.trend_established,
        "trend_rule": "A trend may be stated only with ≥ 6 monthly points with man-hours.",
        "cite": cid,
    }, narrowed or sc.narrowed


def t_get_breakdown(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    sc = _scope(ctx, q)
    measure = BreakdownMeasure(params["measure"])
    dim = BreakdownDimension(params["dimension"])
    bd = views.breakdown(ctx.db, sc, measure, dim, min(int(params.get("top_n") or 10), 20))

    def row(r: Any) -> dict[str, Any]:
        return {
            "key": r.label_en,
            "count": r.count_display,
            "man_hours": fmt.number(Decimal(r.man_hours), 0) if r.man_hours else None,
            "rate": r.rate_display,
            "share": r.share_display,
        }

    cid = ctx.cite(
        AiTool.get_breakdown,
        f"{measure.value} by {dim.value} — get_breakdown, {service.scope_label(sc)}, "
        f"{bd.context.period.label_en}",
        period=bd.context.period.label_en,
        scope=service.scope_label(sc),
        base=bd.rate_label_en,
    )
    return {
        "context": _context(bd.context, sc),
        "measure": measure.value,
        "dimension": dim.value,
        "rate_label": bd.rate_label_en,
        "total": bd.total_count,
        "rows": [row(r) for r in bd.rows],
        "other": row(bd.other) if bd.other else None,
        "cite": cid,
    }, narrowed or sc.narrowed


def _incident_rows(
    ctx: ToolContext, incs: list[Incident], with_detail: bool = False
) -> list[dict[str, Any]]:
    db = ctx.db
    cases = inc_svc.load_cases(db, [i.id for i in incs])
    sites = dict(db.execute(select(Site.id, Site.code)).all())
    zones = dict(db.execute(select(Zone.id, Zone.code)).all())
    engs = dict(
        db.execute(
            select(ProjectEngagement.id, Contractor.short_code).join(
                Contractor, Contractor.id == ProjectEngagement.contractor_id
            )
        ).all()
    )
    tz = inc_svc.tz_of(ctx.project)
    out = []
    for i in incs:
        cs = cases.get(i.id, [])
        names = ctx.names() + [c.person_name for c in cs if c.person_name]
        out.append(
            {
                "ref": i.ref,
                "date": i.occurred_date.isoformat(),
                "time_band": f"{i.occurred_at.astimezone(tz).hour:02d}h",
                "shift": i.shift.value if i.shift else None,
                "types": list(i.incident_types),
                "cases": [
                    {
                        "case": f"{i.ref}-P{c.person_no}",
                        "category": c.category.value,
                        "classification": c.classification_status.value,
                        "employer": engs.get(c.employer_engagement_id)
                        if c.employer_engagement_id
                        else None,
                        "trade": c.trade.value if c.trade else None,
                        "mechanism": c.mechanism.value if c.mechanism else None,
                        "agency": c.agency.value if c.agency else None,
                        "body_part": c.body_part.value if c.body_part else None,
                        "nature": c.nature.value if c.nature else None,
                    }
                    for c in cs
                ],
                "site": sites.get(i.site_id),
                "zone": zones.get(i.zone_id) if i.zone_id else None,
                "contractor": (
                    engs.get(i.responsible_engagement_id) if i.responsible_engagement_id else None
                ),
                "activity": i.activity.value if i.activity else None,
                "actual_severity": i.actual_severity,
                "potential_severity": i.potential_severity,
                "hipo": i.hipo,
                "status": i.status.value,
                "work_related": i.work_related,
                "title": redact(i.title, names),
            }
        )
        if with_detail:
            out[-1]["description"] = redact(i.description, names)
            out[-1]["immediate_actions"] = redact(i.immediate_actions, names)
    return out


def t_search_incidents(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    sc = _scope(ctx, q)
    w = sc.window
    rows: list[Incident] = []
    for proj in sc.projects:
        stmt = inc_svc.scoped_query(ctx.db, ctx.p, proj).where(
            Incident.occurred_date >= w.start, Incident.occurred_date <= w.end
        )
        status = params.get("status")
        if status:
            stmt = stmt.where(Incident.status == IncidentStatus(status))
        else:
            stmt = stmt.where(Incident.status.not_in([IncidentStatus.draft, IncidentStatus.voided]))
        if params.get("activity"):
            stmt = stmt.where(Incident.activity == params["activity"])
        rows += list(ctx.db.scalars(stmt))
    rows = [
        i
        for i in rows
        if sc.flt.site_ok(i.site_id)
        and sc.flt.eng_ok(i.responsible_engagement_id)
        and sc.flt.zone_ok(i.zone_id, sc.facts.zones)
    ]
    if params.get("hipo") is not None:
        rows = [i for i in rows if i.hipo == bool(params["hipo"])]
    types = set(params.get("types") or [])
    if types:
        rows = [i for i in rows if types & set(i.incident_types)]
    out = _incident_rows(ctx, sorted(rows, key=lambda i: i.occurred_at))
    cats = set(params.get("categories") or [])
    mech, agency = params.get("mechanism"), params.get("agency")
    if cats or mech or agency:
        out = [
            r
            for r in out
            if any(
                (not cats or c["category"] in cats)
                and (not mech or c["mechanism"] == mech)
                and (not agency or c["agency"] == agency)
                for c in r["cases"]
            )
        ]
    limit = min(int(params.get("limit") or 50), 50)
    refs = [r["ref"] for r in out[:limit]]
    cid = ctx.cite(
        AiTool.search_incidents,
        f"Incidents — search_incidents, {service.scope_label(sc)}, {sc.period.label_en}",
        period=sc.period.label_en,
        scope=service.scope_label(sc),
        refs=refs,
    )
    return {
        "period": sc.period.label_en,
        "scope": service.scope_label(sc),
        "total": len(out),
        "incidents": out[:limit],
        "truncated": len(out) > limit,
        "identity_note": "Identities are in the incident register for authorised roles.",
        "cite": cid,
    }, narrowed or sc.narrowed


def t_get_incident(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    ref = str(params.get("ref") or "").strip()
    inc = ctx.db.scalar(select(Incident).where(Incident.ref == ref))
    if inc is None:
        return {"not_found_or_no_access": True, "message": NO_ACCESS}, False
    proj = ctx.db.get(Project, inc.project_id)
    ok, _ = _allowed_projects(ctx, [proj.code] if proj else [])
    visible = (
        ok
        and proj is not None
        and inc.status != IncidentStatus.draft
        and ctx.db.scalar(inc_svc.scoped_query(ctx.db, ctx.p, proj).where(Incident.id == inc.id))
        is not None
    )
    if not visible:
        return {"not_found_or_no_access": True, "message": NO_ACCESS}, True
    row = _incident_rows(ctx, [inc], with_detail=True)[0]
    names = ctx.names()
    v = ctx.db.get(Investigation, inc.id)
    if v is not None:
        row["investigation"] = {
            "level": v.level.value,
            "method": v.method.value if v.method else None,
            "due_date": v.due_date.isoformat() if v.due_date else None,
            "submitted": v.submitted_at is not None,
            "approved": v.approved_at is not None,
            "immediate_causes": redact(v.immediate_causes, names),
            "root_causes": [
                {"code": rc.get("code"), "text": redact(str(rc.get("text") or ""), names)}
                for rc in v.root_causes or []
            ],
            "lessons_learned": redact(v.lessons_learned, names),
            "ptw_involved": v.ptw_involved,
        }
    cas = inc_svc.linked_cas(ctx.db, inc.id)
    row["corrective_actions"] = [
        {
            "ref": a.ref,
            "status": a.status.value,
            "control_level": a.control_level.value,
            "due_date": a.due_date.isoformat(),
        }
        for a in cas
    ]
    row["identity_note"] = "Identities are in the incident register for authorised roles."
    row["cite"] = ctx.cite(
        AiTool.get_incident, f"{inc.ref} — get_incident", refs=[inc.ref] + [a.ref for a in cas]
    )
    return row, False


def _owner_role(db: Session, uid: uuid.UUID, pid: uuid.UUID) -> str:
    roles = user_roles(db, uid, pid)
    for r in ROLE_ORDER:
        if r in roles:
            return r.value
    return "user"


def t_list_corrective_actions(
    ctx: ToolContext, params: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    projects, narrowed = _allowed_projects(ctx, params.get("project_codes"))
    if not projects:
        return {"no_access": True, "message": NO_ACCESS}, True
    pids = [x.id for x in projects]
    engs, n2 = _eng_ids(ctx.db, list(params.get("contractor_codes") or []), pids)
    day = ctx.as_of
    out: list[dict[str, Any]] = []
    eng_codes = dict(
        ctx.db.execute(
            select(ProjectEngagement.id, Contractor.short_code).join(
                Contractor, Contractor.id == ProjectEngagement.contractor_id
            )
        ).all()
    )
    for proj in projects:
        stmt = ca_svc.scoped_query(ctx.p, proj)
        if params.get("status"):
            stmt = stmt.where(CorrectiveAction.status.in_([CaStatus(s) for s in params["status"]]))
        for key in ("priority", "control_level", "source_type"):
            if params.get(key):
                stmt = stmt.where(getattr(CorrectiveAction, key) == params[key])
        if engs:
            stmt = stmt.where(CorrectiveAction.responsible_engagement_id.in_(engs))
        if params.get("due_from"):
            stmt = stmt.where(CorrectiveAction.due_date >= _date(params["due_from"]))
        if params.get("due_to"):
            stmt = stmt.where(CorrectiveAction.due_date <= _date(params["due_to"]))
        cas = list(ctx.db.scalars(stmt.order_by(CorrectiveAction.due_date)))
        ext = (
            dict(
                ctx.db.execute(
                    select(CaExtension.ca_id, func.count())
                    .where(
                        CaExtension.ca_id.in_([a.id for a in cas]),
                        CaExtension.status == ExtensionStatus.approved,
                    )
                    .group_by(CaExtension.ca_id)
                ).all()
            )
            if cas
            else {}
        )
        for a in cas:
            over = ca_svc.overdue_at(a, day)
            if params.get("overdue") is not None and bool(params["overdue"]) != over:
                continue
            out.append(
                {
                    "ref": a.ref,
                    "title": redact(a.title, ctx.names()),
                    "priority": a.priority.value,
                    "control_level": a.control_level.value,
                    "source_type": a.source_type.value,
                    "contractor": eng_codes.get(a.responsible_engagement_id),
                    "owner_role": _owner_role(ctx.db, a.owner_id, proj.id),
                    "due_date": a.due_date.isoformat(),
                    "original_due_date": a.original_due_date.isoformat(),
                    "overdue": over,
                    "days_overdue": (day - a.due_date).days if over else 0,
                    "extensions": int(ext.get(a.id, 0)),
                    "status": a.status.value,
                }
            )
    limit = min(int(params.get("limit") or 100), 100)
    cid = ctx.cite(
        AiTool.list_corrective_actions,
        f"Corrective actions — list_corrective_actions, {', '.join(x.code for x in projects)}, "
        f"as of {day.isoformat()}",
        scope=", ".join(x.code for x in projects),
        refs=[r["ref"] for r in out[:limit]],
    )
    return {
        "as_of": day.isoformat(),
        "total": len(out),
        "overdue_total": sum(1 for r in out if r["overdue"]),
        "items": out[:limit],
        "truncated": len(out) > limit,
        "cite": cid,
    }, narrowed or n2


def _group_label(
    ctx: ToolContext,
    group_by: str,
    site: uuid.UUID,
    zone: uuid.UUID | None,
    eng: uuid.UUID | None,
    d: date,
    cat: str | None,
    codes: dict[str, dict[Any, str]],
) -> str:
    if group_by == "site":
        return codes["site"].get(site, "?")
    if group_by == "zone":
        return codes["zone"].get(zone, "no zone") if zone else "no zone"
    if group_by == "contractor":
        return codes["eng"].get(eng, "?") if eng else "?"
    if group_by == "week":
        ws = ctx.project.settings.week_start if ctx.project.settings else "sunday"
        return week_start(d, ws).isoformat()  # type: ignore[arg-type]
    return cat or "not recorded"


def _codes(db: Session) -> dict[str, dict[Any, str]]:
    return {
        "site": dict(db.execute(select(Site.id, Site.code)).all()),
        "zone": dict(db.execute(select(Zone.id, Zone.code)).all()),
        "eng": dict(
            db.execute(
                select(ProjectEngagement.id, Contractor.short_code).join(
                    Contractor, Contractor.id == ProjectEngagement.contractor_id
                )
            ).all()
        ),
    }


def t_list_observations_summary(
    ctx: ToolContext, params: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    sc = _scope(ctx, q)
    w = sc.window
    group_by = str(params.get("group_by") or "category")
    codes = _codes(ctx.db)
    tot: Counter[str] = Counter()
    safe: Counter[str] = Counter()
    for proj in sc.projects:
        stmt = obs_svc.scoped_query(ctx.p, proj).where(
            Observation.observed_date >= w.start, Observation.observed_date <= w.end
        )
        for o in ctx.db.scalars(stmt):
            if not (sc.flt.site_ok(o.site_id) and sc.flt.eng_ok(o.observed_engagement_id)):
                continue
            if not sc.flt.zone_ok(o.zone_id, sc.facts.zones):
                continue
            cat = o.obs_type.value if group_by == "obs_type" else o.category.value
            k = _group_label(
                ctx,
                group_by,
                o.site_id,
                o.zone_id,
                o.observed_engagement_id,
                o.observed_date,
                cat,
                codes,
            )
            tot[k] += 1
            if obs_svc.is_safe(o):
                safe[k] += 1
    rows = [
        {"group": k, "total": n, "safe": safe[k], "unsafe": n - safe[k]}
        for k, n in sorted(tot.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    cid = ctx.cite(
        AiTool.list_observations_summary,
        f"Observations by {group_by} — list_observations_summary, {service.scope_label(sc)}, "
        f"{sc.period.label_en}",
        period=sc.period.label_en,
        scope=service.scope_label(sc),
    )
    return {
        "period": sc.period.label_en,
        "scope": service.scope_label(sc),
        "group_by": group_by,
        "total": sum(tot.values()),
        "safe": sum(safe.values()),
        "unsafe": sum(tot.values()) - sum(safe.values()),
        "groups": rows,
        "cite": cid,
    }, narrowed or sc.narrowed


def t_list_inspections_summary(
    ctx: ToolContext, params: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    sc = _scope(ctx, q)
    w = sc.window
    group_by = str(params.get("group_by") or "type")
    codes = _codes(ctx.db)
    stats: dict[str, Counter[str]] = defaultdict(Counter)
    scores: dict[str, list[Decimal]] = defaultdict(list)
    T = InspectionTimeliness  # noqa: N806
    for proj in sc.projects:
        grace = hse_settings.get(ctx.db, proj.id).inspection_grace_days
        for ins in ctx.db.scalars(ins_svc._scoped(ctx.p, proj)):
            d = ins.planned_date or ins.completed_date
            if d is None or not (w.start <= d <= w.end):
                continue
            if not (sc.flt.site_ok(ins.site_id) and sc.flt.eng_ok(ins.engagement_id)):
                continue
            k = _group_label(
                ctx,
                "site" if group_by == "site" else group_by,
                ins.site_id,
                ins.zone_id,
                ins.engagement_id,
                d,
                ins.inspection_type.value,
                codes,
            )
            tl = ins_svc.timeliness(ins, grace)
            c = stats[k]
            if ins.plan_id is not None and ins.planned_date is not None:
                c["planned"] += 1
            c[
                {
                    T.on_time: "on_time",
                    T.late: "late",
                    T.missed: "missed",
                    T.cancelled: "cancelled",
                    T.unplanned: "unplanned",
                }.get(tl, "open")
            ] += 1
            sc_ = ins_svc.score(ins)
            if sc_ is not None:
                scores[k].append(sc_)
    rows = []
    for k in sorted(stats):
        c = stats[k]
        avg = sum(scores[k], Decimal(0)) / len(scores[k]) if scores[k] else None
        rows.append(
            {
                "group": k,
                "planned": c["planned"],
                "on_time": c["on_time"],
                "late": c["late"],
                "missed": c["missed"],
                "cancelled": c["cancelled"],
                "unplanned": c["unplanned"],
                "not_yet_due_or_open": c["open"],
                "average_score": fmt.percent(avg, 1) if avg is not None else None,
            }
        )
    cid = ctx.cite(
        AiTool.list_inspections_summary,
        f"Inspections by {group_by} — list_inspections_summary, {service.scope_label(sc)}, "
        f"{sc.period.label_en}",
        period=sc.period.label_en,
        scope=service.scope_label(sc),
    )
    return {
        "period": sc.period.label_en,
        "scope": service.scope_label(sc),
        "group_by": group_by,
        "groups": rows,
        "cite": cid,
    }, narrowed or sc.narrowed


def _p_display(p: float | None) -> str | None:
    if p is None:
        return None
    return "<0.001" if p < 0.001 else fmt.dec_str(Decimal(str(p)), 3)


def _f2(v: float | None) -> str | None:
    return None if v is None else fmt.number(Decimal(str(v)), 2)


def t_compare_groups(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    sc = _scope(ctx, q)
    dim = CompareDimension(params["dimension"])
    measure = str(params.get("measure") or "injury_cases")
    cats = [CaseCategory(c) for c in params.get("categories") or []]
    comp, basis, labels = groups.compare_groups(
        ctx.db, sc, dim, measure, cats, params.get("event_type"), params.get("reference")
    )
    base_label = fmt.hours_label(sc.config.rate_base)[0] if basis == "man_hours" else None
    cid = ctx.cite(
        AiTool.compare_groups,
        f"{measure} by {dim.value} — compare_groups, {service.scope_label(sc)}, "
        f"{sc.period.label_en}" + (f", {base_label}" if base_label else ""),
        period=sc.period.label_en,
        scope=service.scope_label(sc),
        base=base_label,
    )
    return {
        "period": sc.period.label_en,
        "scope": service.scope_label(sc),
        "measure": measure,
        "dimension": dim.value,
        "exposure_basis": basis,
        "rate_label": base_label,
        "reference_group": labels.get(comp.reference or "", comp.reference),
        "groups": [
            {
                "group": labels.get(g.key, g.key),
                "count": g.count,
                "exposure": fmt.number(Decimal(str(g.exposure)), 0)
                if g.exposure is not None
                else None,
                "rate": _f2(g.rate),
                "rate_ratio": _f2(g.rate_ratio),
                "ci95_low": _f2(g.ci_low),
                "ci95_high": _f2(g.ci_high),
            }
            for g in comp.groups
        ],
        "test": comp.test,
        "p_value": _p_display(comp.p_value),
        "n": comp.total_events,
        "higher_group": labels.get(comp.higher_group or "", comp.higher_group),
        "sample_sufficient": comp.sample_sufficient,
        "supports_association": comp.supports_association,
        "rule": "State an association only when supports_association is true; say "
        "'associated with', never 'caused by'. Otherwise: 'No statistically supported "
        "difference (n = …)'.",
        "cite": cid,
    }, narrowed or sc.narrowed


def t_get_data_quality(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    sc = _scope(ctx, q)
    dq = service.data_quality(ctx.db, sc)
    cid = ctx.cite(
        AiTool.get_data_quality,
        f"Data completeness {dq.completeness.display} — get_data_quality, "
        f"{service.scope_label(sc)}, {dq.context.period.label_en}",
        metric=KpiMetric.K45,
        value=dq.completeness.display,
        period=dq.context.period.label_en,
        scope=service.scope_label(sc),
    )
    return {
        "context": _context(dq.context, sc),
        "completeness": dq.completeness.display,
        "missing_engagement_days": dq.context.missing_engagement_days,
        "missing_returns_sample": [
            {
                "contractor": m.engagement.short_code,
                "site": m.site_code,
                "date": m.work_date.isoformat(),
            }
            for m in dq.missing_returns[:20]
        ],
        "provisional_cases": dq.provisional_cases,
        "late_reports": dq.late_reports,
        "investigations_overdue": dq.investigations_overdue,
        "restated_months": dq.restated_months,
        "cite": cid,
    }, narrowed or sc.narrowed


def t_get_lti_free(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    sc = _scope(ctx, q)
    lf = service.lti_free_read(sc)
    cid = ctx.cite(
        AiTool.get_lti_free,
        f"LTI-free {lf.days_display} days / {lf.man_hours_display} h — get_lti_free, "
        f"{service.scope_label(sc)}, as of {lf.as_of.isoformat()}",
        metric=KpiMetric.K28,
        value=lf.days_display,
        scope=service.scope_label(sc),
        refs=[lf.last_lti_incident_ref] if lf.last_lti_incident_ref else [],
    )
    return {
        "scope": service.scope_label(sc),
        "as_of": lf.as_of.isoformat(),
        "days": lf.days_display,
        "man_hours": lf.man_hours_display,
        "basis": lf.basis,
        "last_lti_date": lf.last_lti_date.isoformat() if lf.last_lti_date else None,
        "last_lti_ref": lf.last_lti_incident_ref,
        "run_start": lf.run_start.isoformat(),
        "longest_run_days": lf.longest_run_days,
        "cite": cid,
    }, narrowed or sc.narrowed


def _one_project(ctx: ToolContext, params: dict[str, Any]) -> tuple[Project | None, bool]:
    code = params.get("project_code")
    projects, narrowed = _allowed_projects(ctx, [code] if code else None)
    return (projects[0] if projects else None), narrowed


def t_get_settings_and_targets(
    ctx: ToolContext, params: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    proj, narrowed = _one_project(ctx, params)
    if proj is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    s = hse_settings.get(ctx.db, proj.id)
    ps = proj.settings
    ltifr = ps.ltifr_base_hours if ps else kscope.DEFAULT_LTIFR
    rate = ps.rate_base_hours if ps else kscope.DEFAULT_RATE
    cid = ctx.cite(
        AiTool.get_settings_and_targets,
        f"Settings — get_settings_and_targets, {proj.code}",
        scope=proj.code,
    )
    return {
        "project": proj.code,
        "ltifr_base": fmt.hours_label(ltifr)[0],
        "rate_base": fmt.hours_label(rate)[0],
        "low_exposure_hours": fmt.number(s.low_exposure_hours, 0),
        "completeness_threshold_pct": s.completeness_threshold_pct,
        "lost_days_cap": s.lost_days_cap,
        "fatality_lost_days_charge": s.fatality_lost_days_charge,
        "include_commuting_in_rates": s.include_commuting_in_rates,
        "new_starter_days": s.new_starter_days,
        "heat_season": f"{s.heat_season_start} to {s.heat_season_end}",
        "inspection_grace_days": s.inspection_grace_days,
        "ca_max_extensions": s.ca_max_extensions,
        "leading_warning_drop_pct": s.leading_warning_drop_pct,
        "leading_warning_rise_pct": s.leading_warning_rise_pct,
        "kpi_targets": dict(s.kpi_targets or {}),
        "cite": cid,
    }, narrowed


def t_get_leading_warnings(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    proj, narrowed = _one_project(ctx, params)
    if proj is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    q, _ = _query(ctx, {"project_codes": [proj.code]})
    assert q is not None  # noqa: S101
    sc = _scope(ctx, q)
    res = views.leading_indicators(sc, min(int(params.get("months") or 3), 12))
    cid = ctx.cite(
        AiTool.get_leading_warnings,
        f"Leading warnings — get_leading_warnings, {service.scope_label(sc)}, "
        + ", ".join(res.evaluated_months),
        period=", ".join(res.evaluated_months),
        scope=service.scope_label(sc),
    )
    return {
        "scope": service.scope_label(sc),
        "evaluated_months": res.evaluated_months,
        "warnings": [
            {
                "code": w.code.value,
                "month": w.month,
                "contractor_tree": w.engagement.short_code if w.engagement else None,
                "message": w.message_en,
                "inputs": [{"name": i.label_en, "value": i.display} for i in w.inputs],
            }
            for w in res.warnings
        ],
        "cite": cid,
    }, narrowed or sc.narrowed


def t_get_expiring_items(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    proj, narrowed = _one_project(ctx, params)
    if proj is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    res = dash_svc.expiring_items(
        ctx.db,
        ctx.p,
        proj.id,
        min(int(params.get("within_days") or 14), 90),
        bool(params.get("include_overdue", True)),
        ctx.as_of,
    )
    items = []
    for i in res.items:
        access = i.kind in ACCESS_KINDS
        ref = i.ref
        if access and ref and (ref.startswith("WKR-") or i.kind in PERSON_KINDS):
            ref = None  # AI-5 / KA-5: no worker numbers or person-linked refs
        items.append(
            {
                "kind": i.kind.value,
                "ref": ref,
                "title": i.kind.value.replace("_", " ")
                if access
                else redact(i.title_en, ctx.names()),
                "due_date": i.due_date.isoformat(),
                "days_left": i.days_left,
                "contractor": i.engagement.short_code if i.engagement else None,
            }
        )
    cid = ctx.cite(
        AiTool.get_expiring_items,
        f"Due and overdue items — get_expiring_items, {proj.code}, as of {ctx.as_of.isoformat()}",
        scope=proj.code,
        refs=[str(i["ref"]) for i in items if i["ref"]],
    )
    return {
        "project": proj.code,
        "as_of": ctx.as_of.isoformat(),
        "items": items,
        "cite": cid,
    }, narrowed


def t_get_access_kpis(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """T14 (1-dashboard v1.1 §5.9; 2-access-permits KA-5): aggregates only."""
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    try:
        sc = kscope.build(ctx.db, ctx.p, q, Capability.access_kpi_view)
    except ApiError:
        return {"no_access": True, "message": NO_ACCESS}, True
    if not access_views.has_access(sc):
        return {
            "no_access": True,
            "message": "Access KPIs exist only for airport projects you may view (capability 77).",
        }, True
    flt = params.get("filters") or {}
    gate_id = None
    gate_codes = [str(g) for g in flt.get("gate_codes") or []]
    if gate_codes:
        gate_id = ctx.db.scalar(
            select(Gate.id).where(
                Gate.gate_code == gate_codes[0], Gate.project_id.in_(q.project_ids)
            )
        )
        if gate_id is None:
            raise ToolError(f"Unknown gate {gate_codes[0]}.")
    metrics = [KpiMetric(m) for m in params.get("metrics") or []] or None
    group_by = [AccessKpiGroupBy(g) for g in params.get("group_by") or []]
    res = access_views.access_kpis(ctx.db, sc, metrics, group_by, gate_id)
    codes, who = _codes_who(sc)
    period = res.context.period.label_en
    out = []
    for v in res.metrics:
        row = _kpi(v)
        row["cite"] = ctx.cite(
            AiTool.get_access_kpis,
            f"{v.short_label_en} {v.display} — get_access_kpis, {codes}, {period}, {who}",
            metric=v.metric,
            value=v.display,
            period=period,
            scope=service.scope_label(sc),
        )
        out.append(row)
    breakdowns = [
        {
            "metric": b.metric,
            "group_by": b.group_by.value,
            "rows": [
                {"key": r.key, "label": r.label_en, "value": r.display,
                 "numerator": r.numerator, "denominator": r.denominator}
                for r in b.rows
            ],
        }
        for b in res.breakdowns
    ]  # fmt: skip
    band = None
    if res.band is not None:
        band = {
            k: v for k, v in res.band.model_dump(mode="json").items() if not isinstance(v, list)
        }
    return {
        "scope": service.scope_label(sc),
        "period": period,
        "note": access_views.GATE_NOTE,
        "band": band,
        "kpis": out,
        "breakdowns": breakdowns,
    }, narrowed or sc.narrowed


def t_get_ptw_kpis(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """T15 (3-ptw KP-5): aggregates only (AI-5)."""
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    flt = params.get("filters") or {}
    q = dataclasses.replace(q, permit_types=[PermitType(t) for t in flt.get("permit_types") or []])
    try:
        sc = kscope.build(ctx.db, ctx.p, q, Capability.ptw_kpi_view)
    except ApiError:
        return {"no_access": True, "message": NO_ACCESS}, True
    if not ptw_views.has_ptw(sc):
        return {
            "no_access": True,
            "message": "PTW KPIs need capability 103 on the project.",
        }, True
    metrics = [KpiMetric(m) for m in params.get("metrics") or []] or None
    group_by = [PtwKpiGroupBy(g) for g in params.get("group_by") or []]
    res = ptw_views.ptw_kpis(ctx.db, sc, metrics, group_by)
    codes, who = _codes_who(sc)
    period = res.context.period.label_en
    out = []
    for v in res.metrics:
        row = _kpi(v)
        row["cite"] = ctx.cite(
            AiTool.get_ptw_kpis,
            f"{v.short_label_en} {v.display} — get_ptw_kpis, {codes}, {period}, {who}",
            metric=v.metric,
            value=v.display,
            period=period,
            scope=service.scope_label(sc),
        )
        out.append(row)
    breakdowns = [
        {
            "metric": b.metric,
            "group_by": b.group_by.value,
            "rows": [
                {"key": r.key, "label": r.label_en, "value": r.display,
                 "numerator": r.numerator, "denominator": r.denominator}
                for r in b.rows
            ],
        }
        for b in res.breakdowns
    ]  # fmt: skip
    band = None
    if res.band is not None:
        band = {
            k: v for k, v in res.band.model_dump(mode="json").items() if not isinstance(v, list)
        }
    return {
        "scope": service.scope_label(sc),
        "period": period,
        "band": band,
        "kpis": out,
        "breakdowns": breakdowns,
    }, narrowed or sc.narrowed


def t_get_certification_kpis(
    ctx: ToolContext, params: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """T16 (4-third-party-cert KC-4): aggregates only (AI-5). Group rows carry categories,
    certificate types, contractors, TPI codes, defect categories, reason codes or months —
    never people, certificate numbers, ban reasons or verification-failure details."""
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    flt = params.get("filters") or {}
    q = dataclasses.replace(
        q,
        equipment_categories=[
            EquipmentCertCategory(c) for c in flt.get("equipment_categories") or []
        ],
        cert_types=[str(t) for t in flt.get("cert_types") or []],
    )
    try:
        sc = kscope.build(ctx.db, ctx.p, q, Capability.cert_kpi_view)
    except ApiError:
        return {"no_access": True, "message": NO_ACCESS}, True
    if not cert_views.has_cert(sc):
        return {
            "no_access": True,
            "message": "Certification KPIs need capability 122 on the project.",
        }, True
    metrics = [KpiMetric(m) for m in params.get("metrics") or []] or None
    group_by = [CertKpiGroupBy(g) for g in params.get("group_by") or []]
    res = cert_views.cert_kpis(ctx.db, sc, metrics, group_by)
    codes, who = _codes_who(sc)
    period = res.context.period.label_en
    out = []
    for v in res.metrics:
        row = _kpi(v)
        row["cite"] = ctx.cite(
            AiTool.get_certification_kpis,
            f"{v.short_label_en} {v.display} — get_certification_kpis, {codes}, {period}, {who}",
            metric=v.metric,
            value=v.display,
            period=period,
            scope=service.scope_label(sc),
        )
        out.append(row)
    breakdowns = [
        {
            "metric": b.metric,
            "group_by": b.group_by.value,
            "rows": [
                {"key": r.key, "label": r.label_en, "value": r.display,
                 "numerator": r.numerator, "denominator": r.denominator}
                for r in b.rows
            ],
        }
        for b in res.breakdowns
    ]  # fmt: skip
    band = None
    if res.band is not None:
        band = {
            k: v for k, v in res.band.model_dump(mode="json").items() if not isinstance(v, list)
        }
    return {
        "scope": service.scope_label(sc),
        "period": period,
        "band": band,
        "kpis": out,
        "breakdowns": breakdowns,
    }, narrowed or sc.narrowed


def t_propose_chart(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    q, narrowed = _query(ctx, params)
    if q is None:
        return {"no_access": True, "message": NO_ACCESS}, True
    sc = _scope(ctx, q)
    spec = charts.chart(ctx.db, sc, ChartId(params["chart_id"]))
    spec = spec.model_copy(update={"chart_id": "ai-1"})
    ctx.chart = spec
    series = [
        {"series": s.label_en, "points": [{"x": pt.x, "value": pt.display} for pt in s.points]}
        for s in spec.series
    ]
    cid = ctx.cite(
        AiTool.propose_chart,
        f"{spec.title_en} — {spec.citation.tool}, {spec.citation.scope_label_en}, "
        f"{spec.citation.period_label_en}",
        period=spec.citation.period_label_en,
        scope=spec.citation.scope_label_en,
        base=spec.citation.base_label_en,
    )
    return {
        "chart": spec.title_en,
        "attached": True,
        "series": series,
        "cite": cid,
    }, narrowed or sc.narrowed


HANDLERS: dict[str, Callable[[ToolContext, dict[str, Any]], tuple[dict[str, Any], bool]]] = {
    AiTool.get_kpis.value: t_get_kpis,
    AiTool.get_kpi_timeseries.value: t_get_kpi_timeseries,
    AiTool.get_breakdown.value: t_get_breakdown,
    AiTool.search_incidents.value: t_search_incidents,
    AiTool.get_incident.value: t_get_incident,
    AiTool.list_corrective_actions.value: t_list_corrective_actions,
    AiTool.list_observations_summary.value: t_list_observations_summary,
    AiTool.list_inspections_summary.value: t_list_inspections_summary,
    AiTool.compare_groups.value: t_compare_groups,
    AiTool.get_data_quality.value: t_get_data_quality,
    AiTool.get_lti_free.value: t_get_lti_free,
    AiTool.get_settings_and_targets.value: t_get_settings_and_targets,
    AiTool.get_leading_warnings.value: t_get_leading_warnings,
    AiTool.get_expiring_items.value: t_get_expiring_items,
    AiTool.propose_chart.value: t_propose_chart,
    AiTool.get_access_kpis.value: t_get_access_kpis,
    AiTool.get_ptw_kpis.value: t_get_ptw_kpis,
    AiTool.get_certification_kpis.value: t_get_certification_kpis,
}


def result_hash(result: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()


def run(ctx: ToolContext, name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Executes one tool call; errors become results the model can read."""
    handler = HANDLERS.get(name)
    narrowed = False
    if handler is None:
        result: dict[str, Any] = {"error": f"Unknown tool {name}."}
    else:
        try:
            with ctx.db.begin_nested():
                result, narrowed = handler(ctx, dict(params or {}))
        except ApiError as e:
            result = {"error": e.code.value, "message": str(e)}
        except (ToolError, ValueError, KeyError) as e:
            result = {"error": "INVALID_PARAMETERS", "message": str(e)}
    if narrowed:
        result["scope_narrowed"] = True
        result.setdefault(
            "scope_note", "Some requested data is outside your access and was left out."
        )
    ctx.runs.append(ToolRun(name, dict(params or {}), result, narrowed, result_hash(result)))
    return result
