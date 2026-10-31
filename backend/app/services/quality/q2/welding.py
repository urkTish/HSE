"""Welding (spec 8-quality §C.6, Q-WLD-01…10): WPS / PQR register, welders and their WPQs with
continuity from the weld log, the weld log with visual and NDT results, NDT percentage per lot
with progressive examination, repairs (R1, R2 with a responsible-person approval, cut out), repair
rates and the weld NCRs. Construction profile only (Q-PRF-04)."""

from __future__ import annotations

import math
import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import (
    APPROVE,
    QDetectionStage,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QRecordType,
)
from app.core.quality.q2 import (
    WELD_POSITIONS,
    QAcceptReject,
    QCompetenceAppliesTo,
    QJointType,
    QNdtMethod,
    QNdtSelection,
    QPqrStatus,
    QWelderStatus,
    QWeldProcess,
    QWeldStandard,
    QWeldStatus,
    QWpqMethod,
    QWpqStatus,
    QWpsStatus,
)
from app.models import Attachment, Project, ProjectEngagement, Worker
from app.models.quality.q2 import QPqr, QWeld, QWelder, QWpq, QWps
from app.schemas.hse_common import ApiWarning
from app.services.common import paginate
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import numbering, rpm, signoff, suppliers
from app.services.quality import registry as reg
from app.services.quality.q2 import base, competence
from app.services.quality.q2.evaluators import d

C = Capability
RT = QRecordType
A = AttachmentOwner
W = QWeldStatus
_ = APPROVE


def _profile(db: Session, project: Project, rt: QRecordType, what: str) -> None:
    qc.ensure_profile_for(db, project, rt, what)


def _rec(p: Principal, project_id: uuid.UUID, eng: uuid.UUID | None = None) -> None:
    qc.require_cover(p, project_id, C.welding_record, None, eng)


def _view(p: Principal, project_id: uuid.UUID) -> None:
    base.require_list(p, project_id, C.welding_record, C.welding_approve)


# ==== WPS / PQR =================================================================================


def wps_ctx(w: QWps) -> rpm.Ctx:
    return rpm.Ctx(None, None, qc.ids(w.created_by_user_id, w.submitted_by_user_id))


def wps_read(db: Session, p: Principal, w: QWps) -> dict[str, Any]:
    acts: list[str] = []
    project = base.project_of(db, w.project_id)
    if w.status == QWpsStatus.draft and p.grant(w.project_id, C.welding_record) is not None:
        acts += ["edit", "submit"]
    if w.status == QWpsStatus.submitted and rpm.resolves(
        db, p, project, RT.wps, "approve", wps_ctx(w), record_id=w.id
    ):
        acts.append("approve")
    if w.status == QWpsStatus.approved and p.grant(w.project_id, C.welding_record) is not None:
        acts += ["revise", "withdraw"]
    return {
        "id": w.id,
        "project_id": w.project_id,
        "wps_no": w.wps_no,
        "revision": w.revision,
        "standard": w.standard,
        "processes": list(w.processes or []),
        "joint_types": list(w.joint_types or []),
        "base_material_group": w.base_material_group,
        "thickness_min_mm": str(w.thickness_min_mm),
        "thickness_max_mm": str(w.thickness_max_mm),
        "diameter_min_mm": str(w.diameter_min_mm) if w.diameter_min_mm is not None else None,
        "diameter_max_mm": str(w.diameter_max_mm) if w.diameter_max_mm is not None else None,
        "positions": list(w.positions or []),
        "filler_class": w.filler_class,
        "f_no": w.f_no,
        "a_no": w.a_no,
        "preheat_min_c": str(w.preheat_min_c) if w.preheat_min_c is not None else None,
        "interpass_max_c": str(w.interpass_max_c) if w.interpass_max_c is not None else None,
        "pwht": w.pwht,
        "gas": w.gas,
        "prequalified": w.prequalified,
        "pqr_ids": list(w.pqr_ids or []),
        "approved_at": w.approved_at,
        "status": w.status,
        "status_reason": w.status_reason,
        "actions": acts,
    }


WPS_EDIT = (
    "standard",
    "processes",
    "joint_types",
    "base_material_group",
    "thickness_min_mm",
    "thickness_max_mm",
    "diameter_min_mm",
    "diameter_max_mm",
    "positions",
    "filler_class",
    "f_no",
    "a_no",
    "preheat_min_c",
    "interpass_max_c",
    "pwht",
    "gas",
    "prequalified",
    "pqr_ids",
)


def _wps_apply(w: QWps, body: dict[str, Any]) -> None:
    for k in WPS_EDIT:
        if k in body and body[k] is not None:
            setattr(w, k, body[k])
    for k in (
        "thickness_min_mm",
        "thickness_max_mm",
        "diameter_min_mm",
        "diameter_max_mm",
        "preheat_min_c",
        "interpass_max_c",
    ):
        v = getattr(w, k)
        if v is not None and not isinstance(v, Decimal):
            setattr(w, k, d(v))
    w.standard = QWeldStandard(w.standard)
    w.processes = [QWeldProcess(x).value for x in w.processes or []]
    bad = [x for x in w.positions or [] if x not in WELD_POSITIONS]
    if bad:
        raise qc.field_err("positions", f"Unknown position(s): {', '.join(bad)}.")
    if not w.processes:
        raise qc.field_err("processes", "Name at least one process.")
    if (
        w.thickness_min_mm is None
        or w.thickness_max_mm is None
        or w.thickness_min_mm > w.thickness_max_mm
    ):
        raise qc.field_err("thickness_max_mm", "Give a thickness range (min ≤ max).")
    for x in w.joint_types or []:
        QJointType(x)


def wps_list(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    _view(p, project.id)
    rows = db.scalars(
        select(QWps).where(QWps.project_id == project.id).order_by(QWps.wps_no, QWps.revision)
    )
    return [wps_read(db, p, w) for w in rows]


def get_wps(db: Session, p: Principal, wps_id: uuid.UUID) -> QWps:
    w = db.get(QWps, wps_id)
    if w is None or not p.can_see_project(w.project_id):
        raise not_found("WPS")
    _view(p, w.project_id)
    return w


def wps_create(db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]) -> QWps:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    _profile(db, project, RT.wps, "A WPS")
    _rec(p, project.id)
    no = str(body["wps_no"]).strip().upper()
    if db.scalar(select(QWps.id).where(QWps.project_id == project.id, QWps.wps_no == no)):
        raise qc.field_err("wps_no", "This WPS number exists; create a new revision instead.")
    w = QWps(
        id=uuid.uuid4(),
        project_id=project.id,
        wps_no=no[:40],
        revision=0,
        status=QWpsStatus.draft,
        created_by_user_id=p.user.id,
    )
    _wps_apply(w, body)
    db.add(w)
    db.flush()
    base.audit_create(db, p, RT.wps, w, wps_no=w.wps_no)
    return w


def wps_update(db: Session, p: Principal, wps_id: uuid.UUID, body: dict[str, Any]) -> QWps:
    w = get_wps(db, p, wps_id)
    project = base.project_of(db, w.project_id)
    qc.writable(project, p)
    if w.status != QWpsStatus.draft:
        raise base.invalid("The WPS", w.status, "edited")
    _rec(p, project.id)
    _wps_apply(w, body)
    db.flush()
    return w


def wps_submit(db: Session, p: Principal, wps_id: uuid.UUID) -> QWps:
    w = get_wps(db, p, wps_id)
    project = base.project_of(db, w.project_id)
    qc.writable(project, p)
    if w.status != QWpsStatus.draft:
        raise base.invalid("The WPS", w.status, "submitted")
    _rec(p, project.id)
    if not w.prequalified and not w.pqr_ids:
        raise qc.field_err("pqr_ids", "A WPS that is not prequalified names its supporting PQR(s).")
    w.submitted_by_user_id = p.user.id
    base.set_status(db, p, RT.wps, w, QWpsStatus.submitted)
    return w


