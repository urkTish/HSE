"""Demo seed of package Q1 construction: ITP, inspection requests, punch lists, handover dossier
(spec 8-quality Appendix A.2 checklists, A.3 ITPs and floor plan, A.4 IRs, punch and dossier).

`app.seed_quality.seed_quality_data` calls `seed` after the Q0 records. Records are written
directly (seed_fake = true), with the same shapes the services write. September 2026 targets
(QX2, QX24, K-156): 120 IRs with round 1 decided (96 approved / with comments, 22 rejected, 2 not
ready), 21 re-inspections (18 approved, 3 rejected), 4 waived witness rounds, 2 cancelled IRs;
4,820 applicable scored checklist items with 31 non-compliant; 46 punch items with a September
target, 24 closed on time. The bulk of the IRs is at the multi-storey car park (Z-MSCP, D-337) so
the Pier B dossier lists a readable set of blockers. RUH-CCH (logistics) gets no Part B record."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.field_enums import (
    ItemType,
    ResponseOwnerType,
    ResponseResult,
    StopRule,
    TemplateKind,
    VersionStatus,
)
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import (
    QDiscipline,
    QNcrCategory,
    QRecordType,
    QSignoffChannel,
)
from app.core.quality.q1 import (
    QApprovalCode,
    QAsbuiltStatus,
    QDossierStatus,
    QIrCommentStatus,
    QIrResult,
    QIrStatus,
    QItpStatus,
    QPlanStatus,
    QPointType,
    QPunchCategory,
    QPunchRaisedDuring,
    QPunchStatus,
    QVerifyingRecord,
    strictest,
)
from app.models import Project, ProjectEngagement, Site, User, Zone
from app.models.field import ChecklistResponse, ChecklistTemplate
from app.models.quality import QCriterion, QMteItem, QMteUsage, QSignoff, QSystem
from app.models.quality.q1 import (
    QAsbuiltItem,
    QDossier,
    QFloorPlan,
    QIr,
    QIrComment,
    QIrRound,
    QItp,
    QItpPoint,
    QPunchItem,
)
from app.services.quality.q1.common import location_key

RIYADH = ZoneInfo("Asia/Riyadh")
PUBLISHED = datetime(2026, 4, 1, 6, 0, tzinfo=UTC)
CRE = "position:CONSULTANT_RE (Consultant Resident Engineer)"


def at(d: date, hh: int = 9, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), RIYADH).astimezone(UTC)


# ---- checklist library (Appendix A.2, kind `quality`) -------------------------------------------

# code → (quality_type, EN title, AR title, items: (EN, AR, critical, na_allowed))
TEMPLATES: dict[str, tuple[str, str, str, list[tuple[str, str, bool, bool]]]] = {
    "QSTC-FW": (
        "ir_inspection",
        "Formwork, line and level",
        "القوالب والاستقامة والمناسيب",
        [
            (
                "Formwork drawings approved and on site",
                "مخططات القوالب معتمدة ومتوفرة في الموقع",
                False,
                False,
            ),
            (
                "Line and level within ± 5 mm in 3 m",
                "الاستقامة والمناسيب ضمن ± 5 مم لكل 3 م",
                True,
                False,
            ),
            (
                "Formwork clean, release agent applied",
                "القوالب نظيفة ومدهونة بمادة الفك",
                False,
                False,
            ),
            ("Joints tight, no grout loss expected", "الوصلات محكمة دون تسرب للمونة", False, False),
            ("Props and bracing per design", "الدعامات والتقوية حسب التصميم", True, False),
            ("Openings and boxouts in place", "الفتحات والصناديق في أماكنها", False, True),
            ("Chamfers and drip details fitted", "الشطفات وتفاصيل التنقيط مركبة", False, True),
            ("Construction joints prepared", "فواصل الصب مجهزة", False, True),
            ("Access and edge protection safe", "الوصول وحماية الحواف آمنة", False, False),
            ("Survey check record attached", "سجل التحقق المساحي مرفق", False, False),
            ("Cover blocks to soffit formwork", "فواصل الغطاء على قوالب البطنية", False, False),
            ("Dimensions checked against drawing", "الأبعاد مطابقة للمخطط", False, True),
        ],
    ),
    "QSTC-RB": (
        "ir_inspection",
        "Reinforcement before pour",
        "حديد التسليح قبل الصب",
        [
            ("Bar sizes as drawing", "أقطار الحديد حسب المخطط", True, False),
            ("Bar spacing as drawing", "تباعد الحديد حسب المخطط", True, False),
            (
                "Cover 40 ± 5 mm with approved spacers",
                "الغطاء 40 ± 5 مم بفواصل معتمدة",
                True,
                False,
            ),
            (
                "Lap lengths and locations per drawing",
                "أطوال وأماكن الوصلات حسب المخطط",
                True,
                False,
            ),
            (
                "Bars clean, free of loose rust and oil",
                "الحديد نظيف وخالٍ من الصدأ والزيت",
                False,
                False,
            ),
            ("Ties secure, cages stable", "الرباطات محكمة والأقفاص ثابتة", False, False),
            ("Chairs and supports adequate", "الكراسي والحوامل كافية", False, False),
            ("Starter bars and dowels positioned", "أشاير الأعمدة والأوتاد في مكانها", False, True),
            ("Couplers installed and checked", "الوصلات الميكانيكية مركبة ومفحوصة", False, True),
            ("Openings trimmed with extra bars", "الفتحات مدعمة بحديد إضافي", False, True),
            (
                "Mill certificates traceable to heats",
                "شهادات المصنع متتبعة لأرقام الصب",
                False,
                False,
            ),
            ("Bending schedule matches", "جدول التشكيل مطابق", False, False),
            ("Embedded earthing continuity bars", "حديد استمرارية التأريض", False, True),
            ("No damaged or rebent bars", "لا يوجد حديد تالف أو معاد ثنيه", False, False),
            ("Construction joint reinforcement", "تسليح فاصل الصب", False, True),
            ("Area clean, ready for concrete", "المنطقة نظيفة وجاهزة للصب", False, False),
        ],
    ),
    "QSTC-PR": (
        "ir_inspection",
        "Concrete pour",
        "صب الخرسانة",
        [
            (
                "Delivery ticket matches approved mix",
                "تذكرة التوريد مطابقة للخلطة المعتمدة",
                True,
                False,
            ),
            ("Slump within the specified range", "الهبوط ضمن المدى المحدد", True, False),
            ("Concrete temperature ≤ 32 °C", "حرارة الخرسانة ≤ 32 °م", True, False),
            ("Time since batching within limit", "الزمن منذ الخلط ضمن الحد", False, False),
            ("Sampling per pour done", "أخذ العينات لكل صبة تم", False, False),
            ("Compaction by vibrators adequate", "الدمك بالهزازات كافٍ", False, False),
            ("No water added on site", "لم تُضف مياه في الموقع", False, False),
            ("Placing sequence followed", "تسلسل الصب متبع", False, True),
            ("Hot weather measures in place", "إجراءات الطقس الحار مطبقة", False, True),
            ("Curing started on time", "المعالجة بدأت في الوقت", False, True),
        ],
    ),
    "QMEP-PT": (
        "ir_inspection",
        "Pressure test",
        "اختبار الضغط",
        [
            ("Test procedure approved", "إجراء الاختبار معتمد", False, False),
            ("Gauge calibrated and in range", "المقياس معاير وضمن المدى", True, False),
            ("Test pressure applied as specified", "ضغط الاختبار مطبق كما هو محدد", True, False),
            ("Holding time achieved", "زمن الثبات متحقق", True, False),
            ("No visible leaks", "لا تسربات مرئية", True, False),
            ("Isolation of equipment done", "عزل المعدات تم", False, True),
            ("Vents and drains provided", "فتحات التهوية والتصريف متوفرة", False, True),
            ("Test medium as specified", "وسط الاختبار كما هو محدد", False, False),
            ("Records signed by tester", "السجلات موقعة من القائم بالاختبار", False, False),
            ("System restored after test", "إعادة النظام بعد الاختبار", False, True),
        ],
    ),
    "QPUN": (
        "punch_walkdown",
        "Punch walkdown",
        "جولة النواقص",
        [
            ("Finishes free of damage and stains", "التشطيبات خالية من التلف والبقع", False, True),
            (
                "Doors and hardware operate correctly",
                "الأبواب والإكسسوارات تعمل بشكل صحيح",
                False,
                True,
            ),
            (
                "MEP fixtures complete and labelled",
                "تجهيزات الكهروميكانيك مكتملة ومعلّمة",
                False,
                True,
            ),
            ("Ceilings complete and aligned", "الأسقف مكتملة ومستوية", False, True),
            ("Area clean and clear of debris", "المنطقة نظيفة وخالية من المخلفات", False, True),
        ],
    ),
}


def _items(code: str, rows: list[tuple[str, str, bool, bool]]) -> list[dict[str, Any]]:
    short = code.rsplit("-", maxsplit=1)[-1][:3] if "-" in code else code[1:4]
    return [
        {
            "item_code": f"{short}-{n:02d}",
            "section_code": "A",
            "order": n,
            "text_en": en,
            "text_ar": ar,
            "item_type": ItemType.yes_no.value,
            "weight": 3 if crit else 1,
            "critical": crit,
            "stop_rule": StopRule.none.value,
            "na_allowed": na,
            "photo_required_on_fail": False,
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
        for n, (en, ar, crit, na) in enumerate(rows, start=1)
    ]


def ensure_library(db: Session) -> dict[str, ChecklistTemplate]:
    """Q1's published quality checklists (idempotent; also used by the Q1 test fixtures)."""
    from app.services.field.library import review_due  # noqa: PLC0415

    faisal = db.scalar(select(User.id).where(User.email == "faisal.harbi@example.com"))
    out = {}
    for code, (qtype, en, ar, rows) in TEMPLATES.items():
        t = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.template_code == code))
        if t is None:
            t = ChecklistTemplate(
                id=uuid.uuid4(),
                template_code=code,
                version=1,
                kind=TemplateKind.quality,
                quality_type=qtype,
                sector_profiles="construction",
                title_en=en,
                title_ar=ar,
                sections=[{"code": "A", "title_en": en, "title_ar": ar, "order": 1}],
                items=_items(code, rows),
                zone_types=[],
                project_ids=[],
                review_due_on=review_due(PUBLISHED),
                authored_by_user_id=faisal,
                published_by_user_id=faisal,
                published_at=PUBLISHED,
                status=VersionStatus.published,
                created_by_user_id=faisal,
                seed_fake=True,
            )
            db.add(t)
            db.flush()
        out[code] = t
    return out


