"""Field assurance KPI page (GET /kpi/field-assurance, 6d-field-assurance §6.7, §8.1, FM-1…FM-3).

Engine values only; aggregates only (FM-2): item codes with item text, topic codes, inspection
types, template codes, engagement codes, zone codes, months and talk languages are the only keys.
Notes: the K-36 source (register / daily returns / mixed) with the SRC-3 reconciliation and the
"checklist-based from <date>" note of the K-34 / K-35 tile."""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.field_enums import FieldKpiGroupBy
from app.core.hse_enums import KpiMetric
from app.kpi import field as kf
from app.kpi import fmt, present, service
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.models import ChecklistTemplate, Zone
from app.schemas.field import FieldBreakdown, FieldBreakdownRow, FieldKpiResponse

M = KpiMetric
G = FieldKpiGroupBy
D = Decimal
FIELD_METRICS = [M.K34, M.K35, M.K36, M.K110, M.K111, M.K112, M.K113, M.K114, M.K115, M.K116,
                 M.K117]  # fmt: skip
NEW = [M.K110, M.K111, M.K112, M.K113, M.K114, M.K115, M.K116, M.K117]


def _row(metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window) -> FieldBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    return FieldBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=present.value_str(defn, r.value),
        display=present.display(defn, r.value),
        numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )


def _pct(num: Decimal, den: Decimal) -> Decimal | None:
    return (num * 100 / den).quantize(D("0.1"), rounding=ROUND_HALF_UP) if den else None


def _prow(key: str, en: str, ar: str, num: Decimal, den: Decimal, note: str | None = None) -> Any:
    v = _pct(num, den)
    return FieldBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=str(v) if v is not None else None,
        display=f"{v} %" if v is not None else "—",
        numerator=fmt.exact(num),
        denominator=fmt.exact(den),
        note=note,
    )


def _texts(db: Session) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for t in db.scalars(select(ChecklistTemplate).order_by(ChecklistTemplate.version)):
        for it in t.items or []:
            out[it["item_code"]] = (it.get("text_en", ""), it.get("text_ar", ""))
    return out


def most_failed(e: Engine, w: Window, db: Session, top: int = 10) -> list[FieldBreakdownRow]:
    """FM-3: ranked by non-compliant answers, ties by fail rate, then code; < 5 applicable →
    "small sample"."""
    acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in kf.resp_in(e, w):
        for code, ok in r.answers:
            acc[code][1] += 1
            acc[code][0] += not ok
    texts = _texts(db)
    ranked = sorted(
        ((c, v) for c, v in acc.items() if v[0] > 0),
        key=lambda x: (-x[1][0], -(D(x[1][0]) / x[1][1]), x[0]),
    )[:top]
    return [
        FieldBreakdownRow(
            key=c,
            label_en=texts.get(c, (c, c))[0] or c,
            label_ar=texts.get(c, (c, c))[1] or c,
            value=str(v[0]),
            display=str(v[0]),
            numerator=str(v[0]),
            denominator=str(v[1]),
            note="small sample" if v[1] < 5 else None,
        )
        for c, v in ranked
    ]


