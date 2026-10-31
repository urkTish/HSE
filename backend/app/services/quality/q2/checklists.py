"""The MIR delivery checklist on the 6d engine (spec 8-quality §C.3.2, §A.7 Q-CHK-01…04):
template `QMIR` (kind `quality`, `quality_type` `mir_inspection`, construction), scored with
`field.scoring.evaluate` and stored as a `checklist_responses` row with owner type `q_mir`
(`execution.store_answers`, as 7b does). Stop rules are not used (Q-CHK-02); a critical failure
fails the response and warns when the MIR is decided."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.field_enums import (
    ItemType,
    ResponseOwnerType,
    ResponseResult,
    StopRule,
    TemplateKind,
    VersionStatus,
)
from app.core.quality.common import QChecklistType
from app.models import Project
from app.models.field import ChecklistResponse, ChecklistTemplate
from app.services.field import execution, scoring
from app.services.quality import common as qc
from app.services.quality import settings as qs

PUBLISHED = datetime(2026, 4, 1, 6, 0, tzinfo=UTC)
CODE = "QMIR"
QTYPE = QChecklistType.mir_inspection.value

# (EN, AR, critical)
ITEMS: list[tuple[str, str, bool]] = [
    (
        "Material matches the approved MAR (type, grade, manufacturer)",
        "المادة مطابقة لطلب الاعتماد (النوع والرتبة والمصنّع)",
        True,
    ),
    (
        "Mill / test certificates received and matching the tags",
        "شهادات المصنع والاختبار مستلمة ومطابقة للبطاقات",
        True,
    ),
    (
        "No visible damage, corrosion or contamination",
        "لا تلف أو صدأ أو تلوث ظاهر",
        True,
    ),
    ("Quantity matches the delivery note", "الكمية مطابقة لإشعار التسليم", False),
    ("Batch / heat / lot tags legible", "بطاقات الدفعة والصهر مقروءة", False),
    ("Packaging as specified", "التغليف حسب المواصفات", False),
    ("Shelf life / manufacture date acceptable", "مدة الصلاحية وتاريخ التصنيع مقبولان", False),
    (
        "Stored in the designated zone, off the ground and protected",
        "مخزنة في المنطقة المحددة مرفوعة عن الأرض ومحمية",
        False,
    ),
]


def items() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    secs = [
        {"code": "A", "title_en": "Critical items", "title_ar": "البنود الحرجة", "order": 1},
        {"code": "B", "title_en": "General", "title_ar": "عام", "order": 2},
    ]
    rows = []
    for n, (en, ar, crit) in enumerate(ITEMS, start=1):
        rows.append(
            {
                "item_code": f"{CODE}-{n:02d}",
                "section_code": "A" if crit else "B",
                "order": n,
                "text_en": en,
                "text_ar": ar,
                "item_type": ItemType.yes_no.value,
                "weight": 3 if crit else 1,
                "critical": crit,
                "stop_rule": StopRule.none.value,
                "na_allowed": not crit,
                "photo_required_on_fail": False,
                "default_severity": "minor",
                "airside_only": False,
                "numeric_rule": None,
                "options": None,
                "suggested_ca_en": None,
                "suggested_ca_ar": None,
                "suggested_control_level": None,
                "reference": "8-quality §C.3.2",
                "guidance_en": None,
                "guidance_ar": None,
            }
        )
    return secs, rows


def ensure_template(db: Session, author: uuid.UUID | None = None) -> ChecklistTemplate:
    t = db.scalar(
        select(ChecklistTemplate)
        .where(ChecklistTemplate.template_code == CODE)
        .order_by(ChecklistTemplate.version.desc())
        .limit(1)
    )
    if t is not None:
        return t
    secs, rows = items()
    t = ChecklistTemplate(
        id=uuid.uuid4(),
        template_code=CODE,
        version=1,
        kind=TemplateKind.quality,
        quality_type=QTYPE,
        sector_profiles="construction",
        title_en="Material delivery inspection",
        title_ar="فحص المواد الموردة",
        sections=secs,
        items=rows,
        zone_types=[],
        project_ids=[],
        pass_mark_pct=85,
        authored_by_user_id=author,
        published_by_user_id=author,
        published_at=PUBLISHED,
        status=VersionStatus.published,
        created_by_user_id=author,
        seed_fake=True,
    )
    db.add(t)
    db.flush()
    return t


def template(db: Session, project: Project, code: str | None = None) -> ChecklistTemplate:
    """Q-CHK-04: the named template, else the project's `checklist_default` for
    `mir_inspection`, else the latest Published construction template of that type (QMIR)."""
    wanted = code or (qs.value(db, project.id, "checklist_default") or {}).get(QTYPE)
    stmt = select(ChecklistTemplate).where(
        ChecklistTemplate.kind == TemplateKind.quality,
        ChecklistTemplate.quality_type == QTYPE,
        ChecklistTemplate.status == VersionStatus.published,
        ChecklistTemplate.sector_profiles.in_(["construction", "both"]),
    )
    if wanted:
        stmt = stmt.where(ChecklistTemplate.template_code == wanted)
    t = db.scalar(
        stmt.order_by(
            ChecklistTemplate.published_at.desc(), ChecklistTemplate.version.desc()
        ).limit(1)
    )
    if t is not None:
        return t
    if code:
        raise qc.field_err(
            "template_code",
            f"{code} is not a Published material inspection checklist.",
            "ليست قائمة فحص مواد منشورة.",
        )
    return ensure_template(db)


def respond(
    db: Session,
    user_id: uuid.UUID,
    project: Project,
    site_id: uuid.UUID,
    zone_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
    answers: list[Any],
    code: str | None = None,
    completed_at: datetime | None = None,
) -> ChecklistResponse:
    """Score and store one MIR checklist response (6d §6.1–§6.2)."""
    t = template(db, project, code)
    raw = [a.model_dump(mode="json") for a in answers]
    sc = scoring.evaluate(t.items, raw, airside=True, require_all=True)
    pct = sc.pct
    passed = not (sc.critical_fails or (pct is not None and pct < t.pass_mark_pct))
    at = completed_at or now()
    r = ChecklistResponse(
        project_id=project.id,
        client_uuid=uuid.uuid4(),
        owner_type=ResponseOwnerType.q_mir,
        template_id=t.id,
        template_code=t.template_code,
        template_version=t.version,
        inspection_type=None,
        site_id=site_id,
        zone_id=zone_id,
        engagement_id=engagement_id,
        airside=False,
        started_at=at,
        completed_at=at,
        completed_date=qc.project_day(project, at),
        received_at=now(),
        inspector_id=user_id,
        answers=[],
        applicable_count=sc.applicable_count,
        compliant_count=sc.compliant_count,
        applicable_weight=sc.applicable_weight,
        earned_weight=sc.earned_weight,
        score_pct=scoring.q(pct) if pct is not None else None,
        critical_fail_count=sc.critical_fails,
        result=ResponseResult.pass_ if passed else ResponseResult.fail,
        submitted=True,
        created_by_user_id=user_id,
    )
    db.add(r)
    db.flush()
    by_code = {a.item_code: (i, a) for i, a in enumerate(answers)}
    r.answers = execution.store_answers(db, user_id, r, sc, by_code, [])
    return r


def critical_failures(r: ChecklistResponse | None) -> list[str]:
    if r is None:
        return []
    return [
        str(a["item_code"])
        for a in r.answers or []
        if a.get("critical") and a.get("applicable") and a.get("compliant") is False
    ]


def read(db: Session, response_id: uuid.UUID | None) -> dict[str, Any] | None:
    r = db.get(ChecklistResponse, response_id) if response_id else None
    if r is None:
        return None
    t = db.get(ChecklistTemplate, r.template_id)
    texts = {it["item_code"]: it for it in (t.items if t else [])}
    return {
        "id": r.id,
        "template_code": r.template_code,
        "template_version": r.template_version,
        "completed_at": r.completed_at,
        "score_pct": str(r.score_pct) if r.score_pct is not None else None,
        "result": r.result.value if r.result else None,
        "critical_fail_count": r.critical_fail_count or 0,
        "critical_failures": critical_failures(r),
        "answers": [
            {
                "item_code": a["item_code"],
                "text_en": texts.get(a["item_code"], {}).get("text_en", ""),
                "text_ar": texts.get(a["item_code"], {}).get("text_ar", ""),
                "critical": bool(a.get("critical")),
                "answer": a.get("answer"),
                "compliant": a.get("compliant"),
                "note": a.get("note"),
            }
            for a in r.answers or []
        ],
    }


def template_read(db: Session, project: Project) -> dict[str, Any]:
    t = template(db, project)
    return {
        "template_code": t.template_code,
        "version": t.version,
        "title_en": t.title_en,
        "title_ar": t.title_ar,
        "items": [
            {
                "item_code": it["item_code"],
                "text_en": it["text_en"],
                "text_ar": it.get("text_ar") or "",
                "critical": bool(it.get("critical")),
                "na_allowed": bool(it.get("na_allowed")),
            }
            for it in sorted(t.items, key=lambda x: (x.get("section_code", ""), x.get("order", 0)))
        ],
    }