# ---- lookups -------------------------------------------------------------------------------------


class _W:
    def __init__(self, db: Session, p: Project) -> None:
        self.db = db
        self.p = p
        self.users = {u.email.split("@")[0]: u.id for u in db.scalars(select(User))}
        self.sites = {s.code: s for s in db.scalars(select(Site).where(Site.project_id == p.id))}
        self.zones = {z.code: z for z in db.scalars(select(Zone).where(Zone.project_id == p.id))}
        self.engs = {
            e.contractor.short_code: e.id
            for e in db.scalars(
                select(ProjectEngagement).where(ProjectEngagement.project_id == p.id)
            )
        }
        self.systems = {
            s.code: s for s in db.scalars(select(QSystem).where(QSystem.project_id == p.id))
        }
        self.crit = {
            c.code: c.id
            for c in db.scalars(select(QCriterion).order_by(QCriterion.version))
            if c.status.value == "published"
        }
        self.mte = {
            m.mte_no: m for m in db.scalars(select(QMteItem).where(QMteItem.project_id == p.id))
        }

    def u(self, who: str) -> uuid.UUID:
        return self.users[who]


# ---- ITPs (Appendix A.3, §B.3.2) --------------------------------------------------------------

H, W_, R_, S_ = QPointType.H, QPointType.W, QPointType.R, QPointType.S
VIR, VDOC, VTST = QVerifyingRecord.ir, QVerifyingRecord.document, QVerifyingRecord.test_request

