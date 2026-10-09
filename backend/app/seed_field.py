"""Phase 6d seed (spec 6d-field-assurance Appendix A): settings, the 15 checklist templates (GSI at
v3), 24 toolbox topics, plan templates and rotation, checklist responses for every inspection
completed since 2026-09-01 (through the execution service, so findings, repeats, CAs and the
stop-work order follow the rules), the named stop-work order and critical fail, the audit history
and the two September audits (FD2), the September register talks (K-36 = the daily returns) and the
two campaigns. Differences from FD9 forced by the Phase 0–6c world are recorded in DECISIONS.

Fictional; refs contain TEST where printed. Notifications and e-mails raised while seeding are
removed at the end (as the other seeds insert without alerts)."""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.core.field_enums import (
    AuditStatus,
    AuditType,
    CampaignReason,
    CampaignStatus,
    InstructedRole,
    ItemType,
    StopRule,
    TalkShift,
    TalkStatus,
    TemplateKind,
    TopicCategory,
    UnderstoodLanguage,
    VersionStatus,
)
from app.core.hse_enums import CaStatus, InspectionStatus, InspectionType
from app.models import (
    BriefingCampaign,
    ChecklistTemplate,
    CorrectiveAction,
    Deployment,
    EmailMessage,
    FieldAudit,
    Incident,
    Inspection,
    InspectionPlan,
    Notification,
    Project,
    StopWorkOrder,
    TalkAttendance,
    ToolboxTalk,
    ToolboxTopic,
    User,
    Worker,
    WorkforceReturn,
)
from app.seed_heat import Ctx
from app.services.field import common as fc

RIYADH = ZoneInfo("Asia/Riyadh")
SEED_CLOCK = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)
FROM = date(2026, 9, 1)
PUB = datetime(2026, 4, 1, 6, 0, tzinfo=UTC)
PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
).decode()


def at(d: date, h: int, mi: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, mi, tzinfo=RIYADH).astimezone(UTC)


def already_seeded(db: Session) -> bool:
    return db.scalar(select(ChecklistTemplate.id).limit(1)) is not None


def _h(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _u(*parts: Any) -> uuid.UUID:
    return uuid.UUID(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:32])


# ---- A.2 libraries -------------------------------------------------------------------------------

GSI_ITEMS = [
    ("Site access controlled and signage at the gates", "ضبط الدخول ولوحات الإرشاد عند البوابات"),
    ("Welfare facilities available at the work front", "مرافق الراحة متوفرة في موقع العمل"),
    ("PPE worn as required for the task", "ارتداء معدات الوقاية المطلوبة"),
    ("Permits displayed at the work fronts", "التصاريح معروضة في مواقع العمل"),
    ("Slab edges and floor openings protected", "حماية حواف البلاطات وفتحات الأرضيات"),
    ("Ladders and temporary stairs in good condition", "السلالم بحالة جيدة"),
    ("Scaffold tags visible at access points", "بطاقات السقالات ظاهرة"),
    ("Materials stacked stable and secured", "تخزين المواد بشكل مستقر"),
    ("Excavation edges barricaded with safe access", "حواجز حول الحفريات ووسيلة نزول آمنة"),
    (
        "Hot work area clear of combustibles",
        "منطقة الأعمال الساخنة خالية من المواد القابلة للاشتعال",
    ),
    ("Fire extinguishers available at the work point", "طفايات الحريق متوفرة"),
    ("Housekeeping and access routes clear", "النظافة وممرات الحركة خالية"),
    (
        "Temporary electrical: RCD protection, no damaged cables",
        "الكهرباء المؤقتة: قاطع تسرب ولا كابلات تالفة",
    ),
    ("Hand tools in good condition", "العدد اليدوية بحالة جيدة"),
    ("Gas cylinders secured upright", "أسطوانات الغاز مثبتة عمودياً"),
    ("Noise and dust controls in place", "ضوابط الضوضاء والغبار مطبقة"),
    ("Lifting exclusion zone in place", "منطقة حظر الرفع مطبقة"),
    ("Pedestrian and vehicle routes segregated", "فصل مسارات المشاة والمركبات"),
    ("Signage and barriers in place", "اللوحات والحواجز في مكانها"),
    ("Lighting adequate for the task", "الإنارة كافية"),
    ("Night work lighting towers positioned", "أبراج الإنارة الليلية في مكانها"),
    ("Waste segregated and removed", "فرز النفايات وإزالتها"),
    ("FOD control at the work area", "ضبط الأجسام الغريبة في منطقة العمل"),
    ("Vehicle beacons on, airside rules followed", "أضواء المركبات تعمل والالتزام بقواعد الساحة"),
]

