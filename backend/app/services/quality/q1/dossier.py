"""Handover dossier (spec 8-quality §B.7, Q-DOS-01…05, D-319): scope, sections from registry
`DOSSIER_SECTIONS` (Q1: itp, ir, punch, asbuilt; ncr when Q0 has not registered it; Q2 and Q4 add
theirs), compile (snapshot with every file's SHA-256, index PDFs EN / AR with the Hijri date, a ZIP
of the index and the referenced files), blockers per setting `dossier_blockers`, submit, accept /
return by the responsible person (`dossier.accept`) and revisions after acceptance.

A section provider returns items as dicts: {ref, title, revision, status, date, record_type,
record_id, link_path, files: [attachment ids]} and its blockers as `registry.Blocker` rows."""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, CapabilityScope, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.hijri import hijri_ar, hijri_en
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QNcrStatus, QRecordType, label
from app.core.quality.q1 import (
    DOSSIER_MAX_BYTES,
    IR_APPROVED,
    PUNCH_LIVE,
    Q1_SECTIONS,
    SECTION_LETTER,
    QAsbuiltStatus,
    QDossierStatus,
    QIrCommentStatus,
    QIrStatus,
    QItpStatus,
    QPointType,
    QPunchCategory,
    QPunchStatus,
    QVerifyingRecord,
)
from app.models import Attachment, Project, Zone
from app.models.quality import QNcr, QSystem
from app.models.quality.q1 import (
    QAsbuiltItem,
    QDossier,
    QIr,
    QIrComment,
    QIrRound,
    QItp,
    QItpPoint,
    QPunchItem,
)
from app.services import attachments, audit
from app.services.common import invalid_transition
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import links, rpm, signoff
from app.services.quality import numbering as qnum
from app.services.quality import registry as reg
from app.services.quality import settings as qs
from app.services.quality.q1 import common as q1c
from app.services.quality.q1 import holds
from app.services.scorecard import render

C = Capability
S = CapabilityScope
ST = QDossierStatus
RT = QRecordType.dossier
STEP = "accept"
Blocker = reg.Blocker


# ---- scope (Q-DOS-01) --------------------------------------------------------------------------


def in_scope(d: QDossier, zone_id: uuid.UUID | None, system_id: uuid.UUID | None) -> bool:
    return (zone_id is not None and zone_id in (d.zone_ids or [])) or (
        system_id is not None and system_id in (d.system_ids or [])
    )


def _scope_where(model: Any, d: QDossier) -> Any:
    conds = []
    if d.zone_ids:
        conds.append(model.zone_id.in_(list(d.zone_ids)))
    if d.system_ids and hasattr(model, "system_id"):
        conds.append(model.system_id.in_(list(d.system_ids)))
    if not conds:
        return model.id.is_(None)
    out = conds[0]
    for c in conds[1:]:
        out = out | c
    return out


def _files(db: Session, owner: AttachmentOwner, owner_id: uuid.UUID) -> list[str]:
    return [str(x) for x in q1c.attachment_ids(db, owner, owner_id)]


# ---- Q1 sections ---------------------------------------------------------------------------------


def _irs(db: Session, d: QDossier) -> list[QIr]:
    return list(
        db.scalars(
            select(QIr)
            .where(
                QIr.project_id == d.project_id,
                _scope_where(QIr, d),
                QIr.status.notin_([QIrStatus.draft, QIrStatus.cancelled]),
            )
            .order_by(QIr.ir_no)
        )
    )


def _itps(db: Session, d: QDossier) -> list[QItp]:
    fams = {ir.itp_family_id for ir in _irs(db, d)}
    for it in db.scalars(select(QItp).where(QItp.project_id == d.project_id)):
        if set(it.zone_ids or []) & set(d.zone_ids or []) or set(it.system_ids or []) & set(
            d.system_ids or []
        ):
            fams.add(it.family_id)
    out = []
    for fam in fams:
        revs = list(
            db.scalars(select(QItp).where(QItp.family_id == fam).order_by(QItp.revision.desc()))
        )
        cur = next((r for r in revs if r.status == QItpStatus.approved), None) or (
            revs[0] if revs else None
        )
        if cur is not None and cur.itp_no:
            out.append(cur)
    return sorted(out, key=lambda r: r.itp_no or "")


def itp_items(db: Session, d: QDossier) -> list[dict[str, Any]]:
    return [
        {
            "ref": f"{it.itp_no} Rev.{it.revision}",
            "title": it.title_en,
            "revision": it.revision,
            "status": it.status.value,
            "date": it.approved_at.date().isoformat() if it.approved_at else None,
            "record_type": "itp",
            "record_id": str(it.id),
            "link_path": f"/quality/itps/{it.id}",
            "files": _files(db, AttachmentOwner.q_itp, it.id),
        }
        for it in _itps(db, d)
    ]


