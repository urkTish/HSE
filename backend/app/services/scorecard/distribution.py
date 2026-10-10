"""Distribution lists and the delivery log (spec 6g §3.7, DL-1…DL-5, P6g-3, P6g-6). Users get an
in-app notice and an email with a link; external members get an email naming the files of their
language (the outbox has no attachment column: the files are recorded on the delivery row,
DECISIONS D-224). Only de-identified aggregate packs go to external members."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, EntityType, Language, NotificationKind, Role
from app.core.errors import ErrorCode, validation_error
from app.core.scorecard_enums import (
    RpChannel,
    RpDeliveryStatus,
    RpLanguage,
    RpMemberKind,
    RpType,
)
from app.models import EmailMessage, RpDelivery, RpPack, RpRecipient, User
from app.schemas.scorecard import (
    RpDeliveryPage,
    RpDeliveryRead,
    RpDistributionList,
    RpDistributionUpdate,
    RpMemberRead,
)
from app.services.permissions import Principal, build_principal, forbidden_error
from app.services.scorecard import common as cm

C = cm.C
EMAIL_LIMIT = 20 * 1024 * 1024
EXTERNAL_TYPES = (RpType.MCR, RpType.OSHA300, RpType.HEAT)
CROSS_CONTRACTOR = (RpType.MCR, RpType.OSHA300, RpType.CPS)


def _scope_err(en: str) -> Exception:
    return cm.code_err(ErrorCode.RECIPIENT_SCOPE, en, "المستلم خارج النطاق المسموح.", "members")


def _members(db: Session, project_id: uuid.UUID, rt: RpType) -> list[RpRecipient]:
    return list(db.scalars(select(RpRecipient).where(RpRecipient.project_id == project_id,
                                                     RpRecipient.report_type == rt)
                           .order_by(RpRecipient.created_at)))  # fmt: skip


def _read(db: Session, m: RpRecipient) -> RpMemberRead:
    return RpMemberRead(
        id=m.id,
        kind=m.kind,
        user=cm.user_ref(db, m.user_id),
        display_name_en=m.display_name_en,
        display_name_ar=m.display_name_ar,
        organisation=m.organisation,
        email=m.email,
        language=m.language,
    )


def summary(db: Session, project_id: uuid.UUID, rt: RpType) -> str:
    """Organisations and roles for the MCR document control (RP-1 (0))."""
    out = []
    for m in _members(db, project_id, rt):
        if m.kind == RpMemberKind.external:
            out.append(f"{m.organisation or '—'} ({m.display_name_en or '—'})")
        else:
            roles = (
                sorted(r.value for r in cm.roles_on(db, m.user_id, project_id)) if m.user_id else []
            )
            out.append(", ".join(roles) or "user")
    return "; ".join(out) or "—"


def get_list(db: Session, p: Principal, project_id: uuid.UUID, rt: RpType) -> RpDistributionList:
    cm.project(db, p, project_id)
    if p.grant(project_id, C.report_pack_prepare) is None and not p.is_manager:
        raise forbidden_error()
    return RpDistributionList(
        project_id=project_id,
        report_type=rt,
        members=[_read(db, m) for m in _members(db, project_id, rt)],
    )


def _user_ok(db: Session, project_id: uuid.UUID, rt: RpType, uid: uuid.UUID) -> None:
    u = db.get(User, uid)
    if u is None:
        raise validation_error("members", "Unknown user.")
    q = build_principal(db, u, None)
    if not q.is_manager and q.grant(project_id, C.report_pack_view) is None:
        raise _scope_err("The user cannot view this report type on the project (DL-1).")
    if rt in CROSS_CONTRACTOR and not q.is_manager:
        roles = cm.roles_on(db, uid, project_id)
        if roles & {Role.contractor_hse_rep, Role.permit_receiver}:
            raise _scope_err("Contractor reps and permit receivers cannot receive packs that show "
                             "other contractors (DL-2).")  # fmt: skip
        if cm.is_viewer(q, project_id) and rt == RpType.CPS:
            raise _scope_err("The CPS is for the HSE Manager only.")


def put_list(
    db: Session, p: Principal, project_id: uuid.UUID, rt: RpType, body: RpDistributionUpdate
) -> RpDistributionList:
    cm.project(db, p, project_id)
    p.require(project_id, C.report_pack_issue)
    c = cm.cfg(db, project_id)
    new: list[RpRecipient] = []
    for i, m in enumerate(body.members):
        if m.kind == RpMemberKind.user:
            if m.user_id is None:
                raise validation_error(f"members[{i}].user_id", "Give the user.")
            _user_ok(db, project_id, rt, m.user_id)
            new.append(
                RpRecipient(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    report_type=rt,
                    kind=m.kind,
                    user_id=m.user_id,
                    language=m.language,
                )
            )
            continue
        email = str(m.email or "")
        domain = email.rsplit("@", 1)[-1].lower()
        if (rt not in EXTERNAL_TYPES or not c["external_distribution_enabled"]
                or domain not in [d.lower() for d in c["external_domains"]]):  # fmt: skip
            raise cm.code_err(ErrorCode.EXTERNAL_NOT_ALLOWED,
                              "External members need external distribution enabled, an allowed "
                              "domain and an aggregate report type (DL-3).",
                              "لا يُسمح بالإرسال الخارجي.", f"members[{i}].email")  # fmt: skip
        if not m.acknowledge_disclosure:
            raise validation_error(f"members[{i}].acknowledge_disclosure",
                                   "Confirm the contract allows disclosure (P6g-6).")  # fmt: skip
        if not (m.display_name_en or m.organisation):
            raise validation_error(f"members[{i}].display_name_en", "Name the role or person.")
        new.append(RpRecipient(id=uuid.uuid4(), project_id=project_id, report_type=rt,
                               kind=m.kind, display_name_en=m.display_name_en,
                               display_name_ar=m.display_name_ar, organisation=m.organisation,
                               email=email, language=m.language,
                               acknowledged_by_user_id=p.user.id))  # fmt: skip
    before = [_read(db, x).model_dump(mode="json") for x in _members(db, project_id, rt)]
    olds = _members(db, project_id, rt)
    if olds:  # the delivery log keeps its user / email; only the list link is dropped
        db.execute(update(RpDelivery).where(RpDelivery.recipient_id.in_([x.id for x in olds]))
                   .values(recipient_id=None))  # fmt: skip
    for old in olds:
        db.delete(old)
    db.flush()
    for x in new:
        db.add(x)
    db.flush()
    from app.services import audit  # noqa: PLC0415

    after = [_read(db, x).model_dump(mode="json") for x in new]
    audit.record(db, AuditAction.update, p.actor(project_id),
                 entity_type=EntityType.distribution_list, project_id=project_id,
                 details={"report_type": rt.value, "before": before, "after": after})  # fmt: skip
    return get_list(db, p, project_id, rt)


def _ext_files(pk: RpPack, lang: RpLanguage, no_xlsx: bool) -> list[dict[str, object]]:
    files = pk.files or {}
    keys = ["pdf_bilingual"] if "pdf_bilingual" in files else (
        ["pdf_en", "pdf_ar"] if lang == RpLanguage.both else [f"pdf_{lang.value}"])  # fmt: skip
    if not no_xlsx:
        keys.append("xlsx")
    return [files[k] for k in keys if k in files]


def precheck(db: Session, pk: RpPack, no_xlsx: bool) -> None:
    """P6g-3: a pack with names is never distributed; DL-4: attachments ≤ 20 MB (estimated from
    the previous revision's files when present; checked again after rendering)."""
    if pk.project_id is None:
        return
    members = _members(db, pk.project_id, pk.report_type)
    if pk.with_names and members:
        raise _scope_err("A pack with names is download-only and is never distributed (P6g-3).")


def distribute(db: Session, pk: RpPack, no_xlsx: bool = False) -> int:
    """DL-4 / DL-5 / RP-8 at Issue. Returns the number of delivery rows."""
    t = now()
    rows: list[RpDelivery] = []
    if pk.with_names:
        return 0
    subject_tail = (f" — Rev {pk.revision} supersedes Rev {pk.revision - 1} — {pk.reissue_reason}"
                    if pk.revision > 0 and pk.reissue_reason else "")  # fmt: skip
    subject = f"{pk.doc_no} Rev {pk.revision} issued{subject_tail}"[:300]
    users: set[uuid.UUID] = set()
    externals: list[RpRecipient] = []
    if pk.report_type == RpType.SCP and pk.engagement_id and pk.project_id:
        users |= cm.reps(db, pk.project_id, pk.engagement_id)
        # parent-tree reps see the card too (C scope over descendants)
        from app.services.scorecard import watch  # noqa: PLC0415

        users |= watch.audience(db, pk.project_id, pk.engagement_id) - (
            cm.officers(db, pk.project_id) | cm.managers(db))  # fmt: skip
    if pk.project_id:
        for m in _members(db, pk.project_id, pk.report_type):
            if m.kind == RpMemberKind.user and m.user_id:
                users.add(m.user_id)
            elif m.kind == RpMemberKind.external:
                externals.append(m)
    if externals:
        size = max(sum(int(str(f["size_bytes"])) for f in _ext_files(pk, m.language, no_xlsx))
                   for m in externals)  # fmt: skip
        if size > EMAIL_LIMIT:
            raise cm.code_err(ErrorCode.PACK_TOO_LARGE_FOR_EMAIL,
                              "The attachments exceed 20 MB: choose separate EN / AR files or "
                              "remove the XLSX for external members (DL-4).",
                              "المرفقات تتجاوز 20 ميجابايت.")  # fmt: skip
    if users:
        cm.send(db, users, NotificationKind.report_pack_issued, subject,
                f"صدرت {pk.doc_no} المراجعة {pk.revision}", pk.project_id, EntityType.report_pack,
                pk.id, email=True)  # fmt: skip
    for uid in sorted(users):
        rows.append(RpDelivery(id=uuid.uuid4(), pack_id=pk.id, user_id=uid,
                               channel=RpChannel.in_app, attachments=[], subject=subject,
                               status=RpDeliveryStatus.sent, sent_at=t))  # fmt: skip
    for m in externals:
        files = _ext_files(pk, m.language, no_xlsx)
        names = [str(f["file_name"]) for f in files]
        lang = Language.ar if m.language == RpLanguage.ar else Language.en
        db.add(EmailMessage(to_email=m.email or "", to_user_id=None, language=lang,
                            template="report_pack", subject=subject[:200],
                            body=f"{subject}\n\nAttached: {', '.join(names)}\n"
                                 "CONFIDENTIAL — aggregate HSE statistics."))  # fmt: skip
        rows.append(RpDelivery(id=uuid.uuid4(), pack_id=pk.id, recipient_id=m.id, email=m.email,
                               channel=RpChannel.email, attachments=names, subject=subject,
                               status=RpDeliveryStatus.sent, sent_at=t))  # fmt: skip
    for r in rows:
        db.add(r)
    db.flush()
    return len(rows)


def bounce(db: Session, delivery_id: uuid.UUID, error: str) -> None:
    """A bounce notice from the mail relay: the delivery is marked and the issuer alerted."""
    d = db.get(RpDelivery, delivery_id)
    if d is None:
        return
    d.status, d.error = RpDeliveryStatus.bounced, error[:500]
    pk = db.get(RpPack, d.pack_id)
    if pk is not None and pk.issued_by_user_id:
        cm.send(
            db,
            [pk.issued_by_user_id],
            NotificationKind.delivery_bounced,
            f"{pk.doc_no} Rev {pk.revision}: delivery to {d.email or 'a user'} bounced",
            f"تعذّر تسليم {pk.doc_no}",
            pk.project_id,
            EntityType.report_pack,
            pk.id,
        )
    db.flush()


def deliveries(
    db: Session, p: Principal, pack_id: uuid.UUID, page: int, size: int
) -> RpDeliveryPage:
    from app.services.scorecard import packs  # noqa: PLC0415

    pk = packs.get_pack(db, p, pack_id)
    staff = p.is_manager or (
        pk.project_id is not None and p.grant(pk.project_id, C.report_pack_prepare) is not None
    )
    if (
        pk.project_id
        and not staff
        and (p.grant(pk.project_id, C.report_pack_view) is None or cm.is_viewer(p, pk.project_id))
    ):
        raise forbidden_error()
    rows = list(db.scalars(select(RpDelivery).where(RpDelivery.pack_id == pk.id)
                           .order_by(RpDelivery.sent_at, RpDelivery.id)))  # fmt: skip
    if not staff:
        rows = [r for r in rows if r.user_id == p.user.id]

    def member(r: RpDelivery) -> str:
        if r.user_id:
            u = db.get(User, r.user_id)
            return u.full_name_en if u else "user"
        return r.email or "—"

    items = [RpDeliveryRead(id=r.id, pack_doc_no=pk.doc_no, revision=pk.revision, member=member(r),
                            channel=r.channel, attachments=list(r.attachments or []),
                            subject=r.subject, status=r.status, error=r.error, sent_at=r.sent_at)
             for r in rows[(page - 1) * size : page * size]]  # fmt: skip
    return RpDeliveryPage(items=items, total=len(rows), page=page, page_size=size)
