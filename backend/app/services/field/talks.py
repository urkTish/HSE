"""Toolbox talks (spec 6d-field-assurance §3.11, §3.12, §4.6, TBT-1…TBT-10, P6d-4, P6d-5):
idempotent offline-tolerant recording with named attendance (card scan or list, signatures),
the language check, evidence rules, adding / removing rows until Locked, void, the register and
suggested topics. Card scans never write gate logs or run the access eligibility check."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, QrKind, QrTokenStatus
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.field_enums import (
    AttendanceMethod,
    CampaignStatus,
    LinkedRefKind,
    SuggestionSource,
    TalkStatus,
    UnderstoodLanguage,
    VersionStatus,
)
from app.core.hse_enums import AttachmentOwner
from app.models import (
    BriefingCampaign,
    Deployment,
    FieldFinding,
    Incident,
    Observation,
    Project,
    QrToken,
    Site,
    TalkAttendance,
    ToolboxTalk,
    ToolboxTopic,
    User,
    Worker,
    Zone,
)
from app.schemas.field import (
    AttendanceAdd,
    AttendanceInput,
    AttendanceRowRead,
    FieldVoid,
    RejectedRow,
    SuggestionList,
    SuggestionRead,
    TalkCreate,
    TalkPage,
    TalkRead,
    TalkTopicRead,
)
from app.schemas.hse_common import ApiWarning
from app.services.access import common as acommon
from app.services.common import ensure_open, invalid_transition, paginate
from app.services.field import campaigns as cmp
from app.services.field import common as fc
from app.services.field.execution import check_times, delay_min
from app.services.hse_common import Refs, make_ref
from app.services.permissions import Grant, Principal, forbidden_error

C = Capability
TS = TalkStatus
UL = UnderstoodLanguage


def _w(code: str, en: str, ar: str, fld: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": en, "message_ar": ar, "field": fld}


def locks_at(db: Session, t: ToolboxTalk) -> Any:
    return t.delivered_at + timedelta(hours=int(fc.cfg(db, t.project_id)["tbt_edit_window_hours"]))


def is_locked(db: Session, t: ToolboxTalk) -> bool:
    return t.status == TS.locked or now() >= locks_at(db, t)


# ---- reads ---------------------------------------------------------------------------------------


def talk_read(db: Session, p: Principal | None, t: ToolboxTalk) -> TalkRead:
    rows = list(
        db.scalars(
            select(TalkAttendance)
            .where(TalkAttendance.talk_id == t.id)
            .order_by(TalkAttendance.created_at, TalkAttendance.id)
        )
    )
    refs = Refs(db).load(
        sites=[t.site_id],
        zones=list(t.zone_ids or []),
        engs=[t.host_engagement_id, *[r.engagement_id for r in rows]],
        users=[t.recorded_by_user_id, t.presenter_user_id],
    )
    names_g = p.grant(t.project_id, C.toolbox_names_view) if p is not None else None
    viewer = p is not None and fc.is_viewer(p, t.project_id)
    deps = {
        d.id: (d, w)
        for d, w in db.execute(
            select(Deployment, Worker)
            .join(Worker, Worker.id == Deployment.worker_id)
            .where(Deployment.id.in_([r.deployment_id for r in rows]))
        ).all()
    }
    out_rows = []
    for r in rows:
        see = (
            names_g is not None
            and names_g.covers_site(t.site_id)
            and (names_g.engagement_ids is None or names_g.covers_engagement(r.engagement_id))
        )
        dw = deps.get(r.deployment_id)
        w = dw[1] if dw else None
        out_rows.append(
            AttendanceRowRead(
                id=r.id,
                deployment_id=r.deployment_id if see else None,
                worker_no=w.worker_no if see and w else None,
                name_en=w.full_name_en if see and w else None,
                name_ar=w.full_name_ar if see and w else None,
                engagement=refs.eng(r.engagement_id),
                method=r.method,
                signed=r.signature_id is not None,
                understood_language=r.understood_language,
                counted_person_type=r.counted_person_type,
            )
        )
    presenter: str | None = None
    if t.presenter_user_id:
        u = refs.user(t.presenter_user_id)
        presenter = u.full_name_en if u else None
    elif t.presenter_deployment_id:
        d = db.get(Deployment, t.presenter_deployment_id)
        wk = db.get(Worker, d.worker_id) if d else None
        presenter = wk.full_name_en if wk else None
    camp = db.get(BriefingCampaign, t.campaign_id) if t.campaign_id else None
    site = refs.site(t.site_id)
    assert site is not None  # noqa: S101
    return TalkRead(
        id=t.id,
        talk_no=t.talk_no,
        project_id=t.project_id,
        site=site,
        zones=[z for z in (refs.zone(x) for x in t.zone_ids or []) if z is not None],
        host_engagement=refs.eng(t.host_engagement_id),
        shift=t.shift,
        delivered_at=t.delivered_at,
        duration_minutes=t.duration_minutes,
        presenter_name=presenter if not viewer else None,
        recorded_by=refs.user(t.recorded_by_user_id) if not viewer else None,
        topics=[
            TalkTopicRead(
                topic_id=uuid.UUID(x["topic_id"]) if x.get("topic_id") else None,
                topic_code=x.get("topic_code"),
                version=x.get("version"),
                title_en=x.get("title_en") or "",
                title_ar=x.get("title_ar") or "",
                category=x.get("category"),
            )
            for x in t.topics or []
        ],
        language=t.language,
        interpreter_languages=list(t.interpreter_languages or []),
        campaign_id=t.campaign_id,
        campaign_no=camp.campaign_no if camp else None,
        attendance=out_rows,
        named_count=len(rows),
        briefed_count=sum(1 for r in rows if r.understood_language != UL.none),
        unnamed_count=t.unnamed_count,
        sheet_photo_ids=[] if viewer else list(t.sheet_photo_ids or []),
        questions_raised=t.questions_raised,
        received_at=t.received_at,
        offline_delay_min=t.offline_delay_min,
        recorded_offline=t.offline_delay_min is not None,
        rejected_rows=[RejectedRow(**x) for x in t.rejected_rows or []],
        warnings=[ApiWarning(**x) for x in t.warnings or []],
        locks_at=locks_at(db, t),
        status=TS.locked if t.status == TS.delivered and is_locked(db, t) else t.status,
        status_reason=t.status_reason,
    )


def _get(db: Session, p: Principal, talk_id: uuid.UUID) -> ToolboxTalk:
    t = db.get(ToolboxTalk, talk_id)
    if t is None or not p.can_see_project(t.project_id):
        raise not_found("Toolbox talk")
    g = p.grant(t.project_id, C.field_view)
    if not fc.in_scope(g, t.site_id, t.host_engagement_id) and t.recorded_by_user_id != p.user.id:
        raise not_found("Toolbox talk")
    return t


def read_talk(db: Session, p: Principal, talk_id: uuid.UUID) -> TalkRead:
    return talk_read(db, p, _get(db, p, talk_id))


def list_talks(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None,
    host: uuid.UUID | None,
    statuses: list[TalkStatus] | None,
    date_from: date | None,
    date_to: date | None,
    topic_code: str | None,
    page: int,
    page_size: int,
) -> TalkPage:
    fc.project(db, p, project_id)
    g = fc.view_grant(p, project_id)
    T = ToolboxTalk  # noqa: N806
    stmt = select(T).where(T.project_id == project_id)
    if g.site_ids is not None:
        stmt = stmt.where(T.site_id.in_(g.site_ids) if g.site_ids else false())
    if g.engagement_ids is not None:
        engs = list(g.engagement_ids)
        stmt = stmt.where(T.host_engagement_id.in_(engs) if engs else false())
    if site_id:
        stmt = stmt.where(T.site_id == site_id)
    if host:
        stmt = stmt.where(T.host_engagement_id == host)
    if statuses:
        stmt = stmt.where(T.status.in_(statuses))
    if date_from:
        stmt = stmt.where(T.delivered_date >= date_from)
    if date_to:
        stmt = stmt.where(T.delivered_date <= date_to)
    if topic_code:
        stmt = stmt.where(T.topic_codes.contains([topic_code]))
    items, total = paginate(db, stmt.order_by(T.delivered_at.desc()), page, page_size)
    return TalkPage(
        items=[talk_read(db, p, t) for t in items], total=total, page=page, page_size=page_size
    )


# ---- attendance (TBT-5…TBT-7) --------------------------------------------------------------------


def _mobilised(dep: Deployment, project_id: uuid.UUID, day: date) -> bool:
    if dep.project_id != project_id or dep.status == DeploymentStatus.pending_induction:
        return False
    if dep.mobilised_on > day:
        return False
    return dep.status == DeploymentStatus.mobilised or (
        dep.demobilised_on is not None and dep.demobilised_on >= day
    )


def _token_dep(db: Session, project_id: uuid.UUID, token: str) -> Deployment | None:
    m = acommon.QR_RE.match(token.strip())
    if m is None or m.group(1) != QrKind.AC.value:
        return None
    q = db.scalar(select(QrToken).where(QrToken.token == m.group(2), QrToken.kind == QrKind.AC))
    if q is None or q.project_id != project_id or q.status != QrTokenStatus.active:
        return None
    return db.get(Deployment, q.subject_id)


def _rows(
    db: Session,
    p: Principal,
    t: ToolboxTalk,
    rows: list[AttendanceInput],
    existing: set[uuid.UUID],
    base: int = 0,
) -> tuple[list[TalkAttendance], list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate and build attendance rows; unknown tokens are rejected per row (TOKEN_UNKNOWN)."""
    day = t.delivered_date
    seen = set(existing)
    out: list[TalkAttendance] = []
    rejected: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for i, x in enumerate(rows):
        fld = f"attendance[{i + base}]"
        dep: Deployment | None = None
        if x.scanned_token:
            dep = _token_dep(db, t.project_id, x.scanned_token)
            if dep is None:  # the token is resolved and then dropped (never stored)
                rejected.append({"code": "TOKEN_UNKNOWN", "index": i + base,
                                 "message": "Unknown or revoked access card: row not saved.",
                                 "message_ar": "بطاقة دخول غير معروفة أو ملغاة."})  # fmt: skip
                continue
        elif x.deployment_id:
            dep = db.get(Deployment, x.deployment_id)
            if dep is None or dep.project_id != t.project_id:
                raise validation_error(f"{fld}.deployment_id", "Unknown deployment.")
        else:
            raise validation_error(fld, "Scan the card or pick the worker.")
        assert dep is not None  # noqa: S101
        if not _mobilised(dep, t.project_id, day):
            raise fc.err(422, ErrorCode.WORKER_NOT_MOBILISED,
                         "The worker is not mobilised on the project at the talk time (TBT-5).",
                         "العامل غير معبأ في المشروع وقت الاجتماع.", field=fld)  # fmt: skip
        if dep.id in seen:
            raise fc.err(422, ErrorCode.DUPLICATE_ATTENDEE, "The worker is already on this talk.",
                         "العامل مسجل في هذا الاجتماع.", field=fld)  # fmt: skip
        seen.add(dep.id)
        w = db.get(Worker, dep.worker_id)
        assert w is not None  # noqa: S101
        lang = w.primary_language.value
        if lang == t.language:
            ul = UL.talk_language
        elif lang in (t.interpreter_languages or []):
            ul = UL.interpreter
        else:
            ul = UL.none
            warnings.append(_w("LANGUAGE_MISMATCH",
                               f"{w.worker_no} may not understand the talk language (TBT-6).",
                               "قد لا يفهم العامل لغة الاجتماع.", fld))  # fmt: skip
        sig_id = None
        if x.signature is not None:
            sig_id = fc.store_photos(db, AttachmentOwner.toolbox_signature, t.id, t.project_id,
                                     [x.signature], p.user.id, f"{fld}.signature")[0]  # fmt: skip
        out.append(
            TalkAttendance(
                id=uuid.uuid4(),
                talk_id=t.id,
                deployment_id=dep.id,
                engagement_id=dep.engagement_id,
                method=x.method,
                signature_id=sig_id,
                understood_language=ul,
                counted_person_type=w.person_type.value,
                created_at=now(),
            )
        )
    return out, rejected, warnings


