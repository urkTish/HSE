"""Quality KPI page and Quality home tiles (spec 8-quality §E.7): profile-aware tiles with targets
and RAG, and the charts C42–C51 built from the KPI engine and SQL month groupings. Aggregates
only (P8-4); the Viewer / Client gets no cost figures. Scope-N-only users get 403 (AC-Q0-03)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.enums import Capability, CapabilityScope
from app.core.quality.common import INTERNAL_STAGES, QNcrStatus, QSectorProfile
from app.core.quality.q4 import QKpi
from app.kpi import quality as qk
from app.models import Project
from app.models.quality import QNcr, QNcrCost
from app.models.quality.q4 import QWorkValue
from app.services.permissions import Principal, forbidden_error

C = Capability
D = Decimal


def kpi_filter(p: Principal, project_id: uuid.UUID, extra: qk.QFilter | None = None) -> qk.QFilter:
    """The caller's grant narrows the filter (Q-ROL-02 engagement tree, Phase 0 rule 11 sites);
    a scope-N-only user sees no KPIs (Q-ROL-04, AC-Q0-03)."""
    g = p.grant(project_id, C.quality_view)
    if g is None or g.scope == CapabilityScope.responsible:
        raise forbidden_error("KPIs are not shown to the responsible-person scope (Q-ROL-04).")
    f = extra or qk.QFilter()
    if g.engagement_ids is not None:
        mine = frozenset(g.engagement_ids)
        f.engagement_ids = mine if f.engagement_ids is None else (f.engagement_ids & mine)
    if g.site_ids is not None:
        mine_s = frozenset(g.site_ids)
        f.site_ids = mine_s if f.site_ids is None else (f.site_ids & mine_s)
    return f


def no_costs(p: Principal, project_id: uuid.UUID) -> bool:
    from app.services.quality.ncr.core import read_only_viewer  # noqa: PLC0415

    return read_only_viewer(p, project_id)


def months_back(end: date, n: int) -> list[tuple[date, date]]:
    out = []
    d = end.replace(day=1)
    for _ in range(n):
        out.append((d, qk.month_end(d)))
        d = (d - timedelta(days=1)).replace(day=1)
    return list(reversed(out))


def tile(e: qk.Engine, k: QKpi, hide_cost: bool) -> dict[str, Any]:
    r = e.result(k).dump()
    if hide_cost and k == QKpi.K148:
        r.update(
            {
                "value": None,
                "numerator": None,
                "display": "—",
                "chips": [c for c in r["chips"] if c["code"] == "copq_pct"],
            }
        )
    t = qk.target_of(e.db, e.project.id, k, e.end)
    r["target"] = str(t) if t is not None else None
    r["rag"] = qk.rag(k, D(r["value"]) if r["value"] else None, t)
    return r


def page(
    db: Session,
    p: Principal,
    project: Project,
    start: date,
    end: date,
    as_of: date,
    flt: qk.QFilter | None = None,
    charts: bool = True,
) -> dict[str, Any]:
    f = kpi_filter(p, project.id, flt)
    e = qk.Engine(db, project, start, end, as_of, f)
    hide = no_costs(p, project.id)
    kpis = qk.tiles_for(e.profile)
    out: dict[str, Any] = {
        "project_id": project.id,
        "profile": e.profile.value if e.profile else None,
        "period_start": e.start,
        "period_end": end,
        "as_of": as_of,
        "tiles": [tile(e, k, hide) for k in kpis],
        "warnings": qk.warnings(db, project, end) if end.day == qk.month_end(end).day else [],
        "charts": {},
    }
    if charts:
        out["charts"] = build_charts(db, e, hide)
    return out


def build_charts(db: Session, e: qk.Engine, hide: bool) -> dict[str, Any]:
    ch: dict[str, Any] = {}
    months = months_back(e.end, 12)
    # C42 NCRs by month stacked by class + open-count line
    rows = db.execute(
        select(func.date_trunc("month", QNcr.opened_date), QNcr.classification, func.count())
        .where(*e._ncr_base(), QNcr.opened_date >= months[0][0], QNcr.opened_date <= e.end)
        .group_by(text("1"), text("2"))
    ).all()
    by: dict[str, dict[str, int]] = defaultdict(lambda: {"minor": 0, "major": 0, "critical": 0})
    for m, cls, n in rows:
        if cls is not None:
            by[m.date().isoformat()[:7]][cls.value] += int(n)
    ch["C42"] = [
        {
            "month": a.isoformat()[:7],
            **by[a.isoformat()[:7]],
            "open": db.scalar(select(func.count()).select_from(QNcr).where(*e._open_at(z))) or 0,
        }
        for a, z in months
    ]
    ch["C43"] = e.result(QKpi.K150).extra["pareto"]
    ch["C43_cause"] = e.k150("cause_category").extra["pareto"]
    ch["C44"] = e.result(QKpi.K144).extra
    if not hide:
        internal = QNcr.detection_stage.in_(list(INTERNAL_STAGES))
        cost = db.execute(
            select(
                func.date_trunc("month", QNcr.opened_date),
                QNcrCost.cost_type,
                internal,
                func.sum(QNcrCost.amount_sar),
            )
            .join(QNcr, QNcr.id == QNcrCost.ncr_id)
            .where(*e._ncr_base(), QNcr.opened_date >= months[0][0], QNcr.opened_date <= e.end)
            .group_by(text("1"), text("2"), text("3"))
        ).all()
        wv = {
            m.isoformat()[:7]: D(v)
            for m, v in db.execute(
                select(QWorkValue.month, QWorkValue.value_sar).where(
                    QWorkValue.project_id == e.project.id, QWorkValue.month >= months[0][0]
                )
            )
        }
        c45: dict[str, dict[str, Any]] = {
            a.isoformat()[:7]: {
                "month": a.isoformat()[:7],
                "by_type": {},
                "internal": D(0),
                "external": D(0),
            }
            for a, _z in months
        }
        for m, ct, inn, amt in cost:
            row = c45.get(m.date().isoformat()[:7])
            if row is None:
                continue
            row["by_type"][ct.value] = str(D(amt))
            row["internal" if inn else "external"] += D(amt)
        for k, row in c45.items():
            gross = row["internal"] + row["external"]
            row["copq_pct"] = str(qk.pct(gross, wv[k], "0.01")) if wv.get(k) else None
            row["internal"], row["external"] = str(row["internal"]), str(row["external"])
        ch["C45"] = list(c45.values())
    if e.profile != QSectorProfile.logistics:
        from app.services.quality.q1 import kpi as q1k  # noqa: PLC0415

        c46 = []
        for a, z in months[-6:]:
            c = q1k.ir_counts(db, e.project.id, a, z)
            c46.append(
                {
                    "month": a.isoformat()[:7],
                    "k141": str(c.ftpr) if c.ftpr is not None else None,
                    "k142": str(c.rejection_rate) if c.rejection_rate is not None else None,
                }
            )
        ch["C46"] = c46
    if e.profile == QSectorProfile.logistics:
        ch["C49"] = excursion_grid(db, e.project.id, months)
    ch["C50"] = supplier_ranking(db, e)
    ch["C51"] = [{"process": k, **v} for k, v in e.dpmo().items()]
    return ch


def excursion_grid(
    db: Session, project_id: uuid.UUID, months: list[tuple[date, date]]
) -> list[dict[str, Any]]:
    """C49: zone × month, worst severity of storage excursions (not dismissed, not voided)."""
    from app.models import Zone  # noqa: PLC0415
    from app.models.quality.q3 import QExcursion  # noqa: PLC0415
    from app.services.quality.q4 import base as b  # noqa: PLC0415

    rank = {"minor": 1, "major": 2, "critical": 3}
    grid: dict[tuple[str, str], str] = {}
    a = b.day_start(months[0][0])
    for z, started, sev in db.execute(
        select(Zone.code, QExcursion.started_at, QExcursion.severity)
        .join(Zone, Zone.id == QExcursion.zone_id)
        .where(
            QExcursion.project_id == project_id,
            QExcursion.transient.is_(False),
            QExcursion.status.not_in(["dismissed", "voided"]),
            QExcursion.started_at >= a,
        )
    ):
        m = b.local_day(started).isoformat()[:7]
        cur = grid.get((z, m))
        if cur is None or rank[sev.value] > rank[cur]:
            grid[(z, m)] = sev.value
    zones = sorted({z for z, _m in grid})
    return [
        {
            "zone": z,
            "months": {m.isoformat()[:7]: grid.get((z, m.isoformat()[:7])) for m, _e in months},
        }
        for z in zones
    ]


def supplier_ranking(db: Session, e: qk.Engine) -> list[dict[str, Any]]:
    from app.models.quality import QSupplier  # noqa: PLC0415
    from app.services.quality.q4 import suppliers  # noqa: PLC0415

    out = []
    for s in db.scalars(select(QSupplier).order_by(QSupplier.supplier_code)):
        x = suppliers.latest_final(db, s.id)
        if x is None or x.score is None:
            continue
        out.append(
            {
                "code": s.supplier_code,
                "name_en": s.legal_name_en,
                "name_ar": s.legal_name_ar,
                "score": str(x.score),
                "band": x.band,
                "period_start": x.period_start.isoformat(),
            }
        )
    return sorted(out, key=lambda r: -D(r["score"]))


_ = QNcrStatus
