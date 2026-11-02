"""Punch list (spec 8-quality §B.5, Q-PUN-01…04) and floor plans with pins (§B.6, Q-PIN-01, -02).

Items are numbered when raised (no draft). Ready for Review needs an after photo and a note; the
responsible person for `punch_item.verify` closes or re-opens; the user who marked an item ready
never closes it (Q-PUN-02 with Q-RPM-06). Plans are PNG / JPEG images; pins are percentages of the
image, so a revision with the same aspect ratio (± 1 %) keeps every pin and another aspect ratio
marks the pins "check position"."""

from __future__ import annotations

import io
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, CapabilityScope, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.field_enums import ResponseOwnerType
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QDiscipline, QRecordType, label
from app.core.quality.q1 import (
    PLAN_MAX_BYTES,
    PLAN_MAX_EDGE,
    PUNCH_LIVE,
    QPlanStatus,
    QPunchCategory,
    QPunchRaisedDuring,
    QPunchStatus,
)
from app.models import Project, Site, Zone
from app.models.quality import QSystem
from app.models.quality.q1 import QFloorPlan, QPunchItem
from app.schemas.hse_common import ApiWarning
from app.services import attachments, audit
from app.services.common import invalid_transition
from app.services.hse_common import check_engagement, check_site_zone, id_warnings
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import links, rpm, signoff
from app.services.quality import numbering as qnum
from app.services.quality import settings as qs
from app.services.quality.q1 import checklists
from app.services.quality.q1 import common as q1c
from app.services.quality.q1.itp import _eng

C = Capability
S = CapabilityScope
ST = QPunchStatus
RT = QRecordType.punch_item
STEP = "verify"


def requesters(it: QPunchItem) -> frozenset[uuid.UUID]:
    """Q-PUN-02: the user who marked the item ready never closes it (D-333)."""
    return qc.ids(it.ready_by_user_id)


def ctx(it: QPunchItem) -> rpm.Ctx:
    return rpm.Ctx(it.site_id, it.responsible_engagement_id, requesters(it))


def can_view(db: Session, p: Principal, it: QPunchItem) -> bool:
    uid = p.user.id
    if uid in (it.raised_by_user_id, it.ready_by_user_id):
        return True
    g = p.grant(it.project_id, C.quality_view)
    if g is None:
        return False
    if g.scope != S.responsible:
        return qc.covers(g, it.site_id, it.responsible_engagement_id)
    if q1c.signed_by(db, RT, it.id, uid):
        return True
    pr = q1c.project(db, it.project_id)
    return rpm.resolves(db, p, pr, RT, STEP, ctx(it), record_id=it.id, can_act=False)


def get_item(db: Session, p: Principal, item_id: uuid.UUID) -> QPunchItem:
    it = db.get(QPunchItem, item_id)
    if it is None or not p.can_see_project(it.project_id) or not can_view(db, p, it):
        raise q1c.denied(
            db, p, EntityType.q_punch_item, item_id, it.project_id if it else None, "Punch item"
        )
    return it


def _audit(db: Session, p: Principal, it: QPunchItem, action: AuditAction, **kw: Any) -> None:
    audit.record(
        db,
        action,
        p.actor(it.project_id),
        entity_type=EntityType.q_punch_item,
        entity_id=it.id,
        project_id=it.project_id,
        **kw,
    )


def _status(db: Session, p: Principal, it: QPunchItem, to: QPunchStatus, **details: Any) -> None:
    before = it.status
    it.status = to
    it.status_changed_at = now()
    it.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        it,
        AuditAction.status_change,
        before={"status": before.value},
        after={"status": to.value},
        details={k: v for k, v in details.items() if v is not None} or None,
    )


def target_for(db: Session, pr: Project, cat: QPunchCategory, raised: date) -> date:
    days = (qs.value(db, pr.id, "punch_target_days") or {}).get(
        cat.value, 14 if cat == QPunchCategory.A else 30
    )
    return raised + timedelta(days=int(days))