def _evidence(rows: list[TalkAttendance], unnamed: int, sheets: int) -> None:
    """TBT-7."""
    unproven = any(r.method != AttendanceMethod.card_scan and r.signature_id is None for r in rows)
    if (unproven or unnamed > 0) and sheets == 0:
        raise fc.err(422, ErrorCode.ATTENDANCE_EVIDENCE_REQUIRED,
                     "Each named row needs a card scan or signature, or attach the sheet photo "
                     "(TBT-7).", "أرفق صورة كشف الحضور أو توقيع كل عامل.",
                     field="sheet_photos")  # fmt: skip


def _scope(p: Principal, project_id: uuid.UUID, site_id: uuid.UUID, host: uuid.UUID) -> Grant:
    """TBT-3: 198 for the host engagement (C / C1) or the site (S)."""
    g = p.require(project_id, C.toolbox_record)
    if not fc.in_scope(g, site_id, host):
        raise forbidden_error("The talk is outside your scope (TBT-3).")
    return g


def create_talk(db: Session, p: Principal, project_id: uuid.UUID, body: TalkCreate) -> TalkRead:
    proj = fc.project(db, p, project_id)
    prior = db.scalar(
        select(ToolboxTalk).where(
            ToolboxTalk.project_id == project_id, ToolboxTalk.client_uuid == body.client_uuid
        )
    )
    if prior is not None:
        return talk_read(db, p, prior)
    ensure_open(proj)
    _scope(p, project_id, body.site_id, body.host_engagement_id)
    received = now()
    check_times(db, p, proj, body.delivered_at, received, "delivered_at")
    site = db.get(Site, body.site_id)
    if site is None or site.project_id != project_id:
        raise validation_error("site_id", "A site of the project.")
    for z in body.zone_ids:
        zz = db.get(Zone, z)
        if zz is None or zz.site_id != site.id:
            raise validation_error("zone_ids", "Zones of the site.")
    from app.services.hse_common import check_engagement  # noqa: PLC0415

    check_engagement(db, proj, body.host_engagement_id, "host_engagement_id")
    if not 5 <= body.duration_minutes <= 120:
        raise validation_error("duration_minutes", "5–120 minutes (TBT-4).")
    warnings: list[dict[str, Any]] = []
    cfg = fc.cfg(db, project_id)
    if body.duration_minutes < int(cfg["tbt_min_minutes"]):
        warnings.append(_w("TBT_SHORT", f"Shorter than {cfg['tbt_min_minutes']} minutes (TBT-4).",
                           "مدة الاجتماع أقل من الحد الأدنى.", "duration_minutes"))  # fmt: skip
    day = fc.local_day(body.delivered_at)
    if body.presenter_user_id is None and body.presenter_deployment_id is None:
        raise validation_error("presenter_user_id", "Name the presenter.")
    if body.presenter_user_id is not None and db.get(User, body.presenter_user_id) is None:
        raise validation_error("presenter_user_id", "Unknown user.")
    if body.presenter_deployment_id is not None:
        pd = db.get(Deployment, body.presenter_deployment_id)
        if pd is None or not _mobilised(pd, project_id, day):
            raise validation_error("presenter_deployment_id", "A mobilised deployment.")
    topics, codes = _topics(db, body, warnings)
    if body.campaign_id is not None:
        c = db.get(BriefingCampaign, body.campaign_id)
        if (
            c is None
            or c.project_id != project_id
            or c.status != CampaignStatus.issued
            or c.topic_code not in codes
        ):
            raise validation_error("campaign_id", "An Issued campaign whose topic is in topics.")
    if fc.p18(body.questions_raised):
        warnings.append(_w("POSSIBLE_ID_NUMBER", "The text may contain an ID number (P1-8).",
                           "قد يحتوي النص على رقم هوية.", "questions_raised"))  # fmt: skip
    seq = fc.next_seq(db, ToolboxTalk, project_id, day.year)
    t = ToolboxTalk(
        talk_no=make_ref("TBT", proj.code, day.year, seq, 5),
        year=day.year,
        seq=seq,
        project_id=project_id,
        client_uuid=body.client_uuid,
        site_id=body.site_id,
        zone_ids=list(body.zone_ids),
        host_engagement_id=body.host_engagement_id,
        shift=body.shift,
        delivered_at=body.delivered_at,
        delivered_date=day,
        duration_minutes=body.duration_minutes,
        presenter_user_id=body.presenter_user_id,
        presenter_deployment_id=body.presenter_deployment_id,
        recorded_by_user_id=p.user.id,
        topics=topics,
        topic_codes=codes,
        language=body.language.value,
        interpreter_languages=[x.value for x in body.interpreter_languages],
        campaign_id=body.campaign_id,
        unnamed_count=body.unnamed_count,
        questions_raised=body.questions_raised,
        received_at=received,
        offline_delay_min=delay_min(body.delivered_at, received),
        status=TS.delivered,
        created_by_user_id=p.user.id,
    )
    db.add(t)
    db.flush()
    rows, rejected, w2 = _rows(db, p, t, body.attendance, set())
    _evidence(rows, body.unnamed_count, len(body.sheet_photos))
    t.sheet_photo_ids = fc.store_photos(db, AttachmentOwner.toolbox_sheet, t.id, project_id,
                                        body.sheet_photos, p.user.id, "sheet_photos")  # fmt: skip
    db.add_all(rows)
    t.rejected_rows = rejected
    t.warnings = warnings + w2
    db.flush()
    fc.record(db, p, AuditAction.create, EntityType.toolbox_talk, t, project_id,
              details={"rows": len(rows), "rejected": len(rejected)})  # fmt: skip
    return talk_read(db, p, t)


