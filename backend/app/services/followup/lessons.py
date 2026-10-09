"""6f lessons learned (spec 6f §3.6-§3.8, §4.4, LL-1…LL-6, DS-1…DS-4, LK-1…LK-4)."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, NotificationKind, Role
from app.core.enums import EntityType as ET  # noqa: N817
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.field_enums import CampaignReason, LinkedRefKind, TopicCategory, VersionStatus
from app.core.followup_enums import (
    FuAckResponse,
    FuChangeStatus,
    FuDistributionStatus,
    FuLessonAction,
    FuLessonSource,
    FuLessonStatus,
    FuLinkKind,
)
from app.core.hse_enums import AttachmentOwner, IncidentStatus
from app.models import (
    ChecklistTemplate,
    CorrectiveAction,
    FuDistribution,
    FuLesson,
    FuLessonLink,
    Incident,
    InjuryCase,
    Investigation,
    Site,
    ToolboxTopic,
    WorkforceReturn,
    Zone,
)
from app.schemas.followup import (
    FuAckRequest,
    FuActionTaken,
    FuApplicability,
    FuDistributionList,
    FuDistributionRead,
    FuKeyLesson,
    FuLessonCreate,
    FuLessonListItem,
    FuLessonPage,
    FuLessonRead,
    FuLessonTransition,
    FuLessonUpdate,
    FuLinkCreate,
    FuLinkDecision,
    FuLinkPage,
    FuLinkRead,
    FuRemovedEngagement,
    FuSimilarLessons,
)
from app.services.common import invalid_transition
from app.services.followup import common as fc
from app.services.permissions import Principal, forbidden_error

C = fc.C
LS = FuLessonStatus
DS = FuDistributionStatus
VISIBLE = (LS.published, LS.archived)
TEXTS = ("title_en", "title_ar", "what_happened_en", "what_happened_ar", "why_en", "why_ar")
MONTHS_AR = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر",
    "نوفمبر", "ديسمبر",
]  # fmt: skip


# ---- access --------------------------------------------------------------------------------------


def _staff(db: Session, p: Principal, ls: FuLesson) -> bool:
    """May see drafts and lessons in review: 220 holders, the author, 219 holders of the source
    project (reps: incidents of their tree)."""
    if p.is_manager or ls.author_id == p.user.id:
        return True
    pid = ls.source_project_id
    g = p.grant(pid, C.lesson_draft) if pid else None
    if g is None:
        return False
    if g.engagement_ids is None:
        return True
    inc = db.get(Incident, ls.incident_id) if ls.incident_id else None
    return inc is not None and g.covers_engagement(inc.responsible_engagement_id)


def _get(db: Session, p: Principal, lesson_id: uuid.UUID) -> FuLesson:
    ls = db.get(FuLesson, lesson_id)
    if ls is None or not p.has_any(C.lesson_library_view):
        raise not_found("Lesson")
    if ls.status not in VISIBLE and not _staff(db, p, ls):
        raise not_found("Lesson")
    return ls


def _draft_project(db: Session, p: Principal, ls: FuLesson) -> uuid.UUID | None:
    ids = list(ls.distribution_project_ids or [])
    return ls.source_project_id or (ids[0] if ids else None)


def _need_draft(db: Session, p: Principal, ls: FuLesson) -> None:
    """219 on the source project (external lessons: anywhere), within the rep's tree."""
    pid = ls.source_project_id
    if pid is None:
        p.require_any(C.lesson_draft)
        return
    p.require(pid, C.lesson_draft)
    if not _staff(db, p, ls):
        raise forbidden_error()


# ---- text ----------------------------------------------------------------------------------------


def _texts(ls: FuLesson) -> dict[str, str | None]:
    out: dict[str, str | None] = {
        k: getattr(ls, k)
        for k in (
            "title_en",
            "title_ar",
            "what_happened_en",
            "what_happened_ar",
            "why_en",
            "why_ar",
        )
    }
    for i, k in enumerate(ls.key_lessons or []):
        out[f"key_lessons[{i}].text_en"] = k.get("text_en")
        out[f"key_lessons[{i}].text_ar"] = k.get("text_ar")
    return out


def _index(ls: FuLesson) -> str:
    parts: list[str] = [ls.lesson_no, *[v or "" for v in _texts(ls).values()]]
    parts += list(ls.root_cause_codes or [])
    for v in (ls.applicability or {}).values():
        parts += [str(x).replace("_", " ") for x in v]
    return fc.normalise(" ".join(parts))


def _matches(index: str, terms: list[str]) -> bool:
    words = index.split()
    return all(any(w.startswith(t) for w in words) for t in terms)


def _month(d: date | datetime | None) -> str | None:
    return None if d is None else f"{d.year:04d}-{d.month:02d}"


# ---- reads ---------------------------------------------------------------------------------------


def link_read(db: Session, k: FuLessonLink) -> FuLinkRead:
    ls = db.get(FuLesson, k.lesson_id)
    return FuLinkRead(
        id=k.id, kind=k.kind, ref=k.ref, project_id=k.project_id, item_code=k.item_code,
        proposed_text_en=k.proposed_text_en, proposed_text_ar=k.proposed_text_ar,
        status=k.status, adopted_version=k.adopted_version, reject_reason=k.reject_reason,
        lesson_no=ls.lesson_no if ls else None, created_at=k.created_at,
    )  # fmt: skip


def _items(db: Session, lesson_id: uuid.UUID) -> list[FuDistribution]:
    return list(
        db.scalars(
            select(FuDistribution)
            .where(FuDistribution.lesson_id == lesson_id)
            .order_by(FuDistribution.project_id, FuDistribution.engagement_id)
        )
    )