def _record_grant(db: Session, p: Principal, pr: Project, site_id: Any, eng_id: Any) -> None:
    """251 in scope; a responsible person (N) records where they resolve for the verification."""
    g = p.require(pr.id, C.punch_record)
    if g.scope == S.responsible:
        if not rpm.resolves(db, p, pr, RT, STEP, rpm.Ctx(site_id, eng_id), can_act=False):
            raise forbidden_error("You verify no punch items of this contractor.")
    elif not qc.covers(g, site_id, eng_id):
        raise forbidden_error("This site or contractor is outside your scope.")


def _pin(db: Session, pr: Project, it: QPunchItem, pin: dict[str, Any] | None) -> None:
    if pin is None:
        return
    if not pin.get("floor_plan_id"):
        it.floor_plan_id, it.pin_x_pct, it.pin_y_pct, it.pin_check = None, None, None, False
        return
    fp = db.get(QFloorPlan, pin["floor_plan_id"])
    if fp is None or fp.project_id != pr.id or fp.status != QPlanStatus.current:
        raise qc.field_err(
            "pin.floor_plan_id", "Pick a current plan of this project.", "اختر مخططاً سارياً."
        )
    if fp.zone_id != it.zone_id:
        raise qc.field_err(
            "pin.floor_plan_id", "The plan belongs to another zone.", "المخطط يخص منطقة أخرى."
        )
    x, y = Decimal(str(pin.get("x_pct"))), Decimal(str(pin.get("y_pct")))
    if not (0 <= x <= 100 and 0 <= y <= 100):
        raise qc.field_err(
            "pin", "Pin positions are 0.0–100.0 % of the image.", "الموقع بين 0 و100٪."
        )
    it.floor_plan_id, it.pin_x_pct, it.pin_y_pct, it.pin_check = (
        fp.id,
        x.quantize(Decimal("0.01")),
        y.quantize(Decimal("0.01")),
        False,
    )


