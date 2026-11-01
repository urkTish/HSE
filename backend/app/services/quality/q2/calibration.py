"""Calibration of measuring and test equipment (spec 8-quality §C.4, Q-CAL-01…07): calibration and
verification records, the M&TE status recomputation that replaces Q0's `unknown`, the manual
out-of-service / limited-use override, out-of-tolerance impact reviews and the status label.

The M&TE register itself (table, CRUD, usage) is Q0's (`app.services.quality.mte`). Q2 recomputes
`cal_status` whenever an instrument or its calibration changes (a session `before_flush` hook, so
Q0's own create / update endpoints also get a live status) and in the daily job."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, event, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import (
    QCalStatus,
    QLinkKind,
    QMteCheckKind,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QRecordType,
    QSupplierCategory,
    label,
)
from app.core.quality.q2 import (
    QCalKind,
    QCalRecordStatus,
    QMteOverride,
    QOotDecision,
    QOotStatus,
)
from app.models import Project
from app.models.quality import QMteItem, QMteUsage, QSettings, QSupplier
from app.models.quality.q2 import QCalibration, QMteCalOverride, QOotItem, QOotReview
from app.schemas.hse_common import ApiWarning
from app.services import audit
from app.services.common import paginate
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import mte as qmte
from app.services.quality import numbering, rpm, suppliers
from app.services.quality import registry as reg
from app.services.quality import settings as qs
from app.services.quality.q2 import base
from app.services.quality.q2.evaluators import d

C = Capability
RT = QRecordType
CS = QCalStatus
A = AttachmentOwner

# Q-CAL-04: other parts' measurements made with an instrument (Q3 logger readings of monitoring
# points the logger was assigned to). fn(db, mte, period_from, period_to) → item dicts with
# record_type, record_id, ref, used_at, value, limit_low, limit_high. Q3 registers it (D-370).
OOT_SOURCES: list[Any] = []
# Usage rows an `OOT_SOURCES` function already reports in its own items (Q3: the logger
# assignment and manual-reading rows of a monitoring point). fn(db, usage) → True to skip.
OOT_USAGE_COVERED: list[Any] = []


# ---- status (Q-CAL-01 / -02 / -03) --------------------------------------------------------------


def due_on(cal_date: date, interval_months: int) -> date:
    """Q-CAL-01 add_months(cal_date, interval) − 1 day (month-end clamp). QX10."""
    return base.add_months(cal_date, interval_months) - timedelta(days=1)


def _soon_days(db: Session, project_id: uuid.UUID) -> int:
    return int(qs.value(db, project_id, "mte_due_soon_days") or 30)


def compute_status(
    db: Session, m: QMteItem, today: date, soon_days: int | None = None
) -> tuple[QCalStatus, str | None]:
    """Q-CAL-02: manual out_of_service / limited_use win; check kind none → not_required; the last
    accepted calibration left out of tolerance → out_of_service (Q-CAL-03); never calibrated →
    overdue; past due → overdue; within `mte_due_soon_days` → due_soon; else calibrated."""
    ov = db.get(QMteCalOverride, m.id) if m.id else None
    if ov is not None:
        return CS(ov.status.value), f"{label('mte_override', ov.status)}: {ov.reason}"
    if m.check_kind == QMteCheckKind.none:
        return CS.not_required, None
    if m.last_calibration_id is not None:
        last = db.get(QCalibration, m.last_calibration_id)
        if last is not None and not last.as_left_ok:
            return CS.out_of_service, (
                f"As-left out of tolerance on {last.cal_date.isoformat()}; out of service until a "
                "later calibration is in tolerance."
            )
    if m.cal_due_on is None:
        return CS.overdue, "Never calibrated."
    if today > m.cal_due_on:
        return CS.overdue, f"Due {m.cal_due_on.isoformat()}."
    days = _soon_days(db, m.project_id) if soon_days is None else soon_days
    if today >= m.cal_due_on - timedelta(days=days):
        return CS.due_soon, f"Due {m.cal_due_on.isoformat()}."
    return CS.calibrated, None


def recompute(db: Session, m: QMteItem, today: date | None = None) -> bool:
    if today is None:
        project = db.get(Project, m.project_id)
        today = qc.project_day(project) if project else now().date()
    st, why = compute_status(db, m, today)
    changed = st != m.cal_status
    m.cal_status = st
    if why is not None or m.cal_status_reason is None or changed:
        m.cal_status_reason = why[:500] if why else None
    return changed


_WATCH = ("check_kind", "interval_months", "cal_due_on", "last_calibration_id", "cal_status")


def _before_flush(session: Session, _ctx: Any, _instances: Any) -> None:
    """Q-CAL-02 "recomputed on every change": new or changed instruments get their status before
    they are written, including those created through Q0's register endpoints."""
    from sqlalchemy import inspect as sa_inspect  # noqa: PLC0415

    items = [o for o in session.new if isinstance(o, QMteItem)]
    for o in session.dirty:
        if isinstance(o, QMteItem):
            st = sa_inspect(o)
            if any(st.attrs[k].history.has_changes() for k in _WATCH):
                items.append(o)
    if not items:
        return
    with session.no_autoflush:
        for m in items:
            if m.project_id is None:
                continue
            recompute(session, m)