def to_read(
    db: Session, p: Principal, ls: FuLesson, warnings: list[Any] | None = None
) -> FuLessonRead:
    from app.services.followup import effectiveness  # noqa: PLC0415

    staff = _staff(db, p, ls) and not (
        ls.source_project_id and fc.is_viewer(p, ls.source_project_id)
    )
    inc = db.get(Incident, ls.incident_id) if ls.incident_id else None
    items = [i for i in _items(db, ls.id) if i.status != DS.withdrawn]
    sup = db.get(FuLesson, ls.superseded_by_id) if ls.superseded_by_id else None
    links = db.scalars(
        select(FuLessonLink)
        .where(FuLessonLink.lesson_id == ls.id)
        .order_by(FuLessonLink.created_at)
    )
    chk = effectiveness.check_of(db, ls.id)
    return FuLessonRead(
        id=ls.id,
        lesson_no=ls.lesson_no,
        source=ls.source,
        incident_id=ls.incident_id if staff else None,
        incident_ref=inc.ref if inc is not None and staff else None,
        source_project_id=ls.source_project_id,
        source_project_code=fc.pcode(db, ls.source_project_id) if ls.source_project_id else None,
        external_ref=ls.external_ref,
        system_created=ls.system_created,
        required=ls.required,
        title_en=ls.title_en,
        title_ar=ls.title_ar,
        what_happened_en=ls.what_happened_en,
        what_happened_ar=ls.what_happened_ar,
        why_en=ls.why_en,
        why_ar=ls.why_ar,
        root_cause_codes=list(ls.root_cause_codes or []),
        key_lessons=[FuKeyLesson(**k) for k in ls.key_lessons or []],
        actions_taken=[FuActionTaken(**a) for a in ls.actions_taken or []],
        applicability=FuApplicability(**(ls.applicability or {})),
        severity_potential=ls.severity_potential,
        photos=list(ls.photos or []),
        distribution_project_ids=list(ls.distribution_project_ids or []),
        distribution_project_codes=fc.project_codes(db, list(ls.distribution_project_ids or [])),
        removed_engagements=[FuRemovedEngagement(**r) for r in ls.removed_engagements or []],
        publish_due_on=ls.publish_due_on,
        author=fc.user_ref(db, ls.author_id) if staff else None,
        approved_by=fc.user_ref(db, ls.approved_by_user_id) if staff else None,
        published_at=ls.published_at,
        archived_at=ls.archived_at,
        superseded_by_lesson_no=sup.lesson_no if sup else None,
        return_comment=ls.return_comment if staff else None,
        status_reason=ls.status_reason,
        status=ls.status,
        links=[link_read(db, k) for k in links],
        acknowledged=sum(1 for i in items if i.status in (DS.acknowledged, DS.not_applicable)),
        distribution_items=len(items),
        check=effectiveness.check_read(db, chk) if chk is not None and staff else None,
        warnings=warnings or [],
        created_at=ls.created_at,
    )


def list_item(ls: FuLesson, db: Session) -> FuLessonListItem:
    return FuLessonListItem(
        id=ls.id,
        lesson_no=ls.lesson_no,
        title_en=ls.title_en,
        title_ar=ls.title_ar,
        status=ls.status,
        archived=ls.status == LS.archived,
        source_project_code=fc.pcode(db, ls.source_project_id) if ls.source_project_id else None,
        published_at=ls.published_at,
        publish_due_on=ls.publish_due_on,
        month=_month(fc.to_local(ls.published_at) if ls.published_at else None),
        root_cause_codes=list(ls.root_cause_codes or []),
        applicability=FuApplicability(**(ls.applicability or {})),
        key_lessons=[FuKeyLesson(**k) for k in ls.key_lessons or []],
    )


def library(
    db: Session,
    p: Principal,
    q: str | None,
    statuses: list[LS] | None,
    activity: Any,
    mechanism: Any,
    do_category: Any,
    root_cause_code: str | None,
    zone_type: str | None,
    trade: Any,
    project_id: uuid.UUID | None,
    year: int | None,
    page: int,
    size: int,
) -> FuLessonPage:
    """LL-5: Published and Archived for every 222 holder; drafts only for staff."""
    if not p.has_any(C.lesson_library_view):
        raise forbidden_error()
    want = set(statuses or VISIBLE)
    terms = fc.search_terms(q) if q else []
    out: list[FuLesson] = []
    for ls in db.scalars(select(FuLesson).where(FuLesson.status.in_(list(want)))):
        if ls.status not in VISIBLE and not _staff(db, p, ls):
            continue
        a = ls.applicability or {}
        if activity and activity.value not in a.get("activities", []):
            continue
        if mechanism and mechanism.value not in a.get("mechanisms", []):
            continue
        if do_category and do_category.value not in a.get("do_categories", []):
            continue
        if trade and trade.value not in a.get("trades", []):
            continue
        if zone_type and zone_type not in a.get("zone_types", []):
            continue
        if root_cause_code and root_cause_code not in (ls.root_cause_codes or []):
            continue
        if (
            project_id
            and project_id != ls.source_project_id
            and project_id not in (ls.distribution_project_ids or [])
        ):
            continue
        when = fc.to_local(ls.published_at).year if ls.published_at else ls.year
        if year and when != year:
            continue
        if terms and not _matches(ls.search_text or _index(ls), terms):
            continue
        out.append(ls)
    out.sort(key=lambda x: (x.published_at or x.created_at, x.lesson_no), reverse=True)
    rows = out[(page - 1) * size : page * size]
    return FuLessonPage(
        items=[list_item(x, db) for x in rows], total=len(out), page=page, page_size=size
    )


def read(db: Session, p: Principal, lesson_id: uuid.UUID) -> FuLessonRead:
    return to_read(db, p, _get(db, p, lesson_id))


# ---- creation (LL-1, LL-2) -----------------------------------------------------------------------