def itp_blockers(db: Session, d: QDossier) -> list[Blocker]:
    """(a) an H or W point verified by IR with no approved IR at a key in scope used by any IR of
    that ITP."""
    out = []
    irs = _irs(db, d)
    for it in _itps(db, d):
        keys = sorted(
            {
                ir.location_key: ir.location_ref for ir in irs if ir.itp_family_id == it.family_id
            }.items()
        )
        pts = db.scalars(
            select(QItpPoint).where(
                QItpPoint.itp_id == it.id,
                QItpPoint.point_type.in_([QPointType.H, QPointType.W]),
                QItpPoint.verifying_record == QVerifyingRecord.ir,
            )
        )
        for pt in pts:
            for key, ref in keys:
                if not holds._releasing(db, it.family_id, key, pt.seq, pt.point_type):
                    out.append(
                        Blocker(
                            "ITP_POINT_OPEN",
                            f"{it.itp_no} point {pt.seq} ({pt.point_type.value}) has no "
                            "approved IR "
                            f"at {ref}.",
                            f"النقطة {pt.seq} من {it.itp_no} بلا طلب فحص معتمد في {ref}.",
                        )
                    )
    return out


def ir_items(db: Session, d: QDossier) -> list[dict[str, Any]]:
    out = []
    for ir in _irs(db, d):
        files: list[str] = []
        for r in db.scalars(
            select(QIrRound).where(QIrRound.ir_id == ir.id).order_by(QIrRound.round_no)
        ):
            files += _files(db, AttachmentOwner.q_ir_round, r.id)
        out.append(
            {
                "ref": ir.ir_no,
                "title": f"Points {', '.join(map(str, ir.point_seqs))} — {ir.location_ref}",
                "revision": ir.current_round,
                "status": ir.status.value,
                "date": ir.decided_date.isoformat() if ir.decided_date else None,
                "record_type": "ir",
                "record_id": str(ir.id),
                "link_path": f"/quality/inspection-requests/{ir.id}",
                "files": files,
            }
        )
    return out


def ir_blockers(db: Session, d: QDossier) -> list[Blocker]:
    """(d) an open IR comment."""
    out = []
    for ir in _irs(db, d):
        if ir.status == QIrStatus.voided:
            continue
        for c in db.scalars(
            select(QIrComment).where(
                QIrComment.ir_id == ir.id, QIrComment.status != QIrCommentStatus.closed
            )
        ):
            out.append(
                Blocker(
                    "IR_COMMENT_OPEN",
                    f"{ir.ir_no}: open comment — {(c.text_en or c.text_ar or '')[:100]}",
                    f"{ir.ir_no}: ملاحظة مفتوحة",
                )
            )
    return out


def _punch(db: Session, d: QDossier) -> list[QPunchItem]:
    return list(
        db.scalars(
            select(QPunchItem)
            .where(
                QPunchItem.project_id == d.project_id,
                _scope_where(QPunchItem, d),
                QPunchItem.status != QPunchStatus.voided,
            )
            .order_by(QPunchItem.punch_no)
        )
    )


def punch_items(db: Session, d: QDossier) -> list[dict[str, Any]]:
    return [
        {
            "ref": it.punch_no,
            "title": (it.description_en or it.description_ar or "")[:150],
            "revision": None,
            "status": it.status.value
            + (
                " (agreed open item)"
                if it.category == QPunchCategory.B and it.status in PUNCH_LIVE
                else ""
            ),
            "date": it.closed_date.isoformat() if it.closed_date else it.target_date.isoformat(),
            "record_type": "punch_item",
            "record_id": str(it.id),
            "link_path": f"/quality/punch/{it.id}",
            "files": [str(x) for x in [*(it.photo_before_ids or []), *(it.photo_after_ids or [])]],
        }
        for it in _punch(db, d)
    ]


def punch_blockers(db: Session, d: QDossier) -> list[Blocker]:
    """(c) an open category A item (Q-PUN-04); B items are agreed open items."""
    return [
        Blocker(
            "PUNCH_A_OPEN",
            f"{it.punch_no} (category A) is still {it.status.value}.",
            f"البند {it.punch_no} (فئة A) لم يُغلق بعد.",
        )
        for it in _punch(db, d)
        if it.category == QPunchCategory.A and it.status in PUNCH_LIVE
    ]


def asbuilt_rows(db: Session, d: QDossier) -> list[QAsbuiltItem]:
    return list(
        db.scalars(
            select(QAsbuiltItem)
            .where(QAsbuiltItem.dossier_id == d.id)
            .order_by(QAsbuiltItem.drawing_no)
        )
    )


def asbuilt_items(db: Session, d: QDossier) -> list[dict[str, Any]]:
    return [
        {
            "ref": a.drawing_no,
            "title": a.title,
            "revision": a.revision,
            "status": a.status.value,
            "date": a.drawing_date.isoformat() if a.drawing_date else None,
            "record_type": "asbuilt",
            "record_id": str(a.id),
            "link_path": f"/quality/dossiers/{d.id}",
            "files": [str(a.attachment_id)] if a.attachment_id else [],
        }
        for a in asbuilt_rows(db, d)
    ]


def asbuilt_blockers(db: Session, d: QDossier) -> list[Blocker]:
    """(f) an empty as-built list or an item not approved."""
    rows = asbuilt_rows(db, d)
    if not rows:
        return [
            Blocker(
                "ASBUILT_EMPTY", "The as-built list is empty.", "قائمة المخططات حسب التنفيذ فارغة."
            )
        ]
    return [
        Blocker(
            "ASBUILT_NOT_APPROVED",
            f"As-built {a.drawing_no} Rev.{a.revision} is not approved.",
            f"المخطط {a.drawing_no} غير معتمد.",
        )
        for a in rows
        if a.status != QAsbuiltStatus.approved
    ]