def wps_approve(
    db: Session,
    p: Principal,
    wps_id: uuid.UUID,
    decision: str,
    comment: str | None,
    paper: dict[str, Any] | None = None,
) -> QWps:
    """Submitted → Approved (260 + RPM `wps.approve`); a later approved revision supersedes the
    earlier one; returned / rejected go back to Draft with a comment ≥ 20."""
    w = get_wps(db, p, wps_id)
    project = base.project_of(db, w.project_id)
    qc.writable(project, p)
    if w.status != QWpsStatus.submitted:
        raise base.invalid("The WPS", w.status, "approved")
    neg = decision in ("rejected", "returned")
    text = qc.reason(comment, 20, "comment") if neg else comment
    base.sign(db, p, project, RT.wps, w.id, "approve", decision, text, wps_ctx(w), paper=paper)
    if neg:
        w.status_reason = text
        base.set_status(db, p, RT.wps, w, QWpsStatus.draft, decision=decision)
        return w
    for old in db.scalars(
        select(QWps).where(
            QWps.project_id == w.project_id,
            QWps.wps_no == w.wps_no,
            QWps.status == QWpsStatus.approved,
        )
    ):
        base.set_status(db, p, RT.wps, old, QWpsStatus.superseded, by=str(w.id))
    w.approved_at = now()
    base.set_status(db, p, RT.wps, w, QWpsStatus.approved)
    return w


def wps_revise(db: Session, p: Principal, wps_id: uuid.UUID) -> QWps:
    w = get_wps(db, p, wps_id)
    project = base.project_of(db, w.project_id)
    qc.writable(project, p)
    if w.status != QWpsStatus.approved:
        raise base.invalid("The WPS", w.status, "revised")
    _rec(p, project.id)
    if db.scalar(
        select(QWps.id).where(
            QWps.project_id == w.project_id, QWps.wps_no == w.wps_no, QWps.revision > w.revision
        )
    ):
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "A later revision exists.", "يوجد إصدار أحدث."
        )
    n = QWps(
        id=uuid.uuid4(),
        project_id=w.project_id,
        wps_no=w.wps_no,
        revision=w.revision + 1,
        status=QWpsStatus.draft,
        created_by_user_id=p.user.id,
    )
    for k in WPS_EDIT:
        setattr(n, k, getattr(w, k))
    db.add(n)
    db.flush()
    return n


def wps_withdraw(db: Session, p: Principal, wps_id: uuid.UUID, why: str | None) -> QWps:
    w = get_wps(db, p, wps_id)
    project = base.project_of(db, w.project_id)
    qc.writable(project, p)
    if w.status != QWpsStatus.approved:
        raise base.invalid("The WPS", w.status, "withdrawn")
    p.require(project.id, C.welding_approve)
    w.status_reason = qc.reason(why, 20)
    base.set_status(db, p, RT.wps, w, QWpsStatus.withdrawn, reason=w.status_reason)
    return w


def pqr_read(db: Session, p: Principal, x: QPqr) -> dict[str, Any]:
    project = base.project_of(db, x.project_id)
    acts = []
    if x.status == QPqrStatus.draft and rpm.resolves(
        db,
        p,
        project,
        RT.pqr,
        "approve",
        rpm.Ctx(None, None, qc.ids(x.created_by_user_id)),
        record_id=x.id,
    ):
        acts.append("approve")
    return {
        "id": x.id,
        "project_id": x.project_id,
        "pqr_no": x.pqr_no,
        "standard": x.standard,
        "process": x.process,
        "test_date": x.test_date,
        "results": x.results or [],
        "lab_supplier_id": x.lab_supplier_id,
        "certificate_no": x.certificate_no,
        "approved_at": x.approved_at,
        "status": x.status,
        "actions": acts,
    }


def pqr_list(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    _view(p, project.id)
    return [
        pqr_read(db, p, x)
        for x in db.scalars(select(QPqr).where(QPqr.project_id == project.id).order_by(QPqr.pqr_no))
    ]


def pqr_create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QPqr, list[ApiWarning]]:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    _profile(db, project, RT.pqr, "A PQR")
    _rec(p, project.id)
    results = []
    for i, r in enumerate(body.get("results") or []):
        if str(r.get("result")) not in ("pass", "fail"):
            raise qc.field_err(f"results[{i}].result", "pass or fail")
        results.append(
            {
                "test": str(r.get("test") or "")[:40],
                "value": str(r.get("value") or "")[:60],
                "result": r["result"],
            }
        )
    x = QPqr(
        id=uuid.uuid4(),
        project_id=project.id,
        pqr_no=str(body["pqr_no"]).strip().upper()[:40],
        standard=QWeldStandard(body["standard"]),
        process=QWeldProcess(body["process"]),
        test_date=body["test_date"],
        results=results,
        lab_supplier_id=body.get("lab_supplier_id"),
        certificate_no=body.get("certificate_no"),
        status=QPqrStatus.draft,
        created_by_user_id=p.user.id,
    )
    warnings = suppliers.check_use(db, x.lab_supplier_id)
    db.add(x)
    db.flush()
    return x, warnings


def pqr_approve(
    db: Session, p: Principal, pqr_id: uuid.UUID, decision: str, comment: str | None
) -> QPqr:
    x = db.get(QPqr, pqr_id)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("PQR")
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    if x.status != QPqrStatus.draft:
        raise base.invalid("The PQR", x.status, "approved")
    if any(r["result"] == "fail" for r in x.results or []) and decision in (
        "approved",
        "approved_with_comments",
    ):
        raise qc.field_err("results", "A PQR with a failed test cannot be approved.")
    neg = decision in ("rejected", "returned")
    text = qc.reason(comment, 20, "comment") if neg else comment
    base.sign(
        db,
        p,
        project,
        RT.pqr,
        x.id,
        "approve",
        decision,
        text,
        rpm.Ctx(None, None, qc.ids(x.created_by_user_id)),
    )
    if not neg:
        x.approved_at = now()
        base.set_status(db, p, RT.pqr, x, QPqrStatus.approved)
    return x


# ==== welders and WPQs ==========================================================================


def welder_read(db: Session, w: QWelder) -> dict[str, Any]:
    wk = db.get(Worker, w.worker_id)
    eng = db.get(ProjectEngagement, w.engagement_id)
    from app.models import Contractor  # noqa: PLC0415

    con = db.get(Contractor, eng.contractor_id) if eng else None
    return {
        "id": w.id,
        "project_id": w.project_id,
        "worker_id": w.worker_id,
        "worker_no": wk.worker_no if wk else None,
        "full_name_en": wk.full_name_en if wk else "—",
        "full_name_ar": wk.full_name_ar if wk else "—",
        "stamp": w.stamp,
        "engagement_id": w.engagement_id,
        "engagement_code": con.short_code if con else None,
        "status": w.status,
    }