def _next_no(db: Session, year: int) -> tuple[str, int]:
    seq = (db.scalar(select(func.max(FuLesson.seq)).where(FuLesson.year == year)) or 0) + 1
    return f"LL-{year}-{seq:03d}", seq


def _what_happened(db: Session, inc: Incident) -> tuple[str, str]:
    """LL-2: month and year, project named, zone generalised to its zone type; names redacted."""
    pc = fc.pcode(db, inc.project_id)
    z = db.get(Zone, inc.zone_id) if inc.zone_id else None
    zt = z.zone_type.value if z is not None and z.zone_type else "site"
    d = inc.occurred_date
    body = fc.redact(db, inc, inc.description or inc.title) or ""
    body = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "", body)
    en = f"{d.strftime('%B')} {d.year}, {pc}, {zt.replace('_', ' ')} zone: {body}".strip()
    ar = f"{MONTHS_AR[d.month - 1]} {d.year}، {pc}، منطقة {zt}"
    return en[:1500], ar


def prefill(db: Session, ls: FuLesson, inc: Incident, inv: Investigation | None) -> None:
    from app.services.incidents import linked_cas  # noqa: PLC0415

    cases = list(db.scalars(select(InjuryCase).where(InjuryCase.incident_id == inc.id)))
    z = db.get(Zone, inc.zone_id) if inc.zone_id else None
    ls.title_en = (fc.redact(db, inc, inc.title) or "")[:150] or None
    ls.what_happened_en, ls.what_happened_ar = _what_happened(db, inc)
    rcs = list((inv.root_causes if inv else None) or [])
    ls.root_cause_codes = list(dict.fromkeys(str(rc["code"]) for rc in rcs))
    why = "; ".join(str(rc.get("text") or "") for rc in rcs if rc.get("text"))
    ls.why_en = (fc.redact(db, inc, why) or "")[:1500] or None
    lines = [x.strip(" -•\t") for x in ((inv.lessons_learned if inv else None) or "").splitlines()]
    ls.key_lessons = [
        {"text_en": (fc.redact(db, inc, x) or "")[:500], "text_ar": ""} for x in lines if x
    ][:5]
    ls.applicability = {
        "activities": [inc.activity.value] if inc.activity else [],
        "zone_types": [z.zone_type.value] if z is not None and z.zone_type else [],
        "trades": sorted({c.trade.value for c in cases}),
        "mechanisms": sorted({c.mechanism.value for c in cases}),
        "do_categories": [inc.do_category.value] if inc.do_category else [],
    }
    ls.severity_potential = inc.potential_severity
    ls.actions_taken = [
        {"ca_ref": ca.ref, "control_level": ca.control_level.value if ca.control_level else None}
        for ca in linked_cas(db, inc.id)
    ]
    ls.search_text = _index(ls)


def _new(db: Session, source: FuLessonSource, at: datetime) -> FuLesson:
    year = fc.local_day(at).year
    no, seq = _next_no(db, year)
    return FuLesson(lesson_no=no, year=year, seq=seq, source=source, status=LS.draft,
                    key_lessons=[], actions_taken=[], applicability={}, photos=[],
                    distribution_project_ids=[], removed_engagements=[], root_cause_codes=[],
                    alerts_sent=[], search_text="")  # fmt: skip


def on_investigation_approved(db: Session, inc: Incident, inv: Investigation) -> FuLesson | None:
    """LL-1: a Draft lesson when an investigation at a required level is approved."""
    if inv.level not in fc.cfg(db, inc.project_id).levels:
        return None
    if db.scalar(select(FuLesson.id).where(FuLesson.incident_id == inc.id)) is not None:
        return None
    at = inv.approved_at or now()
    ls = _new(db, FuLessonSource.incident, at)
    ls.incident_id = inc.id
    ls.source_project_id = inc.project_id
    ls.system_created = True
    ls.required = True
    ls.author_id = inv.lead_investigator_id or inv.approved_by_user_id
    days = int(fc.cfg(db, inc.project_id)["lesson_publish_days"])
    ls.publish_due_on = fc.local_day(at) + timedelta(days=days)
    prefill(db, ls, inc, inv)
    db.add(ls)
    db.flush()
    fc.record(db, None, AuditAction.create, ET.lesson, ls, inc.project_id,
              details={"lesson_no": ls.lesson_no, "rule": "LL-1"})  # fmt: skip
    return ls


def create(db: Session, p: Principal, body: FuLessonCreate) -> FuLessonRead:
    at = now()
    ls = _new(db, body.source, at)
    ls.author_id = p.user.id
    if body.source == FuLessonSource.incident:
        if body.incident_id is None:
            raise validation_error("incident_id", "Choose the source incident.")
        inc = db.get(Incident, body.incident_id)
        if inc is None or not p.can_see_project(inc.project_id):
            raise not_found("Incident")
        p.require(inc.project_id, C.lesson_draft)
        g = p.grant(inc.project_id, C.lesson_draft)
        if g is not None and not g.covers_engagement(inc.responsible_engagement_id):
            raise not_found("Incident")
        inv = db.get(Investigation, inc.id)
        if inv is None:
            raise validation_error("incident_id", "The incident has no investigation.")
        ls.incident_id = inc.id
        ls.source_project_id = inc.project_id
        prefill(db, ls, inc, inv)
    else:
        p.require_any(C.lesson_draft)
        if not (body.external_ref or "").strip():
            raise validation_error("external_ref", "Give the external alert reference.")
        ls.external_ref = body.external_ref
    if body.title_en:
        ls.title_en = body.title_en
    if body.title_ar:
        ls.title_ar = body.title_ar
    ls.search_text = _index(ls)
    db.add(ls)
    db.flush()
    fc.record(db, p, AuditAction.create, ET.lesson, ls, ls.source_project_id)
    return to_read(db, p, ls)