def ncr_items(db: Session, d: QDossier) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(QNcr)
        .where(
            QNcr.project_id == d.project_id, _scope_where(QNcr, d), QNcr.status != QNcrStatus.draft
        )
        .order_by(QNcr.ncr_no)
    )
    return [
        {
            "ref": n.ncr_no,
            "title": n.title,
            "revision": None,
            "status": n.status.value,
            "date": n.closed_date.isoformat()
            if n.closed_date
            else (n.opened_date.isoformat() if n.opened_date else None),
            "record_type": "ncr",
            "record_id": str(n.id),
            "link_path": f"/quality/ncrs/{n.id}",
            "files": _files(db, AttachmentOwner.q_ncr_evidence, n.id),
        }
        for n in rows
    ]


def ncr_blockers(db: Session, d: QDossier) -> list[Blocker]:
    """(b) an NCR in scope not Closed or Voided."""
    return [
        Blocker("NCR_OPEN", f"{n.ncr_no} is {n.status.value}.", f"التقرير {n.ncr_no} لم يُغلق بعد.")
        for n in db.scalars(
            select(QNcr)
            .where(
                QNcr.project_id == d.project_id,
                _scope_where(QNcr, d),
                QNcr.status.notin_([QNcrStatus.draft, QNcrStatus.closed, QNcrStatus.voided]),
            )
            .order_by(QNcr.ncr_no)
        )
    ]


def register_sections() -> None:
    providers = {
        "itp": (itp_items, itp_blockers),
        "ir": (ir_items, ir_blockers),
        "punch": (punch_items, punch_blockers),
        "asbuilt": (asbuilt_items, asbuilt_blockers),
    }
    for code, (items, blocks) in providers.items():
        reg.DOSSIER_SECTIONS[code] = reg.DossierSection(
            items, blocks, label("dossier_section", code), label("dossier_section", code, True)
        )
    # §B.7 names Q0 as the provider of `ncr`; Q0 registered none, so Q1 fills the slot (D-336)
    reg.DOSSIER_SECTIONS.setdefault(
        "ncr",
        reg.DossierSection(
            ncr_items,
            ncr_blockers,
            label("dossier_section", "ncr"),
            label("dossier_section", "ncr", True),
        ),
    )


SECTION_ORDER = (
    "itp",
    "ir",
    "mar",
    "mir",
    "tests",
    "welding",
    "calibration",
    "ncr",
    "punch",
    "asbuilt",
    "documents",
)


def _ordered(codes: list[str]) -> list[str]:
    rank = {c: i for i, c in enumerate(SECTION_ORDER)}
    return sorted(dict.fromkeys(codes), key=lambda c: (rank.get(c, 99), c))


# ---- loading and visibility --------------------------------------------------------------------


def requesters(d: QDossier) -> frozenset[uuid.UUID]:
    return qc.ids(d.compiled_by_user_id, d.submitted_by_user_id, d.created_by_user_id)


def ctx(d: QDossier) -> rpm.Ctx:
    return rpm.Ctx(None, None, requesters(d))


def can_view(db: Session, p: Principal, d: QDossier) -> bool:
    uid = p.user.id
    if uid in (d.compiled_by_user_id, d.created_by_user_id):
        return True
    if qc.covers(p.grant(d.project_id, C.dossier_compile), None, None):
        return True
    g = p.grant(d.project_id, C.quality_view)
    if g is None:
        return False
    if g.scope != S.responsible:
        return True
    if q1c.signed_by(db, RT, d.id, uid):
        return True
    if d.status != ST.submitted:
        return False
    return rpm.resolves(
        db, p, q1c.project(db, d.project_id), RT, STEP, ctx(d), record_id=d.id, can_act=False
    )


def get_dossier(db: Session, p: Principal, dossier_id: uuid.UUID) -> QDossier:
    d = db.get(QDossier, dossier_id)
    if d is None or not p.can_see_project(d.project_id) or not can_view(db, p, d):
        raise q1c.denied(
            db, p, EntityType.q_dossier, dossier_id, d.project_id if d else None, "Dossier"
        )
    return d


def _audit(db: Session, p: Principal, d: QDossier, action: AuditAction, **kw: Any) -> None:
    audit.record(
        db,
        action,
        p.actor(d.project_id),
        entity_type=EntityType.q_dossier,
        entity_id=d.id,
        project_id=d.project_id,
        **kw,
    )


def _status(db: Session, p: Principal, d: QDossier, to: QDossierStatus, **details: Any) -> None:
    before = d.status
    d.status = to
    d.status_changed_at = now()
    d.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        d,
        AuditAction.status_change,
        before={"status": before.value},
        after={"status": to.value},
        details={k: v for k, v in details.items() if v is not None} or None,
    )


def _compiler(db: Session, p: Principal, pr: Project) -> None:
    g = p.require(pr.id, C.dossier_compile)
    if g.scope == S.responsible:
        raise forbidden_error()


def immutable() -> Any:
    return qc.err(
        409,
        ErrorCode.DOSSIER_IMMUTABLE,
        "An accepted dossier is final; start a new revision to change it.",
        "الملف المقبول نهائي؛ أنشئ مراجعة جديدة لتعديله.",
    )


# ---- create, scope, as-built ---------------------------------------------------------------------