def _breakdowns(
    db: Session, scope: Scope, metrics: list[KpiMetric], group_by: list[FieldKpiGroupBy]
) -> list[FieldBreakdown]:
    w = scope.window
    e = scope.engine
    out: list[FieldBreakdown] = []
    for g in dict.fromkeys(group_by):
        if g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, e, mw))
                out.append(FieldBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.contractor:
            engs = sorted(scope.facts.engagements.values(), key=lambda x: x.code)
            engs = [x for x in engs if scope.flt.eng_ok(x.id)]
            for m in metrics:
                if m not in NEW:
                    continue
                rows = [
                    _row(m, x.code, x.code, x.code,
                         scope.sub_engine(scope.narrowed_filter(engs=frozenset({x.id}))), w)
                    for x in engs
                ]  # fmt: skip
                out.append(FieldBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g in (G.inspection_type, G.template, G.zone) and M.K110 in metrics:
            acc: dict[str, list[Decimal]] = defaultdict(lambda: [D(0), D(0)])
            zones = {z.id: z.code for z in db.scalars(select(Zone))}
            for r in kf.resp_in(e, w):
                k = (
                    r.itype
                    if g == G.inspection_type
                    else r.template
                    if g == G.template
                    else (zones.get(r.zone, "—") if r.zone else "—")
                )
                acc[k][0] += r.ew
                acc[k][1] += r.aw
            rows = [_prow(k, k, k, v[0], v[1]) for k, v in sorted(acc.items())]
            out.append(FieldBreakdown(metric=M.K110.value, group_by=g, rows=rows))
        elif g == G.item_code:
            out.append(FieldBreakdown(metric=M.K110.value, group_by=g, rows=most_failed(e, w, db)))
        elif g == G.language and M.K116 in metrics:
            out.append(FieldBreakdown(metric=M.K116.value, group_by=g, rows=_languages(db, e, w)))
    return out


def _languages(db: Session, e: Engine, w: Window) -> list[FieldBreakdownRow]:
    from app.core.field_enums import TalkStatus, UnderstoodLanguage  # noqa: PLC0415
    from app.models import TalkAttendance, ToolboxTalk  # noqa: PLC0415

    ff = kf.ffacts(e)
    if ff is None:
        return []
    acc: dict[str, list[Decimal]] = defaultdict(lambda: [D(0), D(0)])
    end = min(e.as_of, w.end)
    T, A = ToolboxTalk, TalkAttendance  # noqa: N806
    for lang, site, eng, ul in db.execute(
        select(T.language, T.site_id, A.engagement_id, A.understood_language)
        .join(A, A.talk_id == T.id)
        .where(
            T.project_id.in_(ff.pids),
            T.status.in_((TalkStatus.delivered, TalkStatus.locked)),
            T.delivered_date >= w.start,
            T.delivered_date <= end,
        )
    ):
        if not (e.flt.site_ok(site) and e.flt.eng_ok(eng)):
            continue
        acc[lang][1] += 1
        acc[lang][0] += ul != UnderstoodLanguage.none
    return [_prow(k, k, k, v[0], v[1]) for k, v in sorted(acc.items())]


def notes(db: Session, scope: Scope) -> list[str]:
    """K-36 source and SRC-3 reconciliation; K-34 / K-35 "checklist-based from <date>"."""
    from app.services.field import common as fc  # noqa: PLC0415

    out: list[str] = []
    w = scope.window
    a = scope.engine.aggregate(w)
    froms = [fc.cfg(db, p.id).toolbox_from for p in scope.projects]
    if all(f is None or f > w.end for f in froms):
        src = "Daily returns"
    elif all(f is not None and f <= w.start for f in froms):
        src = "Toolbox register"
    else:
        src = "Mixed"
    out.append(f"K-36 source: {src}")
    parts = []
    if a.tbt_dr > 0:
        x = D(abs(a.tbt_reg - a.tbt_dr)) * 100 / a.tbt_dr
        if x > 5:
            parts.append((x, "talks"))
    if a.tbt_att_dr > 0:
        x = D(abs(a.tbt_att_reg - a.tbt_att_dr)) * 100 / a.tbt_att_dr
        if x > 5:
            parts.append((x, "attendees"))
    if parts:
        out.append(
            "Daily returns differ from the toolbox register by "
            + ", ".join(f"{v.quantize(D('0.1'), rounding=ROUND_HALF_UP)} % ({k})" for v, k in parts)
        )
    tf = [fc.cfg(db, p.id).template_from for p in scope.projects]
    first = min((d for d in tf if d is not None), default=None)
    if first is not None:
        out.append(f"K-34 / K-35: checklist-based from {first.isoformat()}")
    return out


def field_kpis(
    db: Session,
    scope: Scope,
    metrics: list[KpiMetric] | None,
    group_by: list[FieldKpiGroupBy] | None,
) -> FieldKpiResponse:
    wanted = [m for m in (metrics or FIELD_METRICS) if m in FIELD_METRICS] or FIELD_METRICS
    return FieldKpiResponse(
        context=service.context(scope),
        metrics=[service.kpi_value(scope, m) for m in wanted],
        breakdowns=_breakdowns(db, scope, wanted, group_by or []),
        notes=notes(db, scope),
    )