# code: (kind, inspection_type / audit_type, EN, AR, n items, n sections, item type,
#        criticals {n: (EN, AR, stop, weight)}, extras)
TPL: dict[str, tuple[Any, ...]] = {
    "SCA": (
        TemplateKind.inspection,
        InspectionType.scaffold,
        "Scaffold area and use",
        "منطقة السقالات واستخدامها",
        12,
        2,
        {
            2: (
                "Scaffold in use shows a green Phase 4 tag",
                "السقالة المستخدمة تحمل بطاقة خضراء",
                True,
            ),
            7: ("Edge protection on working platforms", "حماية الحواف على منصات العمل", False),
        },
    ),
    "EXC": (
        TemplateKind.inspection,
        InspectionType.excavation,
        "Excavation",
        "الحفريات",
        14,
        2,
        {
            3: (
                "Protective system in place for depth ≥ 1.2 m",
                "نظام حماية للحفر بعمق 1.2 م أو أكثر",
                True,
            ),
            6: ("Safe access within 7.5 m travel", "وسيلة نزول آمنة كل 7.5 م", False),
        },
    ),
    "ELD": (
        TemplateKind.inspection,
        InspectionType.electrical,
        "Electrical distribution",
        "التوزيع الكهربائي",
        12,
        2,
        {
            2: ("DBs locked, covers on, live parts shielded", "لوحات التوزيع مقفلة ومغطاة", True),
            4: ("RCD trip time ≤ 40 ms", "زمن فصل قاطع التسرب ≤ 40 مللي ثانية", False),
        },
    ),
    "LGP": (
        TemplateKind.inspection,
        InspectionType.lifting_equipment,
        "Lifting gear pre-use",
        "فحص معدات الرفع قبل الاستخدام",
        10,
        2,
        {
            1: (
                "Slings and shackles tagged, in date, undamaged",
                "الحبال والشكلات معلمة وسارية وسليمة",
                False,
            )
        },
    ),
    "HSK": (
        TemplateKind.inspection,
        InspectionType.housekeeping,
        "Housekeeping",
        "النظافة والترتيب",
        10,
        2,
        {4: ("Escape routes clear", "مخارج الطوارئ خالية", False)},
    ),
    "FOD": (
        TemplateKind.inspection,
        InspectionType.airside_fod_walk,
        "Airside FOD walk",
        "جولة الأجسام الغريبة في الساحة",
        10,
        2,
        {
            3: (
                "No loose debris in the work area and adjacent pavement",
                "لا مخلفات سائبة في منطقة العمل والرصيف المجاور",
                False,
            ),
            6: ("FOD bins lidded and secured", "حاويات الأجسام الغريبة مغطاة ومثبتة", False),
        },
    ),
    "FIR": (
        TemplateKind.inspection,
        InspectionType.fire_safety,
        "Fire safety",
        "السلامة من الحريق",
        10,
        2,
        {
            2: (
                "Combustibles ≥ 11 m from hot work or shielded",
                "المواد القابلة للاشتعال على بعد 11 م أو محمية",
                False,
            ),
            5: ("Extinguishers at the work point", "طفايات الحريق عند نقطة العمل", False),
        },
    ),
    "WEL": (
        TemplateKind.inspection,
        InspectionType.welfare,
        "Welfare",
        "مرافق الرعاية",
        12,
        2,
        {
            1: ("Drinking water available", "مياه الشرب متوفرة", False),
            6: ("Toilets per headcount, clean", "دورات المياه كافية ونظيفة", False),
        },
    ),
    "ENV": (
        TemplateKind.inspection,
        InspectionType.environmental,
        "Environmental",
        "البيئة",
        10,
        2,
        {2: ("No uncontained fuel or chemical", "لا وقود أو مواد كيميائية غير محتواة", False)},
    ),
    "PLT": (
        TemplateKind.inspection,
        InspectionType.plant_vehicle,
        "Plant and vehicles",
        "المعدات والمركبات",
        10,
        2,
        {
            3: (
                "Reversing alarm, beacon and seatbelt working",
                "إنذار الرجوع والضوء وحزام الأمان تعمل",
                False,
            )
        },
    ),
    "PPE": (
        TemplateKind.inspection,
        InspectionType.ppe,
        "Personal protective equipment",
        "معدات الوقاية الشخصية",
        8,
        1,
        {},
    ),
    "LDW": (
        TemplateKind.inspection,
        InspectionType.leadership_walk,
        "Leadership walk",
        "جولة القيادة",
        8,
        1,
        {},
    ),
    "CHA": (
        TemplateKind.audit,
        AuditType.contractor_hse,
        "Contractor HSE audit",
        "تدقيق السلامة للمقاول",
        40,
        8,
        {
            12: ("PTW compliance sampled", "عينة الالتزام بتصاريح العمل", False),
            27: (
                "Competence of high-risk roles sampled",
                "عينة كفاءة الأدوار عالية الخطورة",
                False,
            ),
        },
    ),
    "ISO": (
        TemplateKind.audit,
        AuditType.system_iso45001,
        "ISO 45001 internal audit",
        "تدقيق داخلي ISO 45001",
        48,
        7,
        {
            31: ("Hazard identification (6.1.2)", "تحديد المخاطر (6.1.2)", False),
            44: (
                "Incident investigation and corrective action (10.2)",
                "التحقيق في الحوادث والإجراءات التصحيحية (10.2)",
                False,
            ),
        },
    ),
}
SECTION_NAMES = [
    ("General arrangements", "الترتيبات العامة"),
    ("Controls at the work front", "الضوابط في موقع العمل"),
    ("Leadership and planning", "القيادة والتخطيط"),
    ("Risk assessment", "تقييم المخاطر"),
    ("Permits and isolation", "التصاريح والعزل"),
    ("Competence", "الكفاءة"),
    ("Monitoring", "المراقبة"),
    ("Improvement", "التحسين"),
]


def _item(
    code: str, n: int, sec: str, en: str, ar: str, t: ItemType = ItemType.yes_no, **kw: Any
) -> dict[str, Any]:
    crit = kw.pop("critical", False)
    it = {
        "item_code": f"{code}-{n:02d}",
        "section_code": sec,
        "order": n,
        "text_en": en,
        "text_ar": ar,
        "item_type": t.value,
        "weight": 3 if crit else 1,
        "critical": crit,
        "stop_rule": StopRule.none.value,
        "na_allowed": False,
        "photo_required_on_fail": crit,
        "default_severity": "minor",
        "airside_only": False,
        "numeric_rule": None,
        "options": None,
        "suggested_ca_en": None,
        "suggested_ca_ar": None,
        "suggested_control_level": None,
        "reference": None,
        "guidance_en": None,
        "guidance_ar": None,
    }
    it.update(kw)
    if crit:
        it["suggested_ca_en"] = it["suggested_ca_en"] or f"Correct now: {en}"
        it["suggested_ca_ar"] = it["suggested_ca_ar"] or f"تصحيح فوري: {ar}"
        it["suggested_control_level"] = it["suggested_control_level"] or "engineering"
    return it