def _check_scope(db: Session, pr: Project, zone_ids: list[Any], system_ids: list[Any]) -> None:
    if not zone_ids and not system_ids:
        raise qc.field_err(
            "zone_ids",
            "Choose at least one zone or system.",
            "اختر منطقة أو نظاماً واحداً على الأقل.",
        )
    for i, z in enumerate(zone_ids):
        zz = db.get(Zone, z)
        if zz is None or zz.project_id != pr.id:
            raise qc.field_err(f"zone_ids[{i}]", "The zone is not on this project.")
    for i, s in enumerate(system_ids):
        ss = db.get(QSystem, s)
        if ss is None or ss.project_id != pr.id:
            raise qc.field_err(f"system_ids[{i}]", "The system is not on this project.")


def _sections(codes: list[str] | None) -> list[str]:
    known = list(reg.DOSSIER_SECTIONS)
    if not codes:
        return _ordered(known)
    bad = [c for c in codes if c not in known]
    if bad:
        raise qc.field_err("sections", f"Unknown sections: {bad}.", "أقسام غير معروفة.")
    return _ordered(list(codes))


def create(db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]) -> QDossier:
    pr = qc.get_project(db, p, project_id)
    q1c.writable_construction(db, p, pr, RT)
    _compiler(db, p, pr)
    zones, systems = list(body.get("zone_ids") or []), list(body.get("system_ids") or [])
    _check_scope(db, pr, zones, systems)
    d = QDossier(
        id=uuid.uuid4(),
        project_id=pr.id,
        family_id=uuid.uuid4(),
        dossier_no=qnum.assign(db, pr, RT, on=q1c.day(pr)),
        revision=1,
        title_en=body["title_en"].strip(),
        title_ar=body["title_ar"].strip(),
        zone_ids=zones,
        system_ids=systems,
        sections=_sections(body.get("sections")),
        status=ST.draft,
        warnings=[],
        created_by_user_id=p.user.id,
    )
    db.add(d)
    db.flush()
    _audit(db, p, d, AuditAction.create, after={"dossier_no": d.dossier_no})
    return d


def update(db: Session, p: Principal, dossier_id: uuid.UUID, body: dict[str, Any]) -> QDossier:
    d = get_dossier(db, p, dossier_id)
    pr = q1c.project(db, d.project_id)
    q1c.progress_writable(pr, p)
    _compiler(db, p, pr)
    if d.status == ST.accepted:
        raise immutable()
    if d.status == ST.submitted:
        raise invalid_transition("Dossier", d.status, "edit")
    zones = list(body["zone_ids"]) if body.get("zone_ids") is not None else list(d.zone_ids)
    systems = list(body["system_ids"]) if body.get("system_ids") is not None else list(d.system_ids)
    _check_scope(db, pr, zones, systems)
    d.zone_ids, d.system_ids = zones, systems
    for k in ("title_en", "title_ar"):
        if body.get(k):
            setattr(d, k, body[k].strip())
    if body.get("sections") is not None:
        d.sections = _sections(body["sections"])
    if d.status == ST.compiled:
        d.status = ST.draft  # a scope change makes the compiled files stale
    d.updated_by_user_id = p.user.id
    db.flush()
    _audit(db, p, d, AuditAction.update, details={"fields": sorted(body)})
    return d


def add_asbuilt(db: Session, p: Principal, dossier_id: uuid.UUID, body: dict[str, Any]) -> QDossier:
    d = get_dossier(db, p, dossier_id)
    pr = q1c.project(db, d.project_id)
    q1c.progress_writable(pr, p)
    _compiler(db, p, pr)
    if d.status == ST.accepted:
        raise immutable()
    a = QAsbuiltItem(
        project_id=d.project_id,
        dossier_id=d.id,
        drawing_no=body["drawing_no"].strip()[:60],
        title=body["title"].strip()[:200],
        revision=str(body.get("revision") or "0")[:20],
        drawing_date=body.get("drawing_date"),
        status=QAsbuiltStatus(body.get("status") or "submitted"),
        attachment_id=body.get("attachment_id"),
        created_by_user_id=p.user.id,
    )
    if a.attachment_id is not None:
        att = db.get(Attachment, a.attachment_id)
        if att is None or att.owner_type != AttachmentOwner.q_dossier or att.owner_id != d.id:
            raise qc.field_err("attachment_id", "Upload the drawing to this dossier first.")
    if a.status == QAsbuiltStatus.approved:
        a.approved_by_user_id, a.approved_at = p.user.id, now()
    db.add(a)
    db.flush()
    _audit(db, p, d, AuditAction.update, details={"asbuilt_added": a.drawing_no})
    return d


def update_asbuilt(db: Session, p: Principal, item_id: uuid.UUID, body: dict[str, Any]) -> QDossier:
    a = db.get(QAsbuiltItem, item_id)
    if a is None:
        raise not_found("As-built item")
    d = get_dossier(db, p, a.dossier_id)
    pr = q1c.project(db, d.project_id)
    q1c.progress_writable(pr, p)
    _compiler(db, p, pr)
    if d.status == ST.accepted:
        raise immutable()
    if body.get("delete"):
        db.delete(a)
    else:
        for k in ("drawing_no", "title", "revision", "drawing_date", "attachment_id"):
            if k in body and body[k] is not None:
                setattr(a, k, body[k])
        if body.get("status"):
            a.status = QAsbuiltStatus(body["status"])
            if a.status == QAsbuiltStatus.approved:
                a.approved_by_user_id, a.approved_at = p.user.id, now()
    db.flush()
    _audit(db, p, d, AuditAction.update, details={"asbuilt": str(item_id)})
    return d