def _topics(
    db: Session, body: TalkCreate, warnings: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    out: list[dict[str, Any]] = []
    codes: list[str] = []
    for i, x in enumerate(body.topics):
        fld = f"topics[{i}]"
        if x.topic_id is not None:
            tp = db.get(ToolboxTopic, x.topic_id)
            if tp is None or tp.status not in (VersionStatus.published, VersionStatus.superseded):
                raise validation_error(fld, "A Published library topic.")
            if tp.review_due_on is not None and tp.review_due_on < fc.local_day():
                warnings.append(_w("TOPIC_REVIEW_OVERDUE", f"{tp.topic_code} is past its review "
                                   "date (TBT-2).", "انتهى موعد مراجعة الموضوع.", fld))  # fmt: skip
            out.append({"topic_id": str(tp.id), "topic_code": tp.topic_code,
                        "version": tp.version, "title_en": tp.title_en, "title_ar": tp.title_ar,
                        "category": tp.category.value})  # fmt: skip
            codes.append(tp.topic_code)
        else:
            if not ((x.free_title_en or "").strip() or (x.free_title_ar or "").strip()):
                raise validation_error(fld, "A library topic or a free title with a category.")
            if x.category is None:
                raise validation_error(f"{fld}.category", "Give the category of a free title.")
            out.append({"topic_id": None, "topic_code": None, "version": None,
                        "title_en": x.free_title_en or "", "title_ar": x.free_title_ar or "",
                        "category": x.category.value})  # fmt: skip
    return out, codes


def add_attendance(db: Session, p: Principal, talk_id: uuid.UUID, body: AttendanceAdd) -> TalkRead:
    t = _get(db, p, talk_id)
    ensure_open(fc.project(db, p, t.project_id))
    _scope(p, t.project_id, t.site_id, t.host_engagement_id)
    _not_locked(db, t)
    existing = set(
        db.scalars(select(TalkAttendance.deployment_id).where(TalkAttendance.talk_id == t.id))
    )
    rows, rejected, w2 = _rows(db, p, t, body.rows, existing, base=len(existing))
    _evidence(rows, 0, len(t.sheet_photo_ids or []))
    db.add_all(rows)
    t.rejected_rows = [*(t.rejected_rows or []), *rejected]
    t.warnings = [*(t.warnings or []), *w2]
    t.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.update, EntityType.toolbox_talk, t, t.project_id,
              details={"rows_added": len(rows)})  # fmt: skip
    return talk_read(db, p, t)


