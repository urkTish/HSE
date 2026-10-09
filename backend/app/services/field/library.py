"""Checklist template and toolbox topic libraries (spec 6d-field-assurance §3.1, §3.2, §3.10, §4.1,
TPL-1…TPL-6, TBT-1, TBT-2): org-wide, versioned, one Published version per code; Published versions
are immutable and a new version supersedes the previous one at publication."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.field_enums import (
    SCORED_TYPES,
    ItemType,
    StopRule,
    TemplateKind,
    TopicCategory,
    VersionAction,
    VersionStatus,
)
from app.core.hse_enums import InspectionType
from app.kpi.periods import add_months
from app.models import ChecklistTemplate, InspectionPlan, ToolboxTopic
from app.schemas.field import (
    TemplateCreate,
    TemplatePage,
    TemplateRead,
    TemplateUpdate,
    TopicCreate,
    TopicPage,
    TopicRead,
    TopicUpdate,
    VersionTransition,
)
from app.services import audit
from app.services.common import paginate
from app.services.field import common as fc
from app.services.permissions import Principal, forbidden_error

C = Capability
VS = VersionStatus


def review_due(published_at: datetime) -> date:
    """published_at + 24 months − 1 day (§3.1, §3.10)."""
    return add_months(fc.local_day(published_at), 24) - timedelta(days=1)


def _immutable() -> ApiError:
    return fc.err(
        409,
        ErrorCode.TEMPLATE_IMMUTABLE,
        "A Published version cannot be changed: create a new version (TPL-3).",
        "لا يمكن تعديل إصدار منشور: أنشئ إصداراً جديداً.",
    )


def _audit(
    db: Session, p: Principal, action: AuditAction, et: EntityType, obj: Any, **kw: Any
) -> None:
    audit.record(db, action, p.actor(None), entity_type=et, entity_id=obj.id, project_id=None, **kw)


# ---- templates -----------------------------------------------------------------------------------


def _normalise_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for raw in items:
        it = dict(raw)
        if it.get("critical"):
            it["photo_required_on_fail"] = True  # §3.2: forced true when critical
        out.append(it)
    return out


def template_read(db: Session, t: ChecklistTemplate) -> TemplateRead:
    items = t.items or []
    return TemplateRead.model_validate(
        {
            "id": t.id,
            "template_code": t.template_code,
            "version": t.version,
            "kind": t.kind,
            "inspection_type": t.inspection_type,
            "audit_type": t.audit_type,
            "title_en": t.title_en,
            "title_ar": t.title_ar or "",
            "sections": t.sections or [],
            "items": items,
            "zone_types": t.zone_types or [],
            "project_ids": t.project_ids or [],
            "pass_mark_pct": str(t.pass_mark_pct),
            "review_due_on": t.review_due_on,
            "review_overdue": t.review_due_on is not None and t.review_due_on < fc.local_day(),
            "change_note": t.change_note,
            "authored_by": fc.user_ref(db, t.authored_by_user_id),
            "published_by": fc.user_ref(db, t.published_by_user_id),
            "published_at": t.published_at,
            "status": t.status,
            "status_reason": t.status_reason,
            "item_count": len(items),
            "critical_count": sum(1 for i in items if i.get("critical")),
        }
    )


def get_template(db: Session, template_id: uuid.UUID) -> ChecklistTemplate:
    t = db.get(ChecklistTemplate, template_id)
    if t is None:
        raise not_found("Checklist template")
    return t


def published(db: Session, code: str, at: datetime | None = None) -> ChecklistTemplate | None:
    """The version Published at `at` (TPL-4); default the current Published version."""
    rows = list(
        db.scalars(
            select(ChecklistTemplate)
            .where(
                ChecklistTemplate.template_code == code,
                ChecklistTemplate.published_at.is_not(None),
            )
            .order_by(ChecklistTemplate.version.desc())
        )
    )
    for t in rows:
        if at is None:
            if t.status == VS.published:
                return t
            continue
        if (
            t.published_at is not None
            and t.published_at <= at
            and (t.superseded_at is None or t.superseded_at > at or t.status == VS.published)
        ):
            return t
    if at is not None:
        return published(db, code)
    return None


def offered(t: ChecklistTemplate, project_id: uuid.UUID) -> bool:
    """TPL-1: a template with project_ids is offered only on those projects."""
    return not t.project_ids or project_id in t.project_ids


def list_templates(
    db: Session,
    p: Principal,
    kind: TemplateKind | None,
    inspection_type: InspectionType | None,
    statuses: list[VersionStatus] | None,
    code: str | None,
    project_id: uuid.UUID | None,
    page: int,
    page_size: int,
) -> TemplatePage:
    p.require_any(C.field_library_view)
    T = ChecklistTemplate  # noqa: N806
    stmt = select(T)
    if kind:
        stmt = stmt.where(T.kind == kind)
    if inspection_type:
        stmt = stmt.where(T.inspection_type == inspection_type)
    if statuses:
        stmt = stmt.where(T.status.in_(statuses))
    if code:
        stmt = stmt.where(T.template_code == code)
    if project_id is not None:
        stmt = stmt.where(
            T.status == VS.published,
            (func.cardinality(T.project_ids) == 0) | T.project_ids.contains([project_id]),
        )
    items, total = paginate(db, stmt.order_by(T.template_code, T.version.desc()), page, page_size)
    return TemplatePage(
        items=[template_read(db, t) for t in items], total=total, page=page, page_size=page_size
    )


def read_template(db: Session, p: Principal, template_id: uuid.UUID) -> TemplateRead:
    p.require_any(C.field_library_view)
    return template_read(db, get_template(db, template_id))


def _next_version(db: Session, model: Any, col: Any, code: str) -> int:
    return int(db.scalar(select(func.max(model.version)).where(col == code)) or 0) + 1


def _no_open_draft(db: Session, model: Any, col: Any, code: str) -> None:
    if db.scalar(select(model.id).where(col == code, model.status == VS.draft)) is not None:
        raise fc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            f"{code} already has a Draft version.",
            "يوجد إصدار مسودة لهذا الرمز.",
        )


def create_template(db: Session, p: Principal, body: TemplateCreate) -> TemplateRead:
    p.require_any(C.field_library_author)
    p.ensure_writer()
    if body.kind == TemplateKind.inspection and body.inspection_type is None:
        raise validation_error("inspection_type", "Required for an inspection template.")
    if body.kind == TemplateKind.audit and body.audit_type is None:
        raise validation_error("audit_type", "Required for an audit template.")
    T = ChecklistTemplate  # noqa: N806
    prev = db.scalar(select(T).where(T.template_code == body.template_code).limit(1))
    if prev is not None and prev.kind != body.kind:
        raise validation_error("kind", "The code is used by a template of another kind.")
    _no_open_draft(db, T, T.template_code, body.template_code)
    version = _next_version(db, T, T.template_code, body.template_code)
    data = body.model_dump(mode="json")
    t = T(
        template_code=body.template_code,
        version=version,
        kind=body.kind,
        inspection_type=body.inspection_type if body.kind == TemplateKind.inspection else None,
        audit_type=body.audit_type if body.kind == TemplateKind.audit else None,
        title_en=body.title_en,
        title_ar=body.title_ar,
        sections=data["sections"],
        items=_normalise_items(data["items"]),
        zone_types=data["zone_types"],
        project_ids=body.project_ids,
        pass_mark_pct=body.pass_mark_pct,
        change_note=body.change_note,
        authored_by_user_id=p.user.id,
        status=VS.draft,
        created_by_user_id=p.user.id,
        alerts_sent=[],
    )
    db.add(t)
    db.flush()
    _audit(db, p, AuditAction.create, EntityType.checklist_template, t,
           after={"code": t.template_code, "version": t.version})  # fmt: skip
    return template_read(db, t)


def update_template(
    db: Session, p: Principal, template_id: uuid.UUID, body: TemplateUpdate
) -> TemplateRead:
    p.require_any(C.field_library_author)
    p.ensure_writer()
    t = get_template(db, template_id)
    if t.status != VS.draft:
        raise _immutable()
    data = body.model_dump(mode="json", exclude_unset=True)
    for k, raw in data.items():
        v: Any = raw
        if k == "items":
            v = _normalise_items(raw)
        if k == "project_ids":
            v = body.project_ids or []
        if k == "pass_mark_pct":
            v = body.pass_mark_pct
        if v is None and k in ("title_en", "sections", "items", "zone_types", "pass_mark_pct"):
            continue
        setattr(t, k, v)
    t.updated_by_user_id = p.user.id
    db.flush()
    _audit(db, p, AuditAction.update, EntityType.checklist_template, t, after=data)
    return template_read(db, t)


def delete_template(db: Session, p: Principal, template_id: uuid.UUID) -> None:
    t = get_template(db, template_id)
    if t.authored_by_user_id != p.user.id:
        p.require_any(C.field_library_publish)
    if t.status != VS.draft:
        raise _immutable()
    _audit(db, p, AuditAction.archive, EntityType.checklist_template, t)
    db.delete(t)
    db.flush()


def new_version(db: Session, p: Principal, template_id: uuid.UUID) -> TemplateRead:
    p.require_any(C.field_library_author)
    src = get_template(db, template_id)
    T = ChecklistTemplate  # noqa: N806
    _no_open_draft(db, T, T.template_code, src.template_code)
    t = T(
        template_code=src.template_code,
        version=_next_version(db, T, T.template_code, src.template_code),
        kind=src.kind,
        inspection_type=src.inspection_type,
        audit_type=src.audit_type,
        title_en=src.title_en,
        title_ar=src.title_ar,
        sections=list(src.sections or []),
        items=list(src.items or []),
        zone_types=list(src.zone_types or []),
        project_ids=list(src.project_ids or []),
        pass_mark_pct=src.pass_mark_pct,
        authored_by_user_id=p.user.id,
        status=VS.draft,
        created_by_user_id=p.user.id,
        alerts_sent=[],
    )
    db.add(t)
    db.flush()
    _audit(db, p, AuditAction.create, EntityType.checklist_template, t,
           after={"code": t.template_code, "version": t.version, "from": src.version})  # fmt: skip
    return template_read(db, t)


def completeness(t: ChecklistTemplate) -> list[str]:
    """TPL-2: every failure listed."""
    miss: list[str] = []
    items = t.items or []
    if not (t.title_en or "").strip() or not (t.title_ar or "").strip():
        miss.append("title: EN and AR required")
    if not t.sections:
        miss.append("sections: at least one")
    for s in t.sections or []:
        if not (s.get("title_en") or "").strip() or not (s.get("title_ar") or "").strip():
            miss.append(f"section {s.get('code')}: EN and AR title required")
    if not any(ItemType(i["item_type"]) in SCORED_TYPES for i in items):
        miss.append("items: at least one scored item")
    codes = [i["item_code"] for i in items]
    for c in sorted({c for c in codes if codes.count(c) > 1}):
        miss.append(f"{c}: item code not unique")
    for i in items:
        c = i["item_code"]
        it = ItemType(i["item_type"])
        if not (i.get("text_en") or "").strip() or not (i.get("text_ar") or "").strip():
            miss.append(f"{c}: EN and AR text required")
        if not 1 <= int(i.get("weight") or 0) <= 5:
            miss.append(f"{c}: weight 1–5")
        if it == ItemType.numeric and not i.get("numeric_rule"):
            miss.append(f"{c}: numeric_rule required")
        if it == ItemType.single_select and not 2 <= len(i.get("options") or []) <= 8:
            miss.append(f"{c}: 2–8 options required")
        if i.get("stop_rule") == StopRule.stop_work.value and not i.get("critical"):
            miss.append(f"{c}: stop_work only on critical items")
        if i.get("critical") and it not in SCORED_TYPES:
            miss.append(f"{c}: critical only on scored items")
    return miss


def transition_template(
    db: Session, p: Principal, template_id: uuid.UUID, body: VersionTransition
) -> TemplateRead:
    p.require_any(C.field_library_publish)
    p.ensure_writer()
    t = get_template(db, template_id)
    at = now()
    src = t.status
    if body.action == VersionAction.publish:
        if t.status != VS.draft:
            raise fc.err(409, ErrorCode.INVALID_TRANSITION, "Only a Draft is published.",
                         "يُنشر الإصدار المسودة فقط.")  # fmt: skip
        miss = completeness(t)
        if miss:
            raise fc.err(
                422,
                ErrorCode.TEMPLATE_INCOMPLETE,
                "The template is incomplete: " + "; ".join(miss),
                "النموذج غير مكتمل.",
                missing=miss,
            )
        for old in db.scalars(
            select(ChecklistTemplate).where(
                ChecklistTemplate.template_code == t.template_code,
                ChecklistTemplate.status == VS.published,
            )
        ):
            old.status = VS.superseded
            old.superseded_at = at
        t.status = VS.published
        t.published_at = at
        t.published_by_user_id = p.user.id
        t.review_due_on = review_due(at)
    else:
        if t.status != VS.published:
            raise fc.err(409, ErrorCode.INVALID_TRANSITION, "Only a Published version is retired.",
                         "يتم إيقاف الإصدار المنشور فقط.")  # fmt: skip
        why = fc.reason(body.reason, 20)
        used = db.scalar(
            select(InspectionPlan.id).where(
                InspectionPlan.template_code == t.template_code, InspectionPlan.active.is_(True)
            )
        )
        if used is not None:
            raise fc.err(
                422,
                ErrorCode.TEMPLATE_IN_USE,
                f"{t.template_code} is used by an active inspection plan (TPL-5).",
                "النموذج مستخدم في خطة تفتيش نشطة.",
            )
        t.status = VS.retired
        t.status_reason = why
    t.updated_by_user_id = p.user.id
    db.flush()
    _audit(db, p, AuditAction.status_change, EntityType.checklist_template, t,
           before={"status": src.value}, after={"status": t.status.value})  # fmt: skip
    return template_read(db, t)


# ---- topics --------------------------------------------------------------------------------------


def topic_read(t: ToolboxTopic) -> TopicRead:
    return TopicRead.model_validate(
        {
            "id": t.id,
            "topic_code": t.topic_code,
            "version": t.version,
            "category": t.category,
            "title_en": t.title_en,
            "title_ar": t.title_ar or "",
            "key_points_en": t.key_points_en or [],
            "key_points_ar": t.key_points_ar or [],
            "translations": t.translations or [],
            "linked_refs": t.linked_refs or [],
            "review_due_on": t.review_due_on,
            "review_overdue": t.review_due_on is not None and t.review_due_on < fc.local_day(),
            "published_at": t.published_at,
            "status": t.status,
            "status_reason": t.status_reason,
        }
    )


def get_topic(db: Session, topic_id: uuid.UUID) -> ToolboxTopic:
    t = db.get(ToolboxTopic, topic_id)
    if t is None:
        raise not_found("Toolbox topic")
    return t


def list_topics(
    db: Session,
    p: Principal,
    category: TopicCategory | None,
    statuses: Sequence[VersionStatus] | None,
    code: str | None,
    page: int,
    page_size: int,
) -> TopicPage:
    p.require_any(C.field_library_view)
    T = ToolboxTopic  # noqa: N806
    stmt = select(T)
    if category:
        stmt = stmt.where(T.category == category)
    if statuses:
        stmt = stmt.where(T.status.in_(statuses))
    if code:
        stmt = stmt.where(T.topic_code == code)
    items, total = paginate(db, stmt.order_by(T.topic_code, T.version.desc()), page, page_size)
    return TopicPage(
        items=[topic_read(t) for t in items], total=total, page=page, page_size=page_size
    )


def read_topic(db: Session, p: Principal, topic_id: uuid.UUID) -> TopicRead:
    p.require_any(C.field_library_view)
    return topic_read(get_topic(db, topic_id))


def create_topic(db: Session, p: Principal, body: TopicCreate) -> TopicRead:
    p.require_any(C.field_library_author)
    p.ensure_writer()
    T = ToolboxTopic  # noqa: N806
    _no_open_draft(db, T, T.topic_code, body.topic_code)
    data = body.model_dump(mode="json")
    t = T(
        topic_code=body.topic_code,
        version=_next_version(db, T, T.topic_code, body.topic_code),
        category=body.category,
        title_en=body.title_en,
        title_ar=body.title_ar,
        key_points_en=data["key_points_en"],
        key_points_ar=data["key_points_ar"],
        translations=data["translations"],
        linked_refs=data["linked_refs"],
        authored_by_user_id=p.user.id,
        status=VS.draft,
        created_by_user_id=p.user.id,
        alerts_sent=[],
    )
    db.add(t)
    db.flush()
    _audit(db, p, AuditAction.create, EntityType.toolbox_topic, t,
           after={"code": t.topic_code, "version": t.version})  # fmt: skip
    return topic_read(t)


def update_topic(db: Session, p: Principal, topic_id: uuid.UUID, body: TopicUpdate) -> TopicRead:
    p.require_any(C.field_library_author)
    p.ensure_writer()
    t = get_topic(db, topic_id)
    if t.status != VS.draft:
        raise _immutable()
    data = body.model_dump(mode="json", exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            setattr(t, k, v)
    t.updated_by_user_id = p.user.id
    db.flush()
    _audit(db, p, AuditAction.update, EntityType.toolbox_topic, t, after=data)
    return topic_read(t)


def delete_topic(db: Session, p: Principal, topic_id: uuid.UUID) -> None:
    t = get_topic(db, topic_id)
    if t.authored_by_user_id != p.user.id:
        p.require_any(C.field_library_publish)
    if t.status != VS.draft:
        raise _immutable()
    _audit(db, p, AuditAction.archive, EntityType.toolbox_topic, t)
    db.delete(t)
    db.flush()


def new_topic_version(db: Session, p: Principal, topic_id: uuid.UUID) -> TopicRead:
    p.require_any(C.field_library_author)
    src = get_topic(db, topic_id)
    T = ToolboxTopic  # noqa: N806
    _no_open_draft(db, T, T.topic_code, src.topic_code)
    t = T(
        topic_code=src.topic_code,
        version=_next_version(db, T, T.topic_code, src.topic_code),
        category=src.category,
        title_en=src.title_en,
        title_ar=src.title_ar,
        key_points_en=list(src.key_points_en or []),
        key_points_ar=list(src.key_points_ar or []),
        translations=list(src.translations or []),
        linked_refs=list(src.linked_refs or []),
        authored_by_user_id=p.user.id,
        status=VS.draft,
        created_by_user_id=p.user.id,
        alerts_sent=[],
    )
    db.add(t)
    db.flush()
    return topic_read(t)


def transition_topic(
    db: Session, p: Principal, topic_id: uuid.UUID, body: VersionTransition
) -> TopicRead:
    p.require_any(C.field_library_publish)
    p.ensure_writer()
    t = get_topic(db, topic_id)
    src = t.status
    at = now()
    if body.action == VersionAction.publish:
        if t.status != VS.draft:
            raise fc.err(409, ErrorCode.INVALID_TRANSITION, "Only a Draft is published.",
                         "يُنشر الإصدار المسودة فقط.")  # fmt: skip
        miss: list[str] = []
        if not (t.title_en or "").strip() or not (t.title_ar or "").strip():
            miss.append("title: EN and AR required")
        for lang in ("en", "ar"):
            pts = [x for x in (getattr(t, f"key_points_{lang}") or []) if str(x).strip()]
            if not 3 <= len(pts) <= 10:
                miss.append(f"key_points_{lang}: 3–10 points")
        if miss:
            raise fc.err(422, ErrorCode.TOPIC_INCOMPLETE, "The topic is incomplete: "
                         + "; ".join(miss), "الموضوع غير مكتمل.", missing=miss)  # fmt: skip
        for old in db.scalars(
            select(ToolboxTopic).where(
                ToolboxTopic.topic_code == t.topic_code, ToolboxTopic.status == VS.published
            )
        ):
            old.status = VS.superseded
        t.status = VS.published
        t.published_at = at
        t.published_by_user_id = p.user.id
        t.review_due_on = review_due(at)
    else:
        if t.status != VS.published:
            raise fc.err(409, ErrorCode.INVALID_TRANSITION, "Only a Published version is retired.",
                         "يتم إيقاف الإصدار المنشور فقط.")  # fmt: skip
        t.status = VS.retired
        t.status_reason = fc.reason(body.reason, 20)
    db.flush()
    _audit(db, p, AuditAction.status_change, EntityType.toolbox_topic, t,
           before={"status": src.value}, after={"status": t.status.value})  # fmt: skip
    return topic_read(t)


def require_view(p: Principal) -> None:
    if not p.has_any(C.field_library_view):
        raise forbidden_error()
