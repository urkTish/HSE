# ruff: noqa: E501
"""PTW audits: field, document review, unpermitted work (3-ptw §3.15, §4.9, AU-1…AU-8, §6.8)."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, WeekStart
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import CaPriority, CaSourceType, CaStatus
from app.core.ptw_enums import (
    AuditAnswer,
    AuditFindingSeverity,
    AuditItem,
    Exposure,
    PermitStatus,
    PermitType,
    PtwAuditStatus,
    PtwAuditType,
    StatusReason,
)
from app.models import CorrectiveAction, Permit, PtwAudit
from app.schemas.common import Page
from app.schemas.ptw_audits import (
    AuditCaLink,
    AuditItemInput,
    AuditItemRead,
    PtwAuditChecklist,
    PtwAuditCompleteInput,
    PtwAuditCreate,
    PtwAuditListItem,
    PtwAuditRead,
    PtwAuditUpdate,
)
from app.services import audit, notify, projects
from app.services.access import common as acommon
from app.services.common import ensure_open, paginate
from app.services.hse_common import (
    Refs,
    check_engagement,
    check_site_zone,
    contractor_reps,
    make_ref,
    next_seq,
)
from app.services.permissions import Principal, forbidden_error
from app.services.ptw import common, lifecycle, rules
from app.services.ptw import facts as facts_mod
from app.services.ptw import reference as ref

C = Capability
S = PermitStatus
T = PermitType
SEV_ORDER = {
    AuditFindingSeverity.minor: 0,
    AuditFindingSeverity.major: 1,
    AuditFindingSeverity.critical: 2,
}
CA_FOR = {
    AuditFindingSeverity.critical: CaPriority.critical,
    AuditFindingSeverity.major: CaPriority.high,
}
PRIO_ORDER = {CaPriority.low: 0, CaPriority.medium: 1, CaPriority.high: 2, CaPriority.critical: 3}
LOCK_DAYS = 7
CODE_RE = re.compile(r"\bA(0\d|1\d|20)\b")


# ---- applicability (AU-3) ------------------------------------------------------------------------


def applicable_items(
    db: Session, audit_type: PtwAuditType, permit: Permit | None, at: datetime
) -> list[str]:
    if audit_type == PtwAuditType.unpermitted_work or permit is None:
        return ["A00"]
    out = list(ref.AUDIT_ALWAYS)
    f = facts_mod.compute(db, permit)
    for t in permit.work_types:
        out += ref.AUDIT_TYPE_ITEMS.get(T(t), ())
    if f.gas_required:
        out.append("A06")
    if permit.isolation_cert_ids:
        out.append("A07")
    if permit.exposure in (Exposure.outdoor_direct_sun, Exposure.outdoor_shaded):
        s = f.settings
        if rules.in_season(
            acommon.local_day(at),
            s.midday_ban_period["start_mmdd"],
            s.midday_ban_period["end_mmdd"],
        ):
            out.append("A19")
    return sorted(set(out))


def _item_read(code: str, applies: bool, stored: dict[str, Any] | None) -> AuditItemRead:
    en, ar, sev = ref.AUDIT_ITEMS[code]
    st = stored or {}
    answer = AuditAnswer(st["answer"]) if st.get("answer") else None
    severity = AuditFindingSeverity(st["severity"]) if st.get("severity") else None
    return AuditItemRead(
        code=AuditItem(code),
        label_en=en,
        label_ar=ar,
        applies=applies,
        default_severity=sev,
        answer=answer,
        severity=severity,
        note=st.get("note"),
        photo_attachment_ids=[uuid.UUID(x) for x in st.get("photo_attachment_ids") or []],
        ca_required=answer == AuditAnswer.non_compliant
        and (severity or sev) in (AuditFindingSeverity.critical, AuditFindingSeverity.major),
    )


def _merge_items(
    a: PtwAudit, inputs: list[AuditItemInput], applies: list[str]
) -> list[dict[str, Any]]:
    cur = {x["code"]: x for x in a.items or []}
    seen: set[str] = set()
    for i, it in enumerate(inputs):
        code = it.code.value
        if code in seen:
            raise validation_error(f"items.{i}.code", "An item is listed twice.")
        seen.add(code)
        _en, _ar, default = ref.AUDIT_ITEMS[code]
        if code not in applies:
            if it.answer != AuditAnswer.na:
                raise validation_error(
                    f"items.{i}.answer", f"{code} does not apply to this audit: answer n.a."
                )
        elif it.answer == AuditAnswer.na:
            raise validation_error(
                f"items.{i}.answer", f"{code} applies: n.a. is not allowed (AU-3)."
            )
        sev = it.severity or default
        if SEV_ORDER[sev] < SEV_ORDER[default]:
            raise validation_error(
                f"items.{i}.severity",
                f"The severity of {code} may be raised from {default.value}, not lowered.",
            )
        if a.audit_type == PtwAuditType.unpermitted_work and it.answer != AuditAnswer.non_compliant:
            raise validation_error(
                f"items.{i}.answer",
                "An unpermitted-work audit records A00 as non-compliant (AU-6).",
            )
        cur[code] = {
            "code": code,
            "answer": it.answer.value,
            "severity": sev.value,
            "note": it.note,
            "photo_attachment_ids": [str(x) for x in it.photo_attachment_ids],
        }
    return [cur[c] for c in sorted(cur)]


def _score(a: PtwAudit, applies: list[str]) -> None:
    rows = [
        x
        for x in a.items or []
        if x["code"] in applies and x.get("answer") and x["answer"] != AuditAnswer.na.value
    ]
    a.applicable_count = len(rows)
    a.compliant_count = len([x for x in rows if x["answer"] == AuditAnswer.compliant.value])
    a.critical_count = len(
        [
            x
            for x in rows
            if x["answer"] == AuditAnswer.non_compliant.value
            and x.get("severity") == AuditFindingSeverity.critical.value
        ]
    )
    a.score_pct = (
        (Decimal(a.compliant_count) * 100 / Decimal(a.applicable_count)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        if a.applicable_count
        else None
    )


# ---- CA matching (AU-4, AU-5) --------------------------------------------------------------------


def _cas(db: Session, a: PtwAudit) -> list[CorrectiveAction]:
    return list(
        db.scalars(
            select(CorrectiveAction)
            .where(
                CorrectiveAction.source_type == CaSourceType.ptw_audit,
                CorrectiveAction.source_id == a.id,
            )
            .order_by(CorrectiveAction.ref)
        )
    )


def _ca_code(ca: CorrectiveAction) -> str | None:
    m = CODE_RE.search(f"{ca.title} {ca.description}")
    return m.group(0) if m else None


def _required(a: PtwAudit) -> list[tuple[str, CaPriority]]:
    out = []
    for x in a.items or []:
        if x.get("answer") != AuditAnswer.non_compliant.value:
            continue
        sev = AuditFindingSeverity(x.get("severity") or ref.AUDIT_ITEMS[x["code"]][2])
        if sev in CA_FOR:
            out.append((x["code"], CA_FOR[sev]))
    out.sort(key=lambda r: -PRIO_ORDER[r[1]])
    return out


def match_cas(db: Session, a: PtwAudit) -> tuple[dict[uuid.UUID, str | None], list[str]]:
    """Links CAs to items (a code named in the CA title/description first, then by priority)
    and returns (ca_id → item code, items still missing a CA)."""
    cas = [c for c in _cas(db, a) if c.status != CaStatus.cancelled]
    link: dict[uuid.UUID, str | None] = {c.id: None for c in _cas(db, a)}
    free = list(cas)
    missing: list[str] = []
    req = _required(a)
    pending: list[tuple[str, CaPriority]] = []
    for code, prio in req:
        hit = next(
            (c for c in free if _ca_code(c) == code and PRIO_ORDER[c.priority] >= PRIO_ORDER[prio]),
            None,
        )
        if hit is None:
            pending.append((code, prio))
            continue
        link[hit.id] = code
        free.remove(hit)
    for code, prio in pending:
        hit = next(
            (
                c
                for c in free
                if _ca_code(c) in (None, code) and PRIO_ORDER[c.priority] >= PRIO_ORDER[prio]
            ),
            None,
        )
        if hit is None:
            missing.append(code)
            continue
        link[hit.id] = code
        free.remove(hit)
    return link, sorted(missing)


# ---- reads ---------------------------------------------------------------------------------------


def _locks_at(a: PtwAudit) -> datetime | None:
    return a.completed_at + timedelta(days=LOCK_DAYS) if a.completed_at else None


def _lock_if_due(a: PtwAudit, at: datetime | None = None) -> None:
    la = _locks_at(a)
    if a.status == PtwAuditStatus.completed and la is not None and (at or now()) >= la:
        a.status = PtwAuditStatus.locked


def _applies(db: Session, a: PtwAudit) -> list[str]:
    permit = db.get(Permit, a.permit_id) if a.permit_id else None
    return applicable_items(db, a.audit_type, permit, a.audited_at)


def to_read(db: Session, a: PtwAudit) -> PtwAuditRead:
    refs = Refs(db)
    applies = _applies(db, a)
    stored = {x["code"]: x for x in a.items or []}
    codes = sorted(set(applies) | set(stored))
    link, missing = match_cas(db, a)
    permit = db.get(Permit, a.permit_id) if a.permit_id else None
    site = refs.site(a.site_id)
    auditor = refs.user(a.auditor_user_id)
    assert site is not None and auditor is not None  # noqa: S101
    return PtwAuditRead(
        id=a.id,
        project_id=a.project_id,
        audit_no=a.audit_no,
        audit_type=a.audit_type,
        permit=common.permit_ref(permit) if permit else None,
        site=site,
        zone=refs.zone(a.zone_id),
        engagement=refs.eng_required(a.engagement_id),
        auditor=auditor,
        audited_at=a.audited_at,
        items=[_item_read(c, c in applies, stored.get(c)) for c in codes],
        applicable_count=a.applicable_count,
        compliant_count=a.compliant_count,
        score_pct=a.score_pct,
        critical_count=a.critical_count,
        required_cas=[AuditItem(c) for c in missing],
        cas=[
            AuditCaLink(
                id=c.id,
                ref=c.ref,
                priority=c.priority.value,
                status=c.status.value,
                item_code=AuditItem(code) if (code := link.get(c.id)) else None,
            )
            for c in _cas(db, a)
        ],
        stop_work_issued_at=a.stop_work_issued_at,
        unpermitted_work_desc=a.unpermitted_work_desc,
        permit_suspended=a.permit_suspended,
        status=a.status,
        completed_at=a.completed_at,
        locks_at=_locks_at(a),
        created_at=a.created_at,
        updated_at=a.updated_at or a.created_at,
    )


def _list_item(db: Session, a: PtwAudit, refs: Refs) -> PtwAuditListItem:
    permit = db.get(Permit, a.permit_id) if a.permit_id else None
    auditor = refs.user(a.auditor_user_id)
    assert auditor is not None  # noqa: S101
    return PtwAuditListItem(
        id=a.id,
        audit_no=a.audit_no,
        audit_type=a.audit_type,
        permit=common.permit_ref(permit) if permit else None,
        engagement=refs.eng_required(a.engagement_id),
        zone=refs.zone(a.zone_id),
        auditor=auditor,
        audited_at=a.audited_at,
        score_pct=a.score_pct,
        critical_count=a.critical_count,
        status=a.status,
    )


def _view_grant(db: Session, p: Principal, project_id: uuid.UUID) -> Any:
    projects.get_visible(db, p, project_id)
    g = p.grant(project_id, C.permit_view) or p.grant(project_id, C.ptw_audit_conduct)
    if g is None:
        raise forbidden_error()
    return g


def get_row(db: Session, p: Principal, audit_id: uuid.UUID) -> PtwAudit:
    a = db.get(PtwAudit, audit_id)
    if a is None:
        raise not_found("PTW audit")
    g = _view_grant(db, p, a.project_id)
    if not acommon.grant_covers(g, [a.site_id], a.engagement_id):
        raise forbidden_error("This audit is outside your scope.")
    _lock_if_due(a)
    return a


def read(db: Session, p: Principal, audit_id: uuid.UUID) -> PtwAuditRead:
    return to_read(db, get_row(db, p, audit_id))


def list_audits(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    audit_types: list[PtwAuditType] | None = None,
    statuses: list[PtwAuditStatus] | None = None,
    permit_id: uuid.UUID | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    auditor_user_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Page[PtwAuditListItem]:
    g = _view_grant(db, p, project_id)
    stmt = select(PtwAudit).where(PtwAudit.project_id == project_id)
    if g.site_ids is not None:
        stmt = stmt.where(PtwAudit.site_id.in_(list(g.site_ids)))
    if g.engagement_ids is not None:
        stmt = stmt.where(PtwAudit.engagement_id.in_(list(g.engagement_ids)))
    if audit_types:
        stmt = stmt.where(PtwAudit.audit_type.in_(list(audit_types)))
    if statuses:
        stmt = stmt.where(PtwAudit.status.in_(list(statuses)))
    if permit_id:
        stmt = stmt.where(PtwAudit.permit_id == permit_id)
    if engagement_ids:
        stmt = stmt.where(PtwAudit.engagement_id.in_(list(engagement_ids)))
    if auditor_user_id:
        stmt = stmt.where(PtwAudit.auditor_user_id == auditor_user_id)
    if date_from:
        stmt = stmt.where(PtwAudit.audited_at >= acommon.local_midnight_utc(date_from))
    if date_to:
        stmt = stmt.where(
            PtwAudit.audited_at < acommon.local_midnight_utc(date_to) + timedelta(days=1)
        )
    stmt = stmt.order_by(PtwAudit.audited_at.desc(), PtwAudit.audit_no.desc())
    items, total = paginate(db, stmt, page, page_size)
    refs = Refs(db)
    for a in items:
        _lock_if_due(a)
    return Page[PtwAuditListItem](
        items=[_list_item(db, a, refs) for a in items], total=total, page=page, page_size=page_size
    )


def checklist(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    audit_type: PtwAuditType,
    permit_id: uuid.UUID | None,
) -> PtwAuditChecklist:
    _view_grant(db, p, project_id)
    permit = None
    if audit_type != PtwAuditType.unpermitted_work:
        if permit_id is None:
            raise validation_error("permit_id", "A permit is required for this audit type.")
        permit = common.get_permit(db, p, permit_id)
        if permit.project_id != project_id:
            raise validation_error("permit_id", "The permit is not on this project.")
    applies = applicable_items(db, audit_type, permit, now())
    return PtwAuditChecklist(
        audit_type=audit_type,
        permit=common.permit_ref(permit) if permit else None,
        items=[_item_read(c, True, None) for c in applies],
    )


# ---- writes --------------------------------------------------------------------------------------


def _audit_log(
    db: Session, p: Principal, a: PtwAudit, action: AuditAction, before: Any, after: Any
) -> None:
    audit.record(
        db,
        action,
        p.actor(a.project_id),
        entity_type=EntityType.ptw_audit,
        entity_id=a.id,
        project_id=a.project_id,
        before=before,
        after=after,
    )


def _sod(permit: Permit, user_id: uuid.UUID) -> None:
    if user_id in (
        permit.issuer_user_id,
        permit.receiver_user_id,
        permit.area_authority_user_id,
        permit.hse_reviewer_user_id,
    ):
        raise lifecycle.sod(
            "The auditor cannot be the issuer, receiver, area authority or HSE reviewer of the permit (AU-2).",
            "لا يمكن أن يكون المدقق مُصدِر التصريح أو مستلمه أو مسؤول المنطقة أو مراجع السلامة.",
        )


def _critical_nc(a: PtwAudit) -> list[str]:
    return [
        x["code"]
        for x in a.items or []
        if x.get("answer") == AuditAnswer.non_compliant.value
        and x.get("severity") == AuditFindingSeverity.critical.value
    ]


def _act_on_critical(db: Session, p: Principal, a: PtwAudit, at: datetime) -> None:
    """AU-4: a critical non-compliant item on a field audit suspends the live permit; critical
    findings and unpermitted work alert the people of the permit / engagement."""
    crit = _critical_nc(a)
    if not crit:
        return
    permit = db.get(Permit, a.permit_id) if a.permit_id else None
    key = f"critical:{','.join(crit)}"
    sent = list(a.edit_log or [])
    if any(e.get("alert") == key for e in sent):
        return
    a.edit_log = [*sent, {"alert": key, "at": at.isoformat()}]
    if (
        a.audit_type == PtwAuditType.field
        and permit is not None
        and permit.status in (S.issued, S.active)
    ):
        lifecycle.suspend_now(
            db,
            permit,
            StatusReason.audit_critical,
            f"Critical audit finding {', '.join(crit)} ({a.audit_no})",
            source_ref=a.audit_no,
            at=at,
        )
        a.permit_suspended = True
    users: set[uuid.UUID] = set(common.officers(db, a.project_id)) | set(notify.managers(db))
    users |= set(contractor_reps(db, a.project_id, a.engagement_id))
    if permit is not None:
        users |= common.permit_people(db, permit)
    title = (
        "Unpermitted work found"
        if a.audit_type == PtwAuditType.unpermitted_work
        else "Critical PTW audit finding"
    )
    notify.notify(
        db,
        sorted(u for u in users if u),
        NotificationKind.ptw_critical_finding,
        f"{title}: {a.audit_no}" + (f" on {permit.permit_no}" if permit else ""),
        f"مخالفة حرجة في تدقيق التصاريح: {a.audit_no}",
        None,
        None,
        EntityType.ptw_audit,
        a.id,
        a.project_id,
    )


def create(db: Session, p: Principal, project_id: uuid.UUID, body: PtwAuditCreate) -> PtwAuditRead:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    at = now()
    if body.audited_at > at + timedelta(minutes=5):
        raise validation_error("audited_at", "The audit time cannot be in the future.")
    permit: Permit | None = None
    if body.audit_type == PtwAuditType.unpermitted_work:
        if body.permit_id is not None:
            raise validation_error("permit_id", "An unpermitted-work audit has no permit (AU-6).")
        if body.site_id is None:
            raise validation_error("site_id", "Enter the site of the unpermitted work.")
        if body.engagement_id is None:
            raise validation_error(
                "engagement_id", "Enter the contractor doing the unpermitted work."
            )
        if body.stop_work_issued_at is None:
            raise validation_error(
                "stop_work_issued_at", "Record when the work was stopped (AU-6)."
            )
        if not body.unpermitted_work_desc:
            raise validation_error("unpermitted_work_desc", "Describe the unpermitted work.")
        check_site_zone(db, project, body.site_id, body.zone_id)
        check_engagement(db, project, body.engagement_id)
        site_id, zone_id, eng_id = body.site_id, body.zone_id, body.engagement_id
    else:
        if body.permit_id is None:
            raise validation_error("permit_id", "A permit is required for this audit type.")
        permit = common.get_permit(db, p, body.permit_id)
        if permit.project_id != project_id:
            raise validation_error("permit_id", "The permit is not on this project.")
        if body.audit_type == PtwAuditType.field:
            from app.services.ptw import board  # noqa: PLC0415

            st = board.status_at(db, permit, body.audited_at)
            if st not in (S.issued, S.active, S.suspended):
                raise common.err(
                    ErrorCode.VALIDATION_ERROR,
                    "A field audit needs the permit Issued, Active or Suspended at the audit time (AU-1).",
                    "التدقيق الميداني يتطلب أن يكون التصريح صادراً أو سارياً أو موقوفاً وقت التدقيق.",
                    field="permit_id",
                )
        elif permit.status not in (S.closed, S.expired):
            raise validation_error(
                "permit_id", "A document review needs a Closed or Expired permit (AU-1)."
            )
        site_id = permit.site_id
        zids = list(permit.zone_ids or [])
        zone_id = body.zone_id if body.zone_id in zids else (zids[0] if zids else None)
        eng_id = permit.engagement_id
    acommon.require_cap(p, project_id, C.ptw_audit_conduct, [site_id], eng_id)
    if permit is not None:
        _sod(permit, p.user.id)
    year = acommon.local_day(body.audited_at).year
    seq = next_seq(db, PtwAudit, project_id, year)
    a = PtwAudit(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        seq=seq,
        audit_no=make_ref("PTA", project.code, year, seq, 5),
        audit_type=body.audit_type,
        permit_id=permit.id if permit else None,
        site_id=site_id,
        zone_id=zone_id,
        engagement_id=eng_id,
        auditor_user_id=p.user.id,
        audited_at=body.audited_at,
        items=[],
        stop_work_issued_at=body.stop_work_issued_at,
        unpermitted_work_desc=body.unpermitted_work_desc,
        status=PtwAuditStatus.draft,
        edit_log=[],
        created_by_user_id=p.user.id,
    )
    db.add(a)
    db.flush()
    applies = applicable_items(db, a.audit_type, permit, a.audited_at)
    items = list(body.items)
    if a.audit_type == PtwAuditType.unpermitted_work and not items:
        items = [AuditItemInput(code=AuditItem.A00, answer=AuditAnswer.non_compliant)]
    a.items = _merge_items(a, items, applies)
    _score(a, applies)
    _audit_log(
        db,
        p,
        a,
        AuditAction.create,
        None,
        {"audit_no": a.audit_no, "audit_type": a.audit_type.value},
    )
    _act_on_critical(db, p, a, at)
    db.flush()
    return to_read(db, a)


def _editable(p: Principal, a: PtwAudit, edit_reason: str | None) -> None:
    _lock_if_due(a)
    if a.status == PtwAuditStatus.locked:
        if not p.is_manager:
            raise common.err(
                ErrorCode.AUDIT_LOCKED,
                "This audit is locked (7 days after completion); only the HSE Manager may edit it with a reason.",
                "التدقيق مقفل؛ التعديل لمدير السلامة فقط مع ذكر السبب.",
                status=409,
            )
        if not edit_reason:
            raise validation_error("edit_reason", "Give the reason for editing a locked audit.")
        return
    if a.auditor_user_id != p.user.id and not p.is_manager:
        raise forbidden_error("Only the auditor edits this audit.")


def update(db: Session, p: Principal, audit_id: uuid.UUID, body: PtwAuditUpdate) -> PtwAuditRead:
    a = get_row(db, p, audit_id)
    if not p.is_manager:
        acommon.require_cap(p, a.project_id, C.ptw_audit_conduct, [a.site_id], a.engagement_id)
    _editable(p, a, body.edit_reason)
    at = now()
    before = {"items": a.items, "score_pct": str(a.score_pct) if a.score_pct is not None else None}
    if body.audited_at is not None:
        if body.audited_at > at + timedelta(minutes=5):
            raise validation_error("audited_at", "The audit time cannot be in the future.")
        a.audited_at = body.audited_at
    if body.stop_work_issued_at is not None:
        a.stop_work_issued_at = body.stop_work_issued_at
    if body.unpermitted_work_desc is not None:
        a.unpermitted_work_desc = body.unpermitted_work_desc
    applies = _applies(db, a)
    if body.items is not None:
        a.items = _merge_items(a, list(body.items), applies)
    a.items = [
        x for x in a.items or [] if x["code"] in applies or x.get("answer") == AuditAnswer.na.value
    ]
    _score(a, applies)
    if a.status != PtwAuditStatus.draft:
        a.edit_log = [
            *(a.edit_log or []),
            {"by": str(p.user.id), "at": at.isoformat(), "reason": body.edit_reason},
        ]
    a.updated_by_user_id = p.user.id
    _audit_log(
        db,
        p,
        a,
        AuditAction.update,
        before,
        {
            "items": a.items,
            "score_pct": str(a.score_pct) if a.score_pct is not None else None,
            "edit_reason": body.edit_reason,
        },
    )
    _act_on_critical(db, p, a, at)
    db.flush()
    return to_read(db, a)


def complete(
    db: Session, p: Principal, audit_id: uuid.UUID, body: PtwAuditCompleteInput
) -> PtwAuditRead:
    a = get_row(db, p, audit_id)
    if a.status != PtwAuditStatus.draft:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            f"{a.audit_no} is {a.status.value}.",
            "التدقيق ليس مسودة.",
            status=409,
        )
    if a.auditor_user_id != p.user.id:
        raise forbidden_error("Only the auditor completes the audit.")
    acommon.require_cap(p, a.project_id, C.ptw_audit_conduct, [a.site_id], a.engagement_id)
    applies = _applies(db, a)
    answered = {x["code"] for x in a.items or [] if x.get("answer")}
    missing_items = [c for c in applies if c not in answered]
    if missing_items:
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"Answer every applicable item first: {', '.join(missing_items)} (AU-3).",
            "أجب عن جميع البنود المنطبقة أولاً.",
            meta={"items": missing_items},
        )
    if a.audit_type == PtwAuditType.unpermitted_work and a.stop_work_issued_at is None:
        raise validation_error("stop_work_issued_at", "Record when the work was stopped (AU-6).")
    _link, missing = match_cas(db, a)
    if missing:
        raise common.err(
            ErrorCode.CA_REQUIRED,
            f"Raise a corrective action for {', '.join(missing)} first (AU-4/AU-5).",
            "أنشئ الإجراء التصحيحي المطلوب أولاً.",
            meta={"items": missing},
        )
    at = now()
    _score(a, applies)
    a.status = PtwAuditStatus.completed
    a.completed_at = at
    a.updated_by_user_id = p.user.id
    _audit_log(
        db,
        p,
        a,
        AuditAction.status_change,
        {"status": "draft"},
        {
            "status": "completed",
            "score_pct": str(a.score_pct) if a.score_pct is not None else None,
            "note": body.note,
        },
    )
    _act_on_critical(db, p, a, at)
    db.flush()
    return to_read(db, a)


# ---- CA source (1-dashboard v1.2) ----------------------------------------------------------------


def ca_source(db: Session, project_id: uuid.UUID, source_id: uuid.UUID) -> PtwAudit:
    a = db.get(PtwAudit, source_id)
    if a is None or a.project_id != project_id:
        raise validation_error("source_id", "The source record is not on this project.")
    return a


# ---- jobs ----------------------------------------------------------------------------------------


def behind_plan(db: Session, project_id: uuid.UUID, at: datetime) -> tuple[int, Decimal] | None:
    """AU-7: (completed field audits since week start, pro-rata target) when behind plan."""
    s = common.settings(db, project_id)
    day = acommon.local_day(at)
    from app.kpi.periods import week_start  # noqa: PLC0415
    from app.models import ProjectSettings  # noqa: PLC0415

    ps = db.get(ProjectSettings, project_id)
    start = week_start(day, ps.week_start) if ps else week_start(day, WeekStart.sunday)
    working = 5
    elapsed = min(working, (day - start).days + 1)
    target = (Decimal(s.ptw_audit_min_per_week) * elapsed / working).quantize(Decimal("0.1"))
    done = len(
        list(
            db.scalars(
                select(PtwAudit.id).where(
                    PtwAudit.project_id == project_id,
                    PtwAudit.audit_type == PtwAuditType.field,
                    PtwAudit.status.in_([PtwAuditStatus.completed, PtwAuditStatus.locked]),
                    PtwAudit.audited_at >= acommon.local_midnight_utc(start),
                )
            )
        )
    )
    return (done, target) if Decimal(done) < target else None


def daily_job(db: Session, at: datetime | None = None) -> int:
    """Locks audits 7 days after completion (§4.9)."""
    at = at or now()
    n = 0
    for a in db.scalars(select(PtwAudit).where(PtwAudit.status == PtwAuditStatus.completed)):
        before = a.status
        _lock_if_due(a, at)
        if a.status != before:
            n += 1
    return n
