"""Temperature excursions and product impact (spec 8-quality §D.4, Q-EXC-01…12).

Detection runs synchronously after every import and manual reading (§4: "within 60 s"), per zone
(storage) or per trip compartment (transit), on a window around the new data: runs are recomputed
from the stored readings and reconciled with the stored excursions (new, grown, or vanished after
a batch void, D-352). Major and critical excursions alert at once (Q-EXC-04) and open an NCR and
a hold (Q-EXC-05). The impact assessment covers every hold line (Q-EXC-07…09) and is signed by
the responsible person of `excursion.impact` with the storage class as qualifier."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import ErrorCode
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import (
    QCalStatus,
    QDetectionStage,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QNcrStatus,
    QRecordType,
)
from app.core.quality.q3 import (
    EXCURSION_LIVE,
    SEVERITY_RANK,
    STORAGE_CLASSES,
    QExcursionCause,
    QExcursionKind,
    QExcursionSeverity,
    QExcursionStatus,
    QHoldLineStatus,
    QHoldReason,
    QImpactDecision,
    QReadingTarget,
    QStorageClass,
)
from app.models import Project, Zone
from app.models.quality import QCustomer, QMteItem, QNcr
from app.models.quality.q3 import (
    QExcursion,
    QExcursionImpact,
    QHold,
    QHoldLine,
    QMonitoringPoint,
    QReading,
    QStorageZone,
    QTrip,
)
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import rpm
from app.services.quality.q3 import base as b
from app.services.quality.q3 import engine as eng
from app.services.quality.q3 import holds as hold_svc
from app.services.quality.q3 import stock as stock_svc
from app.services.quality.q3 import storage

C = Capability
RT = QRecordType.excursion
ST = QExcursionStatus
SEV = QExcursionSeverity
A = AttachmentOwner
DAY = timedelta(days=1)


def qualifier(x: QExcursion) -> str:
    return x.storage_class.value


def ctx(x: QExcursion) -> rpm.Ctx:
    return rpm.Ctx(site_id=x.site_id, qualifier=qualifier(x))


def impact_required(db: Session, x: QExcursion) -> bool:
    """Q-EXC-06: major and critical, and any excursion in a `pharma_2_8` zone while
    `pharma_impact_all_excursions`."""
    if x.severity != SEV.minor:
        return True
    return x.storage_class == QStorageClass.pharma_2_8 and bool(
        b.setting(db, x.project_id, "pharma_impact_all_excursions")
    )


def _steps(db: Session, x: QExcursion) -> b.StepList:
    return [("impact", ctx(x), qualifier(x))]


def get_exc(db: Session, p: Principal, exc_id: uuid.UUID) -> tuple[QExcursion, Project]:
    x = db.get(QExcursion, exc_id)
    if x is None or not p.can_see_project(x.project_id):
        raise b.not_found(db, p, RT, exc_id, x.project_id if x else None)
    project = qc.get_project(db, p, x.project_id)
    if not b.can_view(db, p, project, RT, x.id, x.site_id, lambda: _steps(db, x)):
        raise b.not_found(db, p, RT, exc_id, project.id)
    return x, project


# ---- detection ----------------------------------------------------------------------------------


def _window_rows(db: Session, z: QStorageZone, t0: datetime, t1: datetime) -> list[QExcursion]:
    return list(
        db.scalars(
            select(QExcursion).where(
                QExcursion.zone_id == z.zone_id,
                QExcursion.kind == QExcursionKind.storage,
                QExcursion.status != ST.voided,
                QExcursion.started_at < t1,
                (QExcursion.ended_at.is_(None)) | (QExcursion.ended_at > t0),
            )
        )
    )


def _last_reading(db: Session, ids: list[uuid.UUID]) -> datetime | None:
    if not ids:
        return None
    return db.scalar(
        select(QReading.measured_at)
        .where(QReading.target_id.in_(ids), QReading.voided.is_(False))
        .order_by(QReading.measured_at.desc())
        .limit(1)
    )


def detect_zone(
    db: Session,
    project: Project,
    z: QStorageZone,
    t_from: datetime,
    t_to: datetime,
    actor: uuid.UUID | None,
    *,
    manual: bool = False,
    notify: bool = True,
) -> list[QExcursion]:
    """Q-EXC-01…05 for one zone around [t_from, t_to). Returns the live excursions (not
    transients) found or changed."""
    pts = storage.points_of(db, z.zone_id)
    t0 = b.floor_minute(t_from) - DAY
    for x in _window_rows(db, z, t0, t0 + timedelta(minutes=1)):
        t0 = min(t0, b.floor_minute(x.started_at) - timedelta(minutes=z.alarm_delay_minutes + 1))
    last = _last_reading(db, [p.id for p in pts])
    t1 = b.floor_minute(t_to) + DAY
    if last is not None:
        t1 = min(
            t1,
            b.floor_minute(last)
            + timedelta(minutes=max([p.interval_minutes for p in pts] or [15]) * 4),
        )
    t1 = max(t1, b.floor_minute(t_to) + timedelta(minutes=1))
    lim = storage.limits(z)
    gr = storage.zone_grid(db, z, t0, t1)
    found = eng.runs(gr, storage.bands(z), lim)
    for _ in range(12):
        # a run still out at the window end continues into later data already stored
        if not (found and found[-1].ongoing and last is not None and last >= t1):
            break
        t1 = min(t1 + timedelta(days=7), b.floor_minute(last) + timedelta(minutes=60))
        gr = storage.zone_grid(db, z, t0, t1)
        found = eng.runs(gr, storage.bands(z), lim)
    return _reconcile(
        db, project, z, None, None, gr, found, t0, t1, actor, manual=manual, notify=notify
    )


def _reconcile(
    db: Session,
    project: Project,
    z: QStorageZone | None,
    trip: QTrip | None,
    compartment: str | None,
    gr: eng.Grid,
    found: list[eng.Run],
    t0: datetime,
    t1: datetime,
    actor: uuid.UUID | None,
    *,
    manual: bool,
    notify: bool,
    auto: bool = True,
    sc: QStorageClass | None = None,
    lim: eng.Limits | None = None,
) -> list[QExcursion]:
    if z is not None:
        existing = _window_rows(db, z, t0, t1)
        sc = z.storage_class
        lim = storage.limits(z)
    else:
        assert trip is not None  # noqa: S101
        existing = list(
            db.scalars(
                select(QExcursion).where(
                    QExcursion.trip_id == trip.id,
                    QExcursion.compartment == compartment,
                    QExcursion.status != ST.voided,
                )
            )
        )
    assert sc is not None and lim is not None  # noqa: S101
    used: set[uuid.UUID] = set()
    changed: list[QExcursion] = []
    dismissed = [x for x in existing if x.status == ST.dismissed]
    for r in found:
        start, end = gr.at(r.start), gr.at(r.end)
        if any(
            x.started_at < end and (x.ended_at is None or x.ended_at > start) for x in dismissed
        ):
            continue  # a dismissed excursion is never re-detected (Q-EXC-11)
        match = next(
            (
                x
                for x in existing
                if x.id not in used
                and x.status != ST.dismissed
                and x.started_at < end
                and (x.ended_at is None or x.ended_at > start)
            ),
            None,
        )
        x = match or QExcursion(
            id=uuid.uuid4(),
            project_id=project.id,
            kind=QExcursionKind.transit if trip else QExcursionKind.storage,
            site_id=z.site_id if z else trip.site_id,  # type: ignore[union-attr]
            zone_id=z.zone_id if z else None,
            trip_id=trip.id if trip else None,
            compartment=compartment,
            storage_class=sc,
            status=ST.detected,
            detected_at=now(),
            alerts_sent=[],
            created_by_user_id=actor,
        )
        before_sev = x.severity if match else None
        was_transient = x.transient if match else True
        x.transient = r.transient
        x.started_at = start
        x.ended_at = None if r.ongoing else end
        x.duration_min = r.duration
        x.peak_value = r.peak
        x.peak_point_id = r.peak_point
        x.max_deviation = b.q2(r.max_deviation) or Decimal(0)
        x.degree_minutes = r.degree_minutes
        x.severity = r.severity
        x.data_gap = r.data_gap
        x.range_min, x.range_max = lim.lo, lim.hi
        if match is None:
            db.add(x)
        used.add(x.id)
        db.flush()
        if x.transient:
            continue
        if x.exc_no is None:
            x.exc_no = b.number(db, project, RT, x.started_at)
        if auto and (
            was_transient
            or before_sev is None
            or SEVERITY_RANK[x.severity] > SEVERITY_RANK[before_sev]
        ):
            _on_detected(db, project, x, actor, manual=manual and r.ongoing, notify=notify)
        changed.append(x)
    for x in existing:
        if x.id not in used and x.status != ST.dismissed and x.started_at >= t0:
            # the run vanished (e.g. its readings were voided, Q-IMP-05)
            x.status = ST.voided
            b.audit_status(db, None, project, RT, x.id, "live", "voided", reason="readings voided")
    db.flush()
    return changed


def _on_detected(
    db: Session,
    project: Project,
    x: QExcursion,
    actor: uuid.UUID | None,
    *,
    manual: bool,
    notify: bool,
) -> None:
    """Q-EXC-04 alerts and Q-EXC-05 NCR + hold for major / critical (once each)."""
    serious = x.severity != SEV.minor
    if notify and (serious or manual) and x.status in EXCURSION_LIVE:
        _alert(db, project, x)
    if not serious or x.status not in EXCURSION_LIVE:
        return
    if x.ncr_id is None:
        n = b.raise_ncr(
            db,
            project,
            QNcrSourceType.excursion if x.kind != QExcursionKind.transit else QNcrSourceType.trip,
            x.id if x.kind != QExcursionKind.transit else x.trip_id,  # type: ignore[arg-type]
            actor=actor,
            classification=QNcrClass(x.severity.value),
            category=QNcrCategory.temperature,
            title=_title(db, x),
        )
        x.ncr_id = n.id
    if x.kind == QExcursionKind.transit:
        _notify_consignees(db, x)
        return
    if x.hold_id is None and bool(b.setting(db, project.id, "excursion_auto_hold")):
        zone = db.get(Zone, x.zone_id) if x.zone_id else None
        snap = stock_svc.latest_before(db, x.site_id, x.started_at) if x.site_id else None
        lines = stock_svc.stock_hold_lines(db, snap, zone.code if zone else None) if snap else []
        h = hold_svc.place(
            db,
            project,
            site_id=x.site_id,  # type: ignore[arg-type]
            reason=QHoldReason.excursion,
            lines=lines,
            placed_by=actor,
            zone_id=x.zone_id,
            zone_level=not lines,
            storage_class=x.storage_class if x.storage_class == QStorageClass.pharma_2_8 else None,
            source=(RT, x.id, x.exc_no),
            ncr_id=x.ncr_id,
            note=f"Stock of the {b.local(snap.as_of):%Y-%m-%d %H:%M} snapshot"
            if snap
            else "Zone-level hold: add the lines (Q-HLD-02)",
        )
        x.hold_id = h.id


def _title(db: Session, x: QExcursion) -> str:
    where = ""
    if x.zone_id:
        zone = db.get(Zone, x.zone_id)
        where = zone.code if zone else ""
    elif x.trip_id:
        t = db.get(QTrip, x.trip_id)
        where = t.trip_no if t else ""
    end = f"{b.local(x.ended_at):%H:%M}" if x.ended_at else "ongoing"
    return f"{where} excursion {b.local(x.started_at):%Y-%m-%d %H:%M}–{end} ({x.severity.value})"


def _alert(db: Session, project: Project, x: QExcursion) -> None:
    users = b.holders(db, project, C.excursion_assess, x.site_id) | set(
        b.resolvers(db, project, RT, "impact", ctx(x), qualifier=qualifier(x), record_id=x.id)
    )
    peak = f"{x.peak_value} °C" if x.peak_value is not None else ""
    b.send(
        db,
        project,
        users,
        f"exc:{x.id}:alert:{x.severity.value}",
        f"Temperature excursion {x.exc_no} ({x.severity.value})",
        f"انحراف حراري {x.exc_no} ({x.severity.value})",
        body_en=f"{_title(db, x)}; peak {peak}. Check the product and record the cause.",
        body_ar=f"{_title(db, x)}؛ الذروة {peak}. افحص المنتج وسجّل السبب.",
        rt=RT,
        rid=x.id,
        path=f"/quality/excursions/{x.id}",
    )


def _notify_consignees(db: Session, x: QExcursion) -> None:
    """Q-TRN-05: a "notify consignee" task on the shipments delivered after the start."""
    from app.models.quality.q3 import QShipment  # noqa: PLC0415

    for s in db.scalars(select(QShipment).where(QShipment.trip_id == x.trip_id)):
        if s.delivered_at is None or s.delivered_at >= x.started_at:
            s.notify_consignee = True


def detect_trip(
    db: Session,
    project: Project,
    trip: QTrip,
    actor: uuid.UUID | None,
    notify: bool = True,
    auto: bool = True,
) -> list[QExcursion]:
    """Q-TRN-05: transit excursions per compartment with the compartment range and the bands of
    its strictest class."""
    from app.services.quality.q3 import transport  # noqa: PLC0415

    out: list[QExcursion] = []
    for comp in trip.compartments or []:
        code = comp["code"]
        rows = db.execute(
            select(
                QReading.measured_at, QReading.temperature_c, QReading.id, QReading.probe_fault
            ).where(
                QReading.target_type == QReadingTarget.trip,
                QReading.target_id == trip.id,
                QReading.channel == code,
                QReading.voided.is_(False),
            )
        ).all()
        if not rows:
            continue
        pid = uuid.uuid5(trip.id, code)
        readings = [eng.Reading(pid, r[0], r[1], r[2], r[3]) for r in rows]
        t0 = b.floor_minute(min(r.at for r in readings))
        t1 = b.floor_minute(max(r.at for r in readings)) + timedelta(minutes=60)
        sc = transport.strictest(comp)
        d = STORAGE_CLASSES[sc]
        lim = eng.Limits(
            Decimal(str(comp["range_min"])) if comp.get("range_min") is not None else None,
            Decimal(str(comp["range_max"])) if comp.get("range_max") is not None else None,
        )
        interval = int(comp.get("interval_minutes") or 5)
        factor = b.dsetting(db, project.id, "reading_gap_factor")
        gr = eng.grid(readings, {pid: interval}, factor, lim, t0, t1)
        found = eng.runs(gr, eng.Bands(d.alarm_delay, d.d1, d.d2, d.t1, d.t2), lim)
        out += _reconcile(
            db,
            project,
            None,
            trip,
            code,
            gr,
            found,
            t0,
            t1,
            actor,
            manual=False,
            notify=notify,
            sc=sc,
            lim=lim,
            auto=auto,
        )
    return out


# ---- workflow -----------------------------------------------------------------------------------


def _live(x: QExcursion, *allowed: QExcursionStatus) -> None:
    if x.transient or x.status not in allowed:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            f"Not allowed while {x.status.value}.",
            "غير مسموح في هذه الحالة.",
        )


def _assessor(db: Session, p: Principal, project: Project, x: QExcursion) -> None:
    """268 with a real grant on the site, or the responsible person of `excursion.impact`."""
    g = p.grant(project.id, C.excursion_assess)
    if g is None:
        raise forbidden_error()
    if g.scope.value == "responsible":
        if not b.resolves(db, p, project, RT, x.id, "impact", ctx(x), qualifier(x)):
            raise forbidden_error()
    elif not g.covers_site(x.site_id):
        raise forbidden_error("This site is outside your scope.")


def acknowledge(db: Session, p: Principal, exc_id: uuid.UUID) -> dict[str, Any]:
    x, project = get_exc(db, p, exc_id)
    qc.writable(project, p)
    _assessor(db, p, project, x)
    if x.acknowledged_at is None:
        x.acknowledged_by_user_id = p.user.id
        x.acknowledged_at = now()
    return read(db, p, x)


def set_cause(db: Session, p: Principal, exc_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Detected → Under Assessment (268, cause entered)."""
    x, project = get_exc(db, p, exc_id)
    qc.writable(project, p)
    _assessor(db, p, project, x)
    _live(x, ST.detected, ST.under_assessment)
    x.cause = QExcursionCause(body["cause"])
    x.cause_note = (body.get("cause_note") or "").strip() or None
    if x.cause == QExcursionCause.other and not x.cause_note:
        raise qc.field_err("cause_note", "Describe the cause.", "صف السبب.")
    if x.status == ST.detected:
        x.status = ST.under_assessment
        b.audit_status(
            db, p, project, RT, x.id, ST.detected, ST.under_assessment, cause=x.cause.value
        )
    return read(db, p, x)


