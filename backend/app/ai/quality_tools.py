"""AI tools T26–T29 of the Quality module (spec 8-quality §E.9, Q-AI-01…04): Quality KPIs, NCR
search, SPC status and the cold-chain summary. Every tool checks capability 238 (with 40 to ask)
per project; the Viewer / Client gets T26, T28 and T29 aggregates and no T27. No person names,
signatures or contact data reach the AI layer (P8-4); supplier, contractor and customer names are
business names and may appear. Free texts (NCR titles) are redacted (P1-8)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.enums import Capability, CapabilityScope
from app.core.hse_enums import AiTool
from app.core.quality.common import NCR_LIVE, QNcrStatus
from app.core.quality.q4 import QKpi
from app.kpi import quality as qk
from app.models import Project, ProjectEngagement
from app.models.quality import QNcr, QSupplier

if TYPE_CHECKING:
    from app.ai.tools import ToolContext

NO_ACCESS = "No access to the requested data."
GROUP_BY = (
    "month",
    "supplier",
    "contractor",
    "category",
    "cause_category",
    "zone",
    "test_type",
    "process",
)
QPERIOD = {
    "type": "object",
    "description": "start and end dates (inclusive); default the last complete month.",
    "properties": {
        "start": {"type": "string", "format": "date"},
        "end": {"type": "string", "format": "date"},
    },
}


def defs(tool: Any) -> list[dict[str, Any]]:
    projects = {
        "type": "array",
        "items": {"type": "string"},
        "description": "Project codes; default = the current project.",
    }
    return [
        tool(
            AiTool.get_quality_kpis,
            "T26: Quality KPIs K-141..K-169 (value, numerator, denominator, chips, target, RAG) "
            "for a period, optionally grouped (month, supplier, contractor, category, "
            "cause_category, zone, test_type, process). Aggregates only.",
            {
                "project_codes": projects,
                "period": QPERIOD,
                "metrics": {
                    "type": "array",
                    "items": {"type": "string", "enum": [k.value for k in QKpi]},
                },
                "filters": {
                    "type": "object",
                    "properties": {
                        "supplier_code": {"type": "string"},
                        "contractor_code": {"type": "string"},
                        "test_type": {"type": "string"},
                    },
                },
                "group_by": {"type": "string", "enum": list(GROUP_BY)},
            },
            [],
        ),
        tool(
            AiTool.search_ncrs,
            "T27: search NCRs (status, class, category, cause_category, source_type, supplier, "
            "contractor, opened_from / opened_to, overdue, repeat; limit ≤ 50). Returns NCR "
            "numbers, redacted titles, class, status, categories, contractor and supplier names, "
            "age, target date, repeat flag; cost only with capability 242. Never person names.",
            {
                "project_codes": projects,
                "filters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "class": {"type": "string"},
                        "category": {"type": "string"},
                        "cause_category": {"type": "string"},
                        "source_type": {"type": "string"},
                        "supplier_code": {"type": "string"},
                        "contractor_code": {"type": "string"},
                        "opened_from": {"type": "string", "format": "date"},
                        "opened_to": {"type": "string", "format": "date"},
                        "overdue": {"type": "boolean"},
                        "repeat": {"type": "boolean"},
                    },
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            [],
        ),
        tool(
            AiTool.get_spc_status,
            "T28: SPC charts (all or by code): type, centre and limits, provisional flag, last "
            "25 points, signals (rule, point) and Cp / Cpk.",
            {
                "project_codes": projects,
                "chart_codes": {"type": "array", "items": {"type": "string"}},
                "period": QPERIOD,
            },
            [],
        ),
        tool(
            AiTool.get_cold_chain_summary,
            "T29: cold chain for a period: excursions by zone and severity, time out of range and "
            "coverage per zone, MKT, mapping validity, open holds from excursions, transport "
            "temperature compliance.",
            {
                "project_codes": projects,
                "period": QPERIOD,
                "zone_codes": {"type": "array", "items": {"type": "string"}},
            },
            [],
        ),
    ]


def _projects(
    ctx: ToolContext, codes: list[str] | None, need_names: bool = False
) -> tuple[list[Project], bool]:
    """Q-AI-01: 40 (ask) and 238 on the project, not the responsible-person scope N."""
    wanted = [c.strip() for c in codes or [] if c and c.strip()]
    rows = (
        list(ctx.db.scalars(select(Project).where(Project.code.in_(wanted))))
        if wanted
        else [ctx.project]
    )
    ok = []
    for x in rows:
        g = ctx.p.grant(x.id, Capability.quality_view)
        if (
            ctx.p.grant(x.id, Capability.ai_ask) is None
            or g is None
            or g.scope == CapabilityScope.responsible
        ):
            continue
        ok.append(x)
    return ok, len(ok) < max(len(wanted), 1)


def _period(params: dict[str, Any], as_of: date) -> tuple[date, date]:
    per = params.get("period") or {}
    if per.get("start") and per.get("end"):
        return date.fromisoformat(str(per["start"])[:10]), date.fromisoformat(str(per["end"])[:10])
    end = as_of.replace(day=1) - timedelta(days=1)
    return end.replace(day=1), end


def _viewer(ctx: ToolContext, project: Project) -> bool:
    from app.services.quality.ncr.core import read_only_viewer  # noqa: PLC0415

    return read_only_viewer(ctx.p, project.id)


def _supplier(ctx: ToolContext, code: str | None) -> QSupplier | None:
    return (
        ctx.db.scalar(select(QSupplier).where(QSupplier.supplier_code == code.upper()))
        if code
        else None
    )


def _eng(ctx: ToolContext, project: Project, code: str | None) -> ProjectEngagement | None:
    from app.models import Contractor  # noqa: PLC0415

    if not code:
        return None
    return ctx.db.scalar(
        select(ProjectEngagement)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(ProjectEngagement.project_id == project.id, Contractor.short_code == code.upper())
    )


def _clean(r: dict[str, Any], hide_cost: bool) -> dict[str, Any]:
    out = {
        k: r[k] for k in ("kpi", "name_en", "unit", "value", "numerator", "denominator", "display")
    }
    out["chips"] = [
        {"code": c["code"], "label": c["label_en"], "value": c["value"]} for c in r["chips"]
    ]
    if hide_cost and r["kpi"] == QKpi.K148.value:
        out.update({"value": None, "numerator": None, "display": "—"})
        out["chips"] = [c for c in out["chips"] if c["code"] == "copq_pct"]
    return out


def t_get_quality_kpis(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """T26 (Q-AI-01): aggregates only."""
    from app.kpi.quality_views import kpi_filter  # noqa: PLC0415

    projects, narrowed = _projects(ctx, params.get("project_codes"))
    if not projects:
        return {"no_access": True, "message": NO_ACCESS}, True
    start, end = _period(params, ctx.as_of)
    wanted = [QKpi(m) for m in params.get("metrics") or []]
    fl = params.get("filters") or {}
    out = []
    for pr in projects:
        sup = _supplier(ctx, fl.get("supplier_code"))
        eng = _eng(ctx, pr, fl.get("contractor_code"))
        flt = kpi_filter(
            ctx.p,
            pr.id,
            qk.QFilter(
                supplier_id=sup.id if sup else None,
                engagement_ids=frozenset({eng.id}) if eng else None,
                test_type=fl.get("test_type"),
            ),
        )
        e = qk.Engine(ctx.db, pr, start, end, ctx.as_of, flt)
        hide = _viewer(ctx, pr)
        metrics = wanted or qk.tiles_for(e.profile)
        rows = [_clean(e.result(k).dump(), hide) for k in metrics if qk._applies(e, k)]
        for r in rows:
            t = qk.target_of(ctx.db, pr.id, QKpi(r["kpi"]), end)
            r["target"] = str(t) if t is not None else None
        res: dict[str, Any] = {"project": pr.code, "period": f"{start} – {end}", "kpis": rows}
        gb = params.get("group_by")
        if gb:
            res["group_by"] = gb
            res["groups"] = _groups(ctx, pr, e, gb, metrics, hide)
        out.append(res)
    cid = ctx.cite(
        AiTool.get_quality_kpis,
        f"Quality KPIs — get_quality_kpis, {', '.join(p.code for p in projects)}, {start} – {end}",
        period=f"{start} – {end}",
        scope=", ".join(p.code for p in projects),
    )
    return {"projects": out, "cite": cid}, narrowed


def _groups(
    ctx: ToolContext, pr: Project, e: qk.Engine, gb: str, metrics: list[QKpi], hide: bool
) -> list[dict[str, Any]]:
    from sqlalchemy import func  # noqa: PLC0415

    db = ctx.db
    if gb == "month":
        rows = []
        for y, m in e.months():
            ms = date(y, m, 1)
            sub = qk.Engine(db, pr, ms, qk.month_end(ms), ctx.as_of, e.flt)
            rows.append(
                {
                    "key": ms.isoformat()[:7],
                    "kpis": [
                        _clean(sub.result(k).dump(), hide) for k in metrics if qk._applies(sub, k)
                    ],
                }
            )
        return rows
    if gb == "supplier":
        cnt = db.execute(
            select(QSupplier.supplier_code, QSupplier.legal_name_en, func.count(QNcr.id))
            .join(QNcr, QNcr.supplier_id == QSupplier.id)
            .where(*e._opened())
            .group_by(QSupplier.supplier_code, QSupplier.legal_name_en)
            .order_by(func.count(QNcr.id).desc())
        ).all()
        return [{"key": c, "supplier": n, "ncrs_raised": int(k)} for c, n, k in cnt]
    if gb == "contractor":
        from app.models import Contractor  # noqa: PLC0415

        cnt = db.execute(
            select(Contractor.short_code, Contractor.legal_name_en, func.count(QNcr.id))
            .join(ProjectEngagement, ProjectEngagement.contractor_id == Contractor.id)
            .join(QNcr, QNcr.responsible_engagement_id == ProjectEngagement.id)
            .where(*e._opened())
            .group_by(Contractor.short_code, Contractor.legal_name_en)
            .order_by(func.count(QNcr.id).desc())
        ).all()
        return [{"key": c, "contractor": n, "ncrs_raised": int(k)} for c, n, k in cnt]
    if gb in ("category", "cause_category"):
        par = e.k150(gb).extra["pareto"]
        return [
            {"key": r["code"], "count": r["count"], "cumulative_pct": r["cumulative_pct"]}
            for r in par["rows"]
        ]
    if gb == "zone":
        from app.models import Zone  # noqa: PLC0415

        zones = e.result(QKpi.K162).extra.get("zones") or []
        codes = (
            {
                z.id: z.code
                for z in db.scalars(select(Zone).where(Zone.id.in_([x["zone_id"] for x in zones])))
            }
            if zones
            else {}
        )
        return [
            {
                "key": codes.get(x["zone_id"], str(x["zone_id"])),
                "tor_pct": str(x["tor_pct"]),
                "coverage_pct": str(x["coverage_pct"]),
            }
            for x in zones
        ]
    if gb == "test_type":
        return [
            {"key": c["code"].split(":", 1)[1], "fail_pct": c["value"]}
            for c in e.result(QKpi.K152).chips
        ]
    return [{"key": k, **v} for k, v in e.dpmo().items()]


def t_search_ncrs(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """T27: never for the Viewer / Client; no person names, finding or RCA texts, photos."""
    from app.ai.masking import redact  # noqa: PLC0415
    from app.services.quality.ncr.core import _scope_cond  # noqa: PLC0415

    projects, narrowed = _projects(ctx, params.get("project_codes"))
    projects = [x for x in projects if not _viewer(ctx, x)]
    if not projects:
        return {"no_access": True, "message": NO_ACCESS}, True
    f = params.get("filters") or {}
    limit = max(1, min(int(params.get("limit") or 20), 50))
    rows = []
    for pr in projects:
        stmt = select(QNcr).where(
            QNcr.project_id == pr.id,
            QNcr.status != QNcrStatus.draft,
            _scope_cond(ctx.db, ctx.p, pr),
        )
        if f.get("status"):
            stmt = stmt.where(QNcr.status == f["status"])
        if f.get("class"):
            stmt = stmt.where(QNcr.classification == f["class"])
        for k, col in (
            ("category", QNcr.category),
            ("cause_category", QNcr.cause_category),
            ("source_type", QNcr.source_type),
        ):
            if f.get(k):
                stmt = stmt.where(col == f[k])
        sup = _supplier(ctx, f.get("supplier_code"))
        if sup:
            stmt = stmt.where(QNcr.supplier_id == sup.id)
        eng = _eng(ctx, pr, f.get("contractor_code"))
        if eng:
            stmt = stmt.where(QNcr.responsible_engagement_id == eng.id)
        if f.get("opened_from"):
            stmt = stmt.where(QNcr.opened_date >= date.fromisoformat(str(f["opened_from"])[:10]))
        if f.get("opened_to"):
            stmt = stmt.where(QNcr.opened_date <= date.fromisoformat(str(f["opened_to"])[:10]))
        if f.get("repeat"):
            stmt = stmt.where(QNcr.repeat_of_id.is_not(None))
        if f.get("overdue"):
            stmt = stmt.where(QNcr.status.in_(list(NCR_LIVE)), QNcr.target_close_date < ctx.as_of)
        costs = ctx.p.grant(pr.id, Capability.ncr_manage) is not None
        for n in ctx.db.scalars(stmt.order_by(QNcr.opened_date.desc()).limit(limit)):
            e = (
                ctx.db.get(ProjectEngagement, n.responsible_engagement_id)
                if n.responsible_engagement_id
                else None
            )
            s = ctx.db.get(QSupplier, n.supplier_id) if n.supplier_id else None
            row = {
                "ncr_no": n.ncr_no,
                "title": redact(n.title, ctx.names()),
                "class": n.classification.value if n.classification else None,
                "status": n.status.value,
                "category": n.category.value if n.category else None,
                "cause_category": n.cause_category.value if n.cause_category else None,
                "source_type": n.source_type.value,
                "contractor": e.contractor.legal_name_en if e else None,
                "supplier": s.legal_name_en if s else None,
                "age_days": (ctx.as_of - n.opened_date).days
                if n.opened_date and n.status in NCR_LIVE
                else None,
                "target_close_date": n.target_close_date.isoformat()
                if n.target_close_date
                else None,
                "repeat": n.repeat_of_id is not None,
            }
            if costs:
                row["cost_gross_sar"] = str(n.cost_gross_sar)
            rows.append(row)
    cid = ctx.cite(
        AiTool.search_ncrs,
        f"NCRs — search_ncrs, {', '.join(p.code for p in projects)}",
        refs=[str(r["ncr_no"]) for r in rows if r["ncr_no"]],
    )
    return {"ncrs": rows[:limit], "cite": cid}, narrowed


def t_get_spc_status(ctx: ToolContext, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    from app.models.quality.q4 import QSpcChart  # noqa: PLC0415
    from app.services.quality.q4 import spc  # noqa: PLC0415

    projects, narrowed = _projects(ctx, params.get("project_codes"))
    if not projects:
        return {"no_access": True, "message": NO_ACCESS}, True
    per = params.get("period") or {}
    start = date.fromisoformat(str(per["start"])[:10]) if per.get("start") else None
    end = date.fromisoformat(str(per["end"])[:10]) if per.get("end") else None
    codes = [c.upper() for c in params.get("chart_codes") or []]
    out = []
    for pr in projects:
        stmt = select(QSpcChart).where(QSpcChart.project_id == pr.id, QSpcChart.active.is_(True))
        if codes:
            stmt = stmt.where(QSpcChart.code.in_(codes))
        for ch in ctx.db.scalars(stmt.order_by(QSpcChart.code)):
            r = spc.chart_read(ctx.db, ch, start, end)["result"]
            out.append(
                {
                    "project": pr.code,
                    "code": ch.code,
                    "title": ch.title_en,
                    "type": ch.chart_type.value,
                    "centre": r.get("cl"),
                    "ucl": r.get("ucl"),
                    "lcl": r.get("lcl"),
                    "provisional": r.get("provisional"),
                    "limits_drawn": r.get("limits_drawn"),
                    "points": r.get("points", [])[-25:],
                    "signals": r.get("signals", []),
                    "capability": r.get("capability"),
                }
            )
    cid = ctx.cite(
        AiTool.get_spc_status, f"SPC — get_spc_status, {', '.join(p.code for p in projects)}"
    )
    return {"charts": out, "cite": cid}, narrowed


def t_get_cold_chain_summary(
    ctx: ToolContext, params: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """T29 (AC-Q4-32): per-zone excursions, TOR and MKT matching K-161 / K-162."""
    from sqlalchemy import func  # noqa: PLC0415

    from app.kpi.quality_views import kpi_filter  # noqa: PLC0415
    from app.models import Zone  # noqa: PLC0415
    from app.models.quality.q3 import QExcursion, QHold, QStorageZone  # noqa: PLC0415
    from app.services.quality.q3 import storage  # noqa: PLC0415
    from app.services.quality.q4 import base as b  # noqa: PLC0415

    projects, narrowed = _projects(ctx, params.get("project_codes"))
    if not projects:
        return {"no_access": True, "message": NO_ACCESS}, True
    start, end = _period(params, ctx.as_of)
    want = {c.upper() for c in params.get("zone_codes") or []}
    out = []
    for pr in projects:
        # the caller's grant sites narrow K-161 / K-162 / K-167 as on the KPI page (D-370)
        flt = kpi_filter(ctx.p, pr.id)
        e = qk.Engine(ctx.db, pr, start, end, ctx.as_of, flt)
        if e.profile is None or e.profile.value != "logistics":
            continue
        a, z_end = b.day_start(start), b.day_start(end + timedelta(days=1))
        zones = []
        for sz, z in ctx.db.execute(
            select(QStorageZone, Zone)
            .join(Zone, Zone.id == QStorageZone.zone_id)
            .where(
                QStorageZone.project_id == pr.id,
                QStorageZone.active.is_(True),
                *flt.at(QStorageZone.site_id),  # grant sites (rule 11)
            )
            .order_by(Zone.code)
        ):
            if want and z.code not in want:
                continue
            sev = dict(
                ctx.db.execute(
                    select(QExcursion.severity, func.count())
                    .where(
                        QExcursion.zone_id == z.id,
                        QExcursion.kind == "storage",
                        QExcursion.transient.is_(False),
                        QExcursion.status.not_in(["dismissed", "voided"]),
                        QExcursion.started_at >= a,
                        QExcursion.started_at < z_end,
                    )
                    .group_by(QExcursion.severity)
                ).all()
            )
            mon = out_ = per = 0
            for y, m in e.months():
                p_, m_, o_ = storage.month_tor(ctx.db, sz, y, m)
                per, mon, out_ = per + p_, mon + m_, out_ + o_
            mkts = []
            for pt in storage.points_of(ctx.db, z.id, active=True):
                mk = storage.point_mkt(ctx.db, sz, pt, a, z_end)
                if mk is not None:
                    mkts.append(str(mk["mkt_c"]))
            zones.append(
                {
                    "zone": z.code,
                    "storage_class": sz.storage_class.value,
                    "excursions": {s.value: int(n) for s, n in sev.items()},
                    "tor_pct": str(qk.pct(out_, mon, "0.01")) if mon else None,
                    "coverage_pct": str(qk.pct(mon, per)) if per else None,
                    "mkt_c_by_point": mkts,
                    "mapping_state": sz.mapping_state.value,
                    "mapped_until": sz.mapped_until.isoformat() if sz.mapped_until else None,
                }
            )
        holds = (
            ctx.db.scalar(
                select(func.count())
                .select_from(QHold)
                .where(
                    QHold.project_id == pr.id,
                    QHold.reason == "excursion",
                    QHold.status.in_(["on_hold", "partly_released"]),
                    *flt.at(QHold.site_id),
                )
            )
            or 0
        )
        k161, k162, k167 = e.result(QKpi.K161), e.result(QKpi.K162), e.result(QKpi.K167)
        out.append(
            {
                "project": pr.code,
                "period": f"{start} – {end}",
                "zones": zones,
                "k161": k161.display,
                "k162": k162.display,
                "k167": k167.display,
                "open_excursion_holds": int(holds),
            }
        )
    cid = ctx.cite(
        AiTool.get_cold_chain_summary,
        f"Cold chain — get_cold_chain_summary, {start} – {end}",
        period=f"{start} – {end}",
    )
    return {"projects": out, "cite": cid}, narrowed


def quality_warnings(ctx: ToolContext, project: Project, months: int) -> list[dict[str, Any]]:
    """Q-AI-04: T13 returns E26–E28 with numerators and denominators, never names."""
    g = ctx.p.grant(project.id, Capability.quality_view)
    if g is None or g.scope == CapabilityScope.responsible:
        return []
    out = []
    d = ctx.as_of.replace(day=1) - timedelta(days=1)
    for _ in range(months):
        out += qk.warnings(ctx.db, project, d)
        d = d.replace(day=1) - timedelta(days=1)
    return out


HANDLERS = {
    AiTool.get_quality_kpis.value: t_get_quality_kpis,
    AiTool.search_ncrs.value: t_search_ncrs,
    AiTool.get_spc_status.value: t_get_spc_status,
    AiTool.get_cold_chain_summary.value: t_get_cold_chain_summary,
}