# seq, type, activity EN / AR, characteristic EN / AR, criteria codes, acceptance EN, verifying,
# template, extra
STC_POINTS: list[tuple[Any, ...]] = [
    (
        10,
        R_,
        "Approved mix design and materials",
        "اعتماد تصميم الخلطة والمواد",
        "MAR approved (A or B)",
        "اعتماد طلب المواد (A أو B)",
        [],
        "MAR approved (A or B)",
        VDOC,
        None,
        {},
    ),
    (
        20,
        W_,
        "Formwork, line and level",
        "القوالب والاستقامة والمناسيب",
        "± 5 mm in 3 m",
        "± 5 مم لكل 3 م",
        ["FORM-TOL"],
        None,
        VIR,
        "QSTC-FW",
        {},
    ),
    (
        30,
        H,
        "Reinforcement before pour",
        "حديد التسليح قبل الصب",
        "Size, spacing, cover 40 ± 5 mm, laps",
        "القطر والتباعد والغطاء 40 ± 5 مم والوصلات",
        ["COVER-40"],
        "Spacers and laps per drawing",
        VIR,
        "QSTC-RB",
        {},
    ),
    (
        40,
        W_,
        "Embedded items and MEP sleeves",
        "العناصر المدفونة وجلب الكهروميكانيك",
        "Position and fixing as drawings",
        "الموقع والتثبيت حسب المخططات",
        [],
        "As drawings",
        VIR,
        None,
        {},
    ),
    (
        50,
        W_,
        "Pour: slump, concrete temperature, sampling",
        "الصب: الهبوط وحرارة الخرسانة وأخذ العينات",
        "Slump, temperature, sampling per pour",
        "الهبوط والحرارة والعينات لكل صبة",
        ["SLUMP-100", "CONC-TEMP-32"],
        "Sampling per pour",
        VIR,
        "QSTC-PR",
        {"test_type_codes": ["SLUMP", "CONC-CYL"], "competence_code": "CONC-FIELD-TECH"},
    ),
    (
        60,
        S_,
        "Curing for 7 days",
        "المعالجة لمدة 7 أيام",
        "Wet curing maintained",
        "المعالجة الرطبة مستمرة",
        ["CURE-7D"],
        None,
        VIR,
        None,
        {},
    ),
    (
        70,
        H,
        "Striking of formwork",
        "فك القوالب",
        "≥ 70 % f'c by cubes or 7 days",
        "≥ 70 % من المقاومة أو 7 أيام",
        ["STRIKE-70"],
        None,
        VIR,
        None,
        {},
    ),
    (
        80,
        R_,
        "28-day strength",
        "المقاومة عند 28 يوماً",
        "f'c 40 MPa (ACI 318)",
        "المقاومة 40 ميغاباسكال",
        ["CONC-ACI-40"],
        None,
        VTST,
        None,
        {"test_type_codes": ["CONC-CYL"]},
    ),
    (
        90,
        W_,
        "Surface finish and dimensions",
        "تشطيب السطح والأبعاد",
        "As specification",
        "حسب المواصفات",
        [],
        "As specification",
        VIR,
        None,
        {},
    ),
]
STL_POINTS: list[tuple[Any, ...]] = [
    (
        10,
        R_,
        "WPS / PQR and welder qualifications",
        "مواصفات اللحام وتأهيل اللحامين",
        "Approved WPS and valid WPQ",
        "مواصفة معتمدة وتأهيل ساري",
        [],
        "WPS approved, WPQ valid",
        VDOC,
        None,
        {},
    ),
    (
        20,
        W_,
        "Fit-up before welding",
        "التجميع قبل اللحام",
        "Root gap, alignment, bevel",
        "فتحة الجذر والمحاذاة والشطف",
        [],
        "Per WPS-NAJD-SMAW-01",
        VIR,
        None,
        {"competence_code": "CWI"},
    ),
    (
        30,
        H,
        "Visual inspection of completed welds",
        "الفحص البصري للحامات المكتملة",
        "AWS D1.1 Table 8.1",
        "جدول AWS D1.1 8.1",
        [],
        "AWS D1.1 visual acceptance",
        VIR,
        None,
        {"competence_code": "CWI"},
    ),
    (
        40,
        R_,
        "NDT results (RT 10 %)",
        "نتائج الفحص غير الإتلافي",
        "RT per lot",
        "التصوير الإشعاعي لكل دفعة",
        [],
        "AWS D1.1 RT acceptance",
        VTST,
        None,
        {},
    ),
    (
        50,
        W_,
        "Bolt tightening",
        "شد البراغي",
        "Torque M20 400 ± 20 N·m",
        "عزم M20 400 ± 20 نيوتن·م",
        ["TORQUE-M20"],
        None,
        VIR,
        None,
        {},
    ),
]
AFP_POINTS: list[tuple[Any, ...]] = [
    (
        10,
        R_,
        "Approved asphalt mix design",
        "اعتماد تصميم الخلطة الإسفلتية",
        "Marshall mix approved",
        "خلطة مارشال معتمدة",
        [],
        "Mix design approved",
        VDOC,
        None,
        {},
    ),
    (
        20,
        H,
        "Base course acceptance",
        "قبول طبقة الأساس",
        "Compaction ≥ 98 %",
        "الدمك ≥ 98 %",
        ["COMP-98"],
        None,
        VIR,
        None,
        {},
    ),
    (
        30,
        W_,
        "Laying temperature and tack coat",
        "حرارة الفرش وطبقة اللصق",
        "Per specification",
        "حسب المواصفات",
        [],
        "Laying temperature per spec",
        VIR,
        None,
        {},
    ),
    (
        40,
        W_,
        "Compaction of surface course",
        "دمك الطبقة السطحية",
        "Compaction ≥ 98 %",
        "الدمك ≥ 98 %",
        ["COMP-98"],
        None,
        VIR,
        None,
        {},
    ),
    (
        50,
        R_,
        "Cores: thickness and density",
        "العينات اللبية: السماكة والكثافة",
        "Per specification",
        "حسب المواصفات",
        [],
        "Core results per spec",
        VTST,
        None,
        {},
    ),
]
HVC_POINTS: list[tuple[Any, ...]] = [
    (
        10,
        R_,
        "Shop drawings and material approval",
        "مخططات التنفيذ واعتماد المواد",
        "Approved shop drawings",
        "مخططات تنفيذ معتمدة",
        [],
        "Approved",
        VDOC,
        None,
        {},
    ),
    (
        20,
        W_,
        "Ductwork installation",
        "تركيب مجاري الهواء",
        "Supports, joints, sealing",
        "الحوامل والوصلات والإحكام",
        [],
        "SMACNA installation practice",
        VIR,
        None,
        {},
    ),
    (
        30,
        H,
        "Duct leakage / pressure test",
        "اختبار تسرب مجاري الهواء",
        "Leakage class per specification",
        "فئة التسرب حسب المواصفات",
        [],
        "Leakage within class",
        VIR,
        "QMEP-PT",
        {},
    ),
    (
        40,
        W_,
        "Insulation and vapour barrier",
        "العزل وحاجز البخار",
        "Thickness and continuity",
        "السماكة والاستمرارية",
        [],
        "As specification",
        VIR,
        None,
        {},
    ),
]


def _points(
    db: Session, w: _W, it: QItp, rows: list[tuple[Any, ...]], by: uuid.UUID, tweak: Any = None
) -> None:
    for r in rows:
        seq, typ, a_en, a_ar, c_en, c_ar, crit, acc, ver, tpl, extra = r
        if tweak:
            typ, crit = tweak(seq, typ, list(crit))
        db.add(
            QItpPoint(
                itp_id=it.id,
                seq=seq,
                activity_en=a_en,
                activity_ar=a_ar,
                characteristic_en=c_en,
                characteristic_ar=c_ar,
                point_type=typ,
                criteria_ids=[w.crit[c] for c in crit if c in w.crit],
                acceptance_text_en=acc,
                acceptance_text_ar=c_ar if acc else None,
                reference="Spec 03 30 00" if it.discipline == QDiscipline.STC else None,
                verifying_record=ver,
                checklist_template_code=tpl,
                test_type_codes=list(extra.get("test_type_codes") or []),
                frequency_text="each pour" if it.discipline == QDiscipline.STC else "each lot",
                competence_code=extra.get("competence_code"),
                created_by_user_id=by,
                seed_fake=True,
            )
        )
    db.flush()


def _sign(
    db: Session,
    p: Project,
    rt: QRecordType,
    rid: uuid.UUID,
    step: str,
    decision: str,
    who: uuid.UUID,
    when: datetime,
    capacity: str = CRE,
    comment: str | None = None,
    paper: dict[str, Any] | None = None,
) -> QSignoff:
    s = QSignoff(
        id=uuid.uuid4(),
        project_id=p.id,
        record_type=rt.value,
        record_id=rid,
        step=step,
        decision=decision,
        comment=comment,
        signed_by_user_id=who,
        signed_at=when,
        signer_capacity=capacity if not paper else f"paper: {paper['position']}",
        channel=QSignoffChannel.paper if paper else QSignoffChannel.in_app,
        external_name=paper["name"] if paper else None,
        external_organisation=paper["organisation"] if paper else None,
        external_position=paper["position"] if paper else None,
        external_signed_on=paper["signed_on"] if paper else None,
        evidence_attachment_ids=[],
        seed_fake=True,
    )
    db.add(s)
    return s