def welders_list(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    _view(p, project.id)
    g = p.grant(project.id, C.welding_record) or p.grant(project.id, C.quality_view)
    out = []
    for w in db.scalars(
        select(QWelder).where(QWelder.project_id == project.id).order_by(QWelder.stamp)
    ):
        if (
            p.is_manager
            or g is None
            or g.engagement_ids is None
            or w.engagement_id in g.engagement_ids
        ):
            out.append(welder_read(db, w))
    return out


def welder_create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> QWelder:
    import re  # noqa: PLC0415

    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    _profile(db, project, RT.weld, "A welder")
    stamp = str(body["stamp"]).strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{2,10}", stamp):
        raise qc.field_err("stamp", "Stamp: 2–10 capital letters, digits or -.")
    eng = db.get(ProjectEngagement, body["engagement_id"])
    if eng is None or eng.project_id != project.id:
        raise qc.field_err("engagement_id", "The contractor must be engaged on the project.")
    _rec(p, project.id, eng.id)
    if db.get(Worker, body["worker_id"]) is None:
        raise qc.field_err("worker_id", "Unknown worker.")
    if db.scalar(
        select(QWelder.id).where(QWelder.project_id == project.id, QWelder.stamp == stamp)
    ):
        raise qc.field_err(
            "stamp", "This stamp is already used on the project.", "الختم مستخدم في المشروع."
        )
    w = QWelder(
        id=uuid.uuid4(),
        project_id=project.id,
        worker_id=body["worker_id"],
        stamp=stamp,
        engagement_id=eng.id,
        status=QWelderStatus.active,
        created_by_user_id=p.user.id,
    )
    db.add(w)
    db.flush()
    return w


def welder_status(
    db: Session, p: Principal, welder_id: uuid.UUID, status: QWelderStatus
) -> QWelder:
    w = db.get(QWelder, welder_id)
    if w is None or not p.can_see_project(w.project_id):
        raise not_found("Welder")
    project = base.project_of(db, w.project_id)
    qc.writable(project, p)
    _rec(p, project.id, w.engagement_id)
    w.status = status
    db.flush()
    return w


def wpq_ctx(x: QWpq) -> rpm.Ctx:
    return rpm.Ctx(None, None, qc.ids(x.created_by_user_id))


def last_use(
    db: Session, welder_id: uuid.UUID, process: QWeldProcess, project_id: uuid.UUID
) -> date | None:
    rows = db.scalars(
        select(QWeld.welded_on).where(
            QWeld.project_id == project_id,
            QWeld.process == process,
            QWeld.status != W.voided,
            QWeld.welder_ids.any(welder_id),
        )
    )
    dates = list(rows)
    return max(dates) if dates else None


def continuity(db: Session, x: QWpq) -> tuple[date, date]:
    """Q-WLD-03: last_use(process) = latest welded_on of not-voided welds by the welder with the
    process, or the WPQ test date if later (plus six-monthly confirmations in
    `weld_log_or_confirmation` mode); continuity_until = add_months(last_use, months) − 1 day."""
    months = int(base.setting(db, x.project_id, "wpq_continuity_months") or 6)
    mode = base.setting(db, x.project_id, "wpq_confirmation_mode")
    cands = [x.test_date]
    lu = last_use(db, x.welder_id, x.process, x.project_id)
    if lu:
        cands.append(lu)
    if mode == "weld_log_or_confirmation":
        cands += [date.fromisoformat(c["date"]) for c in x.confirmations or [] if c.get("date")]
    use = max(cands)
    return use, base.add_months(use, months) - timedelta(days=1)


def refresh_wpq(db: Session, x: QWpq) -> None:
    if x.status not in (QWpqStatus.active, QWpqStatus.lapsed):
        return
    x.last_use, x.continuity_until = continuity(db, x)


def wpq_read(db: Session, p: Principal, x: QWpq, today: date) -> dict[str, Any]:
    welder = db.get(QWelder, x.welder_id)
    project = base.project_of(db, x.project_id)
    acts: list[str] = []
    if x.status == QWpqStatus.draft and rpm.resolves(
        db, p, project, RT.wpq, "approve", wpq_ctx(x), record_id=x.id
    ):
        acts.append("approve")
    if x.status == QWpqStatus.active and p.grant(x.project_id, C.welding_approve) is not None:
        acts += ["revoke", "confirm"]
    return {
        "id": x.id,
        "project_id": x.project_id,
        "wpq_no": x.wpq_no,
        "welder_id": x.welder_id,
        "stamp": welder.stamp if welder else "",
        "standard": x.standard,
        "process": x.process,
        "test_wps_id": x.test_wps_id,
        "test_date": x.test_date,
        "coupon_thickness_mm": str(x.coupon_thickness_mm)
        if x.coupon_thickness_mm is not None
        else None,
        "coupon_diameter_mm": str(x.coupon_diameter_mm)
        if x.coupon_diameter_mm is not None
        else None,
        "coupon_position": x.coupon_position,
        "positions": list(x.positions or []),
        "thickness_min_mm": str(x.thickness_min_mm),
        "thickness_max_mm": str(x.thickness_max_mm),
        "diameter_min_mm": str(x.diameter_min_mm) if x.diameter_min_mm is not None else None,
        "f_no": x.f_no,
        "test_method": x.test_method,
        "result": x.result,
        "examiner_supplier_id": x.examiner_supplier_id,
        "last_use": x.last_use,
        "continuity_until": x.continuity_until,
        "days_left": (x.continuity_until - today).days if x.continuity_until else None,
        "revalidation_due": x.revalidation_due,
        "confirmations": x.confirmations or [],
        "status": x.status,
        "status_reason": x.status_reason,
        "actions": acts,
    }


def wpq_list(
    db: Session, p: Principal, project_id: uuid.UUID, welder_id: uuid.UUID | None
) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    _view(p, project.id)
    stmt = select(QWpq).where(QWpq.project_id == project.id)
    if welder_id:
        stmt = stmt.where(QWpq.welder_id == welder_id)
    today = qc.project_day(project)
    return [wpq_read(db, p, x, today) for x in db.scalars(stmt.order_by(QWpq.test_date.desc()))]


def wpq_create(db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]) -> QWpq:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    _profile(db, project, RT.wpq, "A WPQ")
    welder = db.get(QWelder, body["welder_id"])
    if welder is None or welder.project_id != project.id:
        raise qc.field_err("welder_id", "The welder is not on this project.")
    _rec(p, project.id, welder.engagement_id)
    pos = list(body.get("positions") or [])
    bad = [x for x in pos if x not in WELD_POSITIONS]
    if bad or not pos:
        raise qc.field_err("positions", "Give the qualified positions.")
    x = QWpq(
        id=uuid.uuid4(),
        project_id=project.id,
        welder_id=welder.id,
        standard=QWeldStandard(body["standard"]),
        process=QWeldProcess(body["process"]),
        test_wps_id=body.get("test_wps_id"),
        test_date=body["test_date"],
        coupon_thickness_mm=d(body.get("coupon_thickness_mm")),
        coupon_diameter_mm=d(body.get("coupon_diameter_mm")),
        coupon_position=body.get("coupon_position"),
        positions=pos,
        thickness_min_mm=d(body["thickness_min_mm"]),
        thickness_max_mm=d(body["thickness_max_mm"]),
        diameter_min_mm=d(body.get("diameter_min_mm")),
        f_no=body.get("f_no"),
        test_method=QWpqMethod(body["test_method"]),
        result=QAcceptReject(body.get("result") or "accept"),
        examiner_supplier_id=body.get("examiner_supplier_id"),
        personnel_certificate_id=body.get("personnel_certificate_id"),
        revalidation_due=body.get("revalidation_due"),
        confirmations=[],
        alerts_sent=[],
        status=QWpqStatus.draft,
        created_by_user_id=p.user.id,
    )
    if (
        x.thickness_min_mm is None
        or x.thickness_max_mm is None
        or x.thickness_min_mm > x.thickness_max_mm
    ):
        raise qc.field_err("thickness_max_mm", "Give the qualified thickness range.")
    db.add(x)
    db.flush()
    return x


def wpq_approve(
    db: Session,
    p: Principal,
    wpq_id: uuid.UUID,
    decision: str,
    comment: str | None,
    paper: dict[str, Any] | None = None,
) -> QWpq:
    x = db.get(QWpq, wpq_id)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("WPQ")
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    if x.status != QWpqStatus.draft:
        raise base.invalid("The WPQ", x.status, "approved")
    neg = decision in ("rejected", "returned")
    if not neg and x.result != QAcceptReject.accept:
        raise qc.field_err("result", "A failed qualification test cannot be approved.")
    text = qc.reason(comment, 20, "comment") if neg else comment
    base.sign(db, p, project, RT.wpq, x.id, "approve", decision, text, wpq_ctx(x), paper=paper)
    if neg:
        x.status_reason = text
        db.flush()
        return x
    x.wpq_no = x.wpq_no or numbering.assign(db, project, RT.wpq)
    x.approved_at = now()
    x.status = QWpqStatus.active
    refresh_wpq(db, x)
    base.set_status(db, p, RT.wpq, x, QWpqStatus.active)
    return x


