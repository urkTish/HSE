"""Logistics metrics of a calendar month (spec 8-quality §E.4 K-160…K-168, computed from the Q3
records so Q4's KPI catalogue and dashboards can read them, and shown on the Q3 screens):
receiving rejection rate, excursions per zone-month, time out of range with coverage, OTIF,
damage rate, inventory record accuracy, FEFO compliance, transport temperature compliance and
hygiene / pest check compliance. Rounding half-up at output only; a zero denominator gives None."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.quality.q3 import (
    QExcursionKind,
    QExcursionStatus,
    QLineDecision,
    QMappingState,
    QReceiptStatus,
    QTripStatus,
)
from app.models import Project
from app.models.quality.q3 import (
    QCycleCount,
    QCycleCountLine,
    QDamageReport,
    QExcursion,
    QFefoCheck,
    QReceipt,
    QReceiptLine,
    QShipment,
    QShipmentLine,
    QStorageZone,
    QThroughput,
    QTrip,
)
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality.q3 import base as b
from app.services.quality.q3 import engine as eng
from app.services.quality.q3 import hygiene, storage
from app.services.quality.q3 import stock as stock_svc

D = Decimal


def pct(n: int | D, d: int | D, dp: str = "0.1") -> D | None:
    if not d:
        return None
    return (D(n) * 100 / D(d)).quantize(D(dp), ROUND_HALF_UP)


def month(db: Session, project: Project, year: int, mon: int) -> dict[str, Any]:
    a, e = b.month_bounds(year, mon)
    as_of = min(e, now())
    first = date(year, mon, 1)
    last = (b.local_day(e) - timedelta(days=1)) if e else first
    out: dict[str, Any] = {"year": year, "month": mon}

    # K-160 receiving
    rec = list(
        db.scalars(
            select(QReceipt).where(
                QReceipt.project_id == project.id,
                QReceipt.status == QReceiptStatus.decided,
                QReceipt.decided_at >= a,
                QReceipt.decided_at < e,
            )
        )
    )
    ids = [r.id for r in rec]
    decs: dict[uuid.UUID, set[QLineDecision]] = {}
    n_lines = n_rej_lines = 0
    for ln in db.scalars(
        select(QReceiptLine).where(QReceiptLine.receipt_id.in_(ids or [uuid.uuid4()]))
    ):
        decs.setdefault(ln.receipt_id, set()).add(ln.decision)  # type: ignore[arg-type]
        n_lines += 1
        n_rej_lines += ln.decision == QLineDecision.reject
    lim = int(b.setting(db, project.id, "dock_dwell_max_minutes"))
    out["k160"] = {
        "receipts": len(rec),
        "rejected": sum(1 for r in rec if QLineDecision.reject in decs.get(r.id, set())),
        "value": pct(
            sum(1 for r in rec if QLineDecision.reject in decs.get(r.id, set())), len(rec)
        ),
        "deviation_rate": pct(
            sum(1 for r in rec if QLineDecision.accept_with_deviation in decs.get(r.id, set())),
            len(rec),
        ),
        "quarantine_rate": pct(
            sum(1 for r in rec if QLineDecision.quarantine in decs.get(r.id, set())), len(rec)
        ),
        "line_rejection_pct": pct(n_rej_lines, n_lines),
        "dock_dwell_over_limit": sum(
            1 for r in rec if r.dwell_minutes is not None and r.dwell_minutes > lim
        ),
    }

    # K-161 / K-162 storage
    zones = list(
        db.scalars(
            select(QStorageZone).where(
                QStorageZone.project_id == project.id, QStorageZone.active.is_(True)
            )
        )
    )
    mon_total = out_total = period_total = 0
    zone_months = 0
    per_zone = []
    gmin = int(b.setting(db, project.id, "monitoring_gap_alert_minutes"))
    gaps = 0
    for z in zones:
        gr = storage.zone_grid(db, z, a, e)
        p_, m_, o_ = eng.coverage(gr)
        if m_:
            zone_months += 1
        mon_total += m_
        out_total += o_
        period_total += p_
        gaps += len(eng.gaps(gr, gmin))
        per_zone.append(
            {
                "zone_id": z.zone_id,
                "monitored": m_,
                "out": o_,
                "tor_pct": pct(o_, m_, "0.01"),
                "coverage_pct": pct(m_, p_),
            }
        )
    excs = list(
        db.scalars(
            select(QExcursion).where(
                QExcursion.project_id == project.id,
                QExcursion.transient.is_(False),
                QExcursion.started_at >= a,
                QExcursion.started_at < e,
                QExcursion.status.not_in([QExcursionStatus.dismissed, QExcursionStatus.voided]),
            )
        )
    )
    storage_x = [x for x in excs if x.kind != QExcursionKind.transit]
    out["k161"] = {
        "excursions": len(storage_x),
        "zone_months": zone_months,
        "value": (D(len(storage_x)) / zone_months).quantize(D("0.01"), ROUND_HALF_UP)
        if zone_months
        else None,
        "by_severity": {
            s: sum(1 for x in storage_x if x.severity.value == s)
            for s in ("minor", "major", "critical")
        },
        "transit_excursions": sum(1 for x in excs if x.kind == QExcursionKind.transit),
        "dismissed": db.scalar(
            select(func.count())
            .select_from(QExcursion)
            .where(
                QExcursion.project_id == project.id,
                QExcursion.status == QExcursionStatus.dismissed,
                QExcursion.started_at >= a,
                QExcursion.started_at < e,
            )
        )
        or 0,
    }
    out["k162"] = {
        "monitored_minutes": mon_total,
        "out_minutes": out_total,
        "period_minutes": period_total,
        "value": pct(out_total, mon_total, "0.01"),
        "coverage_pct": pct(mon_total, period_total),
        "zones_not_mapped": sum(1 for z in zones if z.mapping_state != QMappingState.mapped),
        "gaps": gaps,
        "zones": per_zone,
    }

    # K-163 OTIF (Q-TRN-08)
    window = timedelta(minutes=int(b.setting(db, project.id, "otif_window_minutes")))
    ships = list(
        db.scalars(
            select(QShipment).where(
                QShipment.project_id == project.id,
                QShipment.delivered_at >= a,
                QShipment.delivered_at < e,
                QShipment.promised_at.is_not(None),
            )
        )
    )
    by_ship: dict[uuid.UUID, list[QShipmentLine]] = {}
    if ships:
        for sl in db.scalars(
            select(QShipmentLine).where(QShipmentLine.shipment_id.in_([s.id for s in ships]))
        ):
            by_ship.setdefault(sl.shipment_id, []).append(sl)
    on_time = in_full = both = 0
    for s in ships:
        ot = s.delivered_at <= s.promised_at + window  # type: ignore[operator]
        lines = by_ship.get(s.id, [])
        inf = all(
            ln.delivered_qty is not None and ln.delivered_qty >= ln.ordered_qty for ln in lines
        )
        on_time += ot
        in_full += inf
        both += ot and inf
    out["k163"] = {
        "shipments": len(ships),
        "on_time": on_time,
        "in_full": in_full,
        "otif": both,
        "value": pct(both, len(ships)),
    }

    # K-164 damage
    dmg = (
        db.scalar(
            select(func.coalesce(func.sum(QDamageReport.qty), 0)).where(
                QDamageReport.project_id == project.id,
                QDamageReport.reported_at >= a,
                QDamageReport.reported_at < e,
            )
        )
        or 0
    )
    thr = db.execute(
        select(
            func.coalesce(func.sum(QThroughput.units_received), 0),
            func.coalesce(func.sum(QThroughput.units_dispatched), 0),
        ).where(QThroughput.project_id == project.id, QThroughput.month == first)
    ).one()
    handled = int(thr[0]) + int(thr[1])
    out["k164"] = {
        "units_damaged": D(dmg),
        "units_handled": handled,
        "value": pct(D(dmg), handled, "0.001"),
        "ppm": (D(dmg) * 1_000_000 / handled).quantize(D("0.1"), ROUND_HALF_UP)
        if handled
        else None,
    }

    # K-165 inventory record accuracy
    cc_ids = [
        c.id
        for c in db.scalars(
            select(QCycleCount).where(
                QCycleCount.project_id == project.id,
                QCycleCount.voided.is_(False),
                QCycleCount.counted_at >= a,
                QCycleCount.counted_at < e,
            )
        )
    ]
    cc_lines = list(
        db.scalars(
            select(QCycleCountLine).where(QCycleCountLine.cc_id.in_(cc_ids or [uuid.uuid4()]))
        )
    )
    within = sum(1 for x in cc_lines if x.within_tolerance)
    out["k165"] = {"lines": len(cc_lines), "within": within, "value": pct(within, len(cc_lines))}

    # K-166 FEFO
    checks = list(
        db.scalars(
            select(QFefoCheck).where(
                QFefoCheck.project_id == project.id,
                QFefoCheck.checked_at >= a,
                QFefoCheck.checked_at < e,
            )
        )
    )
    ok = sum(1 for x in checks if stock_svc.fefo_counts(x))
    out["k166"] = {
        "checks": len(checks),
        "counted_compliant": ok,
        "exceptions": sum(1 for x in checks if x.result.value == "exception"),
        "value": pct(ok, len(checks)),
        "weekly_target": int(b.setting(db, project.id, "fefo_checks_per_week")),
    }

    # K-167 transport temperature
    trips = list(
        db.scalars(
            select(QTrip).where(
                QTrip.project_id == project.id,
                QTrip.status.in_([QTripStatus.delivered, QTripStatus.closed]),
                QTrip.delivered_at >= a,
                QTrip.delivered_at < e,
            )
        )
    )
    with_data = [t for t in trips if t.transit_data]
    bad = {x.trip_id for x in excs if x.kind == QExcursionKind.transit}
    out["k167"] = {
        "trips": len(trips),
        "with_data": len(with_data),
        "compliant": sum(1 for t in with_data if t.id not in bad),
        "value": pct(sum(1 for t in with_data if t.id not in bad), len(with_data)),
        "without_data": len(trips) - len(with_data),
        "preload_fails": sum(1 for t in trips if t.preload_passed is False),
        "overrides": sum(1 for t in trips if t.override_reason),
    }

    # K-168 hygiene and pest checks
    done, total = hygiene.compliance(db, project, first, last, b.local_day(as_of))
    out["k168"] = {"done": done, "due": total, "value": pct(done, total)}
    return out


def month_api(
    db: Session, p: Principal, project_id: uuid.UUID, year: int, mon: int
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    if g.scope.value == "responsible":
        from app.services.permissions import forbidden_error  # noqa: PLC0415

        raise forbidden_error("KPIs are not shown to the responsible-person scope (Q-ROL-04).")
    return month(db, project, year, mon)