def _itp(
    db: Session,
    w: _W,
    *,
    no: str,
    rev: int,
    fam: uuid.UUID,
    title: tuple[str, str],
    disc: QDiscipline,
    eng: str,
    zones: list[str],
    systems: list[str],
    status: QItpStatus,
    approved: date | None,
    rows: list[tuple[Any, ...]],
    code: QApprovalCode = QApprovalCode.A,
    note: str | None = None,
    tweak: Any = None,
    superseded: date | None = None,
) -> QItp:
    bilal = w.u("bilal.qureshi")
    it = QItp(
        id=uuid.uuid4(),
        project_id=w.p.id,
        family_id=fam,
        itp_no=no,
        revision=rev,
        title_en=title[0],
        title_ar=title[1],
        discipline=disc,
        work_package_en=title[0],
        engagement_id=w.engs[eng],
        zone_ids=[w.zones[z].id for z in zones],
        system_ids=[w.systems[s].id for s in systems],
        spec_refs=["03 30 00 Cast-in-place concrete"] if disc == QDiscipline.STC else [],
        code_refs=["SBC 304"] if disc == QDiscipline.STC else [],
        method_statement_ref="MS-ANIA-EXP-STC-004" if disc == QDiscipline.STC else None,
        change_note=note,
        approval_code=code if approved else None,
        prepared_by_user_id=bilal,
        submitted_by_user_id=bilal,
        submitted_at=at(approved - timedelta(days=5)) if approved else None,
        decided_at=at(approved, 14) if approved else None,
        approved_at=at(approved, 14) if approved else None,
        superseded_at=at(superseded, 14) if superseded else None,
        status=status,
        status_changed_at=at(superseded or approved or date(2026, 3, 1), 14),
        created_by_user_id=bilal,
        seed_fake=True,
    )
    db.add(it)
    db.flush()
    _points(db, w, it, rows, bilal, tweak)
    if approved:
        _sign(
            db,
            w.p,
            QRecordType.itp,
            it.id,
            "approve",
            "approved_with_comments" if code == QApprovalCode.B else "approved",
            w.u("abdullah.dossary"),
            at(approved, 14),
            comment="Approved as noted: add sampling log." if code == QApprovalCode.B else None,
        )
    return it


def _itps(db: Session, w: _W) -> dict[str, QItp]:
    stc = uuid.uuid4()
    title = (
        "Cast-in-situ concrete, Pier B and car park",
        "الخرسانة المصبوبة في الموقع، الرصيف B ومواقف السيارات",
    )
    zones = ["Z-PIERB", "Z-MSCP"]

    def rev0(seq: int, typ: QPointType, crit: list[str]) -> tuple[QPointType, list[str]]:
        if seq == 50:
            crit = [c for c in crit if c != "CONC-TEMP-32"]
        return (W_ if seq == 70 else typ), crit

    def rev1(seq: int, typ: QPointType, crit: list[str]) -> tuple[QPointType, list[str]]:
        return typ, [c for c in crit if c != "CONC-TEMP-32"] if seq == 50 else crit

    _itp(
        db,
        w,
        no="ITP-ANIA-EXP-STC-001",
        rev=0,
        fam=stc,
        title=title,
        disc=QDiscipline.STC,
        eng="RAWABI",
        zones=zones,
        systems=[],
        status=QItpStatus.superseded,
        approved=date(2026, 2, 10),
        rows=STC_POINTS,
        tweak=rev0,
        superseded=date(2026, 5, 20),
    )
    _itp(
        db,
        w,
        no="ITP-ANIA-EXP-STC-001",
        rev=1,
        fam=stc,
        title=title,
        disc=QDiscipline.STC,
        eng="RAWABI",
        zones=zones,
        systems=[],
        status=QItpStatus.superseded,
        approved=date(2026, 5, 20),
        rows=STC_POINTS,
        note="Point 70 striking becomes a hold point.",
        tweak=rev1,
        superseded=date(2026, 8, 18),
    )
    out = {
        "STC": _itp(
            db,
            w,
            no="ITP-ANIA-EXP-STC-001",
            rev=2,
            fam=stc,
            title=title,
            disc=QDiscipline.STC,
            eng="RAWABI",
            zones=zones,
            systems=[],
            status=QItpStatus.approved,
            approved=date(2026, 8, 18),
            rows=STC_POINTS,
            code=QApprovalCode.B,
            note="Point 50 adds concrete temperature ≤ 32 °C",
        ),
    }
    stl = uuid.uuid4()
    stl_t = ("Structural steel welding, Pier B roof", "لحام الحديد الإنشائي، سقف الرصيف B")
    _itp(
        db,
        w,
        no="ITP-ANIA-EXP-STL-001",
        rev=0,
        fam=stl,
        title=stl_t,
        disc=QDiscipline.STL,
        eng="NAJD",
        zones=["Z-PIERB"],
        systems=[],
        status=QItpStatus.superseded,
        approved=date(2026, 3, 2),
        rows=STL_POINTS,
        superseded=date(2026, 6, 4),
    )
    out["STL"] = _itp(
        db,
        w,
        no="ITP-ANIA-EXP-STL-001",
        rev=1,
        fam=stl,
        title=stl_t,
        disc=QDiscipline.STL,
        eng="NAJD",
        zones=["Z-PIERB"],
        systems=[],
        status=QItpStatus.approved,
        approved=date(2026, 6, 4),
        rows=STL_POINTS,
        note="Bolt tightening point added.",
    )
    out["AFP"] = _itp(
        db,
        w,
        no="ITP-ANIA-EXP-AFP-001",
        rev=0,
        fam=uuid.uuid4(),
        title=("Asphalt surfacing, apron and taxiway B", "رصف الأسفلت، الساحة والممر B"),
        disc=QDiscipline.AFP,
        eng="GULFPAVE",
        zones=["Z-APR-21", "Z-TWB"],
        systems=[],
        status=QItpStatus.approved,
        approved=date(2026, 4, 12),
        rows=AFP_POINTS,
    )
    out["HVC"] = _itp(
        db,
        w,
        no="ITP-ANIA-EXP-HVC-001",
        rev=0,
        fam=uuid.uuid4(),
        title=("Ductwork and pressure tests, Terminal 3", "مجاري الهواء واختبارات الضغط، الصالة 3"),
        disc=QDiscipline.HVC,
        eng="RAWABI",
        zones=[],
        systems=["SYS-T3-HVAC"],
        status=QItpStatus.approved,
        approved=date(2026, 5, 6),
        rows=HVC_POINTS,
    )
    from app.services.quality import numbering  # noqa: PLC0415

    for disc in ("STC", "STL", "AFP", "HVC"):
        numbering.bump_to(db, w.p, QRecordType.itp, 2026, 1, disc)
    return out


# ---- IR generator (Appendix A.4, QX2, QX24) ---------------------------------------------------


R = QIrResult