def wpq_revoke(db: Session, p: Principal, wpq_id: uuid.UUID, why: str | None) -> QWpq:
    x = db.get(QWpq, wpq_id)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("WPQ")
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    if x.status not in (QWpqStatus.active, QWpqStatus.lapsed):
        raise base.invalid("The WPQ", x.status, "revoked")
    p.require(project.id, C.welding_approve)
    x.status_reason = qc.reason(why, 20)
    base.set_status(db, p, RT.wpq, x, QWpqStatus.revoked, reason=x.status_reason)
    return x


def wpq_confirm(db: Session, p: Principal, wpq_id: uuid.UUID, on: date) -> QWpq:
    """ISO 9606-1 six-monthly confirmation (mode `weld_log_or_confirmation`) by a quality
    engineer."""
    x = db.get(QWpq, wpq_id)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("WPQ")
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    p.require(project.id, C.welding_approve)
    if base.setting(db, project.id, "wpq_confirmation_mode") != "weld_log_or_confirmation":
        raise qc.field_err(
            "mode", "Confirmations count only in mode weld_log_or_confirmation (Quality settings)."
        )
    if x.status != QWpqStatus.active:
        raise base.invalid("The WPQ", x.status, "confirmed")
    if on > qc.project_day(project):
        raise qc.field_err("date", "The confirmation date cannot be in the future.")
    x.confirmations = [*(x.confirmations or []), {"date": on.isoformat(), "by": str(p.user.id)}]
    refresh_wpq(db, x)
    db.flush()
    return x


def continuity_job(db: Session, at: datetime) -> int:
    """Daily: the day after continuity_until the WPQ lapses for that process (System); past the
    revalidation date it expires. Alerts at 30 / 7 / 0 days to the engagement quality contacts and
    quality engineers (§C.8)."""
    from app.services.quality.ncr import core as ncr_core  # noqa: PLC0415

    n = 0
    for x in db.scalars(select(QWpq).where(QWpq.status == QWpqStatus.active)):
        project = db.get(Project, x.project_id)
        if project is None:
            continue
        today = qc.project_day(project, at)
        refresh_wpq(db, x)
        welder = db.get(QWelder, x.welder_id)
        if x.revalidation_due and today > x.revalidation_due:
            x.status, x.status_reason = (
                QWpqStatus.expired,
                f"Revalidation due {x.revalidation_due.isoformat()}",
            )
            n += 1
            continue
        if x.continuity_until and today > x.continuity_until:
            x.status, x.status_reason = (
                QWpqStatus.lapsed,
                f"No {x.process.value} weld since {x.last_use}",
            )
            n += 1
            continue
        if x.continuity_until and welder is not None:
            left = (x.continuity_until - today).days
            mark = 0 if left <= 0 else 7 if left <= 7 else 30 if left <= 30 else None
            if mark is not None:
                users = [
                    *ncr_core.engagement_contacts(db, project, welder.engagement_id),
                    *base.quality_engineers(db, project),
                ]
                qc.send(
                    db,
                    users,
                    f"WPQ {x.wpq_no} ({welder.stamp} {x.process.value}): continuity ends "
                    f"{x.continuity_until.isoformat()}",
                    f"استمرارية اللحّام {welder.stamp} تنتهي في {x.continuity_until.isoformat()}",
                    entity_type=EntityType.q_wpq,
                    entity_id=x.id,
                    project_id=project.id,
                    email=False,
                    key=f"wpq_cont:{x.id}:{x.continuity_until.isoformat()}:{mark}",
                    path="/quality/welding?tab=continuity",
                )
    db.flush()
    return n


# ==== welds =====================================================================================


def _num(v: Any) -> Decimal | None:
    return d(v)


def wps_covers(
    w: QWps, process: QWeldProcess, position: str, thickness: Decimal, diameter: Decimal | None
) -> list[str]:
    out = []
    if process.value not in (w.processes or []):
        out.append(f"process {process.value}")
    if w.positions and position not in w.positions:
        out.append(f"position {position}")
    if not w.thickness_min_mm <= thickness <= w.thickness_max_mm:
        out.append(f"thickness {thickness} mm outside {w.thickness_min_mm}–{w.thickness_max_mm}")
    if diameter is not None:
        if w.diameter_min_mm is not None and diameter < w.diameter_min_mm:
            out.append(f"diameter {diameter} < {w.diameter_min_mm}")
        if w.diameter_max_mm is not None and diameter > w.diameter_max_mm:
            out.append(f"diameter {diameter} > {w.diameter_max_mm}")
    return out


def welder_qualified(
    db: Session,
    welder: QWelder,
    process: QWeldProcess,
    position: str,
    thickness: Decimal,
    diameter: Decimal | None,
    on: date,
) -> str | None:
    """Q-WLD-02: an Active WPQ for the process whose positions and ranges cover the joint, with
    continuity valid on welded_on. Returns the problem, or None."""
    if welder.status != QWelderStatus.active:
        return f"{welder.stamp} is inactive"
    wpqs = list(
        db.scalars(
            select(QWpq).where(
                QWpq.welder_id == welder.id,
                QWpq.process == process,
                QWpq.status == QWpqStatus.active,
            )
        )
    )
    if not wpqs:
        return f"{welder.stamp} has no Active {process.value} WPQ"
    for x in wpqs:
        if position not in (x.positions or []):
            continue
        if not x.thickness_min_mm <= thickness <= x.thickness_max_mm:
            continue
        if diameter is not None and x.diameter_min_mm is not None and diameter < x.diameter_min_mm:
            continue
        _use, until = continuity(db, x)
        if until < on:
            return f"{welder.stamp} {process.value} continuity ended {until.isoformat()}"
        return None
    return f"{welder.stamp}'s {process.value} WPQ does not cover {position}, {thickness} mm"


def weld_ctx(x: QWeld) -> rpm.Ctx:
    return rpm.Ctx(x.site_id, x.engagement_id, qc.ids(x.created_by_user_id))


def weld_can_view(db: Session, p: Principal, x: QWeld) -> bool:
    return base.can_view(
        db,
        p,
        x.project_id,
        (C.welding_record, C.welding_approve),
        x.site_id,
        x.engagement_id,
        rt=RT.weld,
        rid=x.id,
        pending=lambda: [("repair2_approve", weld_ctx(x))] if _awaits_r2(db, x) else [],
        own=(x.created_by_user_id,),
    )


def get_weld(db: Session, p: Principal, weld_id: uuid.UUID) -> QWeld:
    x = db.get(QWeld, weld_id)
    base.require_view(
        db,
        p,
        x is not None and weld_can_view(db, p, x),
        EntityType.q_weld,
        weld_id,
        x.project_id if x else None,
        "Weld",
    )
    assert x is not None  # noqa: S101
    return x


def _had_ndt(x: QWeld) -> bool:
    return bool(x.ndt_results)


def _last_reject_at(x: QWeld) -> str | None:
    rej = [r.get("at") for r in x.ndt_results or [] if r.get("result") == "reject"]
    return rej[-1] if rej else None


def _awaits_r2(db: Session, x: QWeld) -> bool:
    return x.status == W.rejected and x.repair_count == 1 and not _r2_signed(db, x)


def _r2_signed(db: Session, x: QWeld) -> bool:
    since = _last_reject_at(x)
    after = datetime.fromisoformat(since) if since else None
    s = signoff.latest(db, RT.weld, x.id, "repair2_approve", after)
    return s is not None and s.decision == "approved"