def hold_lines(db: Session, x: QExcursion) -> list[QHoldLine]:
    if x.hold_id is None:
        return []
    return list(db.scalars(select(QHoldLine).where(QHoldLine.hold_id == x.hold_id)))


def _check_line(db: Session, ln: QHoldLine, imp: QExcursionImpact) -> None:
    if (
        imp.decision == QImpactDecision.release
        and imp.evidence_attachment_id is None
        and len((imp.justification or "").strip()) < 50
    ):
        raise qc.err(
            422,
            ErrorCode.IMPACT_EVIDENCE_REQUIRED,
            f"{ln.sku} {ln.batch}: a release needs stability evidence or a justification of "
            "at least 50 characters (Q-EXC-08).",
            f"{ln.sku} {ln.batch}: الإفراج يتطلب دليل ثبات أو مبرراً لا يقل عن 50 حرفاً.",
        )
    if imp.decision in (QImpactDecision.release, QImpactDecision.destroy):
        cust = db.get(QCustomer, ln.owner_customer_id) if ln.owner_customer_id else None
        if (
            cust is not None
            and cust.owner_release_approval
            and imp.owner_decision_attachment_id is None
        ):
            raise qc.err(
                422,
                ErrorCode.OWNER_DECISION_REQUIRED,
                f"{cust.name_en} decides on {ln.sku} {ln.batch}: attach the owner's written "
                "decision (Q-EXC-09).",
                f"يقرر {cust.name_ar} بشأن {ln.sku} {ln.batch}: أرفق قرار المالك المكتوب.",
            )


