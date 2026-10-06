"""Remaining KPI responses: breakdowns (§6.8), leading indicators + warnings (§6.9) and table
exports (D-10)."""

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import AuditAction, Capability, ExportFormat
from app.core.errors import validation_error
from app.core.hse_enums import (
    BreakdownDimension,
    BreakdownMeasure,
    KpiExportTable,
)
from app.kpi import breakdowns, charts, fmt, service, warnings
from app.kpi.catalogue import LEADING_TILES
from app.kpi.scope import Scope
from app.schemas.kpi import (
    BreakdownResponse,
    BreakdownRow,
    LeadingIndicatorsResponse,
    LeadingWarning,
    WarningInput,
)
from app.services import audit
from app.services import exports as export_svc
from app.services.permissions import forbidden_error

# ---- breakdowns ----------------------------------------------------------------------------------


def _row(r: breakdowns.Row, bd: breakdowns.Breakdown, small_ok: bool) -> BreakdownRow:
    suppressed = bd.persons and not small_ok and 0 < r.count < 3
    rate, rate_disp = breakdowns.rate_display(r.count, r.man_hours, bd.rate_base)
    share = Decimal(r.count) / Decimal(bd.total) * 100 if bd.total else None
    return BreakdownRow(
        key=r.key,
        label_en=r.label_en,
        label_ar=r.label_ar,
        count=None if suppressed else r.count,
        count_display="<3" if suppressed else fmt.number(r.count),
        suppressed=suppressed,
        man_hours=fmt.dec_str(r.man_hours, 2) if r.man_hours is not None else None,
        rate=None if suppressed else rate,
        rate_display=None if suppressed else rate_disp,
        share_pct=None if suppressed else fmt.dec_str(share, 1),
        share_display=None if suppressed or share is None else fmt.percent(share, 1),
    )


def breakdown(
    db: Session,
    scope: Scope,
    measure: BreakdownMeasure,
    dimension: BreakdownDimension,
    top_n: int = 10,
) -> BreakdownResponse:
    bd = breakdowns.compute(db, scope, measure, dimension)
    small_ok = breakdowns.can_see_small_cells(scope)
    ordered = bd.rows
    top, rest = ordered[:top_n], ordered[top_n:]
    other = None
    if rest:
        n = sum(r.count for r in rest)
        mh_vals = [r.man_hours for r in rest if r.man_hours is not None]
        other_row = breakdowns.Row(
            "other",
            "Other",
            "أخرى",
            n,
            sum(mh_vals, Decimal(0)) if bd.exposure_available else None,
        )
        other = _row(other_row, bd, small_ok)
    rate_label = None
    if bd.exposure_available:
        rate_label = fmt.hours_label(bd.rate_base)
    return BreakdownResponse(
        context=service.context(scope),
        measure=measure,
        dimension=dimension,
        exposure_available=bd.exposure_available,
        rate_label_en=f"Rate ({rate_label[0]})" if rate_label else None,
        rate_label_ar=f"المعدل ({rate_label[1]})" if rate_label else None,
        total_count=bd.total,
        rows=[_row(r, bd, small_ok) for r in top],
        other=other,
    )


# ---- leading indicators --------------------------------------------------------------------------


def warning_read(scope: Scope, w: warnings.Warn) -> LeadingWarning:
    return LeadingWarning(
        code=w.code,
        month=w.month_key,
        project_id=w.project_id,
        engagement=service.eng_ref(w.engagement) if w.engagement else None,
        message_en=w.message_en,
        message_ar=w.message_ar,
        inputs=[
            WarningInput(
                key=i.key,
                label_en=i.label_en,
                label_ar=i.label_ar,
                value=fmt.dec_str(i.value, i.dp),
                display=i.display,
            )
            for i in w.inputs
        ],
    )


def leading_indicators(scope: Scope, months: int = 3) -> LeadingIndicatorsResponse:
    wins = warnings.complete_months(scope, scope.window, months)
    found = warnings.evaluate(scope, wins)
    return LeadingIndicatorsResponse(
        context=service.context(scope),
        tiles=[service.tile(scope, m) for m in LEADING_TILES],
        warnings=[warning_read(scope, w) for w in found],
        evaluated_months=[w.start.strftime("%Y-%m") for w in wins],
    )


# ---- exports -------------------------------------------------------------------------------------


def export_table(
    db: Session,
    scope: Scope,
    table: KpiExportTable,
    fmt_: ExportFormat,
    dimension: BreakdownDimension | None,
    measure: BreakdownMeasure | None,
) -> tuple[bytes, str, str]:
    for proj in scope.projects:
        if scope.p.grant(proj.id, Capability.export_kpis) is None:
            raise forbidden_error()
    cols: list[str]
    rows: list[list[Any]] = []
    period = scope.period.label_en
    if table == KpiExportTable.metrics:
        cols = [
            "metric",
            "label",
            "value",
            "display",
            "numerator",
            "denominator",
            "base",
            "period",
            "scope",
            "warnings",
        ]
        for v in service.metric_list(scope, None):
            rows.append(
                [
                    v.metric.value,
                    v.label_en,
                    v.value,
                    v.display,
                    v.numerator,
                    v.denominator,
                    v.base,
                    period,
                    service.scope_label(scope),
                    ",".join(x.value for x in v.warnings),
                ]
            )
    elif table == KpiExportTable.comparisons:
        t = service.comparison_table(scope, None)
        keys = [c.key for c in t.columns]
        cols = ["metric", "label", *keys, "delta_previous", "delta_sply", "delta_r12"]
        for crow in t.rows:
            rows.append(
                [
                    crow.metric.value,
                    crow.label_en,
                    *[crow.cells[k].display for k in keys],
                    *[d.abs_delta_display for d in crow.deltas],
                ]
            )
    elif table == KpiExportTable.contractors:
        lt = charts.league_table(scope)
        cols = [c.key for c in lt.columns]
        rows = [[r.get(c, "") for c in cols] for r in lt.rows]
    else:
        if dimension is None:
            raise validation_error("dimension", "The breakdown export needs a dimension.")
        b = breakdown(db, scope, measure or BreakdownMeasure.injury_cases, dimension, top_n=20)
        cols = ["key", "label", "count", "man_hours", "rate", "share_pct"]
        for brow in [*b.rows, *([b.other] if b.other else [])]:
            rows.append(
                [
                    brow.key,
                    brow.label_en,
                    brow.count_display,
                    brow.man_hours,
                    brow.rate_display,
                    brow.share_display,
                ]
            )
    pid = scope.projects[0].id if len(scope.projects) == 1 else None
    audit.record(
        db,
        AuditAction.export,
        scope.p.actor(pid),
        project_id=pid,
        details={
            "dataset": f"kpi_{table.value}",
            "format": fmt_.value,
            "row_count": len(rows),
            "columns": cols,
            "filters": {
                "projects": [x.code for x in scope.projects],
                "period": period,
                "scope": service.scope_label(scope),
                "dimension": dimension.value if dimension else None,
            },
        },
    )
    return export_svc.encode(cols, rows, fmt_, f"kpi-{table.value}")