# ---- edits ---------------------------------------------------------------------------------------


def update(db: Session, p: Principal, lesson_id: uuid.UUID, body: FuLessonUpdate) -> FuLessonRead:
    ls = _get(db, p, lesson_id)
    data = body.model_dump(exclude_unset=True)
    distribution_only = set(data) <= {"distribution_project_ids", "removed_engagements"}
    if ls.status == LS.in_review and distribution_only:
        p.require_any(C.lesson_publish)
    elif ls.status == LS.draft:
        _need_draft(db, p, ls)
    else:
        raise invalid_transition("Lesson", ls.status, ls.status)
    before = {"status": ls.status.value}
    for k in ("title_en", "title_ar", "what_happened_en", "what_happened_ar", "why_en", "why_ar"):
        if k in data:
            setattr(ls, k, data[k])
    if "root_cause_codes" in data:
        ls.root_cause_codes = list(dict.fromkeys(data["root_cause_codes"] or []))
    if "key_lessons" in data:
        ls.key_lessons = [k.model_dump() for k in body.key_lessons or []]
    if "applicability" in data and body.applicability is not None:
        ls.applicability = body.applicability.model_dump(mode="json")
    if "photos" in data:
        ls.photos = _photos(db, p, ls, body)
    if "distribution_project_ids" in data:
        ids = list(dict.fromkeys(data["distribution_project_ids"] or []))
        for pid in ids:
            fc.project(db, None, pid)
        ls.distribution_project_ids = ids
    if "removed_engagements" in data:
        ls.removed_engagements = [r.model_dump(mode="json") for r in body.removed_engagements or []]
    fc.check_identity(db, ls.incident_id, _texts(ls))
    ls.search_text = _index(ls)
    ls.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.update, ET.lesson, ls, ls.source_project_id, before=before)
    return to_read(db, p, ls, fc.p18_warnings(_texts(ls)))


def _photos(db: Session, p: Principal, ls: FuLesson, body: FuLessonUpdate) -> list[dict[str, Any]]:
    keep = {str(x.get("attachment_id")) for x in ls.photos or []}
    pid = _draft_project(db, p, ls)
    out: list[dict[str, Any]] = []
    for i, ph in enumerate(body.photos or []):
        if ph.attachment_id is not None:
            if str(ph.attachment_id) not in keep:
                raise validation_error(f"photos[{i}].attachment_id", "Unknown photo.")
            aid = ph.attachment_id
        elif ph.file is not None:
            if pid is None:
                raise validation_error("photos", "Choose a project before adding photos.")
            aid = fc.store_file(db, ph.file, AttachmentOwner.fu_lesson_photo, ls.id, pid,
                                p.user.id, f"photos[{i}]")  # fmt: skip
        else:
            raise validation_error(f"photos[{i}]", "Give attachment_id or file.")
        out.append({"attachment_id": str(aid), "redaction_confirmed": ph.redaction_confirmed})
    return out


def delete(db: Session, p: Principal, lesson_id: uuid.UUID) -> None:
    ls = _get(db, p, lesson_id)
    if ls.status != LS.draft or ls.system_created:
        raise invalid_transition("Lesson", ls.status, "deleted")
    if ls.author_id != p.user.id:
        raise forbidden_error("Only the author deletes a manual draft.")
    p.ensure_writer()
    for k in db.scalars(select(FuLessonLink).where(FuLessonLink.lesson_id == ls.id)):
        db.delete(k)
    fc.record(db, p, AuditAction.archive, ET.lesson, ls, ls.source_project_id,
              details={"deleted": True})  # fmt: skip
    db.delete(ls)
    db.flush()


# ---- transitions (§4.4) --------------------------------------------------------------------------


def missing(ls: FuLesson) -> list[str]:
    """LL-3 completeness."""
    out = [k for k in ("title_en", "title_ar", "what_happened_en", "what_happened_ar", "why_en",
                       "why_ar") if not (getattr(ls, k) or "").strip()]  # fmt: skip
    kl = ls.key_lessons or []
    if not kl:
        out.append("key_lessons")
    for i, k in enumerate(kl):
        for lang in ("text_en", "text_ar"):
            if not (k.get(lang) or "").strip():
                out.append(f"key_lessons[{i}].{lang}")
    if not (ls.applicability or {}).get("activities"):
        out.append("applicability.activities")
    return out


def _complete(db: Session, ls: FuLesson) -> None:
    miss = missing(ls)
    if miss:
        raise fc.code_err(
            ErrorCode.LESSON_INCOMPLETE,
            "The lesson is incomplete: " + ", ".join(miss) + ".",
            "الدرس غير مكتمل.",
            miss[0],
            missing=miss,
        )
    bad = [i for i, ph in enumerate(ls.photos or []) if not ph.get("redaction_confirmed")]
    if bad:
        raise fc.code_err(
            ErrorCode.REDACTION_NOT_CONFIRMED,
            "Confirm that every photo is redacted (faces, names, plates).",
            "أكد إخفاء البيانات في كل صورة.",
            f"photos[{bad[0]}]",
        )
    fc.check_identity(db, ls.incident_id, _texts(ls))