def _not_locked(db: Session, t: ToolboxTalk) -> None:
    if t.status == TS.voided:
        raise invalid_transition("Toolbox talk", t.status, "edited")
    if is_locked(db, t):
        raise fc.err(409, ErrorCode.TALK_LOCKED,
                     "The talk is locked: rows can no longer change (TBT-8).",
                     "الاجتماع مقفل ولا يمكن تعديل الحضور.")  # fmt: skip


def remove_attendance(db: Session, p: Principal, talk_id: uuid.UUID, row_id: uuid.UUID) -> TalkRead:
    t = _get(db, p, talk_id)
    ensure_open(fc.project(db, p, t.project_id))
    _scope(p, t.project_id, t.site_id, t.host_engagement_id)
    _not_locked(db, t)
    r = db.get(TalkAttendance, row_id)
    if r is None or r.talk_id != t.id:
        raise not_found("Attendance row")
    if r.signature_id:
        from app.models import Attachment  # noqa: PLC0415
        from app.services import attachments  # noqa: PLC0415

        a = db.get(Attachment, r.signature_id)
        if a is not None:
            attachments.erase(db, a)
    db.delete(r)
    t.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.update, EntityType.toolbox_talk, t, t.project_id,
              details={"row_removed": str(row_id)})  # fmt: skip
    return talk_read(db, p, t)