class _Gen:
    """Builds IRs, rounds, responses and sign-offs; counts opportunities and defects."""

    def __init__(
        self, db: Session, w: _W, tpl: dict[str, ChecklistTemplate], itps: dict[str, QItp]
    ) -> None:
        self.db, self.w, self.tpl, self.itps = db, w, tpl, itps
        self.points = {
            k: {pt.seq: pt for pt in db.scalars(select(QItpPoint).where(QItpPoint.itp_id == it.id))}
            for k, it in itps.items()
        }
        self.na_budget = 0
        self.opps = 0
        self.defects = 0

    def response(
        self, rnd: QIrRound, ir: QIr, pt: QItpPoint, when: datetime, fail: str | None
    ) -> str:
        """fail: None, 'critical' (first critical item non-compliant) or 'minor'."""
        t = self.tpl[pt.checklist_template_code or ""]
        items = t.items
        na_codes = [i["item_code"] for i in items if i["na_allowed"]]
        take = min(self.na_budget, len(na_codes))
        self.na_budget -= take
        na = set(na_codes[:take])
        bad = None
        if fail == "critical":
            bad = next(i["item_code"] for i in items if i["critical"])
        elif fail == "minor":
            bad = next(i["item_code"] for i in items if not i["critical"] and not i["na_allowed"])
        answers = []
        app = comp = 0
        aw = ew = Decimal(0)
        crit_fails = 0
        for i in items:
            code = i["item_code"]
            wgt = Decimal(i["weight"])
            if code in na:
                answers.append(
                    {
                        "item_code": code,
                        "item_type": "yes_no",
                        "answer": "na",
                        "applicable": False,
                        "compliant": None,
                        "critical": i["critical"],
                        "photo_ids": [],
                        "note": None,
                    }
                )
                continue
            ok = code != bad
            app += 1
            comp += int(ok)
            aw += wgt
            ew += wgt if ok else 0
            crit_fails += int(not ok and i["critical"])
            answers.append(
                {
                    "item_code": code,
                    "item_type": "yes_no",
                    "answer": "compliant" if ok else "non_compliant",
                    "note": None if ok else "Found during the inspection; to be corrected.",
                    "applicable": True,
                    "compliant": ok,
                    "critical": i["critical"],
                    "photo_ids": [],
                    "weight": str(wgt),
                    "earned_weight": str(wgt if ok else 0),
                }
            )
        self.opps += app
        self.defects += app - comp
        r = ChecklistResponse(
            id=uuid.uuid4(),
            project_id=ir.project_id,
            client_uuid=uuid.uuid4(),
            owner_type=ResponseOwnerType.q_ir_round,
            template_id=t.id,
            template_code=t.template_code,
            template_version=t.version,
            site_id=ir.site_id,
            zone_id=ir.zone_id,
            engagement_id=ir.engagement_id,
            started_at=when,
            completed_at=when,
            completed_date=when.astimezone(RIYADH).date(),
            received_at=when,
            inspector_id=rnd.inspector_id,
            answers=answers,
            applicable_count=app,
            compliant_count=comp,
            applicable_weight=aw,
            earned_weight=ew,
            score_pct=(ew / aw * 100).quantize(Decimal("0.001")) if aw else None,
            critical_fail_count=crit_fails,
            result=ResponseResult.fail if crit_fails else ResponseResult.pass_,
            submitted=True,
            warnings=[],
            seed_fake=True,
        )
        self.db.add(r)
        return str(r.id)

    def measurements(self, ir: QIr, fail: bool) -> list[dict[str, Any]]:
        vals = {
            "FORM-TOL": ("3", "mm"),
            "COVER-40": ("33" if fail else "41", "mm"),
            "SLUMP-100": ("105", "mm"),
            "CONC-TEMP-32": ("29.5", "°C"),
            "TORQUE-M20": ("402", "N·m"),
            "COMP-98": ("98.6", "%"),
            "STRIKE-70": ("74", "%"),
        }
        out = []
        crits = {c.id: c for c in self.db.scalars(select(QCriterion))}
        for key in self.points:
            if self.itps[key].id != ir.itp_id:
                continue
            for s in ir.point_seqs:
                for cid in self.points[key][s].criteria_ids:
                    c = crits[cid]
                    if c.kind.value == "text":
                        out.append(
                            {
                                "point_seq": s,
                                "name": c.title_en,
                                "value": None,
                                "unit": None,
                                "criterion_id": str(c.id),
                                "criterion_code": c.code,
                                "criterion_version": c.version,
                                "mte_id": None,
                                "mte_no": None,
                                "verdict": "pass",
                                "reason_en": "Verdict entered by the inspector.",
                                "reason_ar": "النتيجة أدخلها المفتش.",
                            }
                        )
                        continue
                    v, unit = vals.get(c.code, ("1", c.unit))
                    bad = fail and c.code == "COVER-40"
                    verdict = (
                        "not_evaluable" if c.kind.value == "rule" else ("fail" if bad else "pass")
                    )
                    mte = self.w.mte.get("MTE-0012") if c.code == "CONC-TEMP-32" else None
                    out.append(
                        {
                            "point_seq": s,
                            "name": c.title_en,
                            "value": v,
                            "unit": unit,
                            "criterion_id": str(c.id),
                            "criterion_code": c.code,
                            "criterion_version": c.version,
                            "mte_id": str(mte.id) if mte else None,
                            "mte_no": mte.mte_no if mte else None,
                            "verdict": verdict,
                            "reason_en": "",
                            "reason_ar": "",
                        }
                    )
        return out

    def ir(
        self,
        key: str,
        no: int | None,
        seqs: list[int],
        zone: str | None,
        loc: str,
        status: QIrStatus,
        submitted: datetime | None,
        requester: str = "joseph.mathew.qc",
        system: str | None = None,
    ) -> QIr:
        it = self.itps[key]
        pts = self.points[key]
        z = self.w.zones[zone] if zone else None
        sy = self.w.systems[system] if system else None
        site = self.w.sites["S-LAND"] if key in ("STC", "STL", "HVC") else self.w.sites["S-AIR"]
        ir = QIr(
            id=uuid.uuid4(),
            project_id=self.w.p.id,
            ir_no=f"IR-ANIA-EXP-2026-{no:05d}" if no else None,
            itp_id=it.id,
            itp_family_id=it.family_id,
            itp_revision=it.revision,
            point_seqs=sorted(seqs),
            engagement_id=it.engagement_id,
            governing_type=strictest([pts[s].point_type for s in seqs]),
            site_id=site.id,
            zone_id=z.id if z else None,
            system_id=sy.id if sy else None,
            location_ref=loc,
            location_key=location_key(z.code if z else None, sy.code if sy else None, loc),
            requested_by_user_id=self.w.u(requester),
            submitted_by_user_id=self.w.u(requester) if submitted else None,
            submitted_at=submitted,
            proposed_at=submitted + timedelta(hours=26) if submitted else None,
            self_check_done=True,
            current_round=1,
            status=status,
            status_changed_at=submitted,
            responsible_set=[self.w.u("abdullah.dossary")],
            alerts_sent=[],
            created_by_user_id=self.w.u(requester),
            seed_fake=True,
        )
        self.db.add(ir)
        self.db.flush()
        return ir

    def round_(
        self,
        ir: QIr,
        n: int,
        decided: datetime | None,
        result: QIrResult | None,
        *,
        fail: str | None = None,
        category: QNcrCategory | None = None,
        comment: str | None = None,
        inspector: str = "abdullah.dossary",
        paper: dict[str, Any] | None = None,
        scheduled: datetime | None = None,
    ) -> QIrRound:
        key = next(k for k, it in self.itps.items() if it.id == ir.itp_id)
        insp = self.w.u(inspector)
        rnd = QIrRound(
            id=uuid.uuid4(),
            ir_id=ir.id,
            project_id=ir.project_id,
            round_no=n,
            scheduled_at=scheduled or decided,
            scheduled_by_user_id=insp,
            inspector_id=insp,
            attended_at=decided,
            inspected_at=decided,
            decided_date=decided.astimezone(RIYADH).date() if decided and result else None,
            responses={},
            measurements=[],
            result=result,
            reject_category=category,
            comment=comment,
            decided_by_user_id=insp if result else None,
            requested_by_user_id=ir.requested_by_user_id,
            correction_note="Corrected as required and checked by the contractor's QC."
            if n > 1
            else None,
            reschedules=[],
            warnings=[],
            seed_fake=True,
        )
        self.db.add(rnd)
        self.db.flush()
        if result is not None and decided is not None and result != QIrResult.not_ready:
            resp = {}
            tpl_seqs = [s for s in ir.point_seqs if self.points[key][s].checklist_template_code]
            target = (
                30 if fail == "critical" and 30 in tpl_seqs else (tpl_seqs[0] if tpl_seqs else None)
            )
            for s in tpl_seqs:
                pt = self.points[key][s]
                resp[str(s)] = self.response(rnd, ir, pt, decided, fail if s == target else None)
            rnd.responses = resp
            rnd.measurements = self.measurements(ir, fail == "critical")
        if result is not None and decided is not None:
            sig = _sign(
                self.db,
                self.w.p,
                QRecordType.ir,
                ir.id,
                "inspect",
                result.value,
                insp,
                decided,
                CRE if ir.governing_type in (H, W_) else "role:qc_inspector",
                comment,
                paper,
            )
            self.db.flush()
            rnd.signoff_id = sig.id
            ir.decided_at = decided
            ir.decided_date = rnd.decided_date
        ir.current_round = n
        return rnd