def create(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    body: dict[str, Any],
    *,
    walkdown_response: Any = None,
) -> tuple[QPunchItem, list[ApiWarning]]:
    pr = qc.get_project(db, p, project_id)
    q1c.writable_construction(db, p, pr, RT)
    cu = body.get("client_uuid")
    if cu is not None:
        dup = db.scalar(select(QPunchItem).where(QPunchItem.client_uuid == cu))
        if dup is not None:
            if dup.raised_by_user_id != p.user.id:
                raise forbidden_error()
            return dup, []
    if body.get("zone_id") is None:
        raise qc.field_err("zone_id", "Choose the zone.", "اختر المنطقة.")
    site, zone = check_site_zone(db, pr, body["site_id"], body["zone_id"])
    eng = check_engagement(db, pr, body["responsible_engagement_id"], "responsible_engagement_id")
    _record_grant(db, p, pr, site.id, eng.id)
    system_id = body.get("system_id")
    if system_id is not None:
        s = db.get(QSystem, system_id)
        if s is None or s.project_id != pr.id:
            raise qc.field_err("system_id", "The system is not on this project.")
    if not (body.get("description_en") or body.get("description_ar") or "").strip():
        raise qc.field_err("description_en", "Describe the item.", "صف البند.")
    photos = list(body.get("photos") or [])
    if not photos:
        raise qc.err(
            422,
            ErrorCode.EVIDENCE_REQUIRED,
            "Add at least one photo of the item.",
            "أرفق صورة واحدة على الأقل.",
        )
    at = now()
    raised = q1c.day(pr)
    cat = QPunchCategory(body["category"])
    it = QPunchItem(
        id=uuid.uuid4(),
        project_id=pr.id,
        punch_no=qnum.assign(db, pr, RT, on=raised),
        site_id=site.id,
        zone_id=zone.id if zone else body["zone_id"],
        system_id=system_id,
        location_ref=(body.get("location_ref") or "").strip()[:120] or "—",
        discipline=QDiscipline(body["discipline"]),
        description_en=(body.get("description_en") or "").strip() or None,
        description_ar=(body.get("description_ar") or "").strip() or None,
        category=cat,
        raised_during=QPunchRaisedDuring(body.get("raised_during") or "walkdown"),
        responsible_engagement_id=eng.id,
        raised_by_user_id=p.user.id,
        raised_at=at,
        raised_date=raised,
        target_date=body.get("target_date") or target_for(db, pr, cat, raised),
        status=ST.open,
        client_uuid=cu,
        walkdown_response_id=walkdown_response,
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    db.add(it)
    db.flush()
    _pin(db, pr, it, body.get("pin"))
    it.photo_before_ids = q1c.store_photos(
        db, AttachmentOwner.q_punch, it.id, pr.id, photos, p.user.id, "photos"
    )
    db.flush()
    _audit(db, p, it, AuditAction.create, after={"punch_no": it.punch_no, "category": cat.value})
    return it, id_warnings(description_en=it.description_en, description_ar=it.description_ar)


def update(db: Session, p: Principal, item_id: uuid.UUID, body: dict[str, Any]) -> QPunchItem:
    it = get_item(db, p, item_id)
    pr = q1c.project(db, it.project_id)
    q1c.progress_writable(pr, p)
    if it.status not in PUNCH_LIVE:
        raise invalid_transition("Punch item", it.status, "edit")
    g = p.grant(pr.id, C.punch_record) or p.grant(pr.id, C.punch_verify)
    if g is None:
        raise forbidden_error()
    if g.scope != S.responsible and not qc.covers(g, it.site_id, it.responsible_engagement_id):
        raise forbidden_error()
    p.ensure_writer()
    for k in ("description_en", "description_ar", "location_ref"):
        if k in body and body[k] is not None:
            setattr(
                it, k, body[k].strip() or None if k != "location_ref" else body[k].strip()[:120]
            )
    if body.get("category"):
        it.category = QPunchCategory(body["category"])
    if body.get("target_date"):
        it.target_date = body["target_date"]
    if "pin" in body:
        _pin(db, pr, it, body["pin"])
    if body.get("confirm_pin"):
        it.pin_check = False
    it.updated_by_user_id = p.user.id
    db.flush()
    _audit(db, p, it, AuditAction.update, details={"fields": sorted(body)})
    return it


def mark_ready(
    db: Session, p: Principal, item_id: uuid.UUID, note: str | None, photos: list[Any]
) -> QPunchItem:
    """Open → Ready for Review (251): ≥ 1 after photo and a note ≥ 10 chars (Q-PUN-02)."""
    it = get_item(db, p, item_id)
    pr = q1c.project(db, it.project_id)
    q1c.progress_writable(pr, p)
    if it.status != ST.open:
        raise invalid_transition("Punch item", it.status, "ready_for_review")
    g = p.require(pr.id, C.punch_record)
    if g.scope != S.responsible and not qc.covers(g, it.site_id, it.responsible_engagement_id):
        raise forbidden_error()
    text = (note or "").strip()
    if len(text) < 10 or not photos:
        raise qc.err(
            422,
            ErrorCode.PUNCH_EVIDENCE_REQUIRED,
            "Ready for review needs at least one photo after the fix and a note of at least 10 "
            "characters (Q-PUN-02).",
            "يتطلب الجاهز للمراجعة صورة بعد الإصلاح وملاحظة لا تقل عن 10 أحرف.",
        )
    it.photo_after_ids = [
        *(it.photo_after_ids or []),
        *q1c.store_photos(db, AttachmentOwner.q_punch, it.id, pr.id, photos, p.user.id, "photos"),
    ]
    it.ready_note = text
    it.ready_by_user_id = p.user.id
    it.ready_at = now()
    _status(db, p, it, ST.ready_for_review)
    res = q1c.acting(db, pr.id, rpm.resolve(db, pr, RT, STEP, ctx(it), record_id=it.id), ctx(it))
    qc.send(
        db,
        [u for u in res.users if u not in requesters(it)],
        f"{it.punch_no} ready for verification",
        f"{it.punch_no} جاهز للتحقق",
        body_en=it.description_en,
        body_ar=it.description_ar,
        entity_type=EntityType.q_punch_item,
        entity_id=it.id,
        project_id=it.project_id,
        email=False,
        key=f"punch_ready:{it.id}:{it.ready_at}",
        path=f"/quality/punch/{it.id}",
    )
    return it


def verify(
    db: Session,
    p: Principal,
    item_id: uuid.UUID,
    decision: str,
    comment: str | None,
    paper: dict[str, Any] | None = None,
) -> QPunchItem:
    """Ready for Review → Closed (approved) or back to Open (rejected, comment) by the responsible
    person for `punch_item.verify` (one sign-off per item)."""
    it = get_item(db, p, item_id)
    pr = q1c.project(db, it.project_id)
    q1c.progress_writable(pr, p)
    if it.status != ST.ready_for_review:
        raise invalid_transition("Punch item", it.status, "closed")
    if decision not in ("approved", "rejected"):
        raise qc.field_err("decision", "approved or rejected")
    text = (
        qc.reason(comment, 10, "comment")
        if decision == "rejected"
        else (comment or "").strip() or None
    )
    if paper:
        signoff.sign_paper(db, p, pr, RT, it.id, STEP, decision, text, paper, ctx(it))
    else:
        rule, capacity = rpm.check_signer(db, p, pr, RT, STEP, ctx(it), record_id=it.id)
        signoff.sign(db, p, pr, RT, it.id, STEP, decision, text, rule, capacity)
    if decision == "approved":
        it.closed_at = now()
        it.closed_date = q1c.day(pr)
        it.closed_by_user_id = p.user.id
        _status(db, p, it, ST.closed)
    else:
        it.status_reason = text
        it.ready_by_user_id = it.ready_by_user_id
        _status(db, p, it, ST.open, returned=text)
    return it


def void(db: Session, p: Principal, item_id: uuid.UUID, why: str | None) -> QPunchItem:
    it = get_item(db, p, item_id)
    pr = q1c.project(db, it.project_id)
    q1c.progress_writable(pr, p)
    p.require(pr.id, C.quality_void)
    if it.status not in PUNCH_LIVE:
        raise invalid_transition("Punch item", it.status, "voided")
    text = qc.reason(why, 20)
    it.status_reason = text
    _status(db, p, it, ST.voided, reason=text)
    return it


def overdue(it: QPunchItem, today: date) -> bool:
    """Q-PUN-03: not closed and today > target_date."""
    return it.status in PUNCH_LIVE and today > it.target_date


def _desc(text: str, note: str | None) -> str:
    return f"{text}: {note}" if note else text


# ---- walkdown (Q-PUN-01) ------------------------------------------------------------------------


def walkdown(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> tuple[list[QPunchItem], list[ApiWarning]]:
    """One checklist response of type `punch_walkdown`; each non-compliant answer or free entry
    becomes an item (with its own photo)."""
    pr = qc.get_project(db, p, project_id)
    q1c.writable_construction(db, p, pr, RT)
    base = {
        k: body.get(k)
        for k in ("site_id", "zone_id", "responsible_engagement_id", "discipline", "system_id")
    }
    base["raised_during"] = "walkdown"
    site, zone = check_site_zone(db, pr, body["site_id"], body.get("zone_id"))
    _record_grant(db, p, pr, site.id, body["responsible_engagement_id"])
    response_id = None
    created: list[QPunchItem] = []
    warnings: list[ApiWarning] = []
    answers = list(body.get("answers") or [])
    if body.get("template_code"):
        t = checklists.template_for(db, body["template_code"], "punch_walkdown")
        if t is None:
            raise qc.field_err("template_code", "Pick a published punch walkdown checklist.")
        r, sc = checklists.record(
            db,
            p.user.id,
            pr,
            ResponseOwnerType.q_punch_walkdown,
            t,
            answers,
            site_id=site.id,
            zone_id=zone.id if zone else None,
            engagement_id=body["responsible_engagement_id"],
            completed_at=now(),
        )
        response_id = r.id
        texts = {i["item_code"]: i for i in t.items}
        by_code = {a["item_code"]: a for a in answers}
        for ev in sc.evals:
            if not ev.non_compliant:
                continue
            a = by_code[ev.code]
            item = texts.get(ev.code, {})
            it, w = create(
                db,
                p,
                pr.id,
                {
                    **base,
                    "location_ref": a.get("location_ref") or body.get("location_ref"),
                    "description_en": _desc(item.get("text_en", ev.code), a.get("note")),
                    "description_ar": _desc(item.get("text_ar", ev.code), a.get("note")),
                    "category": a.get("category") or body.get("category") or "B",
                    "photos": a.get("photos") or [],
                    "pin": a.get("pin"),
                },
                walkdown_response=response_id,
            )
            created.append(it)
            warnings += w
    for e in body.get("entries") or []:
        it, w = create(
            db,
            p,
            pr.id,
            {**base, **{k: v for k, v in e.items() if v is not None}},
            walkdown_response=response_id,
        )
        created.append(it)
        warnings += w
    if not created:
        raise qc.field_err("entries", "The walkdown recorded no item.", "لم تُسجَّل أي بنود.")
    return created, warnings


# ---- list and read ------------------------------------------------------------------------------


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    statuses: list[QPunchStatus] | None = None,
    zone_id: uuid.UUID | None = None,
    category: QPunchCategory | None = None,
    engagement_id: uuid.UUID | None = None,
    floor_plan_id: uuid.UUID | None = None,
    overdue_only: bool = False,
    q: str | None = None,
) -> dict[str, Any]:
    pr = qc.get_project(db, p, project_id)
    if p.grant(pr.id, C.quality_view) is None and p.grant(pr.id, C.punch_record) is None:
        raise forbidden_error()
    stmt = select(QPunchItem).where(QPunchItem.project_id == pr.id)
    if statuses:
        stmt = stmt.where(QPunchItem.status.in_(statuses))
    if zone_id:
        stmt = stmt.where(QPunchItem.zone_id == zone_id)
    if category:
        stmt = stmt.where(QPunchItem.category == category)
    if engagement_id:
        stmt = stmt.where(QPunchItem.responsible_engagement_id == engagement_id)
    if floor_plan_id:
        fam = db.scalar(select(QFloorPlan.family_id).where(QFloorPlan.id == floor_plan_id))
        ids = list(db.scalars(select(QFloorPlan.id).where(QFloorPlan.family_id == fam)))
        stmt = stmt.where(QPunchItem.floor_plan_id.in_(ids))
    today = q1c.day(pr)
    if overdue_only:
        stmt = stmt.where(QPunchItem.status.in_(list(PUNCH_LIVE)), QPunchItem.target_date < today)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            QPunchItem.punch_no.ilike(like)
            | QPunchItem.description_en.ilike(like)
            | QPunchItem.description_ar.ilike(like)
            | QPunchItem.location_ref.ilike(like)
        )
    rows = [r for r in db.scalars(stmt.order_by(QPunchItem.punch_no)) if can_view(db, p, r)]
    hide = q1c.viewer(p, pr.id)
    total = len(rows)
    chunk = rows[(page - 1) * page_size : page * page_size]
    return {
        "items": [list_item(db, r, today, hide) for r in chunk],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def list_item(db: Session, it: QPunchItem, today: date, hide: bool) -> dict[str, Any]:
    zone = db.get(Zone, it.zone_id)
    return {
        "id": it.id,
        "punch_no": it.punch_no,
        "status": it.status,
        "category": it.category,
        "discipline": it.discipline,
        "description_en": it.description_en,
        "description_ar": it.description_ar,
        "location_ref": it.location_ref,
        "zone": {"id": zone.id, "code": zone.code, "name_en": zone.name_en, "name_ar": zone.name_ar}
        if zone
        else None,
        "engagement": _eng(db, it.responsible_engagement_id),
        "raised_date": it.raised_date,
        "target_date": it.target_date,
        "closed_date": it.closed_date,
        "overdue": overdue(it, today),
        "floor_plan_id": it.floor_plan_id,
        "pin_x_pct": str(it.pin_x_pct) if it.pin_x_pct is not None else None,
        "pin_y_pct": str(it.pin_y_pct) if it.pin_y_pct is not None else None,
        "pin_check": it.pin_check,
        "raised_by": q1c.user_ref(db, it.raised_by_user_id, hide),
    }


def allowed_actions(db: Session, p: Principal, it: QPunchItem) -> list[str]:
    if q1c.viewer(p, it.project_id):
        return []
    pr = q1c.project(db, it.project_id)
    out = []
    rec = p.grant(pr.id, C.punch_record)
    in_scope = rec is not None and (
        rec.scope == S.responsible or qc.covers(rec, it.site_id, it.responsible_engagement_id)
    )
    if it.status in PUNCH_LIVE and in_scope:
        out.append("edit")
    if it.status == ST.open and in_scope:
        out.append("mark_ready")
    if it.status == ST.ready_for_review and rpm.resolves(
        db, p, pr, RT, STEP, ctx(it), record_id=it.id
    ):
        out.append("verify")
    if it.status == ST.ready_for_review and p.grant(pr.id, C.punch_verify) is not None:
        out.append("paper_signoff")
    if it.status in PUNCH_LIVE and p.grant(pr.id, C.quality_void) is not None:
        out.append("void")
    if it.status in PUNCH_LIVE and p.grant(pr.id, C.ncr_raise) is not None:
        out.append("raise_ncr")
    return out


def read(
    db: Session, p: Principal, it: QPunchItem, warnings: list[ApiWarning] | None = None
) -> dict[str, Any]:
    from app.core.quality.common import QNcrSourceType  # noqa: PLC0415
    from app.models.quality import QNcr  # noqa: PLC0415

    pr = q1c.project(db, it.project_id)
    hide = q1c.viewer(p, it.project_id)
    site = db.get(Site, it.site_id)
    res = (
        q1c.acting(db, pr.id, rpm.resolve(db, pr, RT, STEP, ctx(it), record_id=it.id), ctx(it))
        if it.status == ST.ready_for_review
        else None
    )
    ncrs = db.scalars(
        select(QNcr).where(QNcr.source_type == QNcrSourceType.punch_item, QNcr.source_id == it.id)
    )
    return {
        **list_item(db, it, q1c.day(pr), hide),
        "project_id": it.project_id,
        "site": {"id": site.id, "code": site.code, "name_en": site.name_en, "name_ar": site.name_ar}
        if site
        else None,
        "system_id": it.system_id,
        "raised_during": it.raised_during,
        "raised_at": it.raised_at,
        "photo_before_ids": [] if hide else list(it.photo_before_ids or []),
        "photo_after_ids": [] if hide else list(it.photo_after_ids or []),
        "ready_note": it.ready_note,
        "ready_at": it.ready_at,
        "ready_by": q1c.user_ref(db, it.ready_by_user_id, hide),
        "closed_by": q1c.user_ref(db, it.closed_by_user_id, hide),
        "status_reason": it.status_reason,
        "responsible": [u for u in (q1c.user_ref(db, x, hide) for x in sorted(res.users)) if u]
        if res
        else [],
        "signoffs": []
        if hide
        else [signoff.read(db, s) for s in signoff.signoffs_for(db, RT, it.id)],
        "ncrs": [{"id": n.id, "ncr_no": n.ncr_no, "status": n.status} for n in ncrs],
        "links": links.links_for(db, p, RT, it.id),
        "allowed_actions": allowed_actions(db, p, it),
        "warnings": [w.model_dump() for w in warnings or []],
    }


# ---- floor plans (§B.6) -------------------------------------------------------------------------


def _image(content: bytes, file_name: str) -> tuple[str, int, int]:
    ctype = attachments._content_type(file_name, content)
    size = attachments._image_size(content, ctype)
    if ctype not in ("image/png", "image/jpeg") or size is None:
        raise qc.err(
            422,
            ErrorCode.PLAN_IMAGE_INVALID,
            "Plans must be PNG or JPEG images (export a PDF sheet as an image first).",
            "يجب أن يكون المخطط صورة PNG أو JPEG (صدّر ورقة PDF كصورة أولاً).",
        )
    if len(content) > PLAN_MAX_BYTES or max(size) > PLAN_MAX_EDGE:
        raise qc.err(
            422,
            ErrorCode.PLAN_IMAGE_INVALID,
            f"Plans must be at most 10 MB with a long edge of at most {PLAN_MAX_EDGE} px.",
            "الحد الأقصى للمخطط 10 ميغابايت وطول الضلع الأطول 6000 بكسل.",
        )
    return ctype, size[0], size[1]


def plan_can_view(db: Session, p: Principal, fp: QFloorPlan) -> bool:
    return p.can_see_project(fp.project_id) and (
        p.grant(fp.project_id, C.quality_view) is not None
        or p.grant(fp.project_id, C.punch_record) is not None
    )


def get_plan(db: Session, p: Principal, plan_id: uuid.UUID) -> QFloorPlan:
    fp = db.get(QFloorPlan, plan_id)
    if fp is None or not plan_can_view(db, p, fp):
        raise q1c.denied(
            db, p, EntityType.q_punch_item, plan_id, fp.project_id if fp else None, "Floor plan"
        )
    return fp


def _plan_writer(db: Session, p: Principal, pr: Project) -> None:
    g = p.require(pr.id, C.punch_record)
    if g.scope == S.responsible and p.grant(pr.id, C.dossier_compile) is None:
        raise forbidden_error("Uploading plans needs capability 251 or 253.")


def upload_plan(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    meta: dict[str, Any],
    file_name: str,
    content: bytes,
    revision_of: uuid.UUID | None = None,
) -> QFloorPlan:
    pr = qc.get_project(db, p, project_id)
    q1c.writable_construction(db, p, pr, RT)
    _plan_writer(db, p, pr)
    ctype, w, h = _image(content, file_name)
    old = None
    if revision_of is not None:
        old = get_plan(db, p, revision_of)
        if old.project_id != pr.id or old.status != QPlanStatus.current:
            raise invalid_transition("Floor plan", old.status, "revised")
        zone_id = old.zone_id
    else:
        zone = db.get(Zone, meta.get("zone_id"))
        if zone is None or zone.project_id != pr.id:
            raise qc.field_err("zone_id", "The zone is not on this project.")
        zone_id = zone.id
    fp = QFloorPlan(
        id=uuid.uuid4(),
        project_id=pr.id,
        family_id=old.family_id if old else uuid.uuid4(),
        zone_id=zone_id,
        level_label=(meta.get("level_label") or (old.level_label if old else "") or "—")[:60],
        title_en=(meta.get("title_en") or (old.title_en if old else "") or "Plan")[:150],
        title_ar=(meta.get("title_ar") or (old.title_ar if old else "") or "مخطط")[:150],
        revision=(meta.get("revision") or (_next_rev(old.revision) if old else "0"))[:20],
        width_px=w,
        height_px=h,
        status=QPlanStatus.current,
        created_by_user_id=p.user.id,
    )
    db.add(fp)
    db.flush()
    a = attachments.store(
        db,
        AttachmentOwner.q_floor_plan,
        fp.id,
        pr.id,
        file_name,
        content,
        ctype,
        p.user.id,
        shrink=False,
    )
    fp.attachment_id = a.id
    moved = 0
    if old is not None:
        old.status = QPlanStatus.superseded
        same = abs((w / h) - (old.width_px / old.height_px)) <= 0.01 * (
            old.width_px / old.height_px
        )
        for it in db.scalars(select(QPunchItem).where(QPunchItem.floor_plan_id == old.id)):
            it.floor_plan_id = fp.id
            if not same:
                it.pin_check = True
            moved += 1
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(pr.id),
        entity_type=EntityType.q_punch_item,
        entity_id=fp.id,
        project_id=pr.id,
        details={"floor_plan": fp.title_en, "revision": fp.revision, "pins_moved": moved},
    )
    return fp