def void_talk(db: Session, p: Principal, talk_id: uuid.UUID, body: FieldVoid) -> TalkRead:
    t = _get(db, p, talk_id)
    ensure_open(fc.project(db, p, t.project_id))
    p.require(t.project_id, C.field_void)
    why = fc.reason(body.reason, 20)
    if t.status == TS.voided:
        raise invalid_transition("Toolbox talk", t.status, TS.voided)
    before = {"status": t.status.value}
    t.status = TS.voided
    t.status_reason = why
    t.updated_at = now()
    db.flush()
    fc.record(db, p, AuditAction.status_change, EntityType.toolbox_talk, t, t.project_id,
              before=before, details={"reason": why})  # fmt: skip
    return talk_read(db, p, t)


def lock_due(db: Session, project_id: uuid.UUID) -> int:
    """§4.6 Delivered → Locked after tbt_edit_window_hours."""
    hours = int(fc.cfg(db, project_id)["tbt_edit_window_hours"])
    n = 0
    for t in db.scalars(
        select(ToolboxTalk).where(
            ToolboxTalk.project_id == project_id,
            ToolboxTalk.status == TS.delivered,
            ToolboxTalk.delivered_at <= now() - timedelta(hours=hours),
        )
    ):
        t.status = TS.locked
        n += 1
    db.flush()
    return n