def weld_actions(db: Session, p: Principal, x: QWeld) -> list[str]:
    out: list[str] = []
    rec = (
        qc.covers(p.grant(x.project_id, C.welding_record), x.site_id, x.engagement_id)
        or p.is_manager
    )
    if rec:
        if x.status == W.welded or (x.status in (W.repaired_r1, W.repaired_r2) and not _had_ndt(x)):
            out.append("visual")
        if x.status == W.visual_accepted and x.lot_code and x.ndt_method:
            out.append("select")
        if x.status == W.ndt_pending or (
            x.status in (W.repaired_r1, W.repaired_r2) and _had_ndt(x)
        ):
            out.append("ndt")
        if x.status == W.visual_rejected or (x.status == W.rejected and x.repair_count == 0):
            out.append("repair")
        if x.status == W.rejected and x.repair_count == 1 and _r2_signed(db, x):
            out.append("repair2")
    if _awaits_r2(db, x) and rpm.resolves(
        db,
        p,
        base.project_of(db, x.project_id),
        RT.weld,
        "repair2_approve",
        weld_ctx(x),
        record_id=x.id,
    ):
        out.append("sign_repair2")
    if x.status != W.voided and p.grant(x.project_id, C.quality_void) is not None:
        out.append("void")
    return out


def weld_read(db: Session, p: Principal, x: QWeld, full: bool = True) -> dict[str, Any]:
    wps = db.get(QWps, x.wps_id)
    stamps = (
        {
            w.id: w.stamp
            for w in db.scalars(select(QWelder).where(QWelder.id.in_(list(x.welder_ids or []))))
        }
        if x.welder_ids
        else {}
    )
    return {
        "id": x.id,
        "project_id": x.project_id,
        "joint_id": x.joint_id,
        "engagement_id": x.engagement_id,
        "drawing_ref": x.drawing_ref,
        "site_id": x.site_id,
        "zone_id": x.zone_id,
        "system_id": x.system_id,
        "wps_id": x.wps_id,
        "wps_no": f"{wps.wps_no} Rev.{wps.revision}" if wps else "",
        "process": x.process,
        "position": x.position,
        "joint_type": x.joint_type,
        "diameter_mm": str(x.diameter_mm) if x.diameter_mm is not None else None,
        "thickness_mm": str(x.thickness_mm),
        "length_mm": str(x.length_mm) if x.length_mm is not None else None,
        "welders": [
            {**w, "stamp": stamps.get(uuid.UUID(str(w["welder_id"])), "")} for w in x.welders or []
        ],
        "welded_on": x.welded_on,
        "visual_result": x.visual_result,
        "visual_defect": x.visual_defect,
        "lot_code": x.lot_code,
        "ndt_method": x.ndt_method,
        "ndt_required_pct": str(x.ndt_required_pct) if x.ndt_required_pct is not None else None,
        "selected_for_ndt": x.selected_for_ndt,
        "selection_reason": x.selection_reason,
        "selected_from_id": x.selected_from_id,
        "ndt_results": x.ndt_results or [],
        "repair_count": x.repair_count,
        "override_reason": x.override_reason,
        "status": x.status,
        "status_reason": x.status_reason,
        "actions": weld_actions(db, p, x) if full else [],
    }