def _next_rev(r: str) -> str:
    try:
        return str(int(r) + 1)
    except ValueError:
        return f"{r}+"


def plan_read(db: Session, p: Principal, fp: QFloorPlan) -> dict[str, Any]:
    zone = db.get(Zone, fp.zone_id)
    pins = list(db.scalars(select(QPunchItem).where(QPunchItem.floor_plan_id == fp.id)))
    pr = q1c.project(db, fp.project_id)
    today = q1c.day(pr)
    hide = q1c.viewer(p, fp.project_id)
    return {
        "id": fp.id,
        "family_id": fp.family_id,
        "zone": {"id": zone.id, "code": zone.code, "name_en": zone.name_en, "name_ar": zone.name_ar}
        if zone
        else None,
        "level_label": fp.level_label,
        "title_en": fp.title_en,
        "title_ar": fp.title_ar,
        "revision": fp.revision,
        "width_px": fp.width_px,
        "height_px": fp.height_px,
        "status": fp.status,
        "attachment_id": fp.attachment_id,
        "pin_count": len(pins),
        "pins": [list_item(db, it, today, hide) for it in pins if can_view(db, p, it)],
        "unpinned_count": 0,
        "created_at": fp.created_at,
    }


def list_plans(
    db: Session, p: Principal, project_id: uuid.UUID, zone_id: uuid.UUID | None, current_only: bool
) -> list[dict[str, Any]]:
    pr = qc.get_project(db, p, project_id)
    if p.grant(pr.id, C.quality_view) is None and p.grant(pr.id, C.punch_record) is None:
        raise forbidden_error()
    stmt = select(QFloorPlan).where(QFloorPlan.project_id == pr.id)
    if zone_id:
        stmt = stmt.where(QFloorPlan.zone_id == zone_id)
    if current_only:
        stmt = stmt.where(QFloorPlan.status == QPlanStatus.current)
    out = []
    for fp in db.scalars(stmt.order_by(QFloorPlan.title_en, QFloorPlan.created_at)):
        d = plan_read(db, p, fp)
        d["unpinned_count"] = int(
            db.scalar(
                select(func.count())
                .select_from(QPunchItem)
                .where(
                    QPunchItem.zone_id == fp.zone_id,
                    QPunchItem.floor_plan_id.is_(None),
                    QPunchItem.status.in_(list(PUNCH_LIVE)),
                )
            )
            or 0
        )
        d["pins"] = []
        out.append(d)
    return out


def plan_image(db: Session, p: Principal, plan_id: uuid.UUID) -> tuple[bytes, str, str]:
    from app.models import Attachment  # noqa: PLC0415

    fp = get_plan(db, p, plan_id)
    a = db.get(Attachment, fp.attachment_id) if fp.attachment_id else None
    if a is None:
        raise not_found("Plan image")
    return attachments.read_content(a), a.content_type, a.file_name


_ = (io, label)