# ---- blockers ------------------------------------------------------------------------------------


def blockers(db: Session, d: QDossier) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Q-DOS-03: (blocking, warnings) by the project's `dossier_blockers` letters."""
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    active = set(qs.value(db, d.project_id, "dossier_blockers") or [])
    block: list[dict[str, Any]] = []
    warn: list[dict[str, Any]] = []
    for code in d.sections or []:
        sec = reg.DOSSIER_SECTIONS.get(code)
        if sec is None:
            continue
        letter = SECTION_LETTER.get(code, "e")
        for b in sec.blockers(db, d):
            row = {"section": code, "letter": letter, **b.__dict__}
            (block if letter in active else warn).append(row)
    return block, warn


# ---- compile (Q-DOS-02, -04) ---------------------------------------------------------------------


def _safe(name: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)
    return keep[:80] or "file"


def snapshot(db: Session, d: QDossier) -> tuple[dict[str, Any], list[tuple[str, Attachment]]]:
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    sections = []
    files: list[tuple[str, Attachment]] = []
    for n, code in enumerate(d.sections or [], start=1):
        sec = reg.DOSSIER_SECTIONS.get(code)
        if sec is None:
            continue
        items = []
        for it in sec.items(db, d):
            fl = []
            for aid in it.get("files") or []:
                a = db.get(Attachment, uuid.UUID(str(aid)))
                if a is None:
                    continue
                path = f"{n:02d}-{code}/{_safe(str(it.get('ref') or ''))}-{_safe(a.file_name)}"
                fl.append(
                    {
                        "attachment_id": str(a.id),
                        "file_name": a.file_name,
                        "sha256": a.sha256,
                        "size": a.size_bytes,
                        "path": path,
                    }
                )
                files.append((path, a))
            items.append({**{k: v for k, v in it.items() if k != "files"}, "files": fl})
        sections.append(
            {
                "code": code,
                "no": n,
                "title_en": sec.title_en,
                "title_ar": sec.title_ar,
                "items": items,
            }
        )
    return {"dossier_no": d.dossier_no, "revision": d.revision, "sections": sections}, files


