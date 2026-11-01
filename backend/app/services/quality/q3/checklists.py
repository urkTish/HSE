"""Quality checklists of Q3 on the 6d engine (spec 8-quality §A.7 Q-CHK-01…04): the receiving
vehicle check `QRCV`, the reefer pre-load `QRPL`, warehouse hygiene `QHYG`, the pest visit `QPST`
and the return inspection `QRET` (kind `quality`, Appendix A.2), and the helper that scores a
response with `field.scoring.evaluate` and stores it as a `checklist_responses` row with a Q3
owner type (`store_answers`, as 7b does). Stop rules are not used (Q-CHK-02)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
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
from app.models import Project
from app.models.field import ChecklistResponse, ChecklistTemplate
from app.services.field import execution, scoring
from app.services.quality import common as qc

PUBLISHED = datetime(2026, 4, 1, 6, 0, tzinfo=UTC)

# code: (quality_type, title EN, title AR, items [(EN, AR, critical)])
TEMPLATES: dict[str, tuple[str, str, str, list[tuple[str, str, bool]]]] = {
    "QRCV": (
        "receiving",
        "Receiving vehicle check",
        "فحص مركبة الاستلام",
        [
            ("Reefer unit running and at setpoint", "وحدة التبريد تعمل وعلى درجة الضبط", True),
            ("Seal intact and matching the documents", "الختم سليم ومطابق للمستندات", True),
            ("No pest signs in the load space", "لا آثار آفات في صندوق الحمولة", True),
            ("Load space clean and odour-free", "صندوق الحمولة نظيف وخالٍ من الروائح", False),
            ("Doors, gaskets and insulation undamaged", "الأبواب والجوانات والعزل سليمة", False),
            ("Load secured, no crushed pallets", "الحمولة مثبتة ولا طبالي مسحوقة", False),
            ("Food and non-food separated", "فصل الأغذية عن غير الأغذية", False),
            ("Temperature record of the trip available", "سجل حرارة الرحلة متوفر", False),
            ("Delivery documents complete", "مستندات التسليم مكتملة", False),
            ("Driver hygiene acceptable", "نظافة السائق مقبولة", False),
            ("No water or condensation on cartons", "لا ماء أو تكاثف على الكراتين", False),
            ("Pallets in good condition", "الطبالي بحالة جيدة", False),
            (
                "Labels readable, Arabic label present",
                "الملصقات مقروءة والملصق العربي موجود",
                False,
            ),
            ("Dock door seal fitted during unloading", "عازل باب الرصيف مركب أثناء التفريغ", False),
            ("Unloading started within the dock slot", "بدأ التفريغ ضمن موعد الرصيف", False),
        ],
    ),
    "QRPL": (
        "reefer_preload",
        "Reefer pre-load check",
        "فحص الشاحنة المبردة قبل التحميل",
        [
            (
                "Pre-cooled: box temperature within the compartment range",
                "تبريد مسبق: حرارة الصندوق ضمن نطاق الحجرة",
                True,
            ),
            ("Clean and odour-free", "نظيف وخالٍ من الروائح", True),
            ("Doors, gaskets and insulation undamaged", "الأبواب والجوانات والعزل سليمة", True),
            ("Airflow clear (no blocked return air)", "مسار الهواء غير مسدود", True),
            ("Logger placed and scanned", "المسجل موضوع وممسوح", True),
            ("Seal applied after loading", "الختم مركب بعد التحميل", True),
            (
                "Reefer fuel or power sufficient for the trip",
                "وقود أو طاقة وحدة التبريد كافية",
                False,
            ),
            ("Load plan respects compartment classes", "خطة التحميل تراعي فئات الحجرات", False),
            ("No damaged pallets loaded", "لا طبالي تالفة محملة", False),
            ("Driver has the delivery documents", "مستندات التسليم مع السائق", False),
            ("Vehicle pre-use check done today", "فحص ما قبل الاستخدام منجز اليوم", False),
            (
                "Spare logger or display reading recorded",
                "قراءة الشاشة أو المسجل الاحتياطي مسجلة",
                False,
            ),
        ],
    ),
    "QHYG": (
        "hygiene",
        "Warehouse hygiene check",
        "فحص نظافة المستودع",
        [
            ("No pest evidence", "لا آثار للآفات", True),
            ("No product contamination", "لا تلوث للمنتجات", True),
            ("Chemicals stored away from food", "المواد الكيميائية بعيدة عن الأغذية", True),
        ]
        + [(f"Hygiene item {i}", f"بند نظافة {i}", False) for i in range(4, 21)],
    ),
    "QPST": (
        "pest_visit",
        "Pest-control visit",
        "زيارة مكافحة الآفات",
        [
            ("All stations serviced", "خدمة جميع المحطات", True),
            ("Only registered chemicals used", "استخدام مواد مسجلة فقط", True),
        ]
        + [(f"Pest visit item {i}", f"بند زيارة {i}", False) for i in range(3, 11)],
    ),
    "QRET": (
        "return_inspection",
        "Return inspection",
        "فحص المرتجعات",
        [
            (
                "Temperature history available for cold goods",
                "سجل الحرارة متوفر للبضائع المبردة",
                True,
            ),
            ("Packaging intact", "التغليف سليم", False),
            ("Seal or tamper evidence intact", "الختم أو دليل العبث سليم", False),
            ("Batch and expiry readable", "الدفعة والانتهاء مقروءة", False),
            ("Quantity matches the RMA", "الكمية مطابقة لتفويض الإرجاع", False),
            ("No pest signs", "لا آثار آفات", True),
            ("No odour or leakage", "لا رائحة أو تسرب", False),
            ("Segregated in the returns area", "معزول في منطقة المرتجعات", False),
        ],
    ),
}


def items_for(code: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _, _, _, rows = TEMPLATES[code]
    secs = [
        {"code": "A", "title_en": "Critical items", "title_ar": "البنود الحرجة", "order": 1},
        {"code": "B", "title_en": "General", "title_ar": "عام", "order": 2},
    ]
    items = []
    for n, (en, ar, crit) in enumerate(rows, start=1):
        items.append(
            {
                "item_code": f"{code}-{n:02d}",
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
                "reference": "8-quality Appendix A.2",
                "guidance_en": None,
                "guidance_ar": None,
            }
        )
    return secs, items


def ensure_templates(db: Session, author: uuid.UUID | None) -> dict[str, ChecklistTemplate]:
    out = {}
    for code, (qtype, en, ar, _) in TEMPLATES.items():
        t = db.scalar(
            select(ChecklistTemplate)
            .where(ChecklistTemplate.template_code == code)
            .order_by(ChecklistTemplate.version.desc())
            .limit(1)
        )
        if t is None:
            secs, items = items_for(code)
            t = ChecklistTemplate(
                id=uuid.uuid4(),
                template_code=code,
                version=1,
                kind=TemplateKind.quality,
                quality_type=qtype,
                sector_profiles="logistics",
                title_en=en,
                title_ar=ar,
                sections=secs,
                items=items,
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
        out[code] = t
    return out


def template(db: Session, quality_type: str, code: str | None = None) -> ChecklistTemplate:
    q = select(ChecklistTemplate).where(
        ChecklistTemplate.kind == TemplateKind.quality,
        ChecklistTemplate.quality_type == quality_type,
        ChecklistTemplate.status == VersionStatus.published,
        ChecklistTemplate.sector_profiles.in_(["logistics", "both"]),
    )
    if code:
        q = q.where(ChecklistTemplate.template_code == code)
    t = db.scalar(
        q.order_by(ChecklistTemplate.published_at.desc(), ChecklistTemplate.version.desc()).limit(1)
    )
    if t is None:
        if code is None and quality_type in {v[0] for v in TEMPLATES.values()}:
            ensure_templates(db, None)
            return template(
                db, quality_type, next(k for k, v in TEMPLATES.items() if v[0] == quality_type)
            )
        raise qc.field_err(
            "template_code",
            f"No published quality checklist of type {quality_type}.",
            "لا توجد قائمة فحص جودة منشورة لهذا النوع.",
        )
    return t


@dataclass
class Outcome:
    response: ChecklistResponse
    passed: bool
    critical_failures: list[str]


def respond(
    db: Session,
    user_id: uuid.UUID,
    project: Project,
    owner_type: ResponseOwnerType,
    quality_type: str,
    site_id: uuid.UUID,
    answers: list[Any],
    *,
    zone_id: uuid.UUID | None = None,
    code: str | None = None,
    completed_at: datetime | None = None,
) -> Outcome:
    """Score and store one quality checklist response (6d §6.1–§6.2)."""
    t = template(db, quality_type, code)
    raw = [a.model_dump(mode="json") if hasattr(a, "model_dump") else dict(a) for a in answers]
    sc = scoring.evaluate(t.items, raw, airside=True, require_all=True)
    pct = sc.pct
    passed = not (sc.critical_fails or (pct is not None and pct < t.pass_mark_pct))
    at = completed_at or now()
    r = ChecklistResponse(
        project_id=project.id,
        client_uuid=uuid.uuid4(),
        owner_type=owner_type,
        template_id=t.id,
        template_code=t.template_code,
        template_version=t.version,
        inspection_type=None,
        site_id=site_id,
        zone_id=zone_id,
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
    by_code = (
        {a.item_code: (i, a) for i, a in enumerate(answers)}
        if answers and hasattr(answers[0], "item_code")
        else {}
    )
    if by_code:
        r.answers = execution.store_answers(db, user_id, r, sc, by_code, [])
    else:
        r.answers = [
            {
                "item_code": ev.code,
                "answer": (ev.answer or {}).get("answer") if hasattr(ev, "answer") else None,
                "compliant": ev.compliant,
                "critical": ev.critical,
                "applicable": ev.applicable,
            }
            for ev in sc.evals
        ]
    crit = [ev.code for ev in sc.evals if ev.critical and ev.compliant is False]
    return Outcome(r, passed, crit)


def response_read(r: ChecklistResponse | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {
        "id": r.id,
        "template_code": r.template_code,
        "template_version": r.template_version,
        "completed_at": r.completed_at,
        "score_pct": r.score_pct,
        "result": r.result,
        "critical_fail_count": r.critical_fail_count,
        "answers": r.answers,
    }