def save_impacts(
    db: Session, p: Principal, exc_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    x, project = get_exc(db, p, exc_id)
    qc.writable(project, p)
    _assessor(db, p, project, x)
    _live(x, ST.under_assessment)
    _save(db, p, x, body.get("lines") or [])
    return read(db, p, x)


def _save(db: Session, p: Principal, x: QExcursion, rows: list[dict[str, Any]]) -> None:
    by_line = {ln.id: ln for ln in hold_lines(db, x)}
    have = {
        i.hold_line_id: i
        for i in db.scalars(select(QExcursionImpact).where(QExcursionImpact.excursion_id == x.id))
    }
    for r in rows:
        ln = by_line.get(r["hold_line_id"])
        if ln is None:
            raise qc.field_err(
                "lines", "A line is not on this excursion's hold.", "بند ليس ضمن حجز هذا الانحراف."
            )
        imp = have.get(ln.id) or QExcursionImpact(
            excursion_id=x.id, hold_line_id=ln.id, created_at=now(), created_by_user_id=p.user.id
        )
        imp.decision = QImpactDecision(r["decision"])
        imp.justification = (r.get("justification") or "").strip() or None
        imp.evidence_attachment_id = b.attachment_on(
            db, r.get("evidence_attachment_id"), A.q_hold, ln.hold_id, "evidence_attachment_id"
        )
        imp.owner_decision_attachment_id = b.attachment_on(
            db,
            r.get("owner_decision_attachment_id"),
            A.q_hold,
            ln.hold_id,
            "owner_decision_attachment_id",
        )
        imp.owner_contact_name = r.get("owner_contact_name")
        imp.owner_decision_date = r.get("owner_decision_date")
        _check_line(db, ln, imp)
        if ln.id not in have:
            db.add(imp)
            have[ln.id] = imp
    db.flush()


def assess(db: Session, p: Principal, exc_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Under Assessment → Assessed: every hold line decided (Q-EXC-07), evidence (Q-EXC-08), the
    owner's decision (Q-EXC-09) and the `excursion.impact` sign-off. A `returned` decision keeps
    the assessment open."""
    x, project = get_exc(db, p, exc_id)
    qc.writable(project, p)
    _assessor(db, p, project, x)
    _live(x, ST.under_assessment)
    if body.get("lines"):
        _save(db, p, x, body["lines"])
    lines = hold_lines(db, x)
    imps = {
        i.hold_line_id: i
        for i in db.scalars(select(QExcursionImpact).where(QExcursionImpact.excursion_id == x.id))
    }
    missing = [ln for ln in lines if ln.id not in imps]
    if x.hold_id is None or not lines or missing:
        raise qc.err(
            422,
            ErrorCode.IMPACT_LINES_INCOMPLETE,
            f"Decide every line of the hold: {len(lines) - len(missing)} of {len(lines)} "
            "decided (Q-EXC-07).",
            f"قرر كل بنود الحجز: {len(lines) - len(missing)} من {len(lines)}.",
            missing=[str(ln.id) for ln in missing],
        )
    for ln in lines:
        _check_line(db, ln, imps[ln.id])
    decision = body.get("decision") or "approved"
    s = b.sign(
        db,
        p,
        project,
        RT,
        x.id,
        "impact",
        ctx(x),
        decision=decision,
        comment=body.get("comment"),
        qualifier=qualifier(x),
    )
    if decision == "returned":
        return read(db, p, x)
    x.status = ST.assessed
    x.assessed_at = now()
    # Q-EXC-10: the approved assessment proposes the decisions on the hold lines
    for ln in lines:
        imp = imps[ln.id]
        ln.proposed_decision = imp.decision
        if imp.owner_decision_attachment_id and not ln.owner_decision_attachment_id:
            ln.owner_decision_attachment_id = imp.owner_decision_attachment_id
    b.audit_status(db, p, project, RT, x.id, ST.under_assessment, ST.assessed, signoff=str(s.id))
    maybe_close(db, x)
    return read(db, p, x)


def reopen(db: Session, p: Principal, exc_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Assessed → Under Assessment (268 + RPM, reason ≥ 20 chars)."""
    x, project = get_exc(db, p, exc_id)
    qc.writable(project, p)
    _assessor(db, p, project, x)
    _live(x, ST.assessed)
    why = qc.reason(body.get("reason"))
    if not b.resolves(db, p, project, RT, x.id, "impact", ctx(x), qualifier(x)):
        raise forbidden_error("Only the responsible person for the impact assessment reopens it.")
    x.status = ST.under_assessment
    x.reopen_reason = why
    b.audit_status(db, p, project, RT, x.id, ST.assessed, ST.under_assessment, reason=why)
    return read(db, p, x)


def close_no_impact(
    db: Session, p: Principal, exc_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    """Under Assessment → Closed for an excursion that needs no assessment (Q-EXC-06)."""
    x, project = get_exc(db, p, exc_id)
    qc.writable(project, p)
    _assessor(db, p, project, x)
    _live(x, ST.under_assessment)
    if impact_required(db, x):
        raise qc.err(
            422,
            ErrorCode.IMPACT_LINES_INCOMPLETE,
            "This excursion needs a product impact assessment (Q-EXC-06).",
            "هذا الانحراف يتطلب تقييم الأثر على المنتج.",
        )
    x.no_impact_note = qc.reason(body.get("note"), 20, "note")
    x.status = ST.closed
    x.closed_at = now()
    b.audit_status(db, p, project, RT, x.id, ST.under_assessment, ST.closed, note=x.no_impact_note)
    return read(db, p, x)


def dismiss(db: Session, p: Principal, exc_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Detected / Under Assessment → Dismissed (probe fault, Q-EXC-11): evidence that the
    instrument was faulty and the `excursion.impact` sign-off; readings get `probe_fault`, the
    instrument is set out of service."""
    x, project = get_exc(db, p, exc_id)
    qc.writable(project, p)
    _assessor(db, p, project, x)
    _live(x, ST.detected, ST.under_assessment)
    kind = body.get("evidence_kind")
    if kind not in ("calibration_check", "second_instrument"):
        raise qc.field_err(
            "evidence_kind",
            "Evidence is a calibration check or a second instrument's readings.",
            "الدليل: فحص معايرة أو قراءات جهاز ثانٍ.",
        )
    m = b.mte_of(db, project, body["mte_id"])
    note = qc.reason(body.get("note"), 20, "note")
    if kind == "second_instrument" and body.get("second_mte_id") is None:
        raise qc.field_err("second_mte_id", "Name the second instrument.", "حدد الجهاز الثاني.")
    if kind == "calibration_check" and body.get("error_c") is None:
        raise qc.field_err(
            "error_c", "Enter the error found on the check (°C).", "أدخل الخطأ المكتشف (°م)."
        )
    s = b.sign(
        db,
        p,
        project,
        RT,
        x.id,
        "impact",
        ctx(x),
        decision="approved",
        comment=f"Dismissed: {note}",
        qualifier=qualifier(x),
    )
    end = x.ended_at or now()
    pts = [pt.id for pt in storage.points_of(db, x.zone_id, active=False)] if x.zone_id else []
    flagged = 0
    for r in db.scalars(
        select(QReading).where(
            QReading.voided.is_(False),
            QReading.measured_at >= x.started_at - timedelta(minutes=60),
            QReading.measured_at < end,
            (QReading.mte_id == m.id) | (QReading.target_id.in_(pts or [uuid.uuid4()])),
        )
    ):
        if r.mte_id == m.id or _logger_at(db, r.target_id, m.id, r.measured_at):
            r.probe_fault = True
            flagged += 1
    m.cal_status = QCalStatus.out_of_service
    m.cal_status_reason = f"Probe fault found on {x.exc_no} ({kind})"
    x.dismissal = {
        "evidence_kind": kind,
        "mte_id": str(m.id),
        "second_mte_id": str(body["second_mte_id"]) if body.get("second_mte_id") else None,
        "error_c": str(body.get("error_c")) if body.get("error_c") is not None else None,
        "attachment_id": str(body["attachment_id"]) if body.get("attachment_id") else None,
        "note": note,
        "readings_flagged": flagged,
        "signoff_id": str(s.id),
    }
    before = x.status
    x.status = ST.dismissed
    x.closed_at = now()
    b.audit_status(db, p, project, RT, x.id, before, ST.dismissed, mte=m.mte_no)
    return read(db, p, x)


def _logger_at(db: Session, point_id: uuid.UUID, mte_id: uuid.UUID, at: datetime) -> bool:
    pt = db.get(QMonitoringPoint, point_id)
    if pt is None:
        return False
    for lg in pt.loggers or []:
        if lg["mte_id"] != str(mte_id):
            continue
        f = datetime.fromisoformat(lg["from"])
        t = datetime.fromisoformat(lg["to"]) if lg.get("to") else None
        if f <= at and (t is None or at < t):
            return True
    return False


def maybe_close(db: Session, x: QExcursion) -> None:
    """Assessed → Closed (System): every line of the linked hold final and the linked NCR (if
    any) Closed."""
    if x.status != ST.assessed:
        return
    if x.hold_id is not None:
        h = db.get(QHold, x.hold_id)
        if h is not None and not hold_svc.final(db, h):
            return
    if x.ncr_id is not None:
        n = db.get(QNcr, x.ncr_id)
        if n is not None and n.status not in (QNcrStatus.closed, QNcrStatus.voided):
            return
    x.status = ST.closed
    x.closed_at = now()
    project = db.get(Project, x.project_id)
    if project is not None:
        b.audit_status(db, None, project, RT, x.id, ST.assessed, ST.closed)


# ---- NCR source adapter (list NS `excursion`) ----------------------------------------------------


def ncr_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    x = db.get(QExcursion, source_id)
    if x is None or x.project_id != project.id:
        raise qc.field_err(
            "source_id", "The excursion is not on this project.", "الانحراف ليس في المشروع."
        )
    zone = db.get(Zone, x.zone_id) if x.zone_id else None
    lo = x.range_min if x.range_min is not None else "—"
    hi = x.range_max if x.range_max is not None else "—"
    rng = f"{lo} … {hi} °C"
    return reg.SourceInfo(
        ref=x.exc_no,
        title=_title(db, x),
        site_id=x.site_id,
        zone_id=x.zone_id,
        engagement_id=b.operator_engagement(db, project),
        item_key=f"EXC:{zone.code if zone else ''}:{x.storage_class.value}",
        detection_stage=QDetectionStage.storage,
        requirement_en=f"Storage class {x.storage_class.value}: keep the product within {rng}.",
        requirement_ar=f"فئة التخزين {x.storage_class.value}: الحفاظ على المنتج ضمن {rng}.",
        finding_en=(
            f"Out of range from {b.local(x.started_at):%Y-%m-%d %H:%M} for {x.duration_min} min; "
            f"peak {x.peak_value} °C, max deviation {x.max_deviation} °C, {x.degree_minutes} °C·min"
            + ("; data gap inside" if x.data_gap else "")
            + "."
        ),
        finding_ar=(
            f"خارج النطاق منذ {b.local(x.started_at):%Y-%m-%d %H:%M} لمدة {x.duration_min} دقيقة؛ "
            f"الذروة {x.peak_value} °م، أقصى انحراف {x.max_deviation} °م."
        ),
        proposed_class=QNcrClass(x.severity.value),
        location_ref=zone.code if zone else None,
        record_type=RT,
    )


def ncr_close_check(db: Session, n: QNcr) -> list[reg.Blocker]:
    """Q-NCR-15: an excursion NCR closes only when its hold lines are released or rejected."""
    x = db.get(QExcursion, n.source_id) if n.source_id else None
    if x is None or x.hold_id is None:
        return []
    h = db.get(QHold, x.hold_id)
    if h is None:
        return []
    if any(ln.line_status == QHoldLineStatus.on_hold for ln in hold_svc.lines_of(db, h)):
        return [
            reg.Blocker(
                "HOLD_NOT_DECIDED",
                f"{h.hold_no}: lines are still on hold.",
                f"{h.hold_no}: بنود ما زالت محجوزة.",
            )
        ]
    return []


def on_ncr_status(db: Session, n: QNcr, to: QNcrStatus) -> None:
    if to != QNcrStatus.closed:
        return
    for x in db.scalars(select(QExcursion).where(QExcursion.ncr_id == n.id)):
        maybe_close(db, x)


# ---- read model ---------------------------------------------------------------------------------


def brief(x: QExcursion) -> dict[str, Any]:
    return {
        "id": x.id,
        "exc_no": x.exc_no,
        "severity": x.severity,
        "status": x.status,
        "started_at": x.started_at,
        "ended_at": x.ended_at,
        "duration_min": x.duration_min,
    }


def read(db: Session, p: Principal, x: QExcursion) -> dict[str, Any]:
    from app.services.quality import signoff  # noqa: PLC0415

    project = db.get(Project, x.project_id)
    assert project is not None  # noqa: S101
    hide = b.hide_names(p, project.id)
    imps = {
        i.hold_line_id: i
        for i in db.scalars(select(QExcursionImpact).where(QExcursionImpact.excursion_id == x.id))
    }
    lines = hold_lines(db, x)
    pt = db.get(QMonitoringPoint, x.peak_point_id) if x.peak_point_id else None
    trip = db.get(QTrip, x.trip_id) if x.trip_id else None
    n = db.get(QNcr, x.ncr_id) if x.ncr_id else None
    h = db.get(QHold, x.hold_id) if x.hold_id else None
    actions = []
    g = p.grant(project.id, C.excursion_assess)
    if g is not None and not x.transient:
        resolves = b.resolves(db, p, project, RT, x.id, "impact", ctx(x), qualifier(x))
        real = g.scope.value != "responsible"
        if x.status in (ST.detected, ST.under_assessment) and (real or resolves):
            actions += ["cause", "acknowledge"]
        if x.status == ST.under_assessment and (real or resolves):
            actions.append("impacts")
            if resolves:
                actions.append("assess")
            if not impact_required(db, x):
                actions.append("close_no_impact")
        if x.status in (ST.detected, ST.under_assessment) and resolves:
            actions.append("dismiss")
        if x.status == ST.assessed and resolves:
            actions.append("reopen")
    return {
        "id": x.id,
        "project_id": x.project_id,
        "exc_no": x.exc_no,
        "kind": x.kind,
        "site": b.site_ref(db, x.site_id),
        "zone": b.zone_ref(db, x.zone_id),
        "trip": {"id": trip.id, "trip_no": trip.trip_no} if trip else None,
        "compartment": x.compartment,
        "storage_class": x.storage_class,
        "transient": x.transient,
        "started_at": x.started_at,
        "ended_at": x.ended_at,
        "duration_min": x.duration_min,
        "peak_value": x.peak_value,
        "peak_point": pt.code if pt else None,
        "max_deviation": x.max_deviation,
        "degree_minutes": x.degree_minutes,
        "severity": x.severity,
        "data_gap": x.data_gap,
        "range_min": x.range_min,
        "range_max": x.range_max,
        "cause": x.cause,
        "cause_note": x.cause_note,
        "status": x.status,
        "impact_required": impact_required(db, x),
        "no_impact_note": x.no_impact_note,
        "dismissal": x.dismissal,
        "acknowledged_at": x.acknowledged_at,
        "acknowledged_by": b.user_ref(db, x.acknowledged_by_user_id, hide),
        "detected_at": x.detected_at,
        "assessed_at": x.assessed_at,
        "closed_at": x.closed_at,
        "ncr": {
            "id": n.id,
            "ncr_no": n.ncr_no,
            "status": n.status,
            "classification": n.classification,
        }
        if n
        else None,
        "hold": {"id": h.id, "hold_no": h.hold_no, "status": h.status, "zone_level": h.zone_level}
        if h
        else None,
        "impact_lines": [
            {
                "hold_line": hold_svc.line_read(db, ln),
                "decision": imps[ln.id].decision if ln.id in imps else None,
                "justification": imps[ln.id].justification if ln.id in imps else None,
                "evidence_attachment_id": imps[ln.id].evidence_attachment_id
                if ln.id in imps
                else None,
                "owner_decision_attachment_id": imps[ln.id].owner_decision_attachment_id
                if ln.id in imps
                else None,
                "owner_contact_name": None
                if hide or ln.id not in imps
                else imps[ln.id].owner_contact_name,
                "owner_decision_date": imps[ln.id].owner_decision_date if ln.id in imps else None,
            }
            for ln in lines
        ],
        "allowed_actions": actions,
        "signoffs": [
            signoff.read(db, s, show_scans=not hide) for s in signoff.signoffs_for(db, RT, x.id)
        ],
    }


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page_no: int,
    size: int,
    *,
    statuses: list[QExcursionStatus] | None = None,
    severity: QExcursionSeverity | None = None,
    zone_id: uuid.UUID | None = None,
    kind: QExcursionKind | None = None,
    transients: bool = False,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    g = b.list_grant(p, project.id)
    q = select(QExcursion).where(
        QExcursion.project_id == project.id, QExcursion.transient.is_(transients)
    )
    if statuses:
        q = q.where(QExcursion.status.in_(statuses))
    else:
        q = q.where(QExcursion.status != ST.voided)
    if severity:
        q = q.where(QExcursion.severity == severity)
    if zone_id:
        q = q.where(QExcursion.zone_id == zone_id)
    if kind:
        q = q.where(QExcursion.kind == kind)
    items = []
    for x in db.scalars(q.order_by(QExcursion.started_at.desc())):
        if g.scope.value == "responsible":
            if not b.can_view(db, p, project, RT, x.id, x.site_id, lambda x=x: _steps(db, x)):
                continue
        elif x.site_id and not g.covers_site(x.site_id):
            continue
        items.append(
            {
                **brief(x),
                "kind": x.kind,
                "zone": b.zone_ref(db, x.zone_id),
                "trip_id": x.trip_id,
                "storage_class": x.storage_class,
                "peak_value": x.peak_value,
                "max_deviation": x.max_deviation,
                "data_gap": x.data_gap,
                "acknowledged": x.acknowledged_at is not None,
                "ncr_id": x.ncr_id,
                "hold_id": x.hold_id,
            }
        )
    return b.page(items, page_no, size)


def open_steps(db: Session, project: Project) -> list[reg.OpenStep]:
    out = []
    for x in db.scalars(
        select(QExcursion).where(
            QExcursion.project_id == project.id,
            QExcursion.transient.is_(False),
            QExcursion.status.in_([ST.detected, ST.under_assessment]),
        )
    ):
        if not impact_required(db, x):
            continue
        out.append(
            reg.OpenStep(
                reg.PendingStep(
                    RT,
                    x.id,
                    project.id,
                    x.exc_no or "EXC",
                    _title(db, x),
                    "impact",
                    x.detected_at,
                    f"/quality/excursions/{x.id}",
                    "Q3",
                ),
                qualifier(x),
                x.site_id,
                None,
                frozenset(),
            )
        )
    return out


_ = QMteItem