def index_doc(db: Session, d: QDossier, snap: dict[str, Any], issued: date) -> render.Doc:
    pr = q1c.project(db, d.project_id)
    zones = [db.get(Zone, z) for z in d.zone_ids or []]
    systems = [db.get(QSystem, s) for s in d.system_ids or []]
    scope = ", ".join([z.code for z in zones if z] + [s.code for s in systems if s])
    control: list[tuple[str, ...]] = [
        ("Dossier no.", "رقم الملف", f"{d.dossier_no} Rev.{d.revision}"),
        ("Project", "المشروع", pr.code),
        ("Title", "العنوان", d.title_en, d.title_ar),
        ("Scope", "النطاق", scope or "—"),
        (
            "Status",
            "الحالة",
            label("dossier_status", d.status),
            label("dossier_status", d.status, True),
        ),
        ("Issue date", "تاريخ الإصدار", issued.isoformat()),
        (
            "Issue date (Hijri, Umm al-Qura)",
            "تاريخ الإصدار الهجري، أم القرى",
            hijri_en(issued),
            hijri_ar(issued),
        ),
    ]
    cols = [
        ("ref", "Reference", "المرجع"),
        ("title", "Title", "العنوان"),
        ("rev", "Rev.", "المراجعة"),
        ("status", "Status", "الحالة"),
        ("date", "Date", "التاريخ"),
        ("files", "Files", "الملفات"),
    ]
    sections = []
    for s in snap["sections"]:
        rows = [
            {
                "ref": i.get("ref") or "—",
                "title": (i.get("title") or "")[:60],
                "rev": "" if i.get("revision") is None else str(i.get("revision")),
                "status": i.get("status") or "",
                "date": i.get("date") or "",
                "files": str(len(i.get("files") or [])),
            }
            for i in s["items"]
        ]
        sections.append(
            render.Section(
                s["code"],
                f"{s['no']:02d} {s['title_en'] or s['code']}",
                f"{s['no']:02d} {s['title_ar'] or s['code']}",
                tables=[render.Table(cols, rows)] if rows else [],
                paragraphs_en=[] if rows else ["No records in scope."],
                paragraphs_ar=[] if rows else ["لا توجد سجلات ضمن النطاق."],
            )
        )
    sign = [signoff.read(db, x) for x in signoff.signoffs_for(db, RT, d.id)]
    sections.append(
        render.Section(
            "signoffs",
            "Sign-off summary",
            "ملخص التوقيعات",
            paragraphs_en=[
                f"{x['step']}: {x['decision']} — {x['text_en']} ({x['signed_at']:%Y-%m-%d})"
                for x in sign
            ]
            or ["Not yet signed."],
            paragraphs_ar=[f"{x['step']}: {x['decision']} — {x['text_ar']}" for x in sign]
            or ["لم يوقَّع بعد."],
        )
    )
    digest = hashlib.sha256(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()
    return render.Doc(
        doc_no=d.dossier_no,
        revision=d.revision,
        title_en=f"Handover dossier {d.dossier_no}",
        title_ar=f"ملف التسليم {d.dossier_no}",
        snapshot_hash=digest,
        control=control,
        sections=sections,
    )


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in entries:
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return buf.getvalue()


def compile_(db: Session, p: Principal, dossier_id: uuid.UUID) -> QDossier:
    d = get_dossier(db, p, dossier_id)
    pr = q1c.project(db, d.project_id)
    q1c.progress_writable(pr, p)
    _compiler(db, p, pr)
    if d.status == ST.accepted:
        raise immutable()
    if d.status not in (ST.draft, ST.compiled, ST.returned):
        raise invalid_transition("Dossier", d.status, "compiled")
    snap, files = snapshot(db, d)
    total = sum(a.size_bytes for _, a in files)
    if total > DOSSIER_MAX_BYTES:
        raise qc.err(
            422,
            ErrorCode.DOSSIER_TOO_LARGE,
            "The package would exceed 2 GB; split the scope into smaller dossiers (Q-DOS-04).",
            "سيتجاوز الملف 2 غيغابايت؛ قسّم النطاق إلى ملفات أصغر.",
        )
    issued = q1c.day(pr)
    at = now()
    d.compiled_at = at
    d.compiled_by_user_id = p.user.id
    snap["compiled_at"] = at.isoformat()
    d.snapshot = snap
    doc = index_doc(db, d, snap, issued)
    en, ar = render.pdf(doc, "en"), render.pdf(doc, "ar")
    base = f"{d.dossier_no}-Rev{d.revision}"
    ia = attachments.store(
        db,
        AttachmentOwner.q_dossier,
        d.id,
        pr.id,
        f"{base}-index-EN.pdf",
        en,
        "application/pdf",
        p.user.id,
        generated=True,
    )
    ib = attachments.store(
        db,
        AttachmentOwner.q_dossier,
        d.id,
        pr.id,
        f"{base}-index-AR.pdf",
        ar,
        "application/pdf",
        p.user.id,
        generated=True,
    )
    entries = [(f"00-index/{base}-index-EN.pdf", en), (f"00-index/{base}-index-AR.pdf", ar)]
    entries += [(path, attachments.read_content(a)) for path, a in files]
    package = _zip(entries)
    pa = attachments.store(
        db,
        AttachmentOwner.q_dossier,
        d.id,
        pr.id,
        f"{base}.zip",
        package,
        "application/zip",
        p.user.id,
        generated=True,
    )
    d.index_en_id, d.index_ar_id, d.package_id = ia.id, ib.id, pa.id
    d.package_sha256 = hashlib.sha256(package).hexdigest()
    _, warn = blockers(db, d)
    d.warnings = warn
    _status(db, p, d, ST.compiled, files=len(files), sha256=d.package_sha256)
    return d


def submit(db: Session, p: Principal, dossier_id: uuid.UUID) -> QDossier:
    d = get_dossier(db, p, dossier_id)
    pr = q1c.project(db, d.project_id)
    q1c.progress_writable(pr, p)
    _compiler(db, p, pr)
    if d.status != ST.compiled:
        raise invalid_transition("Dossier", d.status, "submitted")
    block, warn = blockers(db, d)
    if block:
        raise qc.err(
            422,
            ErrorCode.DOSSIER_BLOCKED,
            "The dossier cannot be submitted: " + " ".join(b["detail_en"] for b in block),
            "لا يمكن تقديم الملف: " + " ".join(b["detail_ar"] for b in block),
            blockers=block,
            warnings=warn,
        )
    d.warnings = warn
    d.submitted_at = now()
    d.submitted_by_user_id = p.user.id
    _status(db, p, d, ST.submitted)
    res = rpm.resolve(db, pr, RT, STEP, ctx(d), record_id=d.id)
    qc.send(
        db,
        [u for u in res.users if u not in requesters(d)],
        f"{d.dossier_no} Rev.{d.revision} submitted for acceptance",
        f"{d.dossier_no} مقدم للقبول",
        body_en=d.title_en,
        body_ar=d.title_ar,
        entity_type=EntityType.q_dossier,
        entity_id=d.id,
        project_id=d.project_id,
        key=f"dossier_submitted:{d.id}:{d.submitted_at}",
        path=f"/quality/dossiers/{d.id}",
    )
    return d


def decide(
    db: Session,
    p: Principal,
    dossier_id: uuid.UUID,
    decision: str,
    comment: str | None,
    paper: dict[str, Any] | None = None,
) -> QDossier:
    d = get_dossier(db, p, dossier_id)
    pr = q1c.project(db, d.project_id)
    q1c.progress_writable(pr, p)
    if d.status == ST.accepted:
        raise immutable()
    if d.status != ST.submitted:
        raise invalid_transition("Dossier", d.status, decision)
    if decision not in ("approved", "returned"):
        raise qc.field_err("decision", "approved or returned")
    text = (
        qc.reason(comment, 20, "comment")
        if decision == "returned"
        else (comment or "").strip() or None
    )
    if paper:
        signoff.sign_paper(db, p, pr, RT, d.id, STEP, decision, text, paper, ctx(d))
    else:
        rule, capacity = rpm.check_signer(db, p, pr, RT, STEP, ctx(d), record_id=d.id)
        signoff.sign(db, p, pr, RT, d.id, STEP, decision, text, rule, capacity)
    d.decided_at = now()
    if decision == "approved":
        _status(db, p, d, ST.accepted)
    else:
        d.status_reason = text
        _status(db, p, d, ST.returned, comment=text)
    qc.send(
        db,
        [u for u in (d.compiled_by_user_id, d.submitted_by_user_id) if u],
        f"{d.dossier_no} Rev.{d.revision} {'accepted' if decision == 'approved' else 'returned'}",
        f"{d.dossier_no} {'مقبول' if decision == 'approved' else 'مُعاد'}",
        body_en=text,
        body_ar=text,
        entity_type=EntityType.q_dossier,
        entity_id=d.id,
        project_id=d.project_id,
        key=f"dossier_decided:{d.id}:{d.decided_at}",
        path=f"/quality/dossiers/{d.id}",
    )
    return d


def reopen(db: Session, p: Principal, dossier_id: uuid.UUID) -> QDossier:
    """Returned → Draft (recompile)."""
    d = get_dossier(db, p, dossier_id)
    pr = q1c.project(db, d.project_id)
    q1c.progress_writable(pr, p)
    _compiler(db, p, pr)
    if d.status != ST.returned:
        raise invalid_transition("Dossier", d.status, "draft")
    _status(db, p, d, ST.draft)
    return d


def new_revision(db: Session, p: Principal, dossier_id: uuid.UUID) -> QDossier:
    """Accepted is final; a later change makes revision + 1 in Draft (as-built list copied)."""
    src = get_dossier(db, p, dossier_id)
    pr = q1c.project(db, src.project_id)
    q1c.writable_construction(db, p, pr, RT)
    _compiler(db, p, pr)
    if src.status != ST.accepted:
        raise invalid_transition("Dossier", src.status, "new revision")
    last = (
        db.scalar(select(func.max(QDossier.revision)).where(QDossier.family_id == src.family_id))
        or src.revision
    )
    if db.scalar(
        select(QDossier.id).where(
            QDossier.family_id == src.family_id, QDossier.status != ST.accepted
        )
    ):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "A newer revision is already open.",
            "توجد مراجعة أحدث مفتوحة.",
        )
    d = QDossier(
        id=uuid.uuid4(),
        project_id=src.project_id,
        family_id=src.family_id,
        dossier_no=src.dossier_no,
        revision=last + 1,
        title_en=src.title_en,
        title_ar=src.title_ar,
        zone_ids=list(src.zone_ids),
        system_ids=list(src.system_ids),
        sections=list(src.sections),
        status=ST.draft,
        warnings=[],
        created_by_user_id=p.user.id,
    )
    db.add(d)
    db.flush()
    for a in asbuilt_rows(db, src):
        db.add(
            QAsbuiltItem(
                project_id=d.project_id,
                dossier_id=d.id,
                drawing_no=a.drawing_no,
                title=a.title,
                revision=a.revision,
                drawing_date=a.drawing_date,
                status=a.status,
                attachment_id=a.attachment_id,
                approved_by_user_id=a.approved_by_user_id,
                approved_at=a.approved_at,
                created_by_user_id=p.user.id,
            )
        )
    db.flush()
    _audit(db, p, d, AuditAction.create, after={"revision_of": str(src.id), "revision": d.revision})
    return d