def weld_list(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    lot_code: str | None,
    status: list[QWeldStatus] | None,
    stamp: str | None,
    q: str | None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    _view(p, project.id)
    Wd = QWeld  # noqa: N806
    stmt = select(Wd).where(
        Wd.project_id == project.id,
        base.scope_cond(
            p, project.id, (C.welding_record, C.welding_approve), Wd.site_id, Wd.engagement_id
        ),
    )
    if lot_code:
        stmt = stmt.where(Wd.lot_code == lot_code)
    if status:
        stmt = stmt.where(Wd.status.in_(status))
    if stamp:
        w = db.scalar(
            select(QWelder).where(QWelder.project_id == project.id, QWelder.stamp == stamp.upper())
        )
        stmt = stmt.where(Wd.welder_ids.any(w.id)) if w else stmt.where(Wd.id.is_(None))
    if q:
        stmt = stmt.where(Wd.joint_id.ilike(f"%{q.strip()}%"))
    items, total = paginate(db, stmt.order_by(Wd.welded_on.desc(), Wd.joint_id), page, page_size)
    return {
        "items": [weld_read(db, p, x, full=False) for x in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _welders_of(
    db: Session, project: Project, rows: list[dict[str, Any]]
) -> list[tuple[QWelder, dict[str, Any]]]:
    out = []
    for i, r in enumerate(rows):
        w = db.get(QWelder, r.get("welder_id")) if r.get("welder_id") else None
        if w is None and r.get("stamp"):
            w = db.scalar(
                select(QWelder).where(
                    QWelder.project_id == project.id, QWelder.stamp == str(r["stamp"]).upper()
                )
            )
        if w is None or w.project_id != project.id:
            raise qc.field_err(f"welders[{i}]", "Unknown welder on this project.")
        out.append(
            (
                w,
                {
                    "welder_id": str(w.id),
                    "root": bool(r.get("root")),
                    "fill": bool(r.get("fill")),
                    "cap": bool(r.get("cap")),
                },
            )
        )
    if not out:
        raise qc.field_err("welders", "Name at least one welder.")
    return out


def _override(db: Session, p: Principal, project: Project, why: str | None) -> str:
    text = qc.reason(why, 20, "override_reason")
    if p.grant(project.id, C.welding_approve) is None:
        raise forbidden_error(
            "Recording a weld with an unqualified welder needs capability 260 (Q-WLD-02)."
        )
    return text


def weld_create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QWeld, list[ApiWarning]]:
    """— → Welded (259): Q-WLD-01 `WPS_RANGE_EXCEEDED`, Q-WLD-02 `WELDER_NOT_QUALIFIED` (or the
    override with reason ≥ 20 by a 260 holder, which raises an NCR, Q-WLD-10)."""
    import re  # noqa: PLC0415

    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    _profile(db, project, RT.weld, "A weld")
    joint = str(body["joint_id"]).strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{3,30}", joint):
        raise qc.field_err("joint_id", "Joint id: 3–30 capital letters, digits or -.")
    if db.scalar(select(QWeld.id).where(QWeld.project_id == project.id, QWeld.joint_id == joint)):
        raise qc.field_err("joint_id", "This joint id exists on the project.", "رقم الوصلة موجود.")
    wps = db.get(QWps, body["wps_id"])
    if wps is None or wps.project_id != project.id:
        raise qc.field_err("wps_id", "Unknown WPS.")
    process = QWeldProcess(body.get("process") or (wps.processes or ["other"])[0])
    position = str(body["position"])
    if position not in WELD_POSITIONS:
        raise qc.field_err("position", "Unknown position.")
    thickness = _num(body["thickness_mm"])
    diameter = _num(body.get("diameter_mm"))
    if thickness is None:
        raise qc.field_err("thickness_mm", "Give the thickness.")
    welded_on: date = body["welded_on"]
    if welded_on > qc.project_day(project):
        raise qc.field_err("welded_on", "The weld date cannot be in the future.")
    problems = (
        [] if wps.status == QWpsStatus.approved else [f"WPS {wps.wps_no} is {wps.status.value}"]
    )
    problems += wps_covers(wps, process, position, thickness, diameter)
    if problems:
        raise qc.err(
            422,
            ErrorCode.WPS_RANGE_EXCEEDED,
            f"{wps.wps_no} Rev.{wps.revision} does not cover the joint: "
            + "; ".join(problems)
            + ".",
            "مواصفة إجراء اللحام لا تغطي الوصلة.",
            problems=problems,
        )
    welders = _welders_of(db, project, list(body.get("welders") or []))
    root = next((w for w, r in welders if r["root"]), welders[0][0])
    eng = root.engagement_id  # Q-RPM-07: the first root-pass welder's engagement
    qc.require_cover(p, project.id, C.welding_record, body.get("site_id"), eng)
    unq = [
        m
        for w, _r in welders
        if (m := welder_qualified(db, w, process, position, thickness, diameter, welded_on))
    ]
    override = None
    if unq:
        if not body.get("override_reason"):
            raise qc.err(
                422,
                ErrorCode.WELDER_NOT_QUALIFIED,
                "Welder not qualified: " + "; ".join(unq) + ".",
                "اللحّام غير مؤهل: " + "؛ ".join(unq),
                problems=unq,
            )
        override = _override(db, p, project, body.get("override_reason"))
    x = QWeld(
        id=uuid.uuid4(),
        project_id=project.id,
        joint_id=joint,
        engagement_id=eng,
        drawing_ref=body.get("drawing_ref"),
        site_id=body.get("site_id"),
        zone_id=body.get("zone_id"),
        system_id=body.get("system_id"),
        wps_id=wps.id,
        process=process,
        position=position,
        joint_type=QJointType(body.get("joint_type") or "butt"),
        diameter_mm=diameter,
        thickness_mm=thickness,
        length_mm=_num(body.get("length_mm")),
        welders=[r for _w, r in welders],
        welder_ids=[w.id for w, _r in welders],
        welded_on=welded_on,
        lot_code=(body.get("lot_code") or "").strip().upper()[:40] or None,
        ndt_method=QNdtMethod(body["ndt_method"]) if body.get("ndt_method") else None,
        ndt_required_pct=_num(body.get("ndt_required_pct")),
        ndt_results=[],
        override_reason=override,
        status=W.welded,
        created_by_user_id=p.user.id,
    )
    db.add(x)
    db.flush()
    warnings: list[ApiWarning] = []
    if override:
        warnings.append(
            qc.warning(
                ErrorCode.WELDER_RECORDED_WITH_OVERRIDE,
                "Recorded with an unqualified welder; an NCR was opened.",
                "سُجّلت مع لحّام غير مؤهل؛ فُتح تقرير عدم مطابقة.",
            )
        )
        _weld_ncr(db, p, project, x, "override")
    for w, _r in welders:
        for q in db.scalars(
            select(QWpq).where(
                QWpq.welder_id == w.id, QWpq.process == process, QWpq.status == QWpqStatus.active
            )
        ):
            refresh_wpq(db, q)
    base.audit_create(db, p, RT.weld, x, joint=x.joint_id)
    return x, warnings


def _weld_ncr(db: Session, p: Principal | None, project: Project, x: QWeld, why: str) -> None:

    titles = {
        "override": f"Weld {x.joint_id} recorded with an unqualified welder",
        "cut_out": f"Weld {x.joint_id} rejected after the second repair — cut out",
        "100pct": f"Lot {x.lot_code}: progressive examination reached 100 % ({x.joint_id})",
    }
    owner = (p.user.id if p else None) or x.created_by_user_id
    assert owner is not None  # noqa: S101
    base.auto_ncr(
        db,
        project,
        QNcrSourceType.weld,
        x.id,
        raised_by=p.user.id if p else None,
        owner_id=owner,
        classification=QNcrClass.major,
        category=QNcrCategory.workmanship,
        title=titles[why],
        evidence=((A.q_weld, x.id),),
    )


def _writer(db: Session, p: Principal, x: QWeld) -> Project:
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    qc.require_cover(p, project.id, C.welding_record, x.site_id, x.engagement_id)
    return project


def weld_visual(db: Session, p: Principal, weld_id: uuid.UUID, body: dict[str, Any]) -> QWeld:
    """Welded (or a VT-only repair) → Visual Accepted / Visual Rejected (with defect type)."""
    x = get_weld(db, p, weld_id)
    project = _writer(db, p, x)
    if not (
        x.status == W.welded or (x.status in (W.repaired_r1, W.repaired_r2) and not _had_ndt(x))
    ):
        raise base.invalid("The weld", x.status, "given a visual result")
    res = QAcceptReject(body["result"])
    if res == QAcceptReject.reject and not (body.get("defect_type") or "").strip():
        raise qc.field_err("defect_type", "Name the defect type.")
    x.visual_result, x.visual_defect = res, (body.get("defect_type") or None)
    if res == QAcceptReject.accept:
        base.set_status(db, p, RT.weld, x, W.visual_accepted)
    elif x.repair_count >= 2:
        x.status_reason = "Visual rejection after the second repair"
        base.set_status(db, p, RT.weld, x, W.cut_out)
        _weld_ncr(db, p, project, x, "cut_out")
    else:
        base.set_status(db, p, RT.weld, x, W.visual_rejected, defect=x.visual_defect)
    return x


def _select(
    db: Session, p: Principal | None, x: QWeld, reason: QNdtSelection, parent: QWeld | None = None
) -> None:
    x.selected_for_ndt, x.selection_reason = True, reason
    x.selected_from_id = parent.id if parent else None
    base.set_status(db, p, RT.weld, x, W.ndt_pending, selection=reason.value)


def weld_select(db: Session, p: Principal, weld_id: uuid.UUID, reason: QNdtSelection) -> QWeld:
    x = get_weld(db, p, weld_id)
    _writer(db, p, x)
    if x.status != W.visual_accepted:
        raise base.invalid("The weld", x.status, "selected for NDT")
    if not x.lot_code or not x.ndt_method:
        raise qc.field_err("lot_code", "Assign the weld to an NDT lot (lot code and method) first.")
    _select(db, p, x, reason)
    return x


def assign_lot(db: Session, p: Principal, weld_id: uuid.UUID, body: dict[str, Any]) -> QWeld:
    x = get_weld(db, p, weld_id)
    _writer(db, p, x)
    if x.status == W.voided:
        raise base.invalid("The weld", x.status, "assigned to a lot")
    x.lot_code = str(body["lot_code"]).strip().upper()[:40]
    x.ndt_method = QNdtMethod(body["ndt_method"])
    x.ndt_required_pct = _num(body.get("ndt_required_pct"))
    db.flush()
    return x


def _lot(db: Session, x: QWeld) -> list[QWeld]:
    if not x.lot_code:
        return []
    return list(
        db.scalars(
            select(QWeld)
            .where(
                QWeld.project_id == x.project_id,
                QWeld.lot_code == x.lot_code,
                QWeld.status != W.voided,
            )
            .order_by(QWeld.welded_on, QWeld.joint_id)
        )
    )


def _tier(db: Session, x: QWeld) -> int:
    t, cur, seen = 0, x, set()
    while (
        cur.selection_reason == QNdtSelection.progressive
        and cur.selected_from_id
        and cur.id not in seen
    ):
        seen.add(cur.id)
        parent = db.get(QWeld, cur.selected_from_id)
        if parent is None:
            break
        t += 1
        cur = parent
    return t


def _progressive(db: Session, p: Principal, project: Project, x: QWeld) -> list[str]:
    """Q-WLD-05 [VERIFY ASME B31.3 §341.3.4]: a rejected random weld adds 2 welds by the same welder
    in the lot (`progressive`); a rejected progressive weld adds 2 more; a rejection in that second
    tier selects every remaining weld of the welder in the lot (`100pct`) and opens an NCR."""
    if not base.setting(db, project.id, "progressive_exam"):
        return []
    if x.selection_reason not in (QNdtSelection.random, QNdtSelection.progressive):
        return []
    tier = _tier(db, x)
    welders = set(x.welder_ids or [])
    pool = [
        w
        for w in _lot(db, x)
        if w.id != x.id and w.status == W.visual_accepted and welders & set(w.welder_ids or [])
    ]
    if tier >= 2:
        for w in pool:
            _select(db, p, w, QNdtSelection.pct100, x)
        _weld_ncr(db, p, project, x, "100pct")
        return [w.joint_id for w in pool]
    picked = pool[:2]
    for w in picked:
        _select(db, p, w, QNdtSelection.progressive, x)
    return [w.joint_id for w in picked]


def weld_ndt(
    db: Session, p: Principal, weld_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QWeld, list[ApiWarning], dict[str, Any]]:
    """NDT Pending (or a repaired weld re-examined by the same method) → Accepted / Rejected, with
    the report number and file (an attachment on the weld) and the technician's competence
    (Q-WLD-08). A rejection after R2 cuts the weld out (Q-WLD-06) and opens an NCR."""
    x = get_weld(db, p, weld_id)
    project = _writer(db, p, x)
    if not (
        x.status == W.ndt_pending or (x.status in (W.repaired_r1, W.repaired_r2) and _had_ndt(x))
    ):
        raise base.invalid("The weld", x.status, "given an NDT result")
    method = QNdtMethod(body.get("method") or (x.ndt_method.value if x.ndt_method else "RT"))
    if x.status in (W.repaired_r1, W.repaired_r2):
        prev = [r for r in x.ndt_results or [] if r.get("repair_round") == 0]
        if prev and prev[0].get("method") != method.value:
            raise qc.field_err("method", "A repair is re-examined by the same method.")
    res = QAcceptReject(body["result"])
    report = (body.get("report_no") or "").strip()
    att = db.get(Attachment, body.get("attachment_id")) if body.get("attachment_id") else None
    if not report or att is None or att.owner_type != A.q_weld or att.owner_id != x.id:
        raise qc.field_err(
            "report_no",
            "Give the NDT report number and attach the report to the weld.",
            "أدخل رقم تقرير الفحص وأرفق التقرير.",
        )
    if res == QAcceptReject.reject and (
        not (body.get("defect_type") or "").strip() or _num(body.get("defect_length_mm")) is None
    ):
        raise qc.field_err("defect_type", "A rejection names the defect type and length.")
    on: date = body.get("examined_on") or qc.project_day(project)
    warnings: list[ApiWarning] = []
    tech = body.get("technician_user_id")
    if tech:
        code = body.get("competence_code") or competence.by_filter(
            db, QCompetenceAppliesTo.ndt_technician, ndt_method=method.value
        )
        warnings += competence.enforce(db, project, tech, code, on, "technician_user_id")
    rnd = x.repair_count
    x.ndt_results = [
        *(x.ndt_results or []),
        {
            "method": method.value,
            "report_no": report[:60],
            "attachment_id": str(att.id),
            "result": res.value,
            "defect_type": (body.get("defect_type") or None),
            "defect_length_mm": str(_num(body.get("defect_length_mm")))
            if body.get("defect_length_mm") is not None
            else None,
            "examined_length_mm": str(_num(body.get("examined_length_mm")) or x.length_mm or "")
            or None,
            "technician_name": (body.get("technician_name") or None),
            "technician_user_id": str(tech) if tech else None,
            "examined_on": on.isoformat(),
            "repair_round": rnd,
            "at": now().isoformat(),
        },
    ]
    extra: dict[str, Any] = {"progressive": []}
    if res == QAcceptReject.accept:
        base.set_status(db, p, RT.weld, x, W.accepted, report=report)
    elif rnd >= 2:
        x.status_reason = "Rejected after the second repair"
        base.set_status(db, p, RT.weld, x, W.cut_out)
        _weld_ncr(db, p, project, x, "cut_out")
    else:
        base.set_status(db, p, RT.weld, x, W.rejected, defect=body.get("defect_type"))
        if rnd == 0:
            extra["progressive"] = _progressive(db, p, project, x)
    if rnd == 0:
        repair_rate_alert(db, project, x, on)
    return x, warnings, extra


def weld_repair(db: Session, p: Principal, weld_id: uuid.UUID, body: dict[str, Any]) -> QWeld:
    """Visual Rejected / Rejected (repair_count 0) → Repaired R1; Rejected (repair_count 1) →
    Repaired R2 only after the `weld.repair2_approve` sign-off (`SIGNOFF_REQUIRED`, Q-WLD-06). The
    repair welder must be qualified (Q-WLD-02)."""
    x = get_weld(db, p, weld_id)
    project = _writer(db, p, x)
    first = x.status == W.visual_rejected or (x.status == W.rejected and x.repair_count == 0)
    second = x.status == W.rejected and x.repair_count == 1
    if not (first or second):
        raise base.invalid("The weld", x.status, "repaired")
    if second and not _r2_signed(db, x):
        raise qc.err(
            422,
            ErrorCode.SIGNOFF_REQUIRED,
            "A second repair needs the responsible person's approval (weld.repair2_approve) first.",
            "الإصلاح الثاني يتطلب اعتماد الشخص المسؤول أولاً.",
            step="repair2_approve",
        )
    on: date = body.get("repaired_on") or qc.project_day(project)
    welders = _welders_of(db, project, list(body.get("welders") or x.welders or []))
    thickness, diameter = x.thickness_mm, x.diameter_mm
    unq = [
        m
        for w, _r in welders
        if (m := welder_qualified(db, w, x.process, x.position, thickness, diameter, on))
    ]
    if unq:
        raise qc.err(
            422,
            ErrorCode.WELDER_NOT_QUALIFIED,
            "Repair welder not qualified: " + "; ".join(unq) + ".",
            "لحّام الإصلاح غير مؤهل.",
            problems=unq,
        )
    x.repair_count += 1
    x.welder_ids = sorted({*(x.welder_ids or []), *(w.id for w, _r in welders)}, key=str)
    base.set_status(
        db, p, RT.weld, x, W.repaired_r1 if first else W.repaired_r2, repaired_on=on.isoformat()
    )
    return x


def weld_sign_repair2(
    db: Session,
    p: Principal,
    weld_id: uuid.UUID,
    decision: str,
    comment: str | None,
    paper: dict[str, Any] | None = None,
) -> QWeld:
    x = get_weld(db, p, weld_id)
    project = base.project_of(db, x.project_id)
    if not _awaits_r2(db, x):
        raise base.invalid("The weld", x.status, "approved for a second repair")
    text = qc.reason(comment, 20, "comment")
    base.sign(
        db, p, project, RT.weld, x.id, "repair2_approve", decision, text, weld_ctx(x), paper=paper
    )
    if decision != "approved":
        x.status_reason = text
        base.set_status(db, p, RT.weld, x, W.cut_out, reason="second repair refused")
        _weld_ncr(db, p, project, x, "cut_out")
    db.flush()
    return x


def weld_void(db: Session, p: Principal, weld_id: uuid.UUID, why: str | None) -> QWeld:
    x = get_weld(db, p, weld_id)
    project = base.project_of(db, x.project_id)
    qc.writable(project, p)
    if x.status == W.voided:
        raise base.invalid("The weld", x.status, "voided")
    p.require(project.id, C.quality_void)
    x.status_reason = qc.reason(why, 20)
    base.set_status(db, p, RT.weld, x, W.voided, reason=x.status_reason)
    for wid in x.welder_ids or []:
        for q in db.scalars(select(QWpq).where(QWpq.welder_id == wid, QWpq.process == x.process)):
            refresh_wpq(db, q)
    return x


# ---- lots, repair rates, continuity board (Q-WLD-04, -07) ---------------------------------------


def _first_exams(x: QWeld, method: str | None = None) -> list[dict[str, Any]]:
    return [
        r
        for r in x.ndt_results or []
        if r.get("repair_round") == 0 and (method is None or r.get("method") == method)
    ][:1]


def lot_summary(db: Session, p: Principal, project_id: uuid.UUID, lot_code: str) -> dict[str, Any]:
    """n = welds of the lot with visual accepted; e = welds examined by the lot's method at first
    NDT; achieved = e ÷ n × 100; shortfall = ⌈r × n ÷ 100⌉ − e when > 0."""
    project = qc.get_project(db, p, project_id)
    _view(p, project.id)
    welds = list(
        db.scalars(
            select(QWeld).where(
                QWeld.project_id == project.id,
                QWeld.lot_code == lot_code.upper(),
                QWeld.status != W.voided,
            )
        )
    )
    if not welds:
        raise not_found("NDT lot")
    method = next((w.ndt_method.value for w in welds if w.ndt_method), None)
    pct = next((w.ndt_required_pct for w in welds if w.ndt_required_pct is not None), Decimal(0))
    vis = [w for w in welds if w.visual_result == QAcceptReject.accept]
    examined = [w for w in vis if _first_exams(w, method)]
    n, e = len(vis), len(examined)
    required = math.ceil(pct * n / 100) if n else 0
    achieved = (Decimal(e) / Decimal(n) * 100).quantize(Decimal("0.1")) if n else Decimal(0)
    stamps = {
        w.id: w.stamp for w in db.scalars(select(QWelder).where(QWelder.project_id == project.id))
    }
    by_welder: dict[str, dict[str, int]] = {}
    for w in vis:
        for wid in w.welder_ids or []:
            row = by_welder.setdefault(
                stamps.get(wid, str(wid)), {"welds": 0, "examined": 0, "rejected": 0}
            )
            row["welds"] += 1
            fx = _first_exams(w, method)
            if fx:
                row["examined"] += 1
                row["rejected"] += 1 if fx[0]["result"] == "reject" else 0
    return {
        "lot_code": lot_code.upper(),
        "ndt_method": method,
        "required_pct": str(pct),
        "welds_visual_accepted": n,
        "examined": e,
        "required": required,
        "shortfall": max(0, required - e),
        "achieved_pct": str(achieved),
        "progressive": sum(1 for w in welds if w.selection_reason == QNdtSelection.progressive),
        "pct100": sum(1 for w in welds if w.selection_reason == QNdtSelection.pct100),
        "by_welder": [{"stamp": k, **v} for k, v in sorted(by_welder.items())],
    }


def pick_welds(
    db: Session, p: Principal, project_id: uuid.UUID, lot_code: str
) -> list[dict[str, Any]]:
    """A random proposal covering the shortfall and every welder of the lot at least once."""
    s = lot_summary(db, p, project_id, lot_code)
    need = int(s["shortfall"])
    pool = list(
        db.scalars(
            select(QWeld).where(
                QWeld.project_id == project_id,
                QWeld.lot_code == lot_code.upper(),
                QWeld.status == W.visual_accepted,
            )
        )
    )
    rnd = random.Random(f"{project_id}:{lot_code}")  # noqa: S311 - a proposal, not security
    rnd.shuffle(pool)
    examined_welders = {
        wid
        for w in db.scalars(
            select(QWeld).where(QWeld.project_id == project_id, QWeld.lot_code == lot_code.upper())
        )
        if _first_exams(w)
        for wid in (w.welder_ids or [])
    }
    out: list[QWeld] = []
    covered = set(examined_welders)
    for w in pool:  # every welder of the lot at least once where possible
        if set(w.welder_ids or []) - covered:
            out.append(w)
            covered |= set(w.welder_ids or [])
    for w in pool:  # then up to the shortfall
        if len(out) >= need:
            break
        if w not in out:
            out.append(w)
    return [{"id": w.id, "joint_id": w.joint_id} for w in out]


def repair_rates(
    db: Session, project: Project, until: date, days: int = 90, welder_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    """Q-WLD-07 per welder: rejected first examinations ÷ first examinations × 100 (by joint), and
    by length when lengths are recorded; re-examinations of repairs are not counted twice."""
    since = until - timedelta(days=days)
    stats: dict[uuid.UUID, dict[str, Decimal]] = {}
    for w in db.scalars(
        select(QWeld).where(QWeld.project_id == project.id, QWeld.status != W.voided)
    ):
        fx = _first_exams(w)
        if not fx:
            continue
        on = date.fromisoformat(fx[0]["examined_on"])
        if not since < on <= until:
            continue
        for wid in w.welder_ids or []:
            if welder_id is not None and wid != welder_id:
                continue
            s = stats.setdefault(
                wid, {"n": Decimal(0), "rej": Decimal(0), "len": Decimal(0), "defect": Decimal(0)}
            )
            s["n"] += 1
            if fx[0]["result"] == "reject":
                s["rej"] += 1
                s["defect"] += d(fx[0].get("defect_length_mm")) or Decimal(0)
            s["len"] += d(fx[0].get("examined_length_mm")) or Decimal(0)
    stamps = {
        w.id: w.stamp for w in db.scalars(select(QWelder).where(QWelder.project_id == project.id))
    }
    out = []
    for wid, s in stats.items():
        out.append(
            {
                "welder_id": wid,
                "stamp": stamps.get(wid, ""),
                "first_examinations": int(s["n"]),
                "rejected": int(s["rej"]),
                "rate_pct": str((s["rej"] / s["n"] * 100).quantize(Decimal("0.1"))),
                "rate_by_length_pct": str((s["defect"] / s["len"] * 100).quantize(Decimal("0.01")))
                if s["len"] > 0
                else None,
            }
        )
    return sorted(out, key=lambda r: r["stamp"])


def repair_rate_alert(db: Session, project: Project, x: QWeld, on: date) -> None:
    limit = Decimal(str(base.setting(db, project.id, "repair_rate_alert_pct") or "5.0"))
    for wid in x.welder_ids or []:
        rows = repair_rates(db, project, on, 90, wid)
        if not rows:
            continue
        r = rows[0]
        if r["first_examinations"] >= 10 and Decimal(r["rate_pct"]) > limit:
            qc.send(
                db,
                base.quality_engineers(db, project),
                f"Welder {r['stamp']}: repair rate {r['rate_pct']} % > {limit} % (90 days) — "
                "consider a retest or revocation",
                f"نسبة إصلاح اللحّام {r['stamp']} {r['rate_pct']} % تجاوزت الحد",
                entity_type=EntityType.q_weld,
                entity_id=x.id,
                project_id=project.id,
                key=f"repair_rate:{wid}:{on.isoformat()[:7]}",
                path="/quality/welding?tab=rates",
            )


def rates_api(db: Session, p: Principal, project_id: uuid.UUID, days: int) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    _view(p, project.id)
    return repair_rates(db, project, qc.project_day(project), days)


def continuity_board(db: Session, p: Principal, project_id: uuid.UUID) -> list[dict[str, Any]]:
    project = qc.get_project(db, p, project_id)
    _view(p, project.id)
    today = qc.project_day(project)
    out = []
    for w in db.scalars(
        select(QWelder).where(QWelder.project_id == project.id).order_by(QWelder.stamp)
    ):
        for x in db.scalars(
            select(QWpq).where(
                QWpq.welder_id == w.id,
                QWpq.status.in_([QWpqStatus.active, QWpqStatus.lapsed, QWpqStatus.expired]),
            )
        ):
            use, until = (
                continuity(db, x)
                if x.status == QWpqStatus.active
                else (x.last_use, x.continuity_until)
            )
            out.append(
                {
                    "welder_id": w.id,
                    "stamp": w.stamp,
                    "wpq_id": x.id,
                    "wpq_no": x.wpq_no,
                    "process": x.process,
                    "last_use": use,
                    "continuity_until": until,
                    "days_left": (until - today).days if until else None,
                    "status": x.status,
                }
            )
    return out


# ---- NCR source (list NS `weld`) ------------------------------------------------------------


def ncr_source(db: Session, project: Project, source_id: uuid.UUID) -> reg.SourceInfo:
    x = db.get(QWeld, source_id)
    if x is None or x.project_id != project.id:
        raise qc.field_err("source_id", "The weld is not on this project.")
    wps = db.get(QWps, x.wps_id)
    last = (x.ndt_results or [{}])[-1]
    return reg.SourceInfo(
        ref=x.joint_id,
        title=f"Weld {x.joint_id}: repair limit or lot expansion",
        site_id=x.site_id,
        zone_id=x.zone_id,
        system_id=x.system_id,
        engagement_id=x.engagement_id,
        item_key=f"WLD:{x.lot_code or x.joint_id}",
        detection_stage=QDetectionStage.in_process,
        requirement_en=f"{wps.wps_no} Rev.{wps.revision}; acceptance per {wps.standard.value}"
        if wps
        else None,
        finding_en=(
            f"{last.get('method') or 'VT'} {last.get('result') or ''} — "
            f"{last.get('defect_type') or x.visual_defect or x.override_reason or ''}"
        ).strip(),
        proposed_class=QNcrClass.major,
        location_ref=x.drawing_ref,
        record_type=RT.weld,
    )


def weld_visible(db: Session, p: Principal, rid: uuid.UUID) -> bool:
    x = db.get(QWeld, rid)
    return x is not None and weld_can_view(db, p, x)