# ---- suggestions (TBT-9) -------------------------------------------------------------------------


def suggestions(
    db: Session, p: Principal, project_id: uuid.UUID, site_id: uuid.UUID, host: uuid.UUID
) -> SuggestionList:
    fc.project(db, p, project_id)
    g = p.grant(project_id, C.toolbox_record) or fc.view_grant(p, project_id)
    if not fc.in_scope(g, site_id, host):
        raise forbidden_error()
    today = fc.local_day()
    since = today - timedelta(days=30)
    current = {
        t.topic_code: t
        for t in db.scalars(
            select(ToolboxTopic).where(ToolboxTopic.status == VersionStatus.published)
        )
    }

    def linked(kind: LinkedRefKind, ref: str) -> list[ToolboxTopic]:
        def hit(t: ToolboxTopic) -> bool:
            return any(
                x.get("kind") == kind.value and x.get("ref") == ref for x in t.linked_refs or []
            )

        return sorted((t for t in current.values() if hit(t)), key=lambda t: t.topic_code)

    picks: list[tuple[ToolboxTopic, SuggestionSource, str | None]] = []
    # (1) campaigns with an unmet pair for the host on the site, by due date
    for c in sorted(
        db.scalars(
            select(BriefingCampaign).where(
                BriefingCampaign.project_id == project_id,
                BriefingCampaign.status == CampaignStatus.issued,
            )
        ),
        key=lambda c: (c.due_date or today, c.campaign_no),
    ):
        unmet = any(
            s.engagement_id == host and s.site_id == site_id and s.met_on is None
            for s in cmp.pair_states(db, c)
        )
        if unmet and c.topic_code in current:
            picks.append((current[c.topic_code], SuggestionSource.campaign, c.campaign_no))
    # (2) topics linked to incidents of the project in the last 30 days, newest first
    for inc in db.scalars(
        select(Incident)
        .where(Incident.project_id == project_id, Incident.occurred_date >= since)
        .order_by(Incident.occurred_at.desc())
    ):
        for t in linked(LinkedRefKind.incident, inc.ref):
            picks.append((t, SuggestionSource.incident, inc.ref))
    # (3) the 3 most failed item codes of the host in the last 30 days
    F = FieldFinding  # noqa: N806
    top = db.execute(
        select(F.item_code, func.count())
        .where(
            F.project_id == project_id,
            F.engagement_id == host,
            F.item_code.is_not(None),
            F.voided.is_(False),
            F.completed_date >= since,
        )
        .group_by(F.item_code)
        .order_by(func.count().desc(), F.item_code)
        .limit(3)
    ).all()
    for code, _n in top:
        if code is None:
            continue
        for t in linked(LinkedRefKind.template_item, code):
            picks.append((t, SuggestionSource.failed_item, code))
    # (4) the 3 unsafe observation categories most recorded for the host in the last 30 days
    from app.kpi.data import SAFE_TYPES  # noqa: PLC0415

    O = Observation  # noqa: E741, N806
    cats = db.execute(
        select(O.category, func.count())
        .where(
            O.project_id == project_id,
            O.observed_engagement_id == host,
            O.observed_date >= since,
            O.obs_type.not_in(list(SAFE_TYPES)),
        )
        .group_by(O.category)
        .order_by(func.count().desc(), O.category)
        .limit(3)
    ).all()
    for cat, _n in cats:
        for t in sorted(current.values(), key=lambda t: t.topic_code):
            if t.category.value == cat.value:
                picks.append((t, SuggestionSource.observation_category, cat.value))
    recent = set()
    for codes in db.scalars(
        select(ToolboxTalk.topic_codes).where(
            ToolboxTalk.project_id == project_id,
            ToolboxTalk.site_id == site_id,
            ToolboxTalk.host_engagement_id == host,
            ToolboxTalk.status != TS.voided,
            ToolboxTalk.delivered_date >= today - timedelta(days=7),
        )
    ):
        recent |= set(codes or [])
    seen: set[str] = set()
    items: list[SuggestionRead] = []
    for t, src, ref_ in picks:
        if t.topic_code in seen:
            continue
        seen.add(t.topic_code)
        items.append(
            SuggestionRead(
                topic_id=t.id, topic_code=t.topic_code, version=t.version, title_en=t.title_en,
                title_ar=t.title_ar, category=t.category, source=src, reason_ref=ref_,
                delivered_recently=t.topic_code in recent,
            )
        )  # fmt: skip
    items.sort(key=lambda s: s.delivered_recently)  # stable: recent ones last
    return SuggestionList(items=items)


def project_of(db: Session, project_id: uuid.UUID) -> Project:
    pr = db.get(Project, project_id)
    assert pr is not None  # noqa: S101
    return pr