def transition(
    db: Session, p: Principal, lesson_id: uuid.UUID, body: FuLessonTransition
) -> FuLessonRead:
    ls = _get(db, p, lesson_id)
    src = ls.status
    a = body.action
    at = now()
    if a == FuLessonAction.submit:
        if src != LS.draft:
            raise invalid_transition("Lesson", src, LS.in_review)
        _need_draft(db, p, ls)
        _complete(db, ls)
        ls.status = LS.in_review
        ls.return_comment = None
    elif a == FuLessonAction.return_to_draft:
        if src != LS.in_review:
            raise invalid_transition("Lesson", src, LS.draft)
        p.require_any(C.lesson_publish)
        ls.return_comment = fc.reason(body.comment, 1, "comment")
        ls.status = LS.draft
    elif a == FuLessonAction.publish:
        if src != LS.in_review:
            raise invalid_transition("Lesson", src, LS.published)
        p.require_any(C.lesson_publish)
        if ls.author_id == p.user.id:
            raise fc.code_err(ErrorCode.SELF_APPROVAL,
                              "The author cannot publish their own lesson (LL-4).",
                              "لا يمكن لمعد الدرس نشره.")  # fmt: skip
        if not ls.distribution_project_ids:
            raise fc.code_err(ErrorCode.NOT_DISTRIBUTED,
                              "Choose at least one project to distribute the lesson to.",
                              "اختر مشروعاً واحداً على الأقل لتوزيع الدرس.",
                              "distribution_project_ids")  # fmt: skip
        _complete(db, ls)
        publish(db, p, ls, at)
    else:
        sys_draft = src == LS.draft and ls.system_created
        if src != LS.published and not sys_draft:
            raise invalid_transition("Lesson", src, LS.archived)
        p.require_any(C.lesson_publish)
        if body.superseded_by_lesson_id is not None and not sys_draft:
            new = db.get(FuLesson, body.superseded_by_lesson_id)
            if new is None or new.status != LS.published or new.id == ls.id:
                raise validation_error("superseded_by_lesson_id", "Choose a Published lesson.")
            ls.superseded_by_id = new.id
            ls.status_reason = body.comment or f"Superseded by {new.lesson_no}"
        else:
            ls.status_reason = fc.reason(body.comment, 20, "comment")
        ls.status = LS.archived
        ls.archived_at = at
        for it in _items(db, ls.id):
            if it.status == DS.pending:
                it.status = DS.withdrawn
    ls.updated_at = at
    db.flush()
    fc.record(db, p, AuditAction.status_change, ET.lesson, ls, ls.source_project_id,
              before={"status": src.value}, details={"action": a.value})  # fmt: skip
    return to_read(db, p, ls)


def pairs(db: Session, project_id: uuid.UUID, day: date) -> list[uuid.UUID]:
    """DS-1: engagements with daily-return headcount > 0 on the project in the 14 days before."""
    W = WorkforceReturn  # noqa: N806
    rows = db.scalars(
        select(W.engagement_id)
        .where(
            W.project_id == project_id,
            W.headcount > 0,
            W.work_date >= day - timedelta(days=14),
            W.work_date < day,
        )
        .distinct()
    )
    return sorted({e for e in rows if e is not None}, key=lambda e: fc.eng_code(db, e) or "")


def bulletin(ls: FuLesson) -> tuple[str, str]:
    """DS-2 bulletin text (EN + AR); the PDF layout is parked for 6g."""
    kl_en = "\n".join(f"- {k.get('text_en')}" for k in ls.key_lessons or [])
    kl_ar = "\n".join(f"- {k.get('text_ar')}" for k in ls.key_lessons or [])
    en = f"{ls.lesson_no} {ls.title_en}\n{ls.what_happened_en}\nWhy: {ls.why_en}\n{kl_en}"
    ar = f"{ls.lesson_no} {ls.title_ar}\n{ls.what_happened_ar}\nلماذا: {ls.why_ar}\n{kl_ar}"
    return en, ar


def publish(db: Session, p: Principal | None, ls: FuLesson, at: datetime) -> list[FuDistribution]:
    """LL-4 / DS-1 / DS-2 / EF-1."""
    from app.services.followup import effectiveness  # noqa: PLC0415

    day = fc.local_day(at)
    removed = {(r["project_id"], r["engagement_id"]) for r in ls.removed_engagements or []}
    made: list[FuDistribution] = []
    for pid in ls.distribution_project_ids or []:
        due = day + timedelta(days=int(fc.cfg(db, pid)["lesson_ack_days"]))
        for eng in pairs(db, pid, day):
            if (str(pid), str(eng)) in removed:
                continue
            it = FuDistribution(lesson_id=ls.id, project_id=pid, engagement_id=eng,
                                ack_due_on=due, status=DS.pending, alerts_sent=[])  # fmt: skip
            db.add(it)
            made.append(it)
    ls.status = LS.published
    ls.published_at = at
    ls.approved_by_user_id = p.user.id if p is not None else None
    db.flush()
    effectiveness.schedule(db, ls, day)
    en_b, ar_b = bulletin(ls)
    for pid in ls.distribution_project_ids or []:
        staff = fc.officers(db, pid) | fc.site_engineers(db, pid, None)
        fc.send(db, staff, NotificationKind.lesson_published,
                f"Lesson {ls.lesson_no} published: {ls.title_en}",
                f"نُشر الدرس {ls.lesson_no}: {ls.title_ar}", pid, ET.lesson, ls.id)  # fmt: skip
    for it in made:
        fc.send(db, fc.reps(db, it.project_id, it.engagement_id), NotificationKind.lesson_published,
                f"Lesson {ls.lesson_no} for {fc.eng_code(db, it.engagement_id)}: brief your "
                f"crews and acknowledge by {it.ack_due_on.isoformat()}.\n{en_b}",
                f"الدرس {ls.lesson_no}: يرجى التوعية والإقرار قبل {it.ack_due_on.isoformat()}.\n"
                f"{ar_b}", it.project_id, ET.lesson_distribution, it.id, email=True)  # fmt: skip
    return made


# ---- distribution and acknowledgement (DS) -------------------------------------------------------


