"""Acceptance criteria library (spec 8-quality §A.6, Q-CRT-01…03): org-wide, versioned like 6d
templates (draft → published → superseded / retired; author 240, publish 239). A record that uses
a criterion pins the version row, so publishing a new version never changes past verdicts.

`evaluate` handles the simple kinds; kind `rule` calls the coded evaluator registered by a part in
`registry.CRITERIA_EVALUATORS` (e.g. Q2's `aci318_strength`). Comparisons use unrounded values and
boundaries are inclusive."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.quality.common import QCriterionKind, QCriterionStatus, QProfileScope, QVerdict
from app.models.quality import QCriterion
from app.services import audit
from app.services.common import paginate
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import registry as reg

C = Capability
K = QCriterionKind
ST = QCriterionStatus
NUM_FIELDS = ("min_value", "max_value", "target", "tol_minus", "tol_plus")
EDITABLE = (
    "title_en",
    "title_ar",
    "profile",
    "kind",
    "unit",
    *NUM_FIELDS,
    "rule_code",
    "params",
    "reference",
    "note_en",
    "note_ar",
    "project_ids",
)


def _d(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _v(verdict: QVerdict, en: str, ar: str, **detail: Any) -> reg.Verdict:
    return reg.Verdict(verdict, en, ar, detail)


def evaluate(c: QCriterion, values: dict[str, Any]) -> reg.Verdict:
    """Q-CRT-01 verdict pass · fail · indicative · not_evaluable with the reason in EN / AR."""
    if c.kind in (K.pass_fail, K.text):
        given = values.get("verdict")
        if given in ("pass", "fail"):
            return _v(
                QVerdict(given), "Verdict entered by the inspector.", "النتيجة أدخلها المفتش."
            )
        return _v(QVerdict.not_evaluable, "No verdict entered.", "لم تُدخل نتيجة.")
    if c.kind == K.rule:
        fn = reg.CRITERIA_EVALUATORS.get(c.rule_code or "")
        if fn is None:
            return _v(
                QVerdict.not_evaluable,
                f"Rule {c.rule_code} is not installed.",
                "القاعدة غير مثبتة.",
            )
        return fn(dict(c.params or {}), values)
    v = _d(values.get("value"))
    if v is None:
        return _v(QVerdict.not_evaluable, "No value entered.", "لم تُدخل قيمة.")
    lo: Decimal | None
    hi: Decimal | None
    if c.kind == K.range:
        lo, hi = c.min_value, c.max_value
    elif c.kind == K.min:
        lo, hi = c.min_value, None
    elif c.kind == K.max:
        lo, hi = None, c.max_value
    else:  # target_tolerance
        if c.target is None:
            return _v(QVerdict.not_evaluable, "The criterion has no target.", "لا قيمة مستهدفة.")
        lo = c.target - (c.tol_minus or Decimal(0))
        hi = c.target + (c.tol_plus or Decimal(0))
    ok = (lo is None or v >= lo) and (hi is None or v <= hi)
    unit = f" {c.unit}" if c.unit else ""
    lim = " – ".join(str(x) for x in (lo, hi) if x is not None)
    if ok:
        return _v(
            QVerdict.pass_,
            f"{v}{unit} within {lim}{unit}.",
            f"{v}{unit} ضمن {lim}{unit}.",
            low=lo,
            high=hi,
        )
    return _v(
        QVerdict.fail,
        f"{v}{unit} outside {lim}{unit}.",
        f"{v}{unit} خارج {lim}{unit}.",
        low=lo,
        high=hi,
    )


def read(c: QCriterion) -> dict[str, Any]:
    return {
        "id": c.id,
        "code": c.code,
        "version": c.version,
        "title_en": c.title_en,
        "title_ar": c.title_ar,
        "profile": c.profile,
        "kind": c.kind,
        "unit": c.unit,
        **{k: (str(getattr(c, k)) if getattr(c, k) is not None else None) for k in NUM_FIELDS},
        "rule_code": c.rule_code,
        "params": c.params or {},
        "reference": c.reference,
        "note_en": c.note_en,
        "note_ar": c.note_ar,
        "project_ids": list(c.project_ids or []),
        "status": c.status,
        "status_reason": c.status_reason,
        "published_at": c.published_at,
        "rule_installed": c.kind != K.rule or (c.rule_code or "") in reg.CRITERIA_EVALUATORS,
    }


def _view(p: Principal) -> None:
    if not (p.has_any(C.quality_view) or p.has_any(C.quality_author)):
        p.require_any(C.quality_view)


def list_page(
    db: Session,
    p: Principal,
    page: int,
    page_size: int,
    *,
    code: str | None = None,
    statuses: list[QCriterionStatus] | None = None,
    profile: QProfileScope | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    _view(p)
    stmt = select(QCriterion)
    if code:
        stmt = stmt.where(QCriterion.code == code.upper())
    if statuses:
        stmt = stmt.where(QCriterion.status.in_(statuses))
    if profile:
        stmt = stmt.where(QCriterion.profile.in_([profile, QProfileScope.both]))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(QCriterion.code.ilike(like) | QCriterion.title_en.ilike(like))
    items, total = paginate(
        db, stmt.order_by(QCriterion.code, QCriterion.version.desc()), page, page_size
    )
    return {"items": [read(c) for c in items], "total": total, "page": page, "page_size": page_size}


def get(db: Session, criterion_id: uuid.UUID) -> QCriterion:
    c = db.get(QCriterion, criterion_id)
    if c is None:
        raise not_found("Criterion")
    return c


def read_one(db: Session, p: Principal, criterion_id: uuid.UUID) -> dict[str, Any]:
    _view(p)
    return read(get(db, criterion_id))


def _check(c: QCriterion) -> None:
    for k in NUM_FIELDS:
        v = getattr(c, k)
        if v is not None and not isinstance(v, Decimal):
            setattr(c, k, _d(v))
    need = {
        K.range: ("min_value", "max_value"),
        K.min: ("min_value",),
        K.max: ("max_value",),
        K.target_tolerance: ("target", "tol_minus", "tol_plus"),
    }.get(c.kind, ())
    missing = [k for k in need if getattr(c, k) is None]
    if missing:
        raise qc.field_err(missing[0], f"{', '.join(missing)} required for kind {c.kind.value}.")
    if (
        c.kind == K.range
        and c.min_value is not None
        and c.max_value is not None
        and c.min_value > c.max_value
    ):
        raise qc.field_err("max_value", "max must be ≥ min.")
    if c.kind == K.rule and not c.rule_code:
        raise qc.field_err("rule_code", "A rule code is required for kind rule.")


def _immutable() -> Any:
    return qc.err(
        409,
        ErrorCode.CRITERION_IMMUTABLE,
        "Only a Draft criterion version can be changed; create a new version.",
        "يمكن تعديل الإصدار المسودة فقط؛ أنشئ إصداراً جديداً.",
    )


def create(db: Session, p: Principal, body: dict[str, Any]) -> dict[str, Any]:
    p.require_any(C.quality_author)
    code = str(body["code"]).strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{3,20}", code):
        raise qc.field_err("code", "Code: 3–20 capital letters, digits or -.")
    if db.scalar(select(QCriterion.id).where(QCriterion.code == code)):
        from app.services.common import duplicate  # noqa: PLC0415

        raise duplicate("code", "This code exists; create a new version instead.")
    c = QCriterion(
        code=code,
        version=1,
        status=ST.draft,
        created_by_user_id=p.user.id,
        params={},
        project_ids=[],
    )
    for k in EDITABLE:
        if k in body and body[k] is not None:
            setattr(c, k, body[k])
    c.kind = K(c.kind)
    c.profile = QProfileScope(c.profile or "both")
    _check(c)
    db.add(c)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(None),
        entity_type=EntityType.q_criterion,
        entity_id=c.id,
        after={"code": c.code, "version": 1},
    )
    return read(c)


def update(
    db: Session, p: Principal, criterion_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    p.require_any(C.quality_author)
    c = get(db, criterion_id)
    if c.status != ST.draft:
        raise _immutable()
    for k in EDITABLE:
        if k in body:
            setattr(c, k, body[k])
    c.kind = K(c.kind)
    c.profile = QProfileScope(c.profile or "both")
    _check(c)
    c.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(None),
        entity_type=EntityType.q_criterion,
        entity_id=c.id,
        after={k: body[k] for k in body if k in EDITABLE},
    )
    return read(c)


def new_version(db: Session, p: Principal, criterion_id: uuid.UUID) -> dict[str, Any]:
    p.require_any(C.quality_author)
    src = get(db, criterion_id)
    if db.scalar(
        select(QCriterion.id).where(QCriterion.code == src.code, QCriterion.status == ST.draft)
    ):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            f"{src.code} already has a Draft.",
            "يوجد إصدار مسودة لهذا الرمز.",
        )
    ver = int(
        db.scalar(select(func.max(QCriterion.version)).where(QCriterion.code == src.code)) or 0
    )
    c = QCriterion(code=src.code, version=ver + 1, status=ST.draft, created_by_user_id=p.user.id)
    for k in EDITABLE:
        setattr(c, k, getattr(src, k))
    db.add(c)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(None),
        entity_type=EntityType.q_criterion,
        entity_id=c.id,
        after={"code": c.code, "version": c.version, "from": src.version},
    )
    return read(c)


def transition(
    db: Session, p: Principal, criterion_id: uuid.UUID, action: str, why: str | None
) -> dict[str, Any]:
    """publish (239; supersedes the Published version) · retire (239, reason ≥ 20)."""
    p.require_any(C.quality_settings)
    c = get(db, criterion_id)
    src = c.status
    if action == "publish":
        if c.status != ST.draft:
            raise qc.err(
                409,
                ErrorCode.INVALID_TRANSITION,
                "Only a Draft is published.",
                "يُنشر الإصدار المسودة فقط.",
            )
        _check(c)
        if not (c.title_en or "").strip() or not (c.title_ar or "").strip():
            raise qc.field_err("title_ar", "EN and AR titles are required to publish.")
        for old in db.scalars(
            select(QCriterion).where(QCriterion.code == c.code, QCriterion.status == ST.published)
        ):
            old.status = ST.superseded
        c.status = ST.published
        c.published_at = now()
        c.published_by_user_id = p.user.id
    elif action == "retire":
        if c.status != ST.published:
            raise qc.err(
                409,
                ErrorCode.INVALID_TRANSITION,
                "Only a Published version is retired.",
                "يتم إيقاف الإصدار المنشور فقط.",
            )
        c.status = ST.retired
        c.status_reason = qc.reason(why, 20)
    else:
        raise qc.field_err("action", "publish or retire")
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(None),
        entity_type=EntityType.q_criterion,
        entity_id=c.id,
        before={"status": src},
        after={"status": c.status},
    )
    return read(c)


def evaluate_api(
    db: Session, p: Principal, criterion_id: uuid.UUID, values: dict[str, Any]
) -> dict[str, Any]:
    _view(p)
    c = get(db, criterion_id)
    v = evaluate(c, values)
    return {
        "criterion_id": c.id,
        "code": c.code,
        "version": c.version,
        "verdict": v.verdict,
        "reason_en": v.reason_en,
        "reason_ar": v.reason_ar,
    }