# ---- downloads (Q-DOS-05) -----------------------------------------------------------------------


def _file(db: Session, aid: uuid.UUID | None) -> tuple[bytes, str, str]:
    a = db.get(Attachment, aid) if aid else None
    if a is None:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "Compile the dossier first.", "اجمع الملف أولاً."
        )
    return attachments.read_content(a), a.content_type, a.file_name


def _package_reader(db: Session, p: Principal, d: QDossier) -> bool:
    if qc.covers(p.grant(d.project_id, C.dossier_compile), None, None):
        return True
    g = p.grant(d.project_id, C.dossier_accept)
    if g is None:
        return False
    if g.scope != S.responsible:
        return True
    return q1c.signed_by(db, RT, d.id, p.user.id) or (
        d.status == ST.submitted
        and rpm.resolves(
            db, p, q1c.project(db, d.project_id), RT, STEP, ctx(d), record_id=d.id, can_act=False
        )
    )


def index_file(
    db: Session, p: Principal, dossier_id: uuid.UUID, lang: str
) -> tuple[bytes, str, str]:
    """The index PDF: 253 / 254 readers at any compiled state; every 238 holder (also the Viewer /
    Client) once accepted."""
    d = get_dossier(db, p, dossier_id)
    if not _package_reader(db, p, d) and d.status != ST.accepted:
        raise forbidden_error(
            "The index is available to you once the dossier is accepted (Q-DOS-05)."
        )
    return _file(db, d.index_ar_id if lang == "ar" else d.index_en_id)


def package_file(db: Session, p: Principal, dossier_id: uuid.UUID) -> tuple[bytes, str, str]:
    """The ZIP needs 253 or 254 (Q-DOS-05)."""
    d = get_dossier(db, p, dossier_id)
    if not _package_reader(db, p, d):
        raise forbidden_error("The package needs capability 253 or 254 (Q-DOS-05).")
    return _file(db, d.package_id)


# ---- read and list ------------------------------------------------------------------------------