def item_read(db: Session, it: FuDistribution, today: date | None = None) -> FuDistributionRead:
    ls = db.get(FuLesson, it.lesson_id)
    d = today or fc.local_day()
    return FuDistributionRead(
        id=it.id, lesson_id=it.lesson_id, lesson_no=ls.lesson_no if ls else "",
        project_id=it.project_id, project_code=fc.pcode(db, it.project_id),
        engagement_id=it.engagement_id, engagement_code=fc.eng_code(db, it.engagement_id),
        ack_due_on=it.ack_due_on, acknowledged_by=fc.user_ref(db, it.acknowledged_by_user_id),
        acknowledged_at=it.acknowledged_at, response=it.response, reason=it.reason,
        on_behalf_note=it.on_behalf_note, status=it.status,
        overdue=it.status == DS.pending and d > it.ack_due_on,
    )  # fmt: skip


def _item_visible(p: Principal, it: FuDistribution) -> bool:
    g = p.grant(it.project_id, C.lesson_library_view)
    if g is None:
        return False
    g2 = p.grant(it.project_id, C.lesson_acknowledge) or p.grant(it.project_id, C.followup_view)
    return g2 is None or g2.covers_engagement(it.engagement_id)


def distribution(db: Session, p: Principal, lesson_id: uuid.UUID) -> FuDistributionList:
    ls = _get(db, p, lesson_id)
    return FuDistributionList(
        items=[item_read(db, i) for i in _items(db, ls.id) if _item_visible(p, i)]
    )


def project_distribution(
    db: Session, p: Principal, project_id: uuid.UUID, statuses: list[DS] | None
) -> FuDistributionList:
    fc.project(db, p, project_id)
    fc.need(p, project_id, C.lesson_library_view, write=False)
    stmt = select(FuDistribution).where(FuDistribution.project_id == project_id)
    if statuses:
        stmt = stmt.where(FuDistribution.status.in_(statuses))
    rows = db.scalars(stmt.order_by(FuDistribution.ack_due_on, FuDistribution.created_at))
    return FuDistributionList(items=[item_read(db, i) for i in rows if _item_visible(p, i)])


def acknowledge(
    db: Session, p: Principal, item_id: uuid.UUID, body: FuAckRequest
) -> FuDistributionRead:
    it = db.get(FuDistribution, item_id)
    if it is None or not p.can_see_project(it.project_id):
        raise not_found("Distribution item")
    g = p.require(it.project_id, C.lesson_acknowledge)
    if not g.covers_engagement(it.engagement_id):
        raise not_found("Distribution item")
    if it.status != DS.pending:
        raise invalid_transition("Distribution item", it.status, DS.acknowledged)
    sc = p.projects.get(it.project_id)
    is_rep = sc is not None and Role.contractor_hse_rep in sc.roles and g.engagement_ids is not None
    note = (body.on_behalf_note or "").strip()
    if not is_rep:
        active = fc.reps(db, it.project_id, it.engagement_id)
        if active or len(note) < 20:
            raise fc.code_err(
                ErrorCode.ON_BEHALF_NOTE_REQUIRED,
                "HSE staff acknowledge only for an engagement without an active Contractor HSE "
                "Rep, with a note of at least 20 characters (DS-3).",
                "يقر مسؤول السلامة فقط عن مقاول بلا ممثل سلامة نشط مع ملاحظة لا تقل عن 20 حرفاً.",
                "on_behalf_note",
                active_reps=len(active),
            )
    if body.response == FuAckResponse.not_applicable:
        it.reason = fc.reason(body.reason, 20)
        it.status = DS.not_applicable
    else:
        it.reason = (body.reason or "").strip() or None
        it.status = DS.acknowledged
    it.response = body.response
    it.on_behalf_note = note or None
    it.acknowledged_by_user_id = p.user.id
    it.acknowledged_at = now()
    db.flush()
    fc.record(db, p, AuditAction.status_change, ET.lesson_distribution, it, it.project_id,
              before={"status": DS.pending.value})  # fmt: skip
    return item_read(db, it)


# ---- links to 6d (LK) ----------------------------------------------------------------------------


def links(db: Session, p: Principal, lesson_id: uuid.UUID) -> FuLinkPage:
    ls = _get(db, p, lesson_id)
    rows = db.scalars(
        select(FuLessonLink)
        .where(FuLessonLink.lesson_id == ls.id)
        .order_by(FuLessonLink.created_at)
    )
    return FuLinkPage(items=[link_read(db, k) for k in rows])


def _latest_topic(db: Session, code: str) -> ToolboxTopic | None:
    return db.scalar(
        select(ToolboxTopic)
        .where(ToolboxTopic.topic_code == code, ToolboxTopic.status != VersionStatus.retired)
        .order_by(ToolboxTopic.version.desc())
        .limit(1)
    )


def _add_ref(t: ToolboxTopic, lesson_no: str) -> None:
    refs = list(t.linked_refs or [])
    if not any(r.get("kind") == "lesson" and r.get("ref") == lesson_no for r in refs):
        refs.append({"kind": LinkedRefKind.lesson.value, "ref": lesson_no})
        t.linked_refs = refs


def _next_topic_code(db: Session) -> str:
    codes = db.scalars(select(ToolboxTopic.topic_code).distinct())
    n = max((int(c[3:]) for c in codes if re.fullmatch(r"TT-\d{3}", c)), default=0)
    return f"TT-{n + 1:03d}"