def _sept(i: int, n: int) -> date:
    """Spread n events over 1–26 September deterministically."""
    return date(2026, 9, 1) + timedelta(days=(i * 26) // max(n, 1))


def _irs(
    db: Session, w: _W, tpl: dict[str, ChecklistTemplate], itps: dict[str, QItp]
) -> dict[str, QIr]:
    g = _Gen(db, w, tpl, itps)
    named: dict[str, QIr] = {}
    # opportunities (QX24): 52 + 9 + 21 + 20 rounds of points [20, 30, 50] (38 items each), 33 of
    # [20, 30] (28), the named rounds (16 + 16 + 10 + 12), less 34 `na` answers → 4,820
    g.na_budget = 34
    numbers = iter(n for n in range(300, 480) if n not in (412, 455, 461))
    # round-1 plan of the 117 generator IRs (the named 00412, 00455 and the paper IR complete 120)
    plan: list[str] = (["pass"] * 85) + (["awc"] * 9) + (["rej"] * 21) + (["nr"] * 2)
    minor_left = 6  # non-compliant minor items in approved-with-comments rounds (31 = 25 + 6)
    reinspect = 0
    passes = 0
    for i, kind in enumerate(plan):
        d = _sept(i, len(plan))
        dec = at(d, 10 + (i % 6), 15)
        loc = f"Level {1 + i % 4} slab, bay {chr(65 + (i // 4) % 20)}{1 + i % 9}"
        seqs = [20, 30, 50]
        if kind == "pass":
            passes += 1
            seqs = [20, 30, 50] if passes <= 52 else [20, 30]
        ir = g.ir(
            "STC", next(numbers), seqs, "Z-MSCP", loc, QIrStatus.approved, dec - timedelta(days=1)
        )
        if kind == "pass":
            g.round_(ir, 1, dec, R.approved)
        elif kind == "awc":
            fail = "minor" if minor_left > 0 else None
            minor_left -= 1 if fail else 0
            rnd = g.round_(
                ir,
                1,
                dec,
                R.approved_with_comments,
                fail=fail,
                comment="Approved with one comment.",
            )
            ir.status = QIrStatus.approved_with_comments
            db.add(
                QIrComment(
                    ir_id=ir.id,
                    round_id=rnd.id,
                    project_id=ir.project_id,
                    text_en="Clean the soffit before the pour.",
                    text_ar="نظف البطنية قبل الصب.",
                    status=QIrCommentStatus.closed,
                    due_on=d + timedelta(days=14),
                    response_text="Cleaned and photographed.",
                    responded_at=dec + timedelta(hours=4),
                    closed_at=dec + timedelta(hours=8),
                    closed_by_user_id=w.u("abdullah.dossary"),
                    seed_fake=True,
                )
            )
        else:
            res = R.rejected if kind == "rej" else R.not_ready
            g.round_(
                ir,
                1,
                dec,
                res,
                fail="critical" if kind == "rej" else None,
                category=QNcrCategory.workmanship if kind == "rej" else None,
                comment="Spacers missing and cover low at several bars."
                if kind == "rej"
                else "Works not ready on arrival.",
            )
            ir.status = QIrStatus.rejected
            # re-inspections: 19 rejected (+ the named 00412) and both not-ready rounds → 21
            if reinspect < 20 and d <= date(2026, 9, 26):
                reinspect += 1
                d2 = d + timedelta(days=2)
                ok = reinspect > 3
                ir.status = QIrStatus.approved if ok else QIrStatus.rejected
                g.round_(
                    ir,
                    2,
                    at(d2, 11),
                    R.approved if ok else R.rejected,
                    fail=None if ok else "critical",
                    category=None if ok else QNcrCategory.workmanship,
                    comment=None if ok else "Cover still below tolerance at grid line 4.",
                )
    # named IRs (Appendix A.4)
    stc = itps["STC"]
    ir412 = g.ir(
        "STC",
        412,
        [30],
        "Z-PIERB",
        "Level 3 slab, grid C14–C20",
        QIrStatus.approved,
        at(date(2026, 9, 12), 15),
    )
    g.round_(
        ir412,
        1,
        at(date(2026, 9, 14), 9, 30),
        R.rejected,
        fail="critical",
        category=QNcrCategory.workmanship,
        comment="Spacers missing under the bottom mat.",
    )
    g.round_(ir412, 2, at(date(2026, 9, 15), 10), R.approved)
    named["412"] = ir412
    ir455 = g.ir(
        "STC",
        455,
        [50],
        "Z-PIERB",
        "Level 2 slab, grid C14–C20",
        QIrStatus.approved_with_comments,
        at(date(2026, 8, 30), 11),
    )
    r455 = g.round_(
        ir455,
        1,
        at(date(2026, 9, 1), 7, 30),
        R.approved_with_comments,
        comment="Approved; one comment.",
    )
    db.add(
        QIrComment(
            ir_id=ir455.id,
            round_id=r455.id,
            project_id=ir455.project_id,
            text_en="Record the sampling log in the pour register.",
            text_ar="سجل عينات الصب في سجل الصبات.",
            status=QIrCommentStatus.closed,
            due_on=date(2026, 9, 15),
            response_text="Log updated.",
            responded_at=at(date(2026, 9, 3)),
            closed_at=at(date(2026, 9, 4)),
            closed_by_user_id=w.u("abdullah.dossary"),
            seed_fake=True,
        )
    )
    m = w.mte.get("MTE-0012")
    if m is not None:
        db.add(
            QMteUsage(
                mte_id=m.id,
                project_id=w.p.id,
                record_type="ir",
                record_id=ir455.id,
                used_at=at(date(2026, 9, 1), 7, 30),
                verdict="ok",
                cal_status_at_use=m.cal_status,
                value_note="Concrete temperature 29.5 °C",
                recorded_by_user_id=w.u("abdullah.dossary"),
                seed_fake=True,
            )
        )
    named["455"] = ir455
    paper = {
        "name": "Abdullah Al-Dossary",
        "organisation": "Consultant (PMC)",
        "position": "Resident Engineer",
        "signed_on": date(2026, 9, 9),
    }
    irp = g.ir(
        "STC",
        next(numbers),
        [20],
        "Z-PIERB",
        "Level 3 columns, grid C14–C16",
        QIrStatus.approved,
        at(date(2026, 9, 8), 10),
    )
    g.round_(irp, 1, at(date(2026, 9, 9), 8), R.approved, inspector="hatem.shehri", paper=paper)
    named["paper"] = irp
    # waived witness rounds (4): HVC-001 point 20 IR-00461 and three at the car park
    hv = itps["HVC"]
    ir461 = g.ir(
        "HVC",
        461,
        [20],
        None,
        "Level 1 east plant room ductwork",
        QIrStatus.approved,
        at(date(2026, 9, 16), 9),
        system="SYS-T3-HVAC",
    )
    rw = g.round_(ir461, 1, None, None, scheduled=at(date(2026, 9, 18), 8))
    rw.result = R.waived
    rw.waived_at = at(date(2026, 9, 18), 9, 20)
    rw.waived_by_user_id = w.u("joseph.mathew.qc")
    rw.decided_date = date(2026, 9, 18)
    rw.review_result = R.approved
    rw.reviewed_at = at(date(2026, 9, 20), 11)
    rw.attended_at = None
    rw.decided_by_user_id = w.u("abdullah.dossary")
    s = _sign(
        db,
        w.p,
        QRecordType.ir,
        ir461.id,
        "inspect",
        "approved",
        w.u("abdullah.dossary"),
        at(date(2026, 9, 20), 11),
    )
    db.flush()
    rw.signoff_id = s.id
    ir461.decided_at, ir461.decided_date = at(date(2026, 9, 20), 11), date(2026, 9, 20)
    named["461"] = ir461
    for j in range(3):
        irw = g.ir(
            "STC",
            next(numbers),
            [40],
            "Z-MSCP",
            f"Level {j + 2} slab, embeds bay W{j + 1}",
            QIrStatus.approved,
            at(date(2026, 9, 5 + j * 6), 9),
        )
        rw = g.round_(irw, 1, None, None, scheduled=at(date(2026, 9, 6 + j * 6), 8))
        rw.result, rw.waived_at = R.waived, at(date(2026, 9, 6 + j * 6), 9, 15)
        rw.waived_by_user_id, rw.decided_date = w.u("joseph.mathew.qc"), date(2026, 9, 6 + j * 6)
        rw.review_result, rw.reviewed_at = R.approved, at(date(2026, 9, 7 + j * 6), 10)
        s = _sign(
            db,
            w.p,
            QRecordType.ir,
            irw.id,
            "inspect",
            "approved",
            w.u("abdullah.dossary"),
            rw.reviewed_at,
        )
        db.flush()
        rw.signoff_id = s.id
    # two IRs cancelled without a decided round
    for j in range(2):
        irc = g.ir(
            "STC",
            next(numbers),
            [20, 30],
            "Z-MSCP",
            f"Ramp {j + 1} slab",
            QIrStatus.cancelled,
            at(date(2026, 9, 10 + j), 9),
        )
        irc.status_reason = "Works re-sequenced; superseded by a later request."
        g.round_(irc, 1, None, None)
    # open IRs for "today" (2026-10-06): two scheduled, two to schedule, one draft
    for j in range(2):
        iro = g.ir(
            "STC",
            next(numbers),
            [30],
            "Z-MSCP",
            f"Level 5 slab, bay T{j + 1}",
            QIrStatus.scheduled,
            at(date(2026, 10, 4), 10 + j),
        )
        g.round_(iro, 1, None, None, scheduled=at(date(2026, 10, 6), 11 + j))
    for j in range(2):
        iro = g.ir(
            "AFP" if j == 0 else "STC",
            next(numbers),
            [20] if j == 0 else [50],
            "Z-APR-21" if j == 0 else "Z-MSCP",
            "Stand 23 base course" if j == 0 else "Level 4 slab, bay K2",
            QIrStatus.submitted,
            at(date(2026, 10, 5), 15),
            requester="joseph.mathew.qc",
        )
        g.round_(iro, 1, None, None)
    g.ir("STC", None, [20], "Z-MSCP", "Level 5 slab, bay T3", QIrStatus.draft, None)
    db.flush()
    last = max(
        int(x.ir_no.rsplit("-", 1)[1])
        for x in db.scalars(select(QIr).where(QIr.project_id == w.p.id))
        if x.ir_no
    )
    from app.services.quality import numbering  # noqa: PLC0415

    numbering.bump_to(db, w.p, QRecordType.ir, 2026, last)
    _ = (stc, hv)
    return named


# ---- floor plan and punch (Appendix A.3, A.4) --------------------------------------------------

_PLAN: bytes | None = None


def plan_png() -> bytes:
    """A simple 4,200 × 2,800 px plan: grid lines and a pier outline (cached)."""
    global _PLAN  # noqa: PLW0603
    if _PLAN is None:
        from PIL import Image, ImageDraw  # noqa: PLC0415

        img = Image.new("L", (4200, 2800), 255)
        d = ImageDraw.Draw(img)
        for x in range(200, 4200, 400):
            d.line([(x, 150), (x, 2650)], fill=170, width=3)
        for y in range(150, 2800, 400):
            d.line([(200, y), (4000, y)], fill=170, width=3)
        d.rectangle([300, 400, 3900, 2400], outline=0, width=12)
        d.rectangle([1600, 900, 2600, 1900], outline=60, width=8)
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        _PLAN = buf.getvalue()
    return _PLAN


def _punch(db: Session, w: _W) -> QFloorPlan:
    from app.services import attachments  # noqa: PLC0415
    from app.services.quality import numbering  # noqa: PLC0415

    z = w.zones["Z-PIERB"]
    hatem = w.u("hatem.shehri")
    fp = QFloorPlan(
        id=uuid.uuid4(),
        project_id=w.p.id,
        family_id=uuid.uuid4(),
        zone_id=z.id,
        level_label="Level 1",
        title_en="Pier B Level 1",
        title_ar="الرصيف B المستوى 1",
        revision="2",
        width_px=4200,
        height_px=2800,
        status=QPlanStatus.current,
        created_by_user_id=hatem,
        seed_fake=True,
    )
    db.add(fp)
    db.flush()
    a = attachments.store(
        db,
        AttachmentOwner.q_floor_plan,
        fp.id,
        w.p.id,
        "pier-b-level-1-rev2.png",
        plan_png(),
        "image/png",
        hatem,
        shrink=False,
        generated=True,
    )
    fp.attachment_id = a.id
    descs = [
        ("Ceiling tile damaged and stained", "بلاطة سقف تالفة وملطخة", QDiscipline.ARC),
        ("Door closer not adjusted", "مغلق الباب غير مضبوط", QDiscipline.ARC),
        (
            "Fire stopping missing around cable tray",
            "مانع الحريق مفقود حول حامل الكابلات",
            QDiscipline.FPS,
        ),
        (
            "Diffuser not aligned with ceiling grid",
            "مخرج الهواء غير محاذٍ لشبكة السقف",
            QDiscipline.HVC,
        ),
        ("Socket outlet faceplate cracked", "غطاء المقبس مشقوق", QDiscipline.ELE),
        ("Paint touch-up needed on column", "يلزم ترميم الدهان على العمود", QDiscipline.ARC),
        ("Floor tile hollow sounding", "بلاط أرضية مجوف الصوت", QDiscipline.ARC),
        ("Sprinkler head escutcheon missing", "غطاء رأس الرشاش مفقود", QDiscipline.FPS),
    ]
    raisers = [w.u("mazen.harbi"), hatem, w.u("abdullah.dossary")]
    # 46 items with a September target: 30 closed (24 on or before target), 16 open (3 category A)
    for i in range(46):
        no = 273 + i
        cat = QPunchCategory.A if i in (5, 17, 45) or i % 5 == 0 else QPunchCategory.B
        target = date(2026, 9, 1) + timedelta(days=(i * 27) // 45)
        if no == 318:
            cat, target = QPunchCategory.A, date(2026, 9, 28)
        raised = target - timedelta(days=14 if cat == QPunchCategory.A else 30)
        closed = i < 30
        late = closed and i % 5 == 4  # 6 late closures
        open_a = (not closed) and no in (300 + 3, 300 + 10, 318)
        if not closed and cat == QPunchCategory.A and not open_a:
            cat = QPunchCategory.B
            raised = target - timedelta(days=30)
        if not closed and open_a:
            cat = QPunchCategory.A
            raised = target - timedelta(days=14)
        en, ar, disc = descs[i % len(descs)]
        pinned = i % 4 == 0 and i < 48 and len([k for k in range(i) if k % 4 == 0]) < 12
        it = QPunchItem(
            id=uuid.uuid4(),
            project_id=w.p.id,
            punch_no=f"PCH-ANIA-EXP-2026-{no:05d}",
            site_id=w.sites["S-LAND"].id,
            zone_id=z.id,
            location_ref=f"Gate B{1 + i % 6} lounge, column C{10 + i % 9}",
            discipline=disc,
            description_en=en,
            description_ar=ar,
            category=cat,
            raised_during=QPunchRaisedDuring.pre_handover if i % 3 else QPunchRaisedDuring.walkdown,
            responsible_engagement_id=w.engs["RAWABI"],
            raised_by_user_id=raisers[i % 3],
            raised_at=at(raised, 10),
            raised_date=raised,
            target_date=target,
            photo_before_ids=[],
            photo_after_ids=[],
            floor_plan_id=fp.id if pinned else None,
            pin_x_pct=Decimal(str(round(8 + (i * 7.3) % 84, 2))) if pinned else None,
            pin_y_pct=Decimal(str(round(15 + (i * 11.9) % 70, 2))) if pinned else None,
            status=QPunchStatus.closed
            if closed
            else (QPunchStatus.ready_for_review if i in (33, 40) else QPunchStatus.open),
            alerts_sent=[],
            created_by_user_id=raisers[i % 3],
            seed_fake=True,
        )
        if closed:
            cd = target + timedelta(days=3) if late else target - timedelta(days=1 + i % 3)
            it.closed_date, it.closed_at, it.closed_by_user_id = (
                cd,
                at(cd, 13),
                w.u("abdullah.dossary"),
            )
            it.ready_by_user_id, it.ready_at = (
                w.u("joseph.mathew.qc"),
                at(cd - timedelta(days=1), 15),
            )
            it.ready_note = "Fixed and cleaned; after photo taken."
        if it.status == QPunchStatus.ready_for_review:
            it.ready_by_user_id, it.ready_at = w.u("joseph.mathew.qc"), at(date(2026, 10, 5), 15)
            it.ready_note = "Fixed; please verify."
        db.add(it)
        db.flush()
        if closed and it.closed_at is not None:
            _sign(
                db,
                w.p,
                QRecordType.punch_item,
                it.id,
                "verify",
                "approved",
                w.u("abdullah.dossary"),
                it.closed_at,
            )
    numbering.bump_to(db, w.p, QRecordType.punch_item, 2026, 318)
    db.flush()
    return fp


def _dossier(db: Session, w: _W) -> None:
    from app.services.quality import ensure_registered, numbering  # noqa: PLC0415
    from app.services.quality import registry as reg  # noqa: PLC0415
    from app.services.quality.q1.dossier import _ordered  # noqa: PLC0415

    ensure_registered()
    # Appendix A.1 places NCR-…-0044 at S-LAND / Z-PIERB; the Q0 rows carry no zone, so the Pier B
    # dossier would not see it (D-337)
    from app.models.quality import QNcr  # noqa: PLC0415

    n44 = db.scalar(
        select(QNcr).where(QNcr.project_id == w.p.id, QNcr.ncr_no == "NCR-ANIA-EXP-2026-0044")
    )
    if n44 is not None and n44.zone_id is None:
        n44.zone_id = w.zones["Z-PIERB"].id
    d = QDossier(
        id=uuid.uuid4(),
        project_id=w.p.id,
        family_id=uuid.uuid4(),
        dossier_no="DOS-ANIA-EXP-2026-0001",
        revision=1,
        title_en="Pier B level 3 structure",
        title_ar="هيكل الرصيف B المستوى 3",
        zone_ids=[w.zones["Z-PIERB"].id],
        system_ids=[],
        sections=_ordered(list(reg.DOSSIER_SECTIONS)),
        status=QDossierStatus.draft,
        warnings=[],
        created_by_user_id=w.u("hatem.shehri"),
        seed_fake=True,
    )
    db.add(d)
    db.flush()
    for no, title, st in (
        ("S-PB-301", "Level 3 slab reinforcement as-built", QAsbuiltStatus.approved),
        ("S-PB-302", "Level 3 slab general arrangement as-built", QAsbuiltStatus.submitted),
    ):
        db.add(
            QAsbuiltItem(
                project_id=w.p.id,
                dossier_id=d.id,
                drawing_no=no,
                title=title,
                revision="1",
                drawing_date=date(2026, 9, 25),
                status=st,
                approved_by_user_id=w.u("hatem.shehri") if st == QAsbuiltStatus.approved else None,
                approved_at=at(date(2026, 9, 28)) if st == QAsbuiltStatus.approved else None,
                created_by_user_id=w.u("bilal.qureshi"),
                seed_fake=True,
            )
        )
    numbering.bump_to(db, w.p, QRecordType.dossier, 2026, 1)


def seed(db: Session) -> None:
    """Seed Q1's Appendix A records (ANIA-EXP; idempotent)."""
    p = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
    if p is None or db.scalar(select(QItp.id).where(QItp.project_id == p.id).limit(1)) is not None:
        return
    tpl = ensure_library(db)
    w = _W(db, p)
    itps = _itps(db, w)
    _irs(db, w, tpl, itps)
    _punch(db, w)
    _dossier(db, w)
    db.flush()