def allowed_actions(db: Session, p: Principal, d: QDossier) -> list[str]:
    if q1c.viewer(p, d.project_id):
        return []
    pr = q1c.project(db, d.project_id)
    comp = qc.covers(p.grant(pr.id, C.dossier_compile), None, None)
    out = []
    if comp and d.status in (ST.draft, ST.compiled, ST.returned):
        out += ["edit", "compile", "asbuilt"]
    if comp and d.status == ST.compiled:
        out.append("submit")
    if comp and d.status == ST.returned:
        out.append("reopen")
    if d.status == ST.submitted and rpm.resolves(db, p, pr, RT, STEP, ctx(d), record_id=d.id):
        out.append("decide")
    if d.status == ST.submitted and p.grant(pr.id, C.dossier_accept) is not None:
        out.append("paper_signoff")
    if (
        comp
        and d.status == ST.accepted
        and not db.scalar(
            select(QDossier.id).where(
                QDossier.family_id == d.family_id, QDossier.status != ST.accepted
            )
        )
    ):
        out.append("new_revision")
    if d.package_id and _package_reader(db, p, d):
        out.append("download_package")
    if d.index_en_id and (_package_reader(db, p, d) or d.status == ST.accepted):
        out.append("download_index")
    return out


def list_item(db: Session, d: QDossier) -> dict[str, Any]:
    zones = [db.get(Zone, z) for z in d.zone_ids or []]
    return {
        "id": d.id,
        "family_id": d.family_id,
        "dossier_no": d.dossier_no,
        "revision": d.revision,
        "title_en": d.title_en,
        "title_ar": d.title_ar,
        "status": d.status,
        "zones": [
            {"id": z.id, "code": z.code, "name_en": z.name_en, "name_ar": z.name_ar}
            for z in zones
            if z
        ],
        "system_ids": list(d.system_ids or []),
        "compiled_at": d.compiled_at,
        "submitted_at": d.submitted_at,
        "decided_at": d.decided_at,
    }


def read(db: Session, p: Principal, d: QDossier, *, with_blockers: bool = True) -> dict[str, Any]:
    pr = q1c.project(db, d.project_id)
    hide = q1c.viewer(p, d.project_id)
    block, warn = (
        blockers(db, d)
        if with_blockers and d.status != ST.accepted
        else ([], list(d.warnings or []))
    )
    systems = [db.get(QSystem, s) for s in d.system_ids or []]
    res = (
        rpm.resolve(db, pr, RT, STEP, ctx(d), record_id=d.id) if d.status == ST.submitted else None
    )
    sections = []
    snap = d.snapshot or {}
    for s in snap.get("sections") or []:
        sections.append(
            {
                "code": s["code"],
                "title_en": s.get("title_en"),
                "title_ar": s.get("title_ar"),
                "item_count": len(s.get("items") or []),
                "file_count": sum(len(i.get("files") or []) for i in s.get("items") or []),
            }
        )
    return {
        **list_item(db, d),
        "project_id": d.project_id,
        "systems": [
            {"id": s.id, "code": s.code, "name_en": s.name_en, "name_ar": s.name_ar}
            for s in systems
            if s
        ],
        "sections": list(d.sections or []),
        "available_sections": [
            {"code": c, "title_en": sec.title_en, "title_ar": sec.title_ar}
            for c, sec in sorted(reg.DOSSIER_SECTIONS.items(), key=lambda kv: _ordered([kv[0]]))
        ],
        "compiled_by": q1c.user_ref(db, d.compiled_by_user_id, hide),
        "snapshot_sections": sections,
        "package_sha256": d.package_sha256,
        "has_files": d.package_id is not None,
        "blockers": block,
        "warnings": warn,
        "status_reason": d.status_reason,
        "asbuilt": [
            {
                "id": a.id,
                "drawing_no": a.drawing_no,
                "title": a.title,
                "revision": a.revision,
                "drawing_date": a.drawing_date,
                "status": a.status,
                "attachment_id": None if hide else a.attachment_id,
            }
            for a in asbuilt_rows(db, d)
        ],
        "revisions": [
            {"id": r.id, "revision": r.revision, "status": r.status}
            for r in db.scalars(
                select(QDossier)
                .where(QDossier.family_id == d.family_id)
                .order_by(QDossier.revision)
            )
        ],
        "responsible": [u for u in (q1c.user_ref(db, x, hide) for x in sorted(res.users)) if u]
        if res
        else [],
        "signoffs": []
        if hide
        else [signoff.read(db, s) for s in signoff.signoffs_for(db, RT, d.id)],
        "links": links.links_for(db, p, RT, d.id),
        "allowed_actions": allowed_actions(db, p, d),
    }


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[QDossierStatus] | None = None,
) -> dict[str, Any]:
    pr = qc.get_project(db, p, project_id)
    if p.grant(pr.id, C.quality_view) is None and p.grant(pr.id, C.dossier_compile) is None:
        raise forbidden_error()
    stmt = select(QDossier).where(QDossier.project_id == pr.id)
    if statuses:
        stmt = stmt.where(QDossier.status.in_(statuses))
    rows = [
        d
        for d in db.scalars(stmt.order_by(QDossier.dossier_no, QDossier.revision))
        if can_view(db, p, d)
    ]
    total = len(rows)
    chunk = rows[(page - 1) * page_size : page * page_size]
    return {
        "items": [list_item(db, d) for d in chunk],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


_ = (IR_APPROVED, Q1_SECTIONS)