def add_link(db: Session, p: Principal, lesson_id: uuid.UUID, body: FuLinkCreate) -> FuLinkRead:
    ls = _get(db, p, lesson_id)
    if ls.source_project_id is not None:
        p.require(ls.source_project_id, C.lesson_draft)
    else:
        p.require_any(C.lesson_draft)
    k = FuLessonLink(lesson_id=ls.id, kind=body.kind, project_id=body.project_id)
    if body.kind == FuLinkKind.topic:
        if body.ref:
            t = _latest_topic(db, body.ref)
            if t is None:
                raise validation_error("ref", "Unknown 6d topic code.")
            _add_ref(t, ls.lesson_no)
        else:
            t = ToolboxTopic(
                topic_code=_next_topic_code(db), version=1,
                category=body.topic_category or TopicCategory.general,
                title_en=(ls.title_en or ls.lesson_no)[:150], title_ar=(ls.title_ar or "")[:150],
                key_points_en=[x.get("text_en") for x in ls.key_lessons or [] if x.get("text_en")],
                key_points_ar=[x.get("text_ar") for x in ls.key_lessons or [] if x.get("text_ar")],
                translations=[], linked_refs=[{"kind": "lesson", "ref": ls.lesson_no}],
                authored_by_user_id=p.user.id, status=VersionStatus.draft,
                created_by_user_id=p.user.id, alerts_sent=[],
            )  # fmt: skip
            db.add(t)
            db.flush()
        k.ref = t.topic_code
    elif body.kind == FuLinkKind.campaign:
        k.ref = _campaign(db, p, ls, body)
    else:
        if not body.ref:
            raise validation_error("ref", "Give the template code.")
        if db.scalar(select(ChecklistTemplate.id).where(
                ChecklistTemplate.template_code == body.ref).limit(1)) is None:  # fmt: skip
            raise validation_error("ref", "Unknown 6d template code.")
        if not ((body.proposed_text_en or "").strip() or (body.proposed_text_ar or "").strip()):
            raise validation_error("proposed_text_en", "Write the proposed item text.")
        k.ref = body.ref
        k.item_code = body.item_code
        k.proposed_text_en = body.proposed_text_en
        k.proposed_text_ar = body.proposed_text_ar
        k.status = FuChangeStatus.open
    db.add(k)
    db.flush()
    fc.record(db, p, AuditAction.create, ET.lesson_link, k, ls.source_project_id,
              details={"lesson_no": ls.lesson_no, "kind": k.kind.value, "ref": k.ref})  # fmt: skip
    return link_read(db, k)


def _campaign(db: Session, p: Principal, ls: FuLesson, body: FuLinkCreate) -> str:
    from app.schemas.field import CampaignCreate  # noqa: PLC0415
    from app.services.field import campaigns  # noqa: PLC0415

    if body.project_id is None or not body.ref:
        raise validation_error("project_id", "Give the project and the 6d topic code.")
    t = db.scalar(
        select(ToolboxTopic).where(
            ToolboxTopic.topic_code == body.ref, ToolboxTopic.status == VersionStatus.published
        )
    )
    if t is None:
        raise validation_error("ref", "Choose a Published 6d topic.")
    sites = list(db.scalars(select(Site.id).where(Site.project_id == body.project_id)))
    msg_en = "; ".join(x.get("text_en") or "" for x in ls.key_lessons or [])[:1000]
    msg_ar = "; ".join(x.get("text_ar") or "" for x in ls.key_lessons or [])[:1000]
    c = campaigns.create_campaign(
        db, p, body.project_id,
        CampaignCreate(topic_id=t.id, reason=CampaignReason.lesson, reason_ref=ls.lesson_no,
                       message_en=msg_en or ls.title_en, message_ar=msg_ar or ls.title_ar,
                       site_ids=sites),
    )  # fmt: skip
    return c.campaign_no


def lesson_published_for(db: Session, p: Principal, lesson_no: str | None) -> None:
    """LK-2: a 6d campaign with reason `lesson` needs a Published lesson the issuer can see."""
    ls = db.scalar(select(FuLesson).where(FuLesson.lesson_no == (lesson_no or "")))
    if ls is None or ls.status != LS.published or not p.has_any(C.lesson_library_view):
        raise fc.code_err(ErrorCode.LESSON_NOT_PUBLISHED,
                          "Reason `lesson` needs a Published lesson number (LK-2).",
                          "يتطلب السبب «درس» رقم درس منشور.", "reason_ref")  # fmt: skip


def change_requests(db: Session, p: Principal, template_code: str | None) -> FuLinkPage:
    if not (p.has_any(C.field_library_author) or p.has_any(C.field_library_publish)):
        raise forbidden_error()
    stmt = select(FuLessonLink).where(FuLessonLink.kind == FuLinkKind.template_change)
    if template_code:
        stmt = stmt.where(FuLessonLink.ref == template_code)
    rows = db.scalars(stmt.order_by(FuLessonLink.created_at))
    return FuLinkPage(items=[link_read(db, k) for k in rows])


def reject_link(db: Session, p: Principal, link_id: uuid.UUID, body: FuLinkDecision) -> FuLinkRead:
    p.require_any(C.field_library_publish)
    k = db.get(FuLessonLink, link_id)
    if k is None or k.kind != FuLinkKind.template_change:
        raise not_found("Change request")
    if k.status != FuChangeStatus.open:
        raise invalid_transition("Change request", k.status, FuChangeStatus.rejected)
    k.status = FuChangeStatus.rejected
    k.reject_reason = fc.reason(body.reason, 20)
    k.decided_by_user_id = p.user.id
    k.decided_at = now()
    db.flush()
    fc.record(db, p, AuditAction.status_change, ET.lesson_link, k, None,
              before={"status": "open"})  # fmt: skip
    return link_read(db, k)


def adopt_on_publish(
    db: Session, template_code: str, version: int, change_note: str | None
) -> None:
    """LK-3: publishing a 6d version whose change note names the lesson no. adopts its requests."""
    if not change_note:
        return
    for k in db.scalars(
        select(FuLessonLink).where(
            FuLessonLink.kind == FuLinkKind.template_change,
            FuLessonLink.ref == template_code,
            FuLessonLink.status == FuChangeStatus.open,
        )
    ):
        ls = db.get(FuLesson, k.lesson_id)
        if ls is not None and ls.lesson_no in change_note:
            k.status = FuChangeStatus.adopted
            k.adopted_version = version
            k.decided_at = now()