def gsi_items(version: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    secs = [
        {
            "code": "A",
            "title_en": "Access and general",
            "title_ar": "الدخول والعموميات",
            "order": 1,
        },
        {
            "code": "B",
            "title_en": "High-risk controls",
            "title_ar": "ضوابط الأعمال عالية الخطورة",
            "order": 2,
        },
        {
            "code": "C",
            "title_en": "Logistics and environment",
            "title_ar": "الحركة والبيئة",
            "order": 3,
        },
    ]
    items = []
    for i, (en, ar) in enumerate(GSI_ITEMS[: 24 if version >= 3 else 22], start=1):
        sec = "A" if i <= 8 else "B" if i <= 16 else "C"
        kw: dict[str, Any] = {}
        if i in (5, 9, 13):
            kw = {"critical": True, "stop_rule": StopRule.stop_work.value}
        elif i == 17:
            kw = {"critical": True}
        if i == 21:
            kw["na_allowed"] = True
        if i in (23, 24):
            kw["airside_only"] = True
        if i == 12:
            kw["suggested_ca_en"] = "Clear and mark the access route"
            kw["suggested_control_level"] = "administrative"
        items.append(_item("GSI", i, sec, en, ar, **kw))
    return secs, items


def tpl_items(code: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kind, _t, title_en, title_ar, n, nsec, crits = TPL[code]
    secs = [
        {
            "code": chr(65 + s),
            "title_en": SECTION_NAMES[s][0]
            if kind == TemplateKind.audit
            else f"{title_en} – part {s + 1}",
            "title_ar": SECTION_NAMES[s][1]
            if kind == TemplateKind.audit
            else f"{title_ar} – الجزء {s + 1}",
            "order": s + 1,
        }
        for s in range(nsec)
    ]
    per = -(-n // nsec)
    items = []
    for i in range(1, n + 1):
        sec = chr(65 + min((i - 1) // per, nsec - 1))
        typ = ItemType.rating_0_3 if kind == TemplateKind.audit else ItemType.yes_no
        kw: dict[str, Any] = {}
        en, ar = f"{title_en}: control point {i}", f"{title_ar}: نقطة تحقق {i}"
        if i in crits:
            en, ar, stop = crits[i]
            kw = {"critical": True}
            if stop:
                kw["stop_rule"] = StopRule.stop_work.value
        if code == "ELD" and i == 4:
            typ = ItemType.numeric
            kw["numeric_rule"] = {"unit": "ms", "min": "0", "max": "40"}
        if code == "LDW":
            typ = [
                ItemType.text,
                ItemType.text,
                ItemType.count_,
                ItemType.count_,
                ItemType.text,
                ItemType.text,
                ItemType.yes_no,
                ItemType.yes_no,
            ][i - 1]
            en = [
                "Conversations held",
                "Positive behaviours seen",
                "Workers spoken to",
                "Concerns raised",
                "Concerns detail",
                "Follow-up agreed",
                "Site rules briefed",
                "Welfare checked",
            ][i - 1]
        if code == "CHA" and i in (36, 37, 38, 39, 40):
            kw["na_allowed"] = True
        if code == "ISO" and i in (46, 47, 48):
            kw["na_allowed"] = True
        items.append(_item(code, i, sec, en, ar, typ, **kw))
    return secs, items


TOPICS: list[tuple[str, TopicCategory, str, str, list[dict[str, str]]]] = [
    ("TT-001", TopicCategory.general, "Site rules and reporting", "قواعد الموقع والإبلاغ", []),
    ("TT-002", TopicCategory.ppe, "Wearing PPE correctly", "ارتداء معدات الوقاية بشكل صحيح", []),
    (
        "TT-003",
        TopicCategory.heat_stress,
        "Heat illness recognition",
        "التعرف على الإجهاد الحراري",
        [{"kind": "incident", "ref": "INC-ANIA-EXP-2026-0150"}],
    ),
    (
        "TT-004",
        TopicCategory.lifting,
        "Lifting zones and signals",
        "مناطق الرفع والإشارات",
        [{"kind": "template_item", "ref": "GSI-17"}],
    ),
    (
        "TT-005",
        TopicCategory.excavation,
        "Excavation edges",
        "حواف الحفريات",
        [{"kind": "template_item", "ref": "GSI-09"}],
    ),
    (
        "TT-006",
        TopicCategory.scaffolding,
        "Scaffold tags",
        "بطاقات السقالات",
        [{"kind": "template_item", "ref": "SCA-02"}],
    ),
    (
        "TT-007",
        TopicCategory.housekeeping,
        "Housekeeping and access routes",
        "النظافة وممرات الحركة",
        [{"kind": "template_item", "ref": "GSI-12"}],
    ),
    (
        "TT-008",
        TopicCategory.hot_work,
        "Hot work and fire watch",
        "الأعمال الساخنة ومراقبة الحريق",
        [],
    ),
    ("TT-009", TopicCategory.manual_handling, "Manual handling", "المناولة اليدوية", []),
    ("TT-010", TopicCategory.traffic_plant, "Plant and pedestrians", "المعدات والمشاة", []),
    (
        "TT-011",
        TopicCategory.airside_driving,
        "Airside driving rules",
        "قواعد القيادة في الساحة",
        [],
    ),
    ("TT-012", TopicCategory.confined_space, "Confined space entry", "دخول الأماكن المحصورة", []),
    ("TT-013", TopicCategory.tools_equipment, "Hand tools", "العدد اليدوية", []),
    (
        "TT-014",
        TopicCategory.work_at_height,
        "Edges and openings: never remove a guardrail",
        "الحواف والفتحات: لا تزل الحاجز أبداً",
        [
            {"kind": "incident", "ref": "INC-ANIA-EXP-2026-0147"},
            {"kind": "template_item", "ref": "GSI-05"},
        ],
    ),
    ("TT-015", TopicCategory.environmental, "Spill response", "الاستجابة للانسكابات", []),
    ("TT-016", TopicCategory.fire_safety, "Using an extinguisher", "استخدام طفاية الحريق", []),
    ("TT-017", TopicCategory.welfare, "Water, rest and shade", "الماء والراحة والظل", []),
    ("TT-018", TopicCategory.permit_compliance, "Working to the permit", "العمل وفق التصريح", []),
    (
        "TT-019",
        TopicCategory.airside_fod_control,
        "FOD on the airside",
        "الأجسام الغريبة في الساحة",
        [{"kind": "template_item", "ref": "FOD-03"}],
    ),
    ("TT-020", TopicCategory.emergency, "Alarm and assembly points", "الإنذار ونقاط التجمع", []),
    ("TT-021", TopicCategory.health, "Fatigue and sleep", "الإرهاق والنوم", []),
    (
        "TT-022",
        TopicCategory.electrical,
        "Temporary electrical safety",
        "سلامة الكهرباء المؤقتة",
        [{"kind": "template_item", "ref": "ELD-02"}],
    ),
    ("TT-023", TopicCategory.behaviour_other, "Stop work authority", "صلاحية إيقاف العمل", []),
    ("TT-024", TopicCategory.work_at_height, "Ladders and steps", "السلالم", []),
]


def _libraries(ctx: Ctx) -> None:
    db = ctx.db
    faisal = ctx.uid("faisal.harbi")
    from app.services.field.library import review_due

    def add_tpl(
        code: str,
        version: int,
        kind: TemplateKind,
        it: Any,
        en: str,
        ar: str,
        secs: Any,
        items: Any,
        pub: datetime,
        sup: datetime | None,
        zone_types: list[str] | None = None,
    ) -> None:
        db.add(ChecklistTemplate(
            template_code=code, version=version, kind=kind,
            inspection_type=it if kind == TemplateKind.inspection else None,
            audit_type=it if kind == TemplateKind.audit else None,
            title_en=en, title_ar=ar, sections=secs, items=items, zone_types=zone_types or [],
            project_ids=[], review_due_on=review_due(pub),
            change_note=None if version == 1 else f"v{version}: wording and items updated",
            authored_by_user_id=faisal, published_by_user_id=faisal, published_at=pub,
            superseded_at=sup, status=VersionStatus.superseded if sup else VersionStatus.published,
            created_by_user_id=faisal,
        ))  # fmt: skip

    v2 = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)
    v3 = datetime(2026, 8, 20, 6, 0, tzinfo=UTC)
    for v, pub, sup in ((1, PUB, v2), (2, v2, v3), (3, v3, None)):
        secs, items = gsi_items(v)
        add_tpl(
            "GSI",
            v,
            TemplateKind.inspection,
            InspectionType.general_site,
            "General site inspection",
            "التفتيش العام على الموقع",
            secs,
            items,
            pub,
            sup,
        )
    for code, spec in TPL.items():
        secs, items = tpl_items(code)
        add_tpl(
            code,
            1,
            spec[0],
            spec[1],
            spec[2],
            spec[3],
            secs,
            items,
            PUB,
            None,
            ["airside"] if code == "FOD" else None,
        )
    langs = ["ur", "hi", "bn"]
    for i, (code, cat, en, ar, refs) in enumerate(TOPICS):
        pub = (
            datetime(2024, 10, 1, 6, 0, tzinfo=UTC)
            if code == "TT-009"
            else datetime(2026, 4, 15, 6, 0, tzinfo=UTC)
        )
        kp_en = [f"{en}: key point {k}" for k in range(1, 4)]
        kp_ar = [f"{ar}: نقطة {k}" for k in range(1, 4)]
        tr = (
            [
                {
                    "language": lg,
                    "key_points": [f"[{lg}] {p}" for p in kp_en],
                    "reviewed_by_name_role": "Site interpreter (TEST)",
                }
                for lg in langs
            ]
            if i < 10
            else []
        )
        db.add(ToolboxTopic(
            topic_code=code, version=1, category=cat, title_en=en, title_ar=ar, key_points_en=kp_en,
            key_points_ar=kp_ar, translations=tr, linked_refs=refs, review_due_on=review_due(pub),
            authored_by_user_id=faisal, published_by_user_id=faisal, published_at=pub,
            status=VersionStatus.published, created_by_user_id=faisal,
        ))  # fmt: skip
    db.flush()


# ---- A.1 settings, A.3 plans ---------------------------------------------------------------------

PLAN_TEMPLATE = {
    InspectionType.general_site: "GSI",
    InspectionType.scaffold: "SCA",
    InspectionType.excavation: "EXC",
    InspectionType.electrical: "ELD",
    InspectionType.lifting_equipment: "LGP",
    InspectionType.housekeeping: "HSK",
    InspectionType.airside_fod_walk: "FOD",
    InspectionType.fire_safety: "FIR",
    InspectionType.welfare: "WEL",
    InspectionType.environmental: "ENV",
    InspectionType.plant_vehicle: "PLT",
    InspectionType.ppe: "PPE",
    InspectionType.leadership_walk: "LDW",
}


def _settings(ctx: Ctx) -> None:
    for code, tb in (("ANIA-EXP", FROM), ("RBT-52", None)):
        s = fc.settings_row(ctx.db, ctx.pid(code))
        s.inspection_template_required_from = FROM
        s.toolbox_register_from = tb
    ctx.db.flush()
    fc.clear_cache(ctx.db)


def _plans(ctx: Ctx) -> None:
    from app.core.field_enums import Rotation

    for pl in ctx.db.scalars(select(InspectionPlan)):
        pl.template_code = PLAN_TEMPLATE[pl.inspection_type]
        if pl.name_en == "General site inspection — Terminal 3":
            pl.rotation = Rotation.zones
            pl.rotation_list = [ctx.zone("ANIA-EXP", z).id for z in ("Z-PIERB", "Z-MSCP", "Z-LAY1")]
        if pl.name_en == "FOD walk — apron":
            pl.rotation = Rotation.zones
            pl.rotation_list = [ctx.zone("ANIA-EXP", z).id for z in ("Z-APR-21", "Z-TWB")]
    ctx.db.flush()


# ---- A.3 / A.4 responses -------------------------------------------------------------------------


def _principal(db: Session, key: str) -> Any:
    from app.services.permissions import build_principal

    u = db.scalar(select(User).where(User.email == f"{key}@example.com"))
    assert u is not None, key
    return build_principal(db, u, None)


def _answers(
    t: ChecklistTemplate,
    nc: set[str],
    *,
    airside: bool,
    values: dict[str, Any] | None = None,
    note: str = "Condition found and recorded on site (TEST).",
) -> list[dict[str, Any]]:
    out = []
    for it in t.items:
        code = it["item_code"]
        typ = it["item_type"]
        if it.get("airside_only") and not airside:
            continue
        a: dict[str, Any] = {"item_code": code}
        if values and code in values:
            a.update(values[code])
        elif typ == "yes_no":
            if code in nc:
                a.update(answer="non_compliant", note=note)
            elif it.get("na_allowed") and _h(code, "na") % 2:
                a["answer"] = "na"
            else:
                a["answer"] = "compliant"
        elif typ == "numeric":
            a["numeric_value"] = "45" if code in nc else "28"
            if code in nc:
                a["note"] = note
        elif typ == "count":
            a["count_value"] = 3
        elif typ == "text":
            a["answer"] = "Recorded during the walk (TEST)."
        if code in nc and it.get("photo_required_on_fail"):
            a["photos"] = [{"file_name": f"{code}.png", "content_base64": PNG}]
        out.append(a)
    return out


def _resubmit(
    ctx: Ctx,
    ins: Inspection,
    who: str,
    nc: set[str],
    *,
    zone: str | None = None,
    eng: str | None = None,
    when: datetime | None = None,
    stop: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    """Re-record a seeded Phase 1 completed inspection through the 6d service (A.3): the
    completion date (hence K-34 / K-35) is kept; the Phase 1 manual findings stay listed."""
    from app.schemas.field import SubmissionCreate
    from app.services.field import execution, library

    db = ctx.db
    proj = db.get(Project, ins.project_id)
    assert proj is not None
    pc = proj.code
    if zone:
        ins.zone_id = ctx.zone(pc, zone).id
    if eng:
        ins.engagement_id = ctx.engs[(pc, eng)].id
    done = when or ins.completed_at
    assert done is not None
    old = list(ins.findings or [])
    ins.status = InspectionStatus.planned
    plan_id = ins.plan_id
    db.flush()
    code = PLAN_TEMPLATE[ins.inspection_type]
    t = library.published(db, code, done - timedelta(minutes=40))
    assert t is not None
    zt = fc.zone_type(db, ins.zone_id)
    if t.zone_types and zt not in t.zone_types:
        ins.zone_id = None if code != "FOD" else ins.zone_id
    body: dict[str, Any] = {
        "client_uuid": str(_u("resp", ins.ref)),
        "inspection_id": str(ins.id),
        "template_code": code,
        "started_at": (done - timedelta(minutes=40)).isoformat(),
        "completed_at": done.isoformat(),
        "answers": _answers(t, nc, airside=zt == "airside", values=extra),
    }
    if stop:
        body["stop_work"] = stop
    set_now(done + timedelta(minutes=5))
    try:
        p = _principal(db, who)
        try:
            execution.submit(db, p, ins.project_id, SubmissionCreate.model_validate(body))
        except Exception as e:  # out of scope for the named inspector: record as the officer
            if getattr(e, "status_code", None) != 403 and getattr(e, "status", None) != 403:
                raise
            fallback = "noura.qahtani" if pc == "ANIA-EXP" else "lina.haddad"
            execution.submit(
                db, _principal(db, fallback), ins.project_id, SubmissionCreate.model_validate(body)
            )
    finally:
        set_now(SEED_CLOCK)
    ins.plan_id = plan_id
    ins.findings = old + list(ins.findings or [])
    db.flush()
    return ins


def _responses(ctx: Ctx) -> None:
    db = ctx.db
    rows = list(db.scalars(
        select(Inspection).where(Inspection.status == InspectionStatus.completed,
                                 Inspection.completed_date >= FROM).order_by(Inspection.completed_at, Inspection.ref)
    ))  # fmt: skip
    by_ref = {i.ref: i for i in rows}
    # Named A.4 records are mapped onto seeded Phase 1 inspections by type and site (DECISIONS):
    # FD3 = the first two GSI walks on S-LAND (Z-MSCP / NAJD), the stop-work order = the third
    # (GSI-05 at Z-PIERB / NAJD), the FOD-03 critical fail = the FOD walk nearest 09-21.
    sites = {s.id: c for (p, c), s in ctx.sites.items()}
    ania = [i for i in rows if i.ref.startswith("INS-ANIA-EXP")]
    # the Phase 1 generator varies types between runs: prefer GSI walks on S-LAND, else take other
    # S-LAND inspections and record them as GSI walks (likewise FOD walks on S-AIR)
    land = sorted((i for i in ania if sites.get(i.site_id) == "S-LAND" and i.completed_date),
                  key=lambda i: (i.inspection_type != InspectionType.general_site,
                                 i.completed_date, i.ref))[:3]  # fmt: skip
    land_gsi = sorted(land, key=lambda i: (i.completed_date, i.ref))
    for x in land_gsi:
        x.inspection_type = InspectionType.general_site
    air = [i for i in ania if sites.get(i.site_id) == "S-AIR" and i.completed_date
           and i not in land_gsi]  # fmt: skip
    fods = sorted(air, key=lambda i: (i.inspection_type != InspectionType.airside_fod_walk,
                                      abs((i.completed_date - date(2026, 9, 21)).days), i.ref))[:1]  # type: ignore[operator]  # fmt: skip
    for x in fods:
        x.inspection_type = InspectionType.airside_fod_walk
    named: dict[str, tuple[Any, ...]] = {}
    if len(land_gsi) >= 2:
        for x in land_gsi[:2]:
            named[x.ref] = ("fahad.mutairi", {"GSI-12"}, "Z-MSCP", "NAJD", None, None)
    if len(land_gsi) >= 3:
        named[land_gsi[2].ref] = ("fahad.mutairi", {"GSI-05"}, "Z-PIERB", "NAJD", "stop", None)
    if fods:
        named[fods[0].ref] = ("omar.siddiqui", {"FOD-03"}, "Z-TWB", "GULFPAVE", None, None)
    for ref, ins in by_ref.items():
        if ref in named:
            who, nc, zone, eng, stop, _x = named[ref]
            sw = None
            if stop:
                d = ins.completed_date
                assert d is not None and ins.completed_at is not None
                sw = {
                    "activity_en": "Formwork striking at level 3, open slab edge grid C-14 to C-20 (TEST)",
                    "instructed_role": InstructedRole.supervisor.value,
                    "instructed_at": (ins.completed_at + timedelta(minutes=5)).isoformat(),
                    "permit_ids": [],
                }
            _resubmit(ctx, ins, who, nc, zone=zone, eng=eng, stop=sw)
            continue
        t_code = PLAN_TEMPLATE[ins.inspection_type]
        from app.services.field import library

        t = library.published(db, t_code)
        assert t is not None
        cands = [
            it["item_code"]
            for it in t.items
            if not it.get("critical")
            and it["item_type"] == "yes_no"
            and it["item_code"] not in ("GSI-12", "GSI-19")
            and not it.get("airside_only")
        ]
        k = _h(ref) % 3
        nc = {cands[(_h(ref, j) % len(cands))] for j in range(k)} if cands else set()
        pc = "ANIA-EXP" if "ANIA" in ref else "RBT-52"
        who = "noura.qahtani" if pc == "ANIA-EXP" else "lina.haddad"
        _resubmit(ctx, ins, who, nc)
    # the order: number 007, CA In Progress, released 16:40 local by Fahad (FND-8)
    o = db.scalar(select(StopWorkOrder).order_by(StopWorkOrder.created_at))
    if o is not None:
        o.seq = 7
        o.order_no = o.order_no.rsplit("-", 1)[0] + "-007"
        ca = db.get(CorrectiveAction, o.ca_id) if o.ca_id else None
        if ca is not None:
            ca.status = CaStatus.in_progress
        db.flush()
        from app.schemas.field import StopWorkRelease
        from app.services.field import stopwork

        d = fc.local_day(o.raised_at)
        set_now(at(d, 16, 40))
        try:
            stopwork.release_order(
                db,
                _principal(db, "fahad.mutairi"),
                o.id,
                StopWorkRelease.model_validate(
                    {
                        "release_note": "Guardrail fitted along grid C-14 to C-20 and checked (TEST).",
                        "photos": [{"file_name": "release.png", "content_base64": PNG}],
                    }
                ),
            )
        finally:
            set_now(SEED_CLOCK)
        if ca is not None:
            ca.status = CaStatus.closed
            ca.completed_date = d
            ca.verified_date = d
    # FOD critical CA closed the same day
    fod = fods[0] if fods else None
    if fod is not None:
        for ca in db.scalars(select(CorrectiveAction).where(CorrectiveAction.source_id == fod.id)):
            ca.status = CaStatus.closed
            ca.completed_date = fod.completed_date
            ca.verified_date = fod.completed_date
    db.flush()


def _fd7(ctx: Ctx) -> None:
    """FD7 leaves SAHARA@S-LAND uncovered in the week ending 2026-09-26: a Phase 1 inspection of
    SAHARA there that week is re-attributed to NAJD (DECISIONS)."""
    db = ctx.db
    sahara, najd = ctx.engs[("ANIA-EXP", "SAHARA")].id, ctx.engs[("ANIA-EXP", "NAJD")].id
    for i in db.scalars(
        select(Inspection).where(
            Inspection.engagement_id == sahara,
            Inspection.site_id == ctx.sites[("ANIA-EXP", "S-LAND")].id,
            Inspection.completed_date >= date(2026, 9, 20),
            Inspection.completed_date <= date(2026, 9, 26),
        )
    ):
        i.engagement_id = najd
    db.flush()


def _coverage(ctx: Ctx, pcode: str, who: str, keep: set[tuple[str, str, date]]) -> None:
    """FD7 / FD9 K-113: an unplanned GSI walk (all compliant) for each engagement-site with
    September hours and no completed inspection in that week (ISP-3), except the `keep` units
    (engagement code, site code, last day of the week) that FD7 leaves uncovered."""
    from app.schemas.field import SubmissionCreate
    from app.services.field import execution, library

    db = ctx.db
    pid = ctx.pid(pcode)
    codes = {e.id: c for (p, c), e in ctx.engs.items() if p == pcode}
    scodes = {x.id: c for (p, c), x in ctx.sites.items() if p == pcode}
    t = library.published(db, "GSI")
    assert t is not None
    W = WorkforceReturn  # noqa: N806
    first: dict[tuple[uuid.UUID, uuid.UUID, date], date] = {}
    for d, e, s in db.execute(
        select(W.work_date, W.engagement_id, W.site_id)
        .where(W.project_id == pid, W.headcount > 0, W.work_date >= FROM - timedelta(days=7),
               W.work_date <= date(2026, 9, 30))
        .order_by(W.work_date)
    ):  # fmt: skip
        if e is None:
            continue
        ws = fc.week_of(db, pid, d)
        if ws + timedelta(days=6) < FROM:
            continue
        first.setdefault((e, s, ws), max(d, ws))
    done = {
        (e, s, fc.week_of(db, pid, d))
        for e, s, d in db.execute(
            select(Inspection.engagement_id, Inspection.site_id, Inspection.completed_date).where(
                Inspection.project_id == pid,
                Inspection.status == InspectionStatus.completed,
                Inspection.completed_date.is_not(None),
            )
        )
        if d is not None
    }
    p = _principal(db, who)
    for (e, s, ws), d in sorted(first.items(), key=lambda x: (x[0][2], str(x[0][1]), str(x[0][0]))):
        if (e, s, ws) in done or (codes.get(e), scodes.get(s), ws + timedelta(days=6)) in keep:
            continue
        done_at = at(max(d, FROM), 10, 30)
        body = {
            "client_uuid": str(_u("cov", e, s, ws)), "template_code": "GSI", "site_id": str(s),
            "engagement_id": str(e), "started_at": (done_at - timedelta(minutes=40)).isoformat(),
            "completed_at": done_at.isoformat(),
            "answers": _answers(t, set(), airside=False),
        }  # fmt: skip
        set_now(done_at + timedelta(minutes=5))
        try:
            execution.submit(db, p, pid, SubmissionCreate.model_validate(body))
        finally:
            set_now(SEED_CLOCK)
    db.flush()


# ---- A.5 audits ----------------------------------------------------------------------------------


def _audits(ctx: Ctx) -> None:
    from app.schemas.field import (
        AuditAnswers,
        AuditCreate,
        AuditTransition,
        AuditUpdate,
    )
    from app.services.field import audits, library

    db = ctx.db
    noura, faisal = ctx.uid("noura.qahtani"), ctx.uid("faisal.harbi")
    land, air = ctx.sites[("ANIA-EXP", "S-LAND")].id, ctx.sites[("ANIA-EXP", "S-AIR")].id
    hist = [
        ("ANIA-EXP", "RAWABI", date(2026, 5, 12), land, 6),
        ("ANIA-EXP", "NAJD", date(2026, 6, 2), land, 7),
        ("ANIA-EXP", "SAHARA", date(2026, 3, 10), land, 8),
        ("ANIA-EXP", "GULFPAVE", date(2026, 3, 20), air, 9),
        ("ANIA-EXP", None, date(2026, 2, 15), land, 10),
        ("RBT-52", "QIMMA", date(2026, 6, 20), ctx.sites[("RBT-52", "S-TWR")].id, 1),
    ]
    for pc, eng, fe, site, seq in hist:
        lead = noura if pc == "ANIA-EXP" else ctx.uid("lina.haddad")
        if eng is None:
            lead = faisal
        db.add(FieldAudit(
            audit_no=f"AUD-{pc}-2026-{seq:03d}", year=2026, seq=seq, project_id=ctx.pid(pc),
            audit_type=AuditType.contractor_hse if eng else AuditType.system_iso45001,
            template_code="CHA" if eng else "ISO",
            auditee_engagement_id=ctx.engs[(pc, eng)].id if eng else None, site_ids=[site],
            lead_auditor_id=lead, team_ids=[], planned_start=fe - timedelta(days=1), planned_end=fe,
            fieldwork_start=fe - timedelta(days=1), fieldwork_end=fe, summary_en="Historical audit (TEST).",
            issued_by_user_id=faisal if lead != faisal else noura, issued_at=at(fe + timedelta(days=4), 10),
            closed_at=at(fe + timedelta(days=40), 10), status=AuditStatus.closed, created_by_user_id=noura,
        ))  # fmt: skip
    db.flush()
    cha = library.published(db, "CHA")
    assert cha is not None
    crit = {"CHA-12", "CHA-27"}

    def ratings(n3: int, n2: int, n1: int, n0: int, na: list[str]) -> list[dict[str, Any]]:
        seq = [3] * n3 + [2] * n2 + [1] * n1 + [0] * n0
        out, k = [], 0
        for it in cha.items:
            c = it["item_code"]
            if c in na:
                out.append({"item_code": c, "answer": "na"})
            elif c in crit:
                out.append({"item_code": c, "answer": "3"})
            else:
                r = seq[k]
                k += 1
                a: dict[str, Any] = {"item_code": c, "answer": str(r)}
                if r <= 1:
                    a["note"] = "Evidence not available for the sample (TEST)."
                out.append(a)
        return out

    plans = [
        (
            "SAHARA",
            land,
            date(2026, 9, 7),
            date(2026, 9, 8),
            date(2026, 9, 12),
            ratings(20, 10, 4, 2, ["CHA-39", "CHA-40"]),
        ),
        (
            "GULFPAVE",
            air,
            date(2026, 9, 22),
            date(2026, 9, 23),
            date(2026, 9, 27),
            ratings(21, 12, 3, 1, ["CHA-40"]),
        ),
    ]
    pid = ctx.pid("ANIA-EXP")
    pn, pf = _principal(db, "noura.qahtani"), _principal(db, "faisal.harbi")
    for eng, site, fs, fe, issue, ans in plans:
        try:
            set_now(at(fs - timedelta(days=10), 9))
            a = audits.create_audit(
                db,
                pn,
                pid,
                AuditCreate.model_validate(
                    {
                        "audit_type": "contractor_hse",
                        "template_code": "CHA",
                        "auditee_engagement_id": str(ctx.engs[("ANIA-EXP", eng)].id),
                        "site_ids": [str(site)],
                        "lead_auditor_id": str(noura),
                        "team_ids": [str(ctx.uid("fahad.mutairi"))],
                        "planned_start": fs.isoformat(),
                        "planned_end": fe.isoformat(),
                    }
                ),
            )
            set_now(at(fs, 8))
            audits.update_audit(
                db,
                pn,
                a.id,
                AuditUpdate.model_validate(
                    {
                        "opening_meeting_at": at(fs, 8).isoformat(),
                        "fieldwork_start": fs.isoformat(),
                        "auditee_attendee_roles": "Project manager, HSE manager, site supervisor",
                    }
                ),
            )
            audits.save_answers(db, pn, a.id, AuditAnswers.model_validate({"answers": ans}))
            set_now(at(fe, 15))
            audits.update_audit(
                db,
                pn,
                a.id,
                AuditUpdate.model_validate(
                    {
                        "fieldwork_end": fe.isoformat(),
                        "closing_meeting_at": at(fe, 14).isoformat(),
                        "summary_en": f"Contractor HSE audit of {eng}: arrangements broadly effective; NCs raised (TEST).",
                        "summary_ar": "تدقيق السلامة للمقاول: الترتيبات فعالة بشكل عام مع ملاحظات.",
                    }
                ),
            )
            audits.transition_audit(
                db, pn, a.id, AuditTransition.model_validate({"action": "complete_fieldwork"})
            )
            set_now(at(issue, 11))
            audits.transition_audit(
                db, pf, a.id, AuditTransition.model_validate({"action": "issue"})
            )
        finally:
            set_now(SEED_CLOCK)
    db.flush()


# ---- A.6 talks and campaigns ---------------------------------------------------------------------


def _talks(ctx: Ctx) -> None:
    """One register talk per daily-return toolbox talk (date, engagement, site), attendance as
    unnamed counts (DR attendees split over the talks); named briefed rows for the campaign pairs
    and the named talk TBT-…-04412 (unnamed reduced so K-36 attendees equal the daily returns)."""
    db = ctx.db
    pc = "ANIA-EXP"
    pid = ctx.pid(pc)
    proj_code = pc
    W = WorkforceReturn  # noqa: N806
    rows = db.execute(
        select(W.work_date, W.engagement_id, W.site_id, W.toolbox_talks, W.toolbox_attendees)
        .where(
            W.project_id == pid,
            W.work_date >= FROM,
            W.work_date <= date(2026, 10, 5),
            W.toolbox_talks > 0,
        )
        .order_by(W.work_date, W.site_id, W.engagement_id)
    ).all()
    topics = {t.topic_code: t for t in db.scalars(select(ToolboxTopic))}
    recorder = {"S-LAND": ctx.uid("fahad.mutairi"), "S-AIR": ctx.uid("omar.siddiqui")}
    site_code = {s.id: c for (p, c), s in ctx.sites.items() if p == pc}
    eng_code = {e.id: c for (p, c), e in ctx.engs.items() if p == pc}
    zones = {"S-LAND": ctx.zone(pc, "Z-PIERB").id, "S-AIR": ctx.zone(pc, "Z-APR-21").id}
    seq = 0
    talks: list[ToolboxTalk] = []
    rot = [
        "TT-001",
        "TT-002",
        "TT-007",
        "TT-010",
        "TT-016",
        "TT-017",
        "TT-020",
        "TT-023",
        "TT-013",
        "TT-018",
    ]
    for d, eng, site, n, att in rows:
        sc = site_code[site]
        for k in range(int(n)):
            seq += 1
            per = int(att) // int(n) + (1 if k < int(att) % int(n) else 0)
            code = rot[_h(d, eng, k) % len(rot)]
            if sc == "S-LAND" and date(2026, 9, 9) <= d <= date(2026, 9, 16) and k == 0:
                code = "TT-014"
            if (
                sc == "S-AIR"
                and k == 0
                and (
                    (eng_code.get(eng) == "GULFPAVE" and d == date(2026, 9, 24))
                    or (eng_code.get(eng) == "RAWABI" and d == date(2026, 10, 1))
                )
            ):
                code = "TT-003"
            tp = topics[code]
            delivered = at(d, 6, 30) + timedelta(minutes=k * 5)
            talks.append(ToolboxTalk(
                talk_no=f"TBT-{proj_code}-2026-{seq:05d}", year=2026, seq=seq, project_id=pid,
                client_uuid=_u("talk", seq), site_id=site,
                zone_ids=[zones[sc]] if sc in zones else [], host_engagement_id=eng, shift=TalkShift.day,
                delivered_at=delivered, delivered_date=d, duration_minutes=15,
                recorded_by_user_id=recorder.get(sc, ctx.uid("noura.qahtani")),
                presenter_user_id=recorder.get(sc, ctx.uid("noura.qahtani")),
                topics=[{"topic_id": str(tp.id), "topic_code": tp.topic_code, "version": tp.version,
                         "title_en": tp.title_en, "title_ar": tp.title_ar, "category": tp.category.value}],
                topic_codes=[code], language=["ur", "hi", "bn", "ar"][_h(d, eng, k, "l") % 4],
                interpreter_languages=["hi", "bn"], unnamed_count=per, received_at=delivered + timedelta(minutes=20),
                status=TalkStatus.locked if d < date(2026, 10, 5) else TalkStatus.delivered,
                created_by_user_id=recorder.get(sc, ctx.uid("noura.qahtani")),
            ))  # fmt: skip
    # A.6: RAWABI meets the CMP-005 pair late on 10-01 (no daily-return talk that day)
    rawabi, s_air = ctx.engs[(pc, "RAWABI")].id, ctx.sites[(pc, "S-AIR")].id
    if not any(t.host_engagement_id == rawabi and t.delivered_date == date(2026, 10, 1)
               and "TT-003" in t.topic_codes for t in talks):  # fmt: skip
        seq += 1
        tp = topics["TT-003"]
        d = date(2026, 10, 1)
        talks.append(ToolboxTalk(
            talk_no=f"TBT-{proj_code}-2026-{seq:05d}", year=2026, seq=seq, project_id=pid,
            client_uuid=_u("talk", seq), site_id=s_air, zone_ids=[zones["S-AIR"]],
            host_engagement_id=rawabi, shift=TalkShift.day, delivered_at=at(d, 6, 30),
            delivered_date=d, duration_minutes=15, recorded_by_user_id=recorder["S-AIR"],
            presenter_user_id=recorder["S-AIR"],
            topics=[{"topic_id": str(tp.id), "topic_code": tp.topic_code, "version": tp.version,
                     "title_en": tp.title_en, "title_ar": tp.title_ar, "category": tp.category.value}],
            topic_codes=["TT-003"], language="ur", interpreter_languages=["hi", "bn"], unnamed_count=0,
            received_at=at(d, 6, 50), status=TalkStatus.locked, created_by_user_id=recorder["S-AIR"],
        ))  # fmt: skip
    db.add_all(talks)
    db.flush()
    # named rows: one briefed worker of each pair engagement at the first campaign talk
    deps = list(db.execute(
        select(Deployment, Worker).join(Worker, Worker.id == Deployment.worker_id)
        .where(Deployment.project_id == pid, Deployment.status == "mobilised",
               Worker.person_type == "contractor_worker")
        .order_by(Worker.worker_no)
    ).all())  # fmt: skip
    by_eng: dict[uuid.UUID, list[tuple[Deployment, Worker]]] = {}
    for dpl, w in deps:
        if dpl.engagement_id is not None:
            by_eng.setdefault(dpl.engagement_id, []).append((dpl, w))

    def name_rows(t: ToolboxTalk, engs: list[uuid.UUID], n: int) -> int:
        added = 0
        for e in engs:
            for dpl, w in by_eng.get(e, [])[:n]:
                ul = (
                    UnderstoodLanguage.talk_language
                    if w.primary_language.value == t.language
                    else UnderstoodLanguage.interpreter
                    if w.primary_language.value in t.interpreter_languages
                    else UnderstoodLanguage.none
                )
                if ul == UnderstoodLanguage.none:
                    t.interpreter_languages = [*t.interpreter_languages, w.primary_language.value]
                    ul = UnderstoodLanguage.interpreter
                db.add(TalkAttendance(talk_id=t.id, deployment_id=dpl.id, engagement_id=e,
                                      method="list", understood_language=ul,
                                      counted_person_type="contractor_worker",
                                      created_at=t.delivered_at, seed_fake=True))  # fmt: skip
                added += 1
        t.unnamed_count = max(0, t.unnamed_count - added)
        return added

    for t in talks:
        if "TT-014" in t.topic_codes or "TT-003" in t.topic_codes:
            name_rows(t, [t.host_engagement_id], 1)
    # TBT-ANIA-EXP-2026-04412 (A.6): NAJD, Z-PIERB, 09-14 06:30, TT-014, ur + bn, 38 rows
    najd = ctx.engs[(pc, "NAJD")].id
    t412 = next(
        (
            t
            for t in talks
            if t.host_engagement_id == najd and t.delivered_date == date(2026, 9, 14)
        ),
        None,
    )
    if t412 is not None:
        tp = topics["TT-014"]
        t412.talk_no, t412.seq = f"TBT-{proj_code}-2026-04412", 4412
        t412.topics = [
            {
                "topic_id": str(tp.id),
                "topic_code": "TT-014",
                "version": tp.version,
                "title_en": tp.title_en,
                "title_ar": tp.title_ar,
                "category": tp.category.value,
            }
        ]
        t412.topic_codes = ["TT-014"]
        t412.language, t412.interpreter_languages = "ur", ["bn"]
        t412.unnamed_count += sum(
            1
            for _ in db.scalars(select(TalkAttendance.id).where(TalkAttendance.talk_id == t412.id))
        )
        db.execute(delete(TalkAttendance).where(TalkAttendance.talk_id == t412.id))
        t412.zone_ids = [ctx.zone(pc, "Z-PIERB").id]
        before = t412.unnamed_count
        excess = name_rows(t412, [najd], 38) - before
        # keep K-36 attendees = the daily returns: take the excess from the same day's other talks
        for sib in talks:
            if excess <= 0:
                break
            if sib is t412 or (sib.host_engagement_id, sib.delivered_date, sib.site_id) != (
                najd,
                t412.delivered_date,
                t412.site_id,
            ):
                continue
            cut = min(excess, sib.unnamed_count)
            sib.unnamed_count -= cut
            excess -= cut
    db.flush()
    # campaigns CMP-004 / CMP-005 (A.6)
    from app.services.field import campaigns

    inc_ids = {x.ref: x.id for x in db.execute(select(Incident.ref, Incident.id))}
    for seq_, code, ref_, issued, due, site_code_, by in (
        (
            4,
            "TT-014",
            "INC-ANIA-EXP-2026-0147",
            date(2026, 9, 9),
            date(2026, 9, 16),
            "S-LAND",
            "faisal.harbi",
        ),
        (
            5,
            "TT-003",
            "INC-ANIA-EXP-2026-0150",
            date(2026, 9, 23),
            date(2026, 9, 30),
            "S-AIR",
            "noura.qahtani",
        ),
    ):
        assert ref_ in inc_ids
        c = BriefingCampaign(
            campaign_no=f"CMP-{proj_code}-2026-{seq_:03d}", year=2026, seq=seq_, project_id=pid,
            topic_id=topics[code].id, topic_code=code, reason=CampaignReason.incident, reason_ref=ref_,
            message_en=f"Brief every crew on {topics[code].title_en} after a recent incident (TEST).",
            message_ar="توعية جميع الطواقم بعد حادث حديث.", site_ids=[ctx.sites[(pc, site_code_)].id],
            issued_by_user_id=ctx.uid(by), issued_at=at(issued, 6, 0), due_date=due,
            status=CampaignStatus.closed if due + timedelta(days=7) < SEED_CLOCK.date() else CampaignStatus.issued,
            created_by_user_id=ctx.uid(by),
        )  # fmt: skip
        c.pairs = campaigns.fix_pairs(db, c, issued)
        db.add(c)
    db.flush()


def _cleanup(db: Session, n0: set[uuid.UUID], e0: set[uuid.UUID]) -> None:
    """Remove the notifications and e-mails raised while seeding (seeds insert without alerts)."""
    db.flush()
    db.execute(
        delete(Notification).where(Notification.id.not_in(n0)) if n0 else delete(Notification)
    )
    db.execute(
        delete(EmailMessage).where(EmailMessage.id.not_in(e0)) if e0 else delete(EmailMessage)
    )
    db.flush()


def seed_field_data(db: Session) -> None:
    if already_seeded(db):
        return
    from app.models import Project

    if db.scalar(select(Project.id).where(Project.code == "ANIA-EXP")) is None:
        return
    n0 = set(db.scalars(select(Notification.id)))
    e0 = set(db.scalars(select(EmailMessage.id)))
    ctx = Ctx(db)
    try:
        set_now(SEED_CLOCK)
        _settings(ctx)
        _libraries(ctx)
        _plans(ctx)
        _fd7(ctx)
        _responses(ctx)
        _coverage(ctx, "ANIA-EXP", "noura.qahtani", {("SAHARA", "S-LAND", date(2026, 9, 26))})
        _coverage(ctx, "RBT-52", "lina.haddad", set())
        _audits(ctx)
        _talks(ctx)
        _cleanup(db, n0, e0)
        fc.clear_cache(db)
    finally:
        set_now(None)


def main() -> int:  # pragma: no cover - CLI
    from app.db.session import get_sessionmaker

    with get_sessionmaker()() as db:
        seed_field_data(db)
        db.commit()
    print("Field assurance seed loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
