"""Inspection Requests (spec 8-quality §B.4, Q-IR-01…04, -07…-09, -11): draft, submit with notice,
self-check and hold checks, return, scheduling (and re-scheduling), attendance, re-inspection,
cancel, void with re-blocking, approval comments, visibility, list and read model. The round
decision, the witness waiver and offline sync live in `decide.py`."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, CapabilityScope, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.field_enums import ResponseOwnerType
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QNcrSourceType, QRecordType, label
from app.core.quality.q1 import (
    IR_APPROVED,
    IR_PENDING,
    POINT_RANK,
    QIrCommentStatus,
    QIrResult,
    QIrStatus,
    QItpStatus,
    QPointType,
    strictest,
)
from app.models import Project, Site, Zone
from app.models.quality import QNcr, QRpRule, QSystem
from app.models.quality.q1 import QIr, QIrComment, QIrRound, QItp, QItpPoint
from app.schemas.hse_common import ApiWarning
from app.services import audit
from app.services.common import invalid_transition
from app.services.hse_common import check_site_zone
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import links, rpm, signoff
from app.services.quality import numbering as qnum
from app.services.quality import registry as reg
from app.services.quality import settings as qs
from app.services.quality.q1 import checklists, holds
from app.services.quality.q1 import common as q1c
from app.services.quality.q1 import itp as itps

C = Capability
S = CapabilityScope
ST = QIrStatus
RT = QRecordType.ir
STEP = "inspect"


# ---- loading, context, visibility --------------------------------------------------------------


def rounds_of(db: Session, ir_id: uuid.UUID) -> list[QIrRound]:
    return list(
        db.scalars(select(QIrRound).where(QIrRound.ir_id == ir_id).order_by(QIrRound.round_no))
    )


def current(db: Session, ir: QIr) -> QIrRound | None:
    return db.scalar(
        select(QIrRound).where(QIrRound.ir_id == ir.id, QIrRound.round_no == ir.current_round)
    )


def requesters(db: Session, ir: QIr) -> frozenset[uuid.UUID]:
    """Q-RPM-06: the requester and submitter never decide; after a waiver also the user who
    recorded the waived round (the result being reviewed)."""
    out = {ir.requested_by_user_id, ir.submitted_by_user_id}
    if ir.status == ST.witness_waived:
        rnd = current(db, ir)
        if rnd is not None:
            out.add(rnd.waived_by_user_id)
    return frozenset(x for x in out if x is not None)


def ctx(db: Session, ir: QIr) -> rpm.Ctx:
    return rpm.Ctx(
        ir.site_id, ir.engagement_id, requesters(db, ir), qualifier=ir.governing_type.value
    )


def resolvers(db: Session, pr: Project, ir: QIr) -> rpm.Resolution:
    """Users who resolve for `ir.inspect` and may act now (segregation applied)."""
    c = ctx(db, ir)
    res = rpm.resolve(db, pr, RT, STEP, c, record_id=ir.id)
    out: rpm.Resolution = q1c.acting(db, pr.id, res, c)
    return out


def can_view(db: Session, p: Principal, ir: QIr) -> bool:
    uid = p.user.id
    if ir.status == ST.draft and ir.ir_no is None:
        return uid in (ir.requested_by_user_id, ir.created_by_user_id) or p.is_manager
    if uid in (ir.requested_by_user_id, ir.submitted_by_user_id):
        return True
    g = p.grant(ir.project_id, C.quality_view)
    if g is not None and g.scope != S.responsible:
        return qc.covers(g, ir.site_id, ir.engagement_id)
    if any(
        uid in (r.inspector_id, r.decided_by_user_id, r.waived_by_user_id)
        for r in rounds_of(db, ir.id)
    ):
        return True
    if g is None:
        return False
    # Q-ROL-04: a responsible person reads IRs where they resolve for the step or have signed
    if q1c.signed_by(db, RT, ir.id, uid):
        return True
    if ir.status not in IR_PENDING:
        return False
    pr = q1c.project(db, ir.project_id)
    return rpm.resolves(db, p, pr, RT, STEP, ctx(db, ir), record_id=ir.id, can_act=False)


def get_ir(db: Session, p: Principal, ir_id: uuid.UUID) -> QIr:
    ir = db.get(QIr, ir_id)
    if ir is None or not p.can_see_project(ir.project_id) or not can_view(db, p, ir):
        raise q1c.denied(db, p, EntityType.q_ir, ir_id, ir.project_id if ir else None, "IR")
    return ir


def get_row(db: Session, ir_id: uuid.UUID) -> QIr:
    ir = db.get(QIr, ir_id)
    if ir is None:
        raise not_found("IR")
    return ir


def points(db: Session, ir: QIr) -> list[QItpPoint]:
    return [
        pt
        for pt in db.scalars(
            select(QItpPoint).where(QItpPoint.itp_id == ir.itp_id).order_by(QItpPoint.seq)
        )
        if pt.seq in (ir.point_seqs or [])
    ]


def _audit(db: Session, p: Principal | None, ir: QIr, action: AuditAction, **kw: Any) -> None:
    from app.services.audit import AuditActor  # noqa: PLC0415

    actor = p.actor(ir.project_id) if p else AuditActor(None, None, ir.project_id)
    audit.record(
        db,
        action,
        actor,
        entity_type=EntityType.q_ir,
        entity_id=ir.id,
        project_id=ir.project_id,
        **kw,
    )


def set_status(db: Session, p: Principal | None, ir: QIr, to: QIrStatus, **details: Any) -> None:
    before = ir.status
    ir.status = to
    ir.status_changed_at = now()
    if p is not None:
        ir.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        ir,
        AuditAction.status_change,
        before={"status": before.value},
        after={"status": to.value},
        details={k: v for k, v in details.items() if v is not None} or None,
    )


def ref(ir: QIr) -> str:
    return ir.ir_no or "IR (draft)"


# ---- create and edit ---------------------------------------------------------------------------


def _not_approved() -> Any:
    return qc.err(
        422,
        ErrorCode.ITP_NOT_APPROVED,
        "New IRs must use the current Approved revision of the ITP (Q-ITP-04).",
        "يجب أن تستخدم طلبات الفحص الجديدة المراجعة المعتمدة الحالية من الخطة.",
    )


def _place(db: Session, pr: Project, it: QItp, ir: QIr, body: dict[str, Any]) -> None:
    site_id = body.get("site_id", ir.site_id)
    zone_id = body.get("zone_id", ir.zone_id if ir.id else None)
    system_id = body.get("system_id", ir.system_id if ir.id else None)
    site, zone = check_site_zone(db, pr, site_id, zone_id)
    if it.zone_ids and zone_id is not None and zone_id not in it.zone_ids:
        raise qc.field_err(
            "zone_id", "The zone is outside the ITP's zones.", "المنطقة خارج نطاق الخطة."
        )
    system = None
    if system_id is not None:
        system = db.get(QSystem, system_id)
        if system is None or system.project_id != pr.id:
            raise qc.field_err("system_id", "The system is not on this project.")
        if it.system_ids and system_id not in it.system_ids:
            raise qc.field_err("system_id", "The system is outside the ITP's systems.")
    ref_text = (body.get("location_ref", ir.location_ref) or "").strip()
    if not ref_text:
        raise qc.field_err("location_ref", "Give the detailed location.", "أدخل الموقع التفصيلي.")
    ir.site_id = site.id
    ir.zone_id = zone.id if zone else None
    ir.system_id = system.id if system else None
    ir.location_ref = ref_text[:120]
    ir.location_key = q1c.location_key(
        zone.code if zone else None, system.code if system else None, ref_text
    )


def _seqs(db: Session, pr: Project, it: QItp, seqs: list[int]) -> tuple[list[int], QPointType]:
    seqs = sorted({int(s) for s in seqs or []})
    mx = int(qs.value(db, pr.id, "ir_max_points"))
    if not 1 <= len(seqs) <= mx:
        raise qc.field_err(
            "point_seqs",
            f"Choose 1 to {mx} points of the ITP.",
            f"اختر من 1 إلى {mx} نقاط من الخطة.",
        )
    types = {pt.seq: pt.point_type for pt in itps.points_of(db, it.id)}
    missing = [s for s in seqs if s not in types]
    if missing:
        raise qc.field_err("point_seqs", f"Not points of this ITP revision: {missing}.")
    return seqs, strictest([types[s] for s in seqs])


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QIr, list[ApiWarning]]:
    """— → Draft (249; Q-IR-01). With `submit = true` it is submitted in the same request."""
    pr = qc.get_project(db, p, project_id)
    q1c.writable_construction(db, p, pr, RT)
    cu = body.get("client_uuid")
    if cu is not None:
        dup = db.scalar(select(QIr).where(QIr.client_uuid == cu))
        if dup is not None:
            if dup.requested_by_user_id != p.user.id:
                raise forbidden_error()
            return dup, []
    it = db.get(QItp, body["itp_id"])
    if it is None or it.project_id != pr.id or not itps.can_view(db, p, it):
        raise qc.field_err("itp_id", "The ITP is not on this project.")
    if it.status != QItpStatus.approved:
        raise _not_approved()
    g = p.require(pr.id, C.ir_submit)
    seqs, gov = _seqs(db, pr, it, body.get("point_seqs") or [])
    ir = QIr(
        id=uuid.uuid4(),
        project_id=pr.id,
        itp_id=it.id,
        itp_family_id=it.family_id,
        itp_revision=it.revision,
        point_seqs=seqs,
        engagement_id=it.engagement_id,
        governing_type=gov,
        requested_by_user_id=p.user.id,
        status=ST.draft,
        client_uuid=cu,
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    _place(db, pr, it, ir, body)
    if not qc.covers(g, ir.site_id, ir.engagement_id):
        raise forbidden_error("This site or contractor is outside your scope (Q-IR-01).")
    _apply(ir, body)
    db.add(ir)
    db.flush()
    _audit(db, p, ir, AuditAction.create, after={"itp": itps.display_no(it), "points": seqs})
    warnings: list[ApiWarning] = []
    if body.get("submit"):
        ir, warnings = submit(db, p, ir.id, body.get("short_notice_reason"))
    return ir, warnings


def _apply(ir: QIr, body: dict[str, Any]) -> None:
    for k in ("extent", "self_check_note"):
        if k in body:
            ir.__setattr__(k, (body[k] or "").strip() or None)
    if "proposed_at" in body and body["proposed_at"] is not None:
        ir.proposed_at = body["proposed_at"]
    if "self_check_done" in body and body["self_check_done"] is not None:
        ir.self_check_done = bool(body["self_check_done"])


def update(db: Session, p: Principal, ir_id: uuid.UUID, body: dict[str, Any]) -> QIr:
    ir = get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    if ir.status != ST.draft:
        raise invalid_transition("IR", ir.status, "edit")
    if p.user.id != ir.requested_by_user_id:
        raise forbidden_error("Only the requester edits a draft IR.")
    it = db.get(QItp, body.get("itp_id") or ir.itp_id)
    if it is None or it.project_id != pr.id:
        raise qc.field_err("itp_id", "The ITP is not on this project.")
    if body.get("itp_id") or body.get("point_seqs") is not None:
        if it.status != QItpStatus.approved:
            raise _not_approved()
        seqs, gov = _seqs(db, pr, it, body.get("point_seqs") or ir.point_seqs)
        ir.itp_id, ir.itp_family_id, ir.itp_revision = it.id, it.family_id, it.revision
        ir.engagement_id, ir.point_seqs, ir.governing_type = it.engagement_id, seqs, gov
    if any(k in body for k in ("site_id", "zone_id", "system_id", "location_ref")):
        _place(db, pr, it, ir, body)
    _apply(ir, body)
    ir.updated_by_user_id = p.user.id
    db.flush()
    _audit(db, p, ir, AuditAction.update, details={"fields": sorted(body)})
    return ir


def notice_hours(db: Session, ir: QIr) -> int | None:
    """Q-IR-03: the point override, else `ir_notice_hours` by type; the strictest of the H / W
    points of the IR (R and S need no notice)."""
    cfg = qs.value(db, ir.project_id, "ir_notice_hours") or {}
    hours = []
    for pt in points(db, ir):
        if pt.point_type in (QPointType.H, QPointType.W):
            hours.append(
                pt.notice_hours
                if pt.notice_hours is not None
                else int(cfg.get(pt.point_type.value, 24))
            )
    return max(hours) if hours else None


def hold_error(res: holds.HoldResult) -> Any:
    return qc.err(
        422,
        ErrorCode.HOLD_POINT_NOT_RELEASED,
        "Hold points must be released first: " + " ".join(b.detail_en for b in res.blockers),
        "يجب اعتماد نقاط التوقف أولاً: " + " ".join(b.detail_ar for b in res.blockers),
        blockers=[b.__dict__ for b in res.blockers],
    )


def hold_check(db: Session, ir: QIr) -> holds.HoldResult:
    it = db.get(QItp, ir.itp_id)
    assert it is not None  # noqa: S101
    return holds.check(
        db, it, list(ir.point_seqs or []), ir.location_key, ir.governing_type, exclude_ir=ir.id
    )


def _override_rule(db: Session, p: Principal, pr: Project, ir: QIr) -> None:
    """Q-RPM-02: the ITP point's `rp_override` is the record's own row (strictest point first)."""
    pts = sorted(points(db, ir), key=lambda x: (-POINT_RANK[x.point_type], x.seq))
    ov = next((pt for pt in pts if pt.rp_override), None)
    if ov is None or ov.rp_override is None:
        return
    base = rpm.effective_rule(db, pr.id, RT, STEP, qualifier=ir.governing_type.value)
    for old in db.scalars(select(QRpRule).where(QRpRule.record_id == ir.id, QRpRule.step == STEP)):
        old.active = False
    db.add(
        QRpRule(
            project_id=pr.id,
            record_type=RT.value,
            step=STEP,
            record_id=ir.id,
            assignee_kind=ov.rp_override["assignee_kind"],
            assignee=str(ov.rp_override["assignee"]),
            self_approval_allowed=base.self_approval_allowed if base else False,
            own_tree_allowed=base.own_tree_allowed if base else False,
            paper_allowed=base.paper_allowed if base else True,
            active=True,
            reason=f"ITP point {ov.seq} responsible-person override (Q-RPM-02)",
            created_by_user_id=p.user.id,
        )
    )
    db.flush()


def submit(
    db: Session, p: Principal, ir_id: uuid.UUID, short_notice_reason: str | None = None
) -> tuple[QIr, list[ApiWarning]]:
    """Draft → Submitted (249): Q-IR-02 … -04, Q-IR-08; number, responsible set, notification."""
    ir = get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.writable_construction(db, p, pr, RT)
    if ir.status != ST.draft:
        raise invalid_transition("IR", ir.status, "submitted")
    g = p.require(pr.id, C.ir_submit)
    if p.user.id != ir.requested_by_user_id and not qc.covers(g, ir.site_id, ir.engagement_id):
        raise forbidden_error()
    it = db.get(QItp, ir.itp_id)
    assert it is not None  # noqa: S101
    if it.status != QItpStatus.approved:
        raise _not_approved()
    at = now()
    warnings: list[ApiWarning] = []
    if ir.proposed_at is None:
        raise qc.field_err(
            "proposed_at", "Propose the inspection date and time.", "اقترح موعد الفحص."
        )
    nh = notice_hours(db, ir)
    if nh is not None and ir.proposed_at < at + timedelta(hours=nh):
        if not (short_notice_reason or "").strip():
            raise qc.err(
                422,
                ErrorCode.IR_NOTICE_TOO_SHORT,
                f"A {ir.governing_type.value} point needs {nh} h notice: propose "
                f"{(at + timedelta(hours=nh)).isoformat(timespec='minutes')} or later, or give a "
                "short-notice reason (Q-IR-03).",
                f"تتطلب هذه النقطة إشعاراً مسبقاً مدته {nh} ساعة أو سبباً للإشعار القصير.",
                notice_hours=nh,
            )
        ir.short_notice = True
        ir.short_notice_reason = qc.reason(short_notice_reason, 20, "short_notice_reason")
        warnings.append(
            qc.warning(
                "IR_SHORT_NOTICE",
                "Submitted with short notice; it is flagged and counted.",
                "قُدِّم بإشعار قصير؛ سيُعلَّم ويُحتسب.",
            )
        )
    if not ir.self_check_done:
        raise qc.err(
            422,
            ErrorCode.SELF_CHECK_REQUIRED,
            "Confirm the contractor's self-check before submitting (Q-IR-04).",
            "أكّد إتمام الفحص الذاتي للمقاول قبل التقديم.",
        )
    res = hold_check(db, ir)
    if not res.ok:
        raise hold_error(res)
    ir.ir_no = qnum.assign(db, pr, RT, on=q1c.day(pr))
    ir.submitted_at = at
    ir.submitted_by_user_id = p.user.id
    ir.current_round = 1
    if not db.scalar(select(QIrRound.id).where(QIrRound.ir_id == ir.id, QIrRound.round_no == 1)):
        db.add(
            QIrRound(
                ir_id=ir.id,
                project_id=ir.project_id,
                round_no=1,
                requested_by_user_id=p.user.id,
                created_by_user_id=p.user.id,
            )
        )
    set_status(db, p, ir, ST.submitted, short_notice=ir.short_notice or None)
    _override_rule(db, p, pr, ir)
    rs = resolvers(db, pr, ir)
    ir.responsible_set = sorted(rs.users)
    db.flush()
    if rs.rule is None or not rs.users:
        warnings.append(
            qc.warning(
                ErrorCode.RESPONSIBLE_PERSON_NOT_SET,
                "No responsible person resolves for this inspection yet; the Quality settings "
                "owner has been told.",
                "لا يوجد شخص مسؤول لهذا الفحص بعد.",
            )
        )
    qc.send(
        db,
        [u for u in rs.users if u not in requesters(db, ir)],
        f"{ir.ir_no} submitted: {ir.governing_type.value} point(s) "
        f"{', '.join(map(str, ir.point_seqs))}",
        f"تم تقديم {ir.ir_no}: النقاط {', '.join(map(str, ir.point_seqs))}",
        body_en=f"{itps.display_no(it)} — {ir.location_ref}; "
        f"proposed {ir.proposed_at:%Y-%m-%d %H:%M}",
        body_ar=f"{itps.display_no(it)} — {ir.location_ref}",
        entity_type=EntityType.q_ir,
        entity_id=ir.id,
        project_id=ir.project_id,
        key=f"ir_submitted:{ir.id}",
        path=f"/quality/inspection-requests/{ir.id}",
    )
    return ir, warnings


def delete_draft(db: Session, p: Principal, ir_id: uuid.UUID) -> None:
    ir = get_ir(db, p, ir_id)
    q1c.progress_writable(q1c.project(db, ir.project_id), p)
    if ir.status != ST.draft or ir.ir_no is not None or p.user.id != ir.requested_by_user_id:
        raise invalid_transition("IR", ir.status, "delete")
    for r in rounds_of(db, ir.id):
        db.delete(r)
    _audit(db, p, ir, AuditAction.archive, details={"deleted_draft": True})
    db.delete(ir)
    db.flush()


# ---- responsible-person actions: return, schedule, attend --------------------------------------


def check_resolver(db: Session, p: Principal, pr: Project, ir: QIr) -> tuple[Any, str]:
    return rpm.check_signer(db, p, pr, RT, STEP, ctx(db, ir), record_id=ir.id)


def return_to_draft(db: Session, p: Principal, ir_id: uuid.UUID, comment: str | None) -> QIr:
    ir = get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    if ir.status != ST.submitted:
        raise invalid_transition("IR", ir.status, "draft")
    check_resolver(db, p, pr, ir)
    text = qc.reason(comment, 20, "comment")
    ir.status_reason = text
    set_status(db, p, ir, ST.draft, returned=text)
    qc.send(
        db,
        [ir.requested_by_user_id],
        f"{ref(ir)} returned: {text[:80]}",
        f"أعيد {ref(ir)}: {text[:80]}",
        entity_type=EntityType.q_ir,
        entity_id=ir.id,
        project_id=ir.project_id,
        key=f"ir_returned:{ir.id}:{ir.status_changed_at}",
        path=f"/quality/inspection-requests/{ir.id}",
    )
    return ir


def competence_warnings(
    db: Session, pr: Project, ir: QIr, inspector_id: uuid.UUID
) -> list[ApiWarning]:
    """Q-IR-07 through registry `COMPETENCE` (Q2); without a provider: an info note."""
    out: list[ApiWarning] = []
    policy = qs.value(db, pr.id, "competence_policy")
    for pt in points(db, ir):
        if not pt.competence_code:
            continue
        v = reg.competence_check(db, inspector_id, pt.competence_code, q1c.day(pr))
        if v.met is None:
            out.append(
                qc.warning(
                    "COMPETENCE_NOT_CONFIGURED", f"Point {pt.seq}: {v.detail_en}", v.detail_ar
                )
            )
        elif not v.met:
            if policy == "block":
                raise qc.err(
                    422,
                    ErrorCode.COMPETENCE_NOT_MET,
                    f"Point {pt.seq} needs competence {pt.competence_code}: {v.detail_en}",
                    f"النقطة {pt.seq} تتطلب الكفاءة {pt.competence_code}: {v.detail_ar}",
                    competence_code=pt.competence_code,
                )
            out.append(
                qc.warning(
                    ErrorCode.COMPETENCE_NOT_MET,
                    f"Point {pt.seq} needs competence {pt.competence_code}: {v.detail_en}",
                    v.detail_ar,
                )
            )
    return out


def schedule(
    db: Session,
    p: Principal,
    ir_id: uuid.UUID,
    scheduled_at: datetime,
    inspector_id: uuid.UUID | None,
    why: str | None,
) -> tuple[QIr, list[ApiWarning]]:
    """Submitted / Re-inspection Requested → Scheduled, and Scheduled → Scheduled (re-schedule
    with a reason, counted). The inspector must resolve for `ir.inspect`."""
    ir = get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    if ir.status not in (ST.submitted, ST.reinspection_requested, ST.scheduled):
        raise invalid_transition("IR", ir.status, "scheduled")
    check_resolver(db, p, pr, ir)
    insp = inspector_id or p.user.id
    res = resolvers(db, pr, ir)
    ok = (
        res.rule is not None
        and insp in res.users
        and rpm.sod_problem(db, _principal(db, insp), pr.id, res.rule, ctx(db, ir)) is None
    )
    if not ok:
        raise qc.field_err(
            "inspector_id",
            "The inspector must be a responsible person for this inspection (Q-RPM-03).",
            "يجب أن يكون المفتش شخصاً مسؤولاً عن هذا الفحص.",
        )
    warnings = competence_warnings(db, pr, ir, insp)
    rnd = current(db, ir)
    assert rnd is not None  # noqa: S101
    resched = ir.status == ST.scheduled
    if resched:
        text = qc.reason(why, 10)
        rnd.reschedules = [
            *(rnd.reschedules or []),
            {
                "from": rnd.scheduled_at.isoformat() if rnd.scheduled_at else None,
                "to": scheduled_at.isoformat(),
                "reason": text,
                "by": str(p.user.id),
                "at": now().isoformat(),
            },
        ]
    rnd.scheduled_at = scheduled_at
    rnd.scheduled_by_user_id = p.user.id
    rnd.inspector_id = insp
    ir.reblocked_at = None
    if resched:
        db.flush()
        _audit(db, p, ir, AuditAction.update, details={"rescheduled_to": scheduled_at.isoformat()})
    else:
        set_status(db, p, ir, ST.scheduled, scheduled_at=scheduled_at.isoformat())
    qc.send(
        db,
        [ir.requested_by_user_id],
        f"{ref(ir)} {'re-scheduled' if resched else 'scheduled'} for {scheduled_at:%Y-%m-%d %H:%M}",
        f"تمت {'إعادة ' if resched else ''}جدولة {ref(ir)}",
        entity_type=EntityType.q_ir,
        entity_id=ir.id,
        project_id=ir.project_id,
        email=False,
        key=f"ir_scheduled:{ir.id}:{rnd.round_no}:{scheduled_at.isoformat()}",
        path=f"/quality/inspection-requests/{ir.id}",
    )
    return ir, warnings


def _principal(db: Session, uid: uuid.UUID) -> Principal:
    from app.services.permissions import build_principal  # noqa: PLC0415

    u = qc.active_user(db, uid)
    if u is None:
        raise qc.field_err("inspector_id", "The inspector is not an active user.")
    return build_principal(db, u, None)


def attend(db: Session, p: Principal, ir_id: uuid.UUID) -> QIr:
    """The inspector records attendance (Q-IR-10 counts attendance before the wait is over)."""
    ir = get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    if ir.status != ST.scheduled:
        raise invalid_transition("IR", ir.status, "attended")
    check_resolver(db, p, pr, ir)
    rnd = current(db, ir)
    assert rnd is not None  # noqa: S101
    rnd.attended_at = rnd.attended_at or now()
    rnd.inspector_id = p.user.id
    db.flush()
    _audit(db, p, ir, AuditAction.update, details={"attended": rnd.attended_at.isoformat()})
    return ir


# ---- contractor actions: re-inspection, cancel ---------------------------------------------------


def request_reinspection(
    db: Session, p: Principal, ir_id: uuid.UUID, note: str | None, photos: list[Any]
) -> QIr:
    """Rejected → Re-inspection Requested (249): correction note ≥ 20 chars and a photo; a new
    round is created."""
    ir = get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    if ir.status != ST.rejected:
        raise invalid_transition("IR", ir.status, "reinspection_requested")
    g = p.require(pr.id, C.ir_submit)
    if p.user.id != ir.requested_by_user_id and not qc.covers(g, ir.site_id, ir.engagement_id):
        raise forbidden_error()
    text = qc.reason(note, 20, "note")
    if not photos:
        raise qc.err(
            422, ErrorCode.EVIDENCE_REQUIRED, "Add a photo of the correction.", "أرفق صورة للتصحيح."
        )
    ir.current_round += 1
    rnd = QIrRound(
        id=uuid.uuid4(),
        ir_id=ir.id,
        project_id=ir.project_id,
        round_no=ir.current_round,
        correction_note=text,
        requested_by_user_id=p.user.id,
        created_by_user_id=p.user.id,
    )
    db.add(rnd)
    db.flush()
    q1c.store_photos(
        db, AttachmentOwner.q_ir_round, rnd.id, ir.project_id, photos, p.user.id, "photos"
    )
    set_status(db, p, ir, ST.reinspection_requested, round=rnd.round_no)
    rs = resolvers(db, pr, ir)
    qc.send(
        db,
        [u for u in rs.users if u not in requesters(db, ir)],
        f"{ref(ir)}: re-inspection requested (round {rnd.round_no})",
        f"{ref(ir)}: مطلوب إعادة الفحص (الجولة {rnd.round_no})",
        body_en=text,
        body_ar=text,
        entity_type=EntityType.q_ir,
        entity_id=ir.id,
        project_id=ir.project_id,
        key=f"ir_reinsp:{ir.id}:{rnd.round_no}",
        path=f"/quality/inspection-requests/{ir.id}",
    )
    return ir


def cancel(db: Session, p: Principal, ir_id: uuid.UUID, why: str | None) -> QIr:
    ir = get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    if ir.status not in (
        ST.draft,
        ST.submitted,
        ST.scheduled,
        ST.rejected,
        ST.reinspection_requested,
    ):
        raise invalid_transition("IR", ir.status, "cancelled")
    own = p.user.id == ir.requested_by_user_id and p.grant(pr.id, C.ir_submit) is not None
    if not own:
        g = p.grant(pr.id, C.ir_inspect)
        if not qc.covers(g, ir.site_id, ir.engagement_id) and not rpm.resolves(
            db, p, pr, RT, STEP, ctx(db, ir), record_id=ir.id
        ):
            raise forbidden_error("Cancelling needs the requester or a 250 holder.")
    p.ensure_writer()
    text = qc.reason(why, 20)
    ir.status_reason = text
    set_status(db, p, ir, ST.cancelled, reason=text)
    return ir


def void(db: Session, p: Principal, ir_id: uuid.UUID, why: str | None) -> QIr:
    """Approved / Approved with Comments → Voided (244): leaves the KPIs; the hold it released is
    no longer released (Q-IR-08) and undecided later IRs at the key are re-blocked."""
    ir = get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    p.require(pr.id, C.quality_void)
    if ir.status not in IR_APPROVED:
        raise invalid_transition("IR", ir.status, "voided")
    text = qc.reason(why, 20)
    ir.status_reason = text
    set_status(db, p, ir, ST.voided, reason=text)
    reblock(db, pr, ir)
    return ir


def reblock(db: Session, pr: Project, voided: QIr) -> list[QIr]:
    out = []
    for later in db.scalars(
        select(QIr).where(
            QIr.itp_family_id == voided.itp_family_id,
            QIr.location_key == voided.location_key,
            QIr.status.in_(list(IR_PENDING)),
            QIr.id != voided.id,
        )
    ):
        if hold_check(db, later).ok:
            continue
        later.reblocked_at = now()
        out.append(later)
        _audit(db, None, later, AuditAction.update, details={"reblocked_by_void": voided.ir_no})
        qc.send(
            db,
            [later.requested_by_user_id],
            f"{ref(later)} is blocked again: {voided.ir_no} was voided",
            f"{ref(later)} محظور مجدداً: أُبطل {voided.ir_no}",
            body_en="The hold point it relied on is no longer released (Q-IR-08).",
            body_ar="لم تعد نقطة التوقف معتمدة.",
            entity_type=EntityType.q_ir,
            entity_id=later.id,
            project_id=later.project_id,
            key=f"ir_reblocked:{later.id}:{voided.id}",
            path=f"/quality/inspection-requests/{later.id}",
        )
    db.flush()
    return out


# ---- approval comments (Q-IR-11) ---------------------------------------------------------------


def get_comment(db: Session, p: Principal, comment_id: uuid.UUID) -> tuple[QIrComment, QIr]:
    c = db.get(QIrComment, comment_id)
    if c is None:
        raise not_found("IR comment")
    return c, get_ir(db, p, c.ir_id)


def respond_comment(
    db: Session, p: Principal, comment_id: uuid.UUID, text: str | None, photos: list[Any]
) -> QIr:
    c, ir = get_comment(db, p, comment_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    g = p.require(pr.id, C.ir_submit)
    if p.user.id != ir.requested_by_user_id and not qc.covers(g, ir.site_id, ir.engagement_id):
        raise forbidden_error()
    if c.status == QIrCommentStatus.closed:
        raise invalid_transition("IR comment", c.status, "responded")
    c.response_text = qc.reason(text, 10, "response_text")
    c.responded_by_user_id = p.user.id
    c.responded_at = now()
    if photos:
        c.response_photo_ids = q1c.store_photos(
            db, AttachmentOwner.q_ir_round, c.round_id, ir.project_id, photos, p.user.id, "photos"
        )
    c.status = QIrCommentStatus.responded
    db.flush()
    _audit(db, p, ir, AuditAction.update, details={"comment_responded": str(c.id)})
    return ir


def close_comment(
    db: Session, p: Principal, comment_id: uuid.UUID, accept: bool, note: str | None
) -> QIr:
    """responded → closed (250 + RPM) or back to open with a note."""
    c, ir = get_comment(db, p, comment_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    if c.status == QIrCommentStatus.closed:
        raise invalid_transition("IR comment", c.status, "closed")
    # the IR is decided, so the step is resolved on the record as signed (Q-RPM-03)
    res = rpm.resolve(db, pr, RT, STEP, ctx(db, ir), record_id=ir.id)
    if p.user.id not in res.users or p.user.id in requesters(db, ir):
        raise forbidden_error("Closing comments needs the responsible person for the inspection.")
    if accept:
        c.status = QIrCommentStatus.closed
        c.closed_by_user_id = p.user.id
        c.closed_at = now()
    else:
        c.status = QIrCommentStatus.open
        c.reopen_comment = qc.reason(note, 10, "note")
    db.flush()
    _audit(db, p, ir, AuditAction.update, details={"comment": str(c.id), "closed": accept})
    return ir


# ---- list and read -----------------------------------------------------------------------------


def _scoped(db: Session, p: Principal, pr: Project, stmt: Any) -> list[QIr]:
    return [ir for ir in db.scalars(stmt) if can_view(db, p, ir)]


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    statuses: list[QIrStatus] | None = None,
    itp_family_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    governing_type: QPointType | None = None,
    mine: bool = False,
    inspector_me: bool = False,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    pr = qc.get_project(db, p, project_id)
    if p.grant(pr.id, C.quality_view) is None and p.grant(pr.id, C.ir_submit) is None:
        raise forbidden_error()
    stmt = select(QIr).where(QIr.project_id == pr.id)
    if statuses:
        stmt = stmt.where(QIr.status.in_(statuses))
    else:
        stmt = stmt.where((QIr.status != ST.draft) | (QIr.requested_by_user_id == p.user.id))
    if itp_family_id:
        stmt = stmt.where(QIr.itp_family_id == itp_family_id)
    if engagement_id:
        stmt = stmt.where(QIr.engagement_id == engagement_id)
    if zone_id:
        stmt = stmt.where(QIr.zone_id == zone_id)
    if governing_type:
        stmt = stmt.where(QIr.governing_type == governing_type)
    if mine:
        stmt = stmt.where(QIr.requested_by_user_id == p.user.id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(QIr.ir_no.ilike(like) | QIr.location_ref.ilike(like))
    if inspector_me or scheduled_from or scheduled_to:
        sub = select(QIrRound.ir_id).where(
            QIrRound.round_no == QIr.current_round, QIrRound.ir_id == QIr.id
        )
        if inspector_me:
            sub = sub.where(QIrRound.inspector_id == p.user.id)
        if scheduled_from:
            sub = sub.where(QIrRound.scheduled_at >= scheduled_from)
        if scheduled_to:
            sub = sub.where(QIrRound.scheduled_at < scheduled_to)
        stmt = stmt.where(sub.exists())
    rows = _scoped(
        db, p, pr, stmt.order_by(QIr.submitted_at.desc().nullsfirst(), QIr.created_at.desc())
    )
    total = len(rows)
    chunk = rows[(page - 1) * page_size : page * page_size]
    hide = q1c.viewer(p, pr.id)
    return {
        "items": [list_item(db, ir, hide) for ir in chunk],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def list_item(db: Session, ir: QIr, hide: bool) -> dict[str, Any]:
    it = db.get(QItp, ir.itp_id)
    rnd = current(db, ir)
    zone = db.get(Zone, ir.zone_id) if ir.zone_id else None
    return {
        "id": ir.id,
        "ir_no": ir.ir_no,
        "status": ir.status,
        "itp_id": ir.itp_id,
        "itp_display_no": itps.display_no(it) if it else None,
        "discipline": it.discipline if it else None,
        "point_seqs": list(ir.point_seqs or []),
        "governing_type": ir.governing_type,
        "location_ref": ir.location_ref,
        "location_key": ir.location_key,
        "zone": {"id": zone.id, "code": zone.code, "name_en": zone.name_en, "name_ar": zone.name_ar}
        if zone
        else None,
        "engagement": itps._eng(db, ir.engagement_id),
        "requested_by": q1c.user_ref(db, ir.requested_by_user_id, hide),
        "proposed_at": ir.proposed_at,
        "submitted_at": ir.submitted_at,
        "current_round": ir.current_round,
        "scheduled_at": rnd.scheduled_at if rnd else None,
        "inspector": q1c.user_ref(db, rnd.inspector_id if rnd else None, hide),
        "short_notice": ir.short_notice,
        "reblocked": ir.reblocked_at is not None,
        "needs_confirmation": bool(rnd and rnd.needs_confirmation),
        "decided_at": ir.decided_at,
    }


def _measurement_read(db: Session, m: dict[str, Any]) -> dict[str, Any]:
    from app.models.quality import QMteItem  # noqa: PLC0415

    mte = db.get(QMteItem, uuid.UUID(m["mte_id"])) if m.get("mte_id") else None
    return {
        **m,
        "mte_no": mte.mte_no if mte else None,
        "mte_cal_due_on": mte.cal_due_on.isoformat() if mte and mte.cal_due_on else None,
        "mte_cal_status": mte.cal_status.value if mte else None,
    }


def round_read(db: Session, rnd: QIrRound, hide: bool) -> dict[str, Any]:
    return {
        "id": rnd.id,
        "round_no": rnd.round_no,
        "scheduled_at": rnd.scheduled_at,
        "inspector": q1c.user_ref(db, rnd.inspector_id, hide),
        "attended_at": rnd.attended_at,
        "inspected_at": rnd.inspected_at,
        "result": rnd.result,
        "review_result": rnd.review_result,
        "reviewed_at": rnd.reviewed_at,
        "reject_category": rnd.reject_category,
        "comment": rnd.comment,
        "close_comments_before_next_hold": rnd.close_comments_before_next_hold,
        "correction_note": rnd.correction_note,
        "waived_at": rnd.waived_at,
        "waived_by": q1c.user_ref(db, rnd.waived_by_user_id, hide),
        "reschedule_count": len(rnd.reschedules or []),
        "reschedules": [] if hide else list(rnd.reschedules or []),
        "measurements": [_measurement_read(db, m) for m in rnd.measurements or []],
        "responses": [
            {"seq": int(k), **(checklists.response_read(db, v) or {})}
            for k, v in sorted((rnd.responses or {}).items(), key=lambda kv: int(kv[0]))
        ],
        "photo_ids": [] if hide else q1c.attachment_ids(db, AttachmentOwner.q_ir_round, rnd.id),
        "needs_confirmation": rnd.needs_confirmation,
        "recorded_offline_at": rnd.recorded_offline_at,
        "warnings": list(rnd.warnings or []),
    }


def ncrs_of(db: Session, ir: QIr) -> list[QNcr]:
    return list(
        db.scalars(
            select(QNcr)
            .where(QNcr.source_type == QNcrSourceType.ir, QNcr.source_id == ir.id)
            .order_by(QNcr.created_at)
        )
    )


def allowed_actions(db: Session, p: Principal, ir: QIr) -> list[str]:
    if q1c.viewer(p, ir.project_id):
        return []
    out: list[str] = []
    pr = q1c.project(db, ir.project_id)
    req = p.user.id == ir.requested_by_user_id
    sub = qc.covers(p.grant(pr.id, C.ir_submit), ir.site_id, ir.engagement_id) or req
    resolves = ir.status in IR_PENDING and rpm.resolves(
        db, p, pr, RT, STEP, ctx(db, ir), record_id=ir.id
    )
    if ir.status == ST.draft and req:
        out += ["edit", "submit"] + (["delete"] if ir.ir_no is None else [])
    if ir.status == ST.submitted and resolves:
        out += ["return", "schedule"]
    if ir.status == ST.reinspection_requested and resolves:
        out.append("schedule")
    if ir.status == ST.scheduled and resolves:
        out += ["reschedule", "attend", "decide"]
    if ir.status == ST.scheduled and sub and ir.governing_type == QPointType.W:
        out.append("waive")
    if ir.status == ST.witness_waived and resolves:
        out.append("review")
    if ir.status in (ST.scheduled, ST.witness_waived) and p.grant(pr.id, C.ir_inspect) is not None:
        out.append("paper_signoff")
    if ir.status == ST.rejected and sub:
        out.append("request_reinspection")
    if ir.status in (
        ST.draft,
        ST.submitted,
        ST.scheduled,
        ST.rejected,
        ST.reinspection_requested,
    ) and (req or resolves):
        out.append("cancel")
    if ir.status in IR_APPROVED and p.grant(pr.id, C.quality_void) is not None:
        out.append("void")
    if (
        ir.status in (ST.rejected, ST.witness_waived, ST.reinspection_requested)
        and p.grant(pr.id, C.ncr_raise) is not None
    ):
        out.append("raise_ncr")
    rnd = current(db, ir)
    if rnd is not None and rnd.needs_confirmation and resolves:
        out.append("confirm_offline")
    return out


def read(
    db: Session, p: Principal, ir: QIr, warnings: list[ApiWarning] | None = None, **extra: Any
) -> dict[str, Any]:
    pr = q1c.project(db, ir.project_id)
    hide = q1c.viewer(p, ir.project_id)
    it = db.get(QItp, ir.itp_id)
    site = db.get(Site, ir.site_id)
    system = db.get(QSystem, ir.system_id) if ir.system_id else None
    res = resolvers(db, pr, ir) if ir.status in IR_PENDING else None
    hold = hold_check(db, ir) if ir.status in (ST.draft, *IR_PENDING) else holds.HoldResult()
    comments = list(
        db.scalars(
            select(QIrComment).where(QIrComment.ir_id == ir.id).order_by(QIrComment.created_at)
        )
    )
    return {
        **list_item(db, ir, hide),
        "project_id": ir.project_id,
        "itp_family_id": ir.itp_family_id,
        "itp_revision": ir.itp_revision,
        "itp_status": it.status if it else None,
        "itp_title_en": it.title_en if it else None,
        "itp_title_ar": it.title_ar if it else None,
        "points": [itps.point_read(db, pt) for pt in points(db, ir)],
        "site": {"id": site.id, "code": site.code, "name_en": site.name_en, "name_ar": site.name_ar}
        if site
        else None,
        "system": {
            "id": system.id,
            "code": system.code,
            "name_en": system.name_en,
            "name_ar": system.name_ar,
        }
        if system
        else None,
        "extent": ir.extent,
        "self_check_done": ir.self_check_done,
        "self_check_note": ir.self_check_note,
        "short_notice_reason": ir.short_notice_reason,
        "notice_hours": notice_hours(db, ir),
        "status_reason": ir.status_reason,
        "rounds": [round_read(db, r, hide) for r in rounds_of(db, ir.id)],
        "comments": [
            {
                "id": c.id,
                "round_id": c.round_id,
                "text_en": c.text_en,
                "text_ar": c.text_ar,
                "status": c.status,
                "due_on": c.due_on,
                "response_text": c.response_text,
                "responded_at": c.responded_at,
                "closed_at": c.closed_at,
                "reopen_comment": c.reopen_comment,
                "overdue": c.status != QIrCommentStatus.closed
                and c.due_on is not None
                and c.due_on < q1c.day(pr),
            }
            for c in comments
        ],
        "responsible": [u for u in (q1c.user_ref(db, x, hide) for x in sorted(res.users)) if u]
        if res
        else [],
        "rp_not_set": bool(res is not None and (res.rule is None or not res.users)),
        "hold_blockers": [b.__dict__ for b in hold.blockers],
        "signoffs": []
        if hide
        else [signoff.read(db, s) for s in signoff.signoffs_for(db, RT, ir.id)],
        "ncrs": [
            {"id": n.id, "ncr_no": n.ncr_no, "status": n.status, "classification": n.classification}
            for n in ncrs_of(db, ir)
        ],
        "links": links.links_for(db, p, RT, ir.id),
        "allowed_actions": allowed_actions(db, p, ir),
        "warnings": [w.model_dump() for w in warnings or []],
        "ncr_prompt": bool(extra.get("ncr_prompt")),
        "ncr_required_next": bool(extra.get("ncr_required_next")),
    }


def location_suggestions(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    itp_family_id: uuid.UUID | None,
    zone_id: uuid.UUID | None,
    q: str | None,
) -> list[dict[str, Any]]:
    """Phone "location autocomplete from earlier keys" (§B.8)."""
    pr = qc.get_project(db, p, project_id)
    if p.grant(pr.id, C.ir_submit) is None and p.grant(pr.id, C.quality_view) is None:
        raise forbidden_error()
    stmt = (
        select(QIr.location_key, func.min(QIr.location_ref), func.max(QIr.created_at))
        .where(QIr.project_id == pr.id)
        .group_by(QIr.location_key)
        .order_by(func.max(QIr.created_at).desc())
        .limit(30)
    )
    if itp_family_id:
        stmt = stmt.where(QIr.itp_family_id == itp_family_id)
    if zone_id:
        stmt = stmt.where(QIr.zone_id == zone_id)
    if q:
        stmt = stmt.where(QIr.location_ref.ilike(f"%{q.strip()}%"))
    return [{"location_key": k, "location_ref": r} for k, r, _ in db.execute(stmt).all()]


_ = (label, QIrResult, ResponseOwnerType, links)