_listening = False


def install_listener() -> None:
    global _listening  # noqa: PLW0603
    if not _listening:
        event.listen(Session, "before_flush", _before_flush)
        _listening = True


def set_override(
    db: Session, p: Principal, mte_id: uuid.UUID, status: QMteOverride | None, why: str | None
) -> dict[str, Any]:
    """Manual out_of_service / limited_use with a reason (261), or clear it (status None)."""
    m = qmte.get_item(db, p, mte_id)
    project = base.project_of(db, m.project_id)
    qc.writable(project, p)
    qc.require_cover(p, project.id, C.mte_manage, m.site_id, m.owner_engagement_id)
    ov = db.get(QMteCalOverride, m.id)
    if status is None:
        if ov is not None:
            db.delete(ov)
    else:
        text = qc.reason(why, 10)
        if ov is None:
            ov = QMteCalOverride(mte_id=m.id, status=status, reason=text, set_at=now())
            db.add(ov)
        ov.status, ov.reason, ov.set_by_user_id, ov.set_at = status, text, p.user.id, now()
    db.flush()
    before = m.cal_status
    recompute(db, m)
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(project.id),
        entity_type=EntityType.q_mte,
        entity_id=m.id,
        project_id=project.id,
        before={"cal_status": before.value},
        after={"cal_status": m.cal_status.value, "override": status.value if status else None},
    )
    return qmte.read(db, m)


# ---- calibration records -------------------------------------------------------------------------


def _points(
    m: QMteItem, raw: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], bool, bool, Decimal | None]:
    """error = as_found − nominal; in tolerance ⇔ |error| ≤ tolerance (the item's ± tolerance by
    default). as_left defaults to as_found when not adjusted."""
    out = []
    found_ok = left_ok = True
    worst: Decimal | None = None
    for i, pt in enumerate(raw):
        nominal, found = d(pt.get("nominal")), d(pt.get("as_found"))
        if nominal is None or found is None:
            raise qc.field_err(f"points[{i}]", "Each point needs a nominal and an as-found value.")
        tol = d(pt.get("tolerance")) or m.tolerance_value
        if tol is None:
            raise qc.field_err(f"points[{i}].tolerance", "Give the tolerance (the item has none).")
        left = d(pt.get("as_left"))
        err_f = found - nominal
        err_l = (left - nominal) if left is not None else err_f
        f_ok, l_ok = abs(err_f) <= tol, abs(err_l) <= tol
        found_ok &= f_ok
        left_ok &= l_ok
        if not f_ok and (worst is None or abs(err_f) > worst):
            worst = abs(err_f)
        out.append(
            {
                "nominal": str(nominal),
                "as_found": str(found),
                "as_left": str(left) if left is not None else None,
                "tolerance": str(tol),
                "error": str(err_f),
                "in_tolerance": f_ok,
                "as_left_in_tolerance": l_ok,
            }
        )
    return out, found_ok, left_ok, worst


def read(db: Session, c: QCalibration, p: Principal | None = None) -> dict[str, Any]:
    m = db.get(QMteItem, c.mte_id)
    sup = db.get(QSupplier, c.provider_supplier_id) if c.provider_supplier_id else None
    ref = db.get(QMteItem, c.reference_mte_id) if c.reference_mte_id else None
    actions: list[str] = []
    if p is not None and c.status == QCalRecordStatus.draft:
        project = base.project_of(db, c.project_id)
        if p.grant(c.project_id, C.mte_manage) is not None:
            actions.append("edit")
        if rpm.resolves(db, p, project, RT.calibration, "accept", ctx(c, m), record_id=c.id):
            actions += ["accept", "reject"]
    return {
        "id": c.id,
        "project_id": c.project_id,
        "cal_no": c.cal_no,
        "mte_id": c.mte_id,
        "mte_no": m.mte_no if m else None,
        "mte_type": m.mte_type if m else None,
        "kind": c.kind,
        "cal_date": c.cal_date,
        "provider_supplier_id": c.provider_supplier_id,
        "provider_code": sup.supplier_code if sup else None,
        "in_house": c.in_house,
        "reference_mte_id": c.reference_mte_id,
        "reference_mte_no": ref.mte_no if ref else None,
        "certificate_no": c.certificate_no,
        "points": c.points or [],
        "as_found_ok": c.as_found_ok,
        "as_left_ok": c.as_left_ok,
        "max_found_error": str(c.max_found_error) if c.max_found_error is not None else None,
        "traceability": c.traceability,
        "uncertainty": c.uncertainty,
        "verification_note": c.verification_note,
        "next_due": c.next_due,
        "decision_comment": c.decision_comment,
        "decided_at": c.decided_at,
        "decided_by": base.user_ref(
            db, c.decided_by_user_id, p is None or base.read_only(p, c.project_id)
        ),
        "status": c.status,
        "certificate_count": base.attachment_count(db, A.q_calibration_cert, c.id),
        "actions": actions,
    }


def ctx(c: QCalibration, m: QMteItem | None) -> rpm.Ctx:
    return rpm.Ctx(
        m.site_id if m else None,
        m.owner_engagement_id if m else None,
        qc.ids(c.created_by_user_id),
    )