def suggested_topics(db: Session, project_id: uuid.UUID, today: date) -> list[tuple[str, str]]:
    """LK-4 (TBT-9 step 1b): (topic code, lesson no.) for lessons published to the project in the
    last 30 days, newest first."""
    since = today - timedelta(days=30)
    out: list[tuple[str, str]] = []
    for ls in db.scalars(
        select(FuLesson)
        .where(FuLesson.status == LS.published)
        .order_by(FuLesson.published_at.desc())
    ):
        if project_id not in (ls.distribution_project_ids or []) or ls.published_at is None:
            continue
        if fc.local_day(ls.published_at) < since:
            continue
        for k in db.scalars(
            select(FuLessonLink).where(
                FuLessonLink.lesson_id == ls.id, FuLessonLink.kind == FuLinkKind.topic
            )
        ):
            out.append((k.ref, ls.lesson_no))
    return out


# ---- similar lessons (LL-6) ----------------------------------------------------------------------


def similar(db: Session, p: Principal, incident_id: uuid.UUID) -> FuSimilarLessons:
    from app.services import incidents  # noqa: PLC0415

    inc = incidents.get_incident(db, p, incident_id)
    return FuSimilarLessons(items=[list_item(x, db) for x in similar_for(db, inc)])


def similar_for(db: Session, inc: Incident) -> list[FuLesson]:
    mechs = {
        c.mechanism.value
        for c in db.scalars(select(InjuryCase).where(InjuryCase.incident_id == inc.id))
    }
    inv = db.get(Investigation, inc.id)
    rcs = {str(r.get("code")) for r in (inv.root_causes if inv else None) or []}
    scored: list[tuple[int, datetime, FuLesson]] = []
    for ls in db.scalars(select(FuLesson).where(FuLesson.status == LS.published)):
        if ls.incident_id == inc.id:
            continue
        a = ls.applicability or {}
        s = 0
        if inc.activity and inc.activity.value in a.get("activities", []):
            s += 1
        if (mechs & set(a.get("mechanisms", []))) or (
            inc.do_category and inc.do_category.value in a.get("do_categories", [])
        ):
            s += 1
        if rcs & set(ls.root_cause_codes or []):
            s += 1
        if s:
            scored.append((s, ls.published_at or ls.created_at, ls))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [x[2] for x in scored[:3]]


# ---- jobs (LL-1 alerts, DS-4) --------------------------------------------------------------------


def daily(db: Session, today: date) -> None:
    for ls in db.scalars(
        select(FuLesson).where(
            FuLesson.status.in_([LS.draft, LS.in_review]),
            FuLesson.required.is_(True),
            FuLesson.publish_due_on.is_not(None),
        )
    ):
        due = ls.publish_due_on
        assert due is not None  # noqa: S101
        pid = ls.source_project_id
        who = ({ls.author_id} if ls.author_id else set()) | fc.managers(db)
        if pid:
            who |= fc.officers(db, pid)
        if due - timedelta(days=3) <= today <= due and fc.once(db, f"fu:lpd:{ls.id}:pre"):
            fc.send(db, who, NotificationKind.lesson_publish_due,
                    f"Lesson {ls.lesson_no} is due for publication on {due.isoformat()}.",
                    f"موعد نشر الدرس {ls.lesson_no} هو {due.isoformat()}.", pid, ET.lesson,
                    ls.id, email=True)  # fmt: skip
        if today > due and fc.once(db, f"fu:lpd:{ls.id}:over"):
            fc.send(db, who, NotificationKind.lesson_publish_due,
                    f"Lesson {ls.lesson_no} is past its publication date {due.isoformat()}.",
                    f"تأخر نشر الدرس {ls.lesson_no} عن {due.isoformat()}.", pid, ET.lesson,
                    ls.id, email=True)  # fmt: skip
    for it in db.scalars(select(FuDistribution).where(FuDistribution.status == DS.pending)):
        ack_alerts(db, it, today)


def ack_alerts(db: Session, it: FuDistribution, today: date) -> None:
    """DS-4: due − 2 days to the reps; the day after due to the reps and the HSE Officers; then
    weekly while pending."""
    ls = db.get(FuLesson, it.lesson_id)
    no = ls.lesson_no if ls else ""
    ec = fc.eng_code(db, it.engagement_id)
    rs = fc.reps(db, it.project_id, it.engagement_id)
    due = it.ack_due_on
    if due - timedelta(days=2) <= today <= due and fc.once(db, f"fu:ack:{it.id}:pre"):
        fc.send(db, rs, NotificationKind.lesson_ack_due,
                f"Acknowledge lesson {no} for {ec} by {due.isoformat()}.",
                f"يرجى الإقرار بالدرس {no} قبل {due.isoformat()}.", it.project_id,
                ET.lesson_distribution, it.id, email=True)  # fmt: skip
    if today > due:
        week = (today - due - timedelta(days=1)).days // 7
        if fc.once(db, f"fu:ack:{it.id}:over:{week}"):
            fc.send(db, rs | fc.officers(db, it.project_id), NotificationKind.lesson_ack_due,
                    f"Lesson {no} acknowledgement for {ec} is overdue (due {due.isoformat()}).",
                    f"تأخر الإقرار بالدرس {no} للمقاول {ec}.", it.project_id,
                    ET.lesson_distribution, it.id, email=True)  # fmt: skip


def corrective_for(db: Session, lesson: FuLesson) -> list[CorrectiveAction]:
    if lesson.incident_id is None:
        return []
    from app.services.incidents import linked_cas  # noqa: PLC0415

    return list(linked_cas(db, lesson.incident_id))


def active_incident(inc: Incident) -> bool:
    return inc.status not in (IncidentStatus.voided, IncidentStatus.draft)