def get_cal(db: Session, p: Principal, cal_id: uuid.UUID) -> QCalibration:
    c = db.get(QCalibration, cal_id)
    if c is None:
        raise not_found("Calibration")
    m = qmte.get_item(db, p, c.mte_id)  # visibility of the instrument
    _ = m
    return c


def list_for_mte(db: Session, p: Principal, mte_id: uuid.UUID) -> list[dict[str, Any]]:
    m = qmte.get_item(db, p, mte_id)
    rows = db.scalars(
        select(QCalibration)
        .where(QCalibration.mte_id == m.id)
        .order_by(QCalibration.cal_date.desc(), QCalibration.created_at.desc())
    )
    return [read(db, c, p) for c in rows]


def _mte_scope(p: Principal, project_id: uuid.UUID) -> Any:
    """Lists narrow to the instruments of the user's sites and engagement tree (Q-ROL-02); an
    instrument owned by the project itself (no owner engagement) narrows by site only."""
    caps = (C.mte_manage, C.calibration_decide)
    return or_(
        base.scope_cond(p, project_id, caps, QMteItem.site_id, QMteItem.owner_engagement_id),
        and_(
            QMteItem.owner_engagement_id.is_(None),
            base.scope_cond(p, project_id, caps, QMteItem.site_id, None),
        ),
    )


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: QCalRecordStatus | None = None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    base.require_list(p, project.id, C.mte_manage, C.calibration_decide)
    stmt = (
        select(QCalibration)
        .join(QMteItem, QMteItem.id == QCalibration.mte_id)
        .where(QCalibration.project_id == project.id, _mte_scope(p, project.id))
    )
    if status:
        stmt = stmt.where(QCalibration.status == status)
    items, total = paginate(
        db,
        stmt.order_by(QCalibration.cal_date.desc(), QCalibration.created_at.desc()),
        page,
        page_size,
    )
    return {
        "items": [read(db, c, p) for c in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _provider_warnings(db: Session, m: QMteItem, c: QCalibration) -> list[ApiWarning]:
    out: list[ApiWarning] = []
    if c.provider_supplier_id is not None:
        sup = db.get(QSupplier, c.provider_supplier_id)
        if sup is None:
            raise qc.field_err("provider_supplier_id", "Unknown supplier.")
        if QSupplierCategory.calibration_lab.value not in [str(x) for x in (sup.categories or [])]:
            raise qc.field_err(
                "provider_supplier_id",
                "The provider must be a supplier of category calibration_lab.",
                "يجب أن يكون المزوّد مختبر معايرة.",
            )
        out += suppliers.check_use(db, sup.id)
        if c.kind == QCalKind.calibration:
            out += suppliers.lab_scope_warning(db, sup.id, m.mte_type.value, c.cal_date)
    elif c.in_house:
        if c.kind == QCalKind.calibration and c.reference_mte_id is None:
            raise qc.field_err(
                "reference_mte_id",
                "An in-house calibration names the reference standard (its MTE no).",
                "المعايرة الداخلية تتطلب جهاز المرجع.",
            )
    elif c.kind == QCalKind.calibration:
        raise qc.field_err(
            "provider_supplier_id", "Name the calibration laboratory or mark it in-house."
        )
    return out


def create(
    db: Session, p: Principal, mte_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QCalibration, list[ApiWarning]]:
    m = qmte.get_item(db, p, mte_id)
    project = base.project_of(db, m.project_id)
    qc.writable(project, p)
    qc.require_cover(p, project.id, C.mte_manage, m.site_id, m.owner_engagement_id)
    qc.require_profile(db, project)
    kind = QCalKind(
        body.get("kind")
        or ("verification" if m.check_kind == QMteCheckKind.verification else "calibration")
    )
    cal_date: date = body["cal_date"]
    if cal_date > qc.project_day(project):
        raise qc.field_err("cal_date", "The calibration date cannot be in the future.")
    c = QCalibration(
        id=uuid.uuid4(),
        project_id=project.id,
        mte_id=m.id,
        kind=kind,
        cal_date=cal_date,
        provider_supplier_id=body.get("provider_supplier_id"),
        in_house=bool(body.get("in_house")),
        reference_mte_id=body.get("reference_mte_id"),
        certificate_no=body.get("certificate_no"),
        traceability=body.get("traceability"),
        uncertainty=body.get("uncertainty"),
        verification_note=body.get("verification_note"),
        status=QCalRecordStatus.draft,
        created_by_user_id=p.user.id,
    )
    pts, f_ok, l_ok, worst = _points(m, list(body.get("points") or []))
    if kind == QCalKind.calibration and not pts:
        raise qc.field_err("points", "A calibration lists at least one point.")
    c.points, c.as_found_ok, c.as_left_ok, c.max_found_error = pts, f_ok, l_ok, worst
    if c.reference_mte_id is not None:
        ref = db.get(QMteItem, c.reference_mte_id)
        if ref is None or ref.project_id != project.id or ref.id == m.id:
            raise qc.field_err(
                "reference_mte_id",
                "The reference standard must be another instrument of the project.",
            )
    warnings = _provider_warnings(db, m, c)
    db.add(c)
    db.flush()
    base.audit_create(db, p, RT.calibration, c, mte=m.mte_no, cal_date=cal_date.isoformat())
    _notify_pending(db, project, c, m)
    return c, warnings


def _notify_pending(db: Session, project: Project, c: QCalibration, m: QMteItem) -> None:
    users = base.resolvers(db, project, RT.calibration, "accept", ctx(c, m), c.id)
    qc.send(
        db,
        users,
        f"{m.mte_no}: calibration of {c.cal_date.isoformat()} to accept",
        f"{m.mte_no}: معايرة بانتظار القبول",
        entity_type=EntityType.q_calibration,
        entity_id=c.id,
        project_id=project.id,
        key=f"cal_pending:{c.id}",
        path=f"/quality/calibration/{c.id}",
    )


def _ensure_draft(c: QCalibration, action: str) -> None:
    if c.status != QCalRecordStatus.draft:
        raise base.invalid("The calibration", c.status, action)


def update(
    db: Session, p: Principal, cal_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QCalibration, list[ApiWarning]]:
    c = get_cal(db, p, cal_id)
    _ensure_draft(c, "edited")
    m = db.get(QMteItem, c.mte_id)
    assert m is not None  # noqa: S101
    project = base.project_of(db, c.project_id)
    qc.writable(project, p)
    qc.require_cover(p, project.id, C.mte_manage, m.site_id, m.owner_engagement_id)
    for k in (
        "cal_date",
        "provider_supplier_id",
        "in_house",
        "reference_mte_id",
        "certificate_no",
        "traceability",
        "uncertainty",
        "verification_note",
    ):
        if k in body:
            setattr(c, k, body[k])
    if "points" in body:
        c.points, c.as_found_ok, c.as_left_ok, c.max_found_error = _points(
            m, list(body["points"] or [])
        )
    warnings = _provider_warnings(db, m, c)
    c.updated_by_user_id = p.user.id
    db.flush()
    return c, warnings


def decide(
    db: Session,
    p: Principal,
    cal_id: uuid.UUID,
    decision: str,
    comment: str | None,
    paper: dict[str, Any] | None = None,
) -> tuple[QCalibration, list[ApiWarning]]:
    """draft → accepted (262 + RPM `calibration.accept`) · rejected (certificate not acceptable,
    comment). Accepting a calibration needs the certificate file
    (`CALIBRATION_CERT_REQUIRED`);
    a verification does not (Q-CAL-06)."""
    c = get_cal(db, p, cal_id)
    _ensure_draft(c, "decided")
    m = db.get(QMteItem, c.mte_id)
    assert m is not None  # noqa: S101
    project = base.project_of(db, c.project_id)
    qc.writable(project, p)
    if decision not in ("approved", "rejected"):
        raise qc.field_err("decision", "approved or rejected")
    text = qc.reason(comment, 20, "comment") if decision == "rejected" else comment
    warnings: list[ApiWarning] = []
    if decision == "approved":
        if c.kind == QCalKind.calibration and (
            not c.certificate_no or base.attachment_count(db, A.q_calibration_cert, c.id) == 0
        ):
            raise qc.err(
                422,
                ErrorCode.CALIBRATION_CERT_REQUIRED,
                "Attach the calibration certificate (file and number) before accepting.",
                "أرفق شهادة المعايرة (الملف والرقم) قبل القبول.",
            )
        warnings = _provider_warnings(db, m, c)
    base.sign(
        db, p, project, RT.calibration, c.id, "accept", decision, text, ctx(c, m), paper=paper
    )
    c.cal_no = numbering.assign(db, project, RT.calibration, on=c.cal_date)
    c.decision_comment = text
    c.decided_at, c.decided_by_user_id = now(), p.user.id
    if decision == "rejected":
        base.set_status(db, p, RT.calibration, c, QCalRecordStatus.rejected, comment=text)
        return c, warnings
    if m.interval_months:
        c.next_due = due_on(c.cal_date, m.interval_months)
    base.set_status(db, p, RT.calibration, c, QCalRecordStatus.accepted)
    _apply_to_mte(db, m, c)
    if not c.as_found_ok:
        open_review(db, project, c, m, p.user.id)
    return c, warnings


def _apply_to_mte(db: Session, m: QMteItem, c: QCalibration) -> None:
    """Q-CAL-01: the latest accepted calibration sets the item's last calibration and due date."""
    last = db.get(QCalibration, m.last_calibration_id) if m.last_calibration_id else None
    if last is not None and last.id != c.id and last.cal_date > c.cal_date:
        return
    m.last_calibration_id = c.id
    if c.next_due is not None:
        m.cal_due_on = c.next_due
    recompute(db, m)
    db.flush()


# ---- out-of-tolerance review (Q-CAL-04) ---------------------------------------------------------

_NUM = r"(-?\d+(?:\.\d+)?)"


def parse_note(note: str | None) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Measurement and criterion limits recorded with a usage (D-342): `value=<v>` and
    `lo=<l>` / `hi=<h>` (or `limit=<x>`) anywhere in `q_mte_usage.value_note`."""
    if not note:
        return None, None, None
    vals: dict[str, Decimal | None] = {}
    for key in ("value", "lo", "hi", "limit"):
        mt = re.search(rf"\b{key}\s*=\s*{_NUM}", note)
        vals[key] = Decimal(mt.group(1)) if mt else None
    lo, hi = vals["lo"], vals["hi"]
    if lo is None and hi is None and vals["limit"] is not None:
        hi = vals["limit"]
    return vals["value"], lo, hi


def margin_of(v: Decimal | None, lo: Decimal | None, hi: Decimal | None) -> Decimal | None:
    if v is None or (lo is None and hi is None):
        return None
    ms = [abs(v - x) for x in (lo, hi) if x is not None]
    return min(ms) if ms else None


def _ref(db: Session, rt: str, rid: uuid.UUID) -> str | None:
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    try:
        ad = reg.RECORD_TYPES.get(QRecordType(rt))
    except ValueError:
        ad = None
    row = ad.get(db, rid) if ad else None
    return ad.ref(row)[:60] if ad and row is not None else None


def open_review(
    db: Session, project: Project, c: QCalibration, m: QMteItem, user_id: uuid.UUID | None
) -> QOotReview:
    """Period: from the last accepted calibration whose as-left was in tolerance (or the first
    usage) to this calibration date; items = every usage of the instrument in the period plus the
    registered `OOT_SOURCES` (Q3 logger readings). no_impact is proposed when the margin between
    the recorded value and the nearest limit is larger than |as-found error|."""
    prev = db.scalar(
        select(QCalibration)
        .where(
            QCalibration.mte_id == m.id,
            QCalibration.id != c.id,
            QCalibration.status == QCalRecordStatus.accepted,
            QCalibration.as_left_ok.is_(True),
            QCalibration.cal_date <= c.cal_date,
        )
        .order_by(QCalibration.cal_date.desc())
        .limit(1)
    )
    first_use = db.scalar(
        select(QMteUsage.used_at)
        .where(QMteUsage.mte_id == m.id)
        .order_by(QMteUsage.used_at)
        .limit(1)
    )
    if prev is not None:
        start = prev.cal_date
    elif first_use is not None:
        start = base.local_day(project, first_use)
    else:
        start = c.cal_date
    err_abs = c.max_found_error or Decimal(0)
    today = qc.project_day(project)
    r = QOotReview(
        id=uuid.uuid4(),
        project_id=project.id,
        oot_no=numbering.assign(db, project, RT.oot_review),
        mte_id=m.id,
        calibration_id=c.id,
        period_from=start,
        period_to=c.cal_date,
        error_abs=err_abs,
        due_on=today + timedelta(days=int(qs.value(db, project.id, "oot_review_days") or 14)),
        status=QOotStatus.open,
        created_by_user_id=user_id,
    )
    db.add(r)
    db.flush()
    usages = db.scalars(
        select(QMteUsage)
        .where(
            QMteUsage.mte_id == m.id,
            QMteUsage.used_at >= base.day_start(project, start),
            QMteUsage.used_at < base.day_end(project, c.cal_date),
        )
        .order_by(QMteUsage.used_at)
    )
    rows: list[dict[str, Any]] = []
    for u in usages:
        if u.record_type == RT.calibration.value:
            continue
        if any(fn(db, u) for fn in OOT_USAGE_COVERED):
            continue
        # D-342 / D-370: the structured value and limits win; the note is the fallback
        nv, nlo, nhi = parse_note(u.value_note)
        v = u.value if u.value is not None else nv
        if u.limit_low is not None or u.limit_high is not None:
            lo, hi = u.limit_low, u.limit_high
        else:
            lo, hi = nlo, nhi
        rows.append(
            {
                "usage_id": u.id,
                "record_type": u.record_type,
                "record_id": u.record_id,
                "ref": _ref(db, u.record_type, u.record_id),
                "used_at": u.used_at,
                "value": v,
                "limit_low": lo,
                "limit_high": hi,
            }
        )
    for fn in OOT_SOURCES:
        rows += fn(db, m, start, c.cal_date)
    for x in rows:
        mg = margin_of(x.get("value"), x.get("limit_low"), x.get("limit_high"))
        db.add(
            QOotItem(
                review_id=r.id,
                usage_id=x.get("usage_id"),
                record_type=x["record_type"],
                record_id=x["record_id"],
                ref=x.get("ref"),
                used_at=x.get("used_at"),
                value=x.get("value"),
                limit_low=x.get("limit_low"),
                limit_high=x.get("limit_high"),
                margin=mg,
                proposed=(
                    QOotDecision.no_impact.value
                    if mg is not None and mg > err_abs
                    else QOotDecision.recheck.value
                    if mg is not None
                    else None
                ),
            )
        )
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        audit.SYSTEM,
        entity_type=EntityType.q_oot_review,
        entity_id=r.id,
        project_id=project.id,
        after={"oot_no": r.oot_no, "mte": m.mte_no, "items": str(len(rows))},
    )
    users = base.resolvers(db, project, RT.oot_review, "decide", review_ctx(r, m), r.id)
    qc.send(
        db,
        users,
        f"{r.oot_no}: out-of-tolerance review for {m.mte_no} (as-found error {err_abs})",
        f"{r.oot_no}: مراجعة الخروج عن التفاوت للجهاز {m.mte_no}",
        entity_type=EntityType.q_oot_review,
        entity_id=r.id,
        project_id=project.id,
        key=f"oot_opened:{r.id}",
        path=f"/quality/calibration/oot/{r.id}",
    )
    return r


def review_ctx(r: QOotReview, m: QMteItem | None) -> rpm.Ctx:
    return rpm.Ctx(m.site_id if m else None, m.owner_engagement_id if m else None, frozenset())


def get_review(db: Session, p: Principal, review_id: uuid.UUID) -> tuple[QOotReview, QMteItem]:
    r = db.get(QOotReview, review_id)
    if r is None:
        raise not_found("OOT review")
    m = qmte.get_item(db, p, r.mte_id)
    return r, m


def item_read(i: QOotItem, err_abs: Decimal) -> dict[str, Any]:
    return {
        "id": i.id,
        "record_type": i.record_type,
        "record_id": i.record_id,
        "ref": i.ref,
        "used_at": i.used_at,
        "value": str(i.value) if i.value is not None else None,
        "limit_low": str(i.limit_low) if i.limit_low is not None else None,
        "limit_high": str(i.limit_high) if i.limit_high is not None else None,
        "margin": str(i.margin) if i.margin is not None else None,
        "error_abs": str(err_abs),
        "proposed": i.proposed,
        "decision": i.decision,
        "justification": i.justification,
        "recheck_record_type": i.recheck_record_type,
        "recheck_record_id": i.recheck_record_id,
        "recheck_ref": i.recheck_ref,
        "ncr_id": i.ncr_id,
        "decided_at": i.decided_at,
    }


def items_of(db: Session, r: QOotReview) -> list[QOotItem]:
    return list(
        db.scalars(
            select(QOotItem)
            .where(QOotItem.review_id == r.id)
            .order_by(QOotItem.used_at, QOotItem.id)
        )
    )


def review_read(db: Session, p: Principal, r: QOotReview, m: QMteItem) -> dict[str, Any]:
    items = items_of(db, r)
    project = base.project_of(db, r.project_id)
    decided = sum(1 for i in items if i.decision)
    actions: list[str] = []
    if r.status == QOotStatus.open:
        if qc.covers(p.grant(r.project_id, C.calibration_decide), m.site_id, m.owner_engagement_id):
            actions.append("decide_items")
        if decided == len(items) and rpm.resolves(
            db, p, project, RT.oot_review, "decide", review_ctx(r, m), record_id=r.id
        ):
            actions.append("close")
    return {
        "id": r.id,
        "project_id": r.project_id,
        "oot_no": r.oot_no,
        "mte_id": m.id,
        "mte_no": m.mte_no,
        "calibration_id": r.calibration_id,
        "period_from": r.period_from,
        "period_to": r.period_to,
        "error_abs": str(r.error_abs),
        "due_on": r.due_on,
        "status": r.status,
        "closed_at": r.closed_at,
        "item_count": len(items),
        "decided_count": decided,
        "proposed_no_impact": sum(1 for i in items if i.proposed == QOotDecision.no_impact.value),
        "ncr_count": sum(1 for i in items if i.ncr_id),
        "items": [item_read(i, r.error_abs) for i in items],
        "actions": actions,
    }


def list_reviews(
    db: Session, p: Principal, project_id: uuid.UUID, status: QOotStatus | None
) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    base.require_list(p, project.id, C.mte_manage, C.calibration_decide)
    stmt = (
        select(QOotReview)
        .join(QMteItem, QMteItem.id == QOotReview.mte_id)
        .where(QOotReview.project_id == project.id, _mte_scope(p, project.id))
    )
    if status:
        stmt = stmt.where(QOotReview.status == status)
    out = []
    for r in db.scalars(stmt.order_by(QOotReview.created_at.desc())):
        m = db.get(QMteItem, r.mte_id)
        items = items_of(db, r)
        out.append(
            {
                "id": r.id,
                "oot_no": r.oot_no,
                "mte_id": r.mte_id,
                "mte_no": m.mte_no if m else "",
                "period_from": r.period_from,
                "period_to": r.period_to,
                "error_abs": str(r.error_abs),
                "due_on": r.due_on,
                "status": r.status,
                "item_count": len(items),
                "decided_count": sum(1 for i in items if i.decision),
            }
        )
    return out


def decide_item(db: Session, p: Principal, item_id: uuid.UUID, body: dict[str, Any]) -> QOotItem:
    i = db.get(QOotItem, item_id)
    if i is None:
        raise not_found("OOT item")
    r, m = get_review(db, p, i.review_id)
    project = base.project_of(db, r.project_id)
    qc.writable(project, p)
    if r.status != QOotStatus.open:
        raise base.invalid("The review", r.status, "changed")
    qc.require_cover(p, project.id, C.calibration_decide, m.site_id, m.owner_engagement_id)
    dec = QOotDecision(body["decision"])
    if i.ncr_id is not None and dec != QOotDecision.ncr:
        raise qc.field_err("decision", "An NCR was raised for this item; the decision stays ncr.")
    if dec == QOotDecision.no_impact:
        i.justification = qc.reason(body.get("justification"), 10, "justification")
    elif dec == QOotDecision.recheck:
        rt, rid, ref = (
            body.get("recheck_record_type"),
            body.get("recheck_record_id"),
            body.get("recheck_ref"),
        )
        if not (rt and rid) and not (ref or "").strip():
            raise qc.field_err("recheck_ref", "Link or name the new inspection or test.")
        if rt and rid:
            from app.services.quality import links  # noqa: PLC0415

            links.create(db, p, RT.oot_review, r.id, QRecordType(rt), rid, QLinkKind.evidence)
        i.recheck_record_type, i.recheck_record_id = rt, rid
        i.recheck_ref = (
            (ref or "").strip()[:60] or _ref(db, rt, rid)
            if rt and rid
            else (ref or "").strip()[:60]
        )
        i.justification = (body.get("justification") or "").strip() or None
    elif i.ncr_id is None:
        if body.get("owner_id") and uuid.UUID(str(body["owner_id"])) not in qc.holders_of(
            db, project, C.ncr_manage
        ):
            raise qc.field_err(
                "owner_id",
                "The NCR owner must be a user on the project holding capability 242.",
                "يجب أن يكون مسؤول التقرير مستخدماً في المشروع لديه الصلاحية 242.",
            )
        n = base.auto_ncr(
            db,
            project,
            QNcrSourceType.oot_review,
            r.id,
            raised_by=p.user.id,
            owner_id=body.get("owner_id") or m.custodian_user_id or p.user.id,
            classification=QNcrClass.major,
            category=QNcrCategory.calibration,
            title=f"{r.oot_no}: {i.ref or i.record_type} measured with {m.mte_no} out of tolerance",
            evidence=((A.q_calibration_cert, r.calibration_id),),
        )
        i.ncr_id = n.id
        i.justification = (body.get("justification") or "").strip() or None
    i.decision = dec.value
    i.decided_at, i.decided_by_user_id = now(), p.user.id
    db.flush()
    return i


def accept_proposals(
    db: Session, p: Principal, review_id: uuid.UUID, justification: str | None
) -> int:
    """Decide every undecided item whose proposal is no_impact with one justification."""
    r, m = get_review(db, p, review_id)
    project = base.project_of(db, r.project_id)
    qc.writable(project, p)
    if r.status != QOotStatus.open:
        raise base.invalid("The review", r.status, "changed")
    qc.require_cover(p, project.id, C.calibration_decide, m.site_id, m.owner_engagement_id)
    text = qc.reason(justification, 10, "justification")
    n = 0
    for i in items_of(db, r):
        if i.decision is None and i.proposed == QOotDecision.no_impact.value:
            i.decision, i.justification = QOotDecision.no_impact.value, text
            i.decided_at, i.decided_by_user_id = now(), p.user.id
            n += 1
    db.flush()
    return n


def close_review(
    db: Session,
    p: Principal,
    review_id: uuid.UUID,
    comment: str | None,
    paper: dict[str, Any] | None = None,
) -> QOotReview:
    r, m = get_review(db, p, review_id)
    project = base.project_of(db, r.project_id)
    qc.writable(project, p)
    if r.status != QOotStatus.open:
        raise base.invalid("The review", r.status, "closed")
    open_items = [i for i in items_of(db, r) if not i.decision]
    if open_items:
        raise qc.err(
            422,
            ErrorCode.OOT_REVIEW_INCOMPLETE,
            f"{len(open_items)} item(s) have no decision yet; decide every item before closing.",
            f"يوجد {len(open_items)} بند بدون قرار؛ قرّر كل البنود قبل الإغلاق.",
            undecided=len(open_items),
        )
    base.sign(
        db,
        p,
        project,
        RT.oot_review,
        r.id,
        "decide",
        "approved",
        comment,
        review_ctx(r, m),
        paper=paper,
    )
    r.closed_at, r.closed_by_user_id = now(), p.user.id
    base.set_status(db, p, RT.oot_review, r, QOotStatus.closed)
    return r


# ---- label (Q-CAL-05) and range coverage (Q-CAL-07) ---------------------------------------------


def label_data(db: Session, p: Principal, mte_id: uuid.UUID, mark: bool) -> dict[str, Any]:
    m = qmte.get_item(db, p, mte_id)
    project = base.project_of(db, m.project_id)
    last = db.get(QCalibration, m.last_calibration_id) if m.last_calibration_id else None
    if mark:
        qc.writable(project, p)
        qc.require_cover(p, project.id, C.mte_manage, m.site_id, m.owner_engagement_id)
        m.label_printed_at = now()
        db.flush()
    colour = {
        CS.calibrated: "green",
        CS.due_soon: "amber",
        CS.limited_use: "amber",
        CS.not_required: "grey",
    }.get(m.cal_status, "red")
    return {
        "mte_id": m.id,
        "mte_no": m.mte_no,
        "project_code": project.code,
        "description": m.description,
        "cal_status": m.cal_status,
        "status_en": label("cal_status", m.cal_status),
        "status_ar": label("cal_status", m.cal_status, True),
        "colour": colour,
        "cal_date": last.cal_date if last else None,
        "due_on": m.cal_due_on,
        "path": f"/quality/mte/{m.id}",
        "printed_at": m.label_printed_at,
    }


def range_warnings(
    db: Session, mte_id: uuid.UUID, lo: Decimal, hi: Decimal, margin: Decimal = Decimal(5)
) -> list[ApiWarning]:
    """Q-CAL-07: a logger or probe used for a zone range should have a calibration point within
    ± 5 °C of the range (ASSUMPTION), on its latest accepted calibration; else
    `CAL_RANGE_NOT_COVERED`. Q3 calls this when it assigns a logger to a monitoring point."""
    m = db.get(QMteItem, mte_id)
    if m is None:
        return []
    last = db.get(QCalibration, m.last_calibration_id) if m.last_calibration_id else None
    noms = [d(x.get("nominal")) for x in (last.points if last else [])]
    near = [x for x in noms if x is not None and lo - margin <= x <= hi + margin]
    if near:
        return []
    return [
        qc.warning(
            ErrorCode.CAL_RANGE_NOT_COVERED,
            f"{m.mte_no} has no calibration point within ±{margin} of {lo}…{hi}; calibrate it "
            "across the range it is used in.",
            f"لا توجد نقطة معايرة للجهاز {m.mte_no} ضمن نطاق الاستخدام.",
            "mte_id",
        )
    ]


def range_check_api(
    db: Session, p: Principal, mte_id: uuid.UUID, lo: Decimal, hi: Decimal
) -> list[ApiWarning]:
    qmte.get_item(db, p, mte_id)
    return range_warnings(db, mte_id, lo, hi)


# ---- jobs ---------------------------------------------------------------------------------------


def daily_status(db: Session, at: datetime) -> int:
    """Q-CAL-02 daily recompute of every project that uses Quality."""
    n = 0
    for s in db.scalars(select(QSettings).where(QSettings.sector_profile.is_not(None))):
        project = db.get(Project, s.project_id)
        if project is None:
            continue
        today = qc.project_day(project, at)
        soon = _soon_days(db, project.id)
        for m in db.scalars(select(QMteItem).where(QMteItem.project_id == project.id)):
            st, why = compute_status(db, m, today, soon)
            if st != m.cal_status:
                m.cal_status, m.cal_status_reason = st, why
                n += 1
    db.flush()
    return n


def due_alerts(db: Session, at: datetime) -> int:
    """§C.8: M&TE due soon / overdue → custodian and quality engineers at 30 / 7 / 0 days, then
    weekly while overdue."""
    n = 0
    for s in db.scalars(select(QSettings).where(QSettings.sector_profile.is_not(None))):
        project = db.get(Project, s.project_id)
        if project is None:
            continue
        today = qc.project_day(project, at)
        qes = base.quality_engineers(db, project)
        for m in db.scalars(
            select(QMteItem).where(
                QMteItem.project_id == project.id,
                QMteItem.status == "active",
                QMteItem.cal_due_on.is_not(None),
            )
        ):
            assert m.cal_due_on is not None  # noqa: S101
            left = (m.cal_due_on - today).days
            if left < 0:
                bucket = f"overdue-w{(-left) // 7}"
            elif left <= 0:
                bucket = "d0"
            elif left <= 7:
                bucket = "d7"
            elif left <= 30:
                bucket = "d30"
            else:
                continue
            users = [u for u in (m.custodian_user_id, *qes) if u]
            n += qc.send(
                db,
                users,
                f"{m.mte_no}: calibration {'overdue' if left < 0 else 'due'} "
                f"{m.cal_due_on.isoformat()}",
                f"{m.mte_no}: موعد المعايرة {m.cal_due_on.isoformat()}",
                entity_type=EntityType.q_mte,
                entity_id=m.id,
                project_id=project.id,
                key=f"mte_due:{m.id}:{m.cal_due_on.isoformat()}:{bucket}",
                path=f"/quality/mte/{m.id}",
            )
    return n


def oot_overdue_alerts(db: Session, at: datetime) -> int:
    n = 0
    for r in db.scalars(select(QOotReview).where(QOotReview.status == QOotStatus.open)):
        project = db.get(Project, r.project_id)
        m = db.get(QMteItem, r.mte_id)
        if project is None or m is None or qc.project_day(project, at) <= r.due_on:
            continue
        users = base.resolvers(db, project, RT.oot_review, "decide", review_ctx(r, m), r.id)
        n += qc.send(
            db,
            users,
            f"{r.oot_no}: out-of-tolerance review overdue (due {r.due_on.isoformat()})",
            f"{r.oot_no}: مراجعة الخروج عن التفاوت متأخرة",
            entity_type=EntityType.q_oot_review,
            entity_id=r.id,
            project_id=project.id,
            key=f"oot_overdue:{r.id}",
            path=f"/quality/calibration/oot/{r.id}",
        )
    return n


def require_decider(p: Principal, project_id: uuid.UUID) -> None:
    if p.grant(project_id, C.calibration_decide) is None:
        raise forbidden_error()
