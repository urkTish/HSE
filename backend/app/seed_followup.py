# ruff: noqa: E501  (deterministic demo data; table-like rows)
"""Phase 6f seed (spec 6f-incident-followup Appendix A; fictional, references contain TEST).

Builds on the Phase 0-6e seeds without changing their September values: the ANIA-EXP rule profile
starts on 2026-10-01 (RBT-52 stays on the Phase 1 I-20 rules); the FU2 airside incident is added
as an October incident with its requirements, packs and submissions recorded through the 6f
services at their own times; the lesson library holds LL-2025-004…LL-2026-008 (FU5-FU7).
Differences from the Appendix (DECISIONS): the FU2 incident takes the next free ref because
INC-ANIA-EXP-2026-0161 is a June incident of the Phase 1 seed; no packs are added to the September
incident INC-ANIA-EXP-2026-0147 (it is not under the profile, so it has no 6f requirement)."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.core.followup_enums import (
    FuAckResponse,
    FuChangeStatus,
    FuChannel,
    FuCheckStatus,
    FuDistributionStatus,
    FuEffectResult,
    FuLessonSource,
    FuLessonStatus,
    FuLinkKind,
    FuPackAction,
)
from app.core.hse_enums import IncidentShift, IncidentStatus, IncidentType, InvestigationLevel
from app.models import (
    EmailMessage,
    FuDistribution,
    FuEffectivenessCheck,
    FuLesson,
    FuLessonLink,
    FuRequirement,
    FuRule,
    FuSettings,
    Incident,
    Investigation,
    Notification,
    ToolboxTopic,
    UserSession,
)
from app.schemas.followup import (
    FuFileInput,
    FuPackCreate,
    FuPackTransition,
    FuSubmissionAck,
    FuSubmissionCreate,
)
from app.seed_field import _cleanup
from app.seed_heat import Ctx

RIYADH = ZoneInfo("Asia/Riyadh")
RULES_FROM = date(2026, 10, 1)
SEED_CLOCK = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)  # 10:00 Riyadh
FU2_SEQ_FALLBACK = 294


def at(d: date, h: int, mi: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, mi, tzinfo=RIYADH).astimezone(UTC)


def already_seeded(db: Session) -> bool:
    return db.scalar(select(FuLesson.id).limit(1)) is not None


def _evidence(name: str) -> FuFileInput:
    body = f"TEST evidence {name} (fictional)".encode()
    return FuFileInput(file_name=f"{name}.txt", content_base64=base64.b64encode(body).decode())


class FCtx(Ctx):
    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def eng(self, pcode: str, short: str) -> uuid.UUID:
        return self.engs[(pcode, short)].id

    def principal(self, key: str) -> Any:
        from app.services.permissions import build_principal  # noqa: PLC0415

        u = self.users[key]
        sess = UserSession(id=uuid.uuid4(), user_id=u.id, created_at=now(), last_seen_at=now(),
                           expires_at=now() + timedelta(hours=8), last_authenticated_at=now())  # fmt: skip
        return build_principal(self.db, u, sess)


# ---- A.1 / A.2 settings and profiles -------------------------------------------------------------

RECIPIENTS = {
    "ANIA-EXP": [
        {"organisation_en": "Airport Development Client (test)",
         "organisation_ar": "عميل تطوير المطار (تجريبي)", "role": "client",
         "email": "client.ania@example.com"},
        {"organisation_en": "Gulf PMC Consultants (test)",
         "organisation_ar": "استشاريو الخليج لإدارة المشاريع (تجريبي)", "role": "pmc",
         "email": "pmc.ania@example.com"},
    ],
    "RBT-52": [
        {"organisation_en": "Riyadh Tower Developer (test)",
         "organisation_ar": "مطور برج الرياض (تجريبي)", "role": "client",
         "email": "client.rbt@example.com"},
    ],
}  # fmt: skip
DIRECTORY = [
    ("gosi", "GOSI Riyadh branch (test)", "التأمينات الاجتماعية فرع الرياض (تجريبي)",
     "https://gosi.test/portal"),
    ("mhrsd", "MHRSD Riyadh labour office (test)", "مكتب العمل بالرياض (تجريبي)", None),
    ("civil_defense", "Civil Defense Riyadh (test)", "الدفاع المدني بالرياض (تجريبي)", None),
    ("airport_operator", "AOCC ANIA (test)", "مركز عمليات المطار (تجريبي)", None),
    ("gaca", "GACA (test portal)", "الهيئة العامة للطيران المدني (بوابة تجريبية)",
     "https://gaca.test/occurrence"),
    ("ncec", "NCEC (test portal)", "المركز الوطني للرقابة على الالتزام البيئي (بوابة تجريبية)",
     "https://ncec.test/eir"),
]  # fmt: skip


def _settings(ctx: FCtx) -> None:
    from app.services.followup import common as fc  # noqa: PLC0415

    for pcode in ("ANIA-EXP", "RBT-52"):
        pid = ctx.pid(pcode)
        s = ctx.db.get(FuSettings, pid) or FuSettings(project_id=pid, values={})
        s.followup_rules_from = RULES_FROM if pcode == "ANIA-EXP" else None
        s.client_recipients = RECIPIENTS[pcode]
        s.body_directory = [
            {"body": b, "office_name_en": en, "office_name_ar": ar, "address_or_portal": portal,
             "email": None}
            for b, en, ar, portal in DIRECTORY
        ]  # fmt: skip
        s.signatory_role_en = "HSE Manager"
        s.signatory_role_ar = "مدير الصحة والسلامة والبيئة"
        ctx.db.add(s)
        ctx.db.flush()
        fc.clear_cache(ctx.db)
        rules = fc.ensure_profile(ctx.db, pid)
        assert any(r.rule_code == "CL-V" and r.active for r in rules)  # noqa: S101
    gaca = ctx.db.scalar(
        select(FuRule).where(FuRule.project_id == ctx.pid("ANIA-EXP"), FuRule.rule_code == "GACA-W")
    )
    assert gaca is not None  # noqa: S101
    fc.clear_cache(ctx.db)


# ---- A.3 FU2 -------------------------------------------------------------------------------------


def _fu2(ctx: FCtx) -> Incident:
    db = ctx.db
    pid = ctx.pid("ANIA-EXP")
    taken = set(db.scalars(select(Incident.seq).where(Incident.project_id == pid,
                                                      Incident.year == 2026)))  # fmt: skip
    seq = 161 if 161 not in taken else max(max(taken, default=0) + 1, FU2_SEQ_FALLBACK)
    z = ctx.zone("ANIA-EXP", "Z-APR-21")
    occurred = at(date(2026, 10, 4), 23, 30)
    inc = Incident(
        id=uuid.uuid4(), project_id=pid, ref=f"INC-ANIA-EXP-2026-{seq:04d}", year=2026, seq=seq,
        site_id=z.site_id, zone_id=z.id, location_detail="Stand 21 (TEST)",
        responsible_engagement_id=ctx.eng("ANIA-EXP", "GULFPAVE"), occurred_at=occurred,
        occurred_date=date(2026, 10, 4), reported_at=at(date(2026, 10, 4), 23, 40),
        reported_by_user_id=ctx.uid("noura.qahtani"), shift=IncidentShift.night,
        incident_types=[IncidentType.property_damage.value],
        primary_type=IncidentType.property_damage,
        title="Escort vehicle contacts parked aircraft wingtip",
        description="An escort vehicle contacted the wingtip of a parked aircraft on stand 21 "
        "while repositioning. No injury. Vehicle stopped, AOCC informed.",
        immediate_actions="Vehicle stopped, area cordoned, AOCC duty manager informed",
        activity=None, work_related=True, actual_severity=2, potential_severity=4,
        airside_flags=["aircraft_involved"], status=IncidentStatus.under_investigation,
        created_by_user_id=ctx.uid("noura.qahtani"), alerts_sent=[], seed_fake=True,
    )  # fmt: skip
    db.add(inc)
    db.flush()
    db.add(
        Investigation(
            incident_id=inc.id, level=InvestigationLevel.L3,
            lead_investigator_id=ctx.uid("noura.qahtani"), team_member_ids=[],
            due_date=date(2026, 10, 18), extensions=[], root_causes=[], ptw_ids=[],
            alerts_sent=[],
        )
    )  # fmt: skip
    db.flush()
    return inc


def _fu2_followup(ctx: FCtx, inc: Incident) -> None:
    from app.services.followup import packs, submissions  # noqa: PLC0415
    from app.services.followup import requirements as rq  # noqa: PLC0415

    db = ctx.db
    set_now(at(date(2026, 10, 4), 23, 41))
    rq.derive(db, inc)
    reqs = {
        r.rule_code: r
        for r in db.scalars(select(FuRequirement).where(FuRequirement.incident_id == inc.id))
    }
    noura = ctx.principal("noura.qahtani")
    # AO-V and CL-V (verbal)
    set_now(at(date(2026, 10, 4), 23, 43))
    submissions.record(db, noura, reqs["AO-V"].id, FuSubmissionCreate(
        channel=FuChannel.phone_radio, submitted_at=at(date(2026, 10, 4), 23, 42),
        contacted_desk_en="AOCC duty manager", contacted_desk_ar="مدير مناوبة مركز العمليات",
        reference_no="AOCC-TEST-1004"))  # fmt: skip
    set_now(at(date(2026, 10, 5), 0, 6))
    submissions.record(db, noura, reqs["CL-V"].id, FuSubmissionCreate(
        channel=FuChannel.phone_radio, submitted_at=at(date(2026, 10, 5), 0, 5),
        contacted_desk_en="PMC duty engineer", contacted_desk_ar="مهندس مناوبة الاستشاري",
        call_note="Called 00:05, informed of aircraft contact (TEST)"))  # fmt: skip
    # CL-F: CLIENT-FLASH generated, approved by Faisal, e-mailed to client + PMC
    set_now(at(date(2026, 10, 5), 9, 30))
    pk = packs.generate(db, noura, reqs["CL-F"].id, FuPackCreate(
        narrative_en="Escort vehicle contacted the wingtip of a parked aircraft on stand 21 while "
        "repositioning. No injury; aircraft inspected by the operator.",
        narrative_ar="لامست مركبة المرافقة طرف جناح طائرة متوقفة في الموقف 21 أثناء إعادة "
        "التموضع. لا إصابات؛ تم فحص الطائرة من المشغل."))  # fmt: skip
    set_now(at(date(2026, 10, 5), 10, 30))
    packs.transition_pack(db, ctx.principal("faisal.harbi"), pk.id,
                          FuPackTransition(action=FuPackAction.approve))  # fmt: skip
    set_now(at(date(2026, 10, 5), 11, 1))
    submissions.record(db, noura, reqs["CL-F"].id, FuSubmissionCreate(
        pack_id=pk.id, channel=FuChannel.email, submitted_at=at(date(2026, 10, 5), 11, 0),
        reference_no="CLIENT-TEST-FLASH-1005", evidence_files=[_evidence("cl-f-email")]))  # fmt: skip
    # AO-W: AO-OCR pack NP-ANIA-EXP-2026-0058, e-mailed 16:10, acknowledged 18:05
    set_now(at(date(2026, 10, 5), 14, 0))
    ao = packs.generate(db, noura, reqs["AO-W"].id, FuPackCreate(
        narrative_en="Airside vehicle contact with a parked aircraft (wingtip), stand 21.",
        narrative_ar="تلامس مركبة مع طائرة متوقفة (طرف الجناح) في الموقف 21."))  # fmt: skip
    from app.models import FuPack  # noqa: PLC0415

    row = db.get(FuPack, ao.id)
    assert row is not None  # noqa: S101
    row.seq = 58
    row.pack_no = "NP-ANIA-EXP-2026-0058"
    db.flush()
    set_now(at(date(2026, 10, 5), 15, 0))
    packs.transition_pack(db, ctx.principal("faisal.harbi"), ao.id,
                          FuPackTransition(action=FuPackAction.approve))  # fmt: skip
    set_now(at(date(2026, 10, 5), 16, 11))
    sub = submissions.record(db, noura, reqs["AO-W"].id, FuSubmissionCreate(
        pack_id=ao.id, channel=FuChannel.email, submitted_at=at(date(2026, 10, 5), 16, 10),
        reference_no="AO-TEST-OCR-1005", evidence_files=[_evidence("ao-w-email")]))  # fmt: skip
    set_now(at(date(2026, 10, 5), 18, 10))
    submissions.acknowledge(db, noura, sub.id, FuSubmissionAck(
        acknowledged_at=at(date(2026, 10, 5), 18, 5), ack_reference="AOCC-TEST-ACK-1005"))  # fmt: skip
    set_now(SEED_CLOCK)


# ---- A.4 lessons -----------------------------------------------------------------------------------

KL = list[tuple[str, str]]


def _lesson(
    ctx: FCtx,
    no: str,
    pcode: str,
    title: tuple[str, str],
    what: tuple[str, str],
    why: tuple[str, str],
    kl: KL,
    applic: dict[str, list[str]],
    rcs: list[str],
    published: datetime | None,
    dist: list[str],
    status: FuLessonStatus = FuLessonStatus.published,
    incident_ref: str | None = None,
    due: date | None = None,
    author: str = "noura.qahtani",
) -> FuLesson:
    from app.services.followup import lessons  # noqa: PLC0415

    db = ctx.db
    year, seq = int(no[3:7]), int(no[8:])
    inc = db.scalar(select(Incident).where(Incident.ref == incident_ref)) if incident_ref else None
    ls = FuLesson(
        lesson_no=no, year=year, seq=seq,
        source=FuLessonSource.incident if inc else FuLessonSource.external,
        incident_id=inc.id if inc else None, source_project_id=ctx.pid(pcode),
        external_ref=None if inc else f"TEST-INDUSTRY-ALERT-{year}-{seq:02d}",
        system_created=inc is not None, required=inc is not None,
        title_en=title[0], title_ar=title[1], what_happened_en=what[0], what_happened_ar=what[1],
        why_en=why[0], why_ar=why[1], root_cause_codes=rcs,
        key_lessons=[{"text_en": a, "text_ar": b} for a, b in kl], actions_taken=[],
        applicability={"activities": [], "zone_types": [], "trades": [], "mechanisms": [],
                       "do_categories": [], **applic},
        severity_potential=inc.potential_severity if inc else None, photos=[],
        distribution_project_ids=[ctx.pid(x) for x in dist], removed_engagements=[],
        publish_due_on=due, author_id=ctx.uid(author),
        approved_by_user_id=ctx.uid("faisal.harbi") if published else None,
        published_at=published, status=status, alerts_sent=[], search_text="",
    )  # fmt: skip
    if inc is not None:
        from app.services.incidents import linked_cas  # noqa: PLC0415

        ls.actions_taken = [
            {
                "ca_ref": ca.ref,
                "control_level": ca.control_level.value if ca.control_level else None,
            }
            for ca in linked_cas(db, inc.id)
        ]
    ls.search_text = lessons._index(ls)
    db.add(ls)
    db.flush()
    return ls


def _items(
    ctx: FCtx, ls: FuLesson, pairs: list[tuple[str, str]], due: date,
    acks: dict[str, tuple[date, str]],
) -> None:  # fmt: skip
    for pcode, short in pairs:
        ack = acks.get(short)
        ctx.db.add(
            FuDistribution(
                lesson_id=ls.id, project_id=ctx.pid(pcode), engagement_id=ctx.eng(pcode, short),
                ack_due_on=due, acknowledged_by_user_id=ctx.uid(ack[1]) if ack else None,
                acknowledged_at=at(ack[0], 10) if ack else None,
                response=FuAckResponse.will_brief if ack else None,
                status=FuDistributionStatus.acknowledged if ack else FuDistributionStatus.pending,
                alerts_sent=[],
            )
        )  # fmt: skip
    ctx.db.flush()


def _check(
    ctx: FCtx, ls: FuLesson, completed: date | None, who: str = "noura.qahtani"
) -> FuEffectivenessCheck:
    from app.services.followup import effectiveness  # noqa: PLC0415

    assert ls.published_at is not None  # noqa: S101
    ch = FuEffectivenessCheck(
        lesson_id=ls.id, project_id=ls.source_project_id,
        due_on=ls.published_at.astimezone(RIYADH).date() + timedelta(days=90), facts={},
        status=FuCheckStatus.scheduled, alerts_sent=[],
    )  # fmt: skip
    ctx.db.add(ch)
    ctx.db.flush()
    if completed is not None:
        f = effectiveness.facts(ctx.db, ls, completed)
        ch.facts = f
        ch.suggested_result = effectiveness.suggest(f)
        ch.result = FuEffectResult.effective
        if ch.suggested_result != ch.result:
            ch.rationale = "Seeded history (TEST): reviewed on site and judged effective."
        ch.completed_by_user_id = ctx.uid(who)
        ch.completed_at = at(completed, 11)
        ch.completed_on = completed
        ch.status = FuCheckStatus.completed
        ctx.db.flush()
    return ch


SCAF = ({"activities": ["scaffolding", "work_at_height"], "zone_types": ["landside", "airside"],
         "trades": ["scaffolder"], "mechanisms": ["fall_from_height"]})  # fmt: skip


def _lessons(ctx: FCtx) -> None:
    both = ["ANIA-EXP", "RBT-52"]
    ll4 = _lesson(
        ctx, "LL-2025-004", "ANIA-EXP",
        ("Reversing plant without a banksman", "رجوع المعدات للخلف دون مرشد"),
        ("November 2025, ANIA-EXP, landside zone: a loader reversed into a barrier.",
         "نوفمبر 2025، ANIA-EXP، منطقة برية: اصطدمت رافعة شوكية بحاجز أثناء الرجوع."),
        ("No banksman was assigned for reversing plant.", "لم يُعيَّن مرشد لحركة المعدات للخلف."),
        [("Assign a banksman for every reversing manoeuvre", "عيّن مرشداً لكل حركة رجوع")],
        {"activities": ["driving_transport"], "mechanisms": ["struck_by_moving_object"]}, ["OF-02"],
        at(date(2025, 11, 20), 10), both, FuLessonStatus.archived,
    )  # fmt: skip
    _lesson(
        ctx, "LL-2025-005", "RBT-52",
        ("Hot work fire watch removed early", "إنهاء مراقبة الحريق مبكراً بعد الأعمال الساخنة"),
        ("December 2025, RBT-52, landside zone: smouldering insulation found after hot work.",
         "ديسمبر 2025، RBT-52، منطقة برية: وُجد عزل يحترق ببطء بعد الأعمال الساخنة."),
        ("The fire watch left before the 60-minute period.", "غادر مراقب الحريق قبل انتهاء 60 دقيقة."),
        [("Keep the fire watch 60 minutes after hot work", "استمر بمراقبة الحريق 60 دقيقة بعد العمل")],
        {"activities": ["hot_work"]}, ["AD-03"], at(date(2025, 12, 10), 10), both,
    )  # fmt: skip
    _lesson(
        ctx, "LL-2025-006", "ANIA-EXP",
        ("Heat stress during an afternoon concrete pour", "إجهاد حراري أثناء صب خرسانة بعد الظهر"),
        ("December 2025, ANIA-EXP, landside zone: a worker felt faint during a long pour.",
         "ديسمبر 2025، ANIA-EXP، منطقة برية: شعر عامل بالإغماء أثناء صب طويل."),
        ("Rest breaks were not adjusted for the work rate.", "لم تُعدَّل فترات الراحة حسب شدة العمل."),
        [("Plan pours for the cooler hours", "خطط لعمليات الصب في الساعات الأبرد")],
        {"activities": ["concrete"]}, ["OF-06"], at(date(2025, 12, 28), 10), both,
    )  # fmt: skip
    _lesson(
        ctx, "LL-2026-001", "RBT-52",
        ("Dropped object from a crane hook block", "سقوط جسم من بكرة خطاف الرافعة"),
        ("January 2026, RBT-52, landside zone: a shackle pin fell from the hook block.",
         "يناير 2026، RBT-52، منطقة برية: سقط مسمار شاكل من بكرة الخطاف."),
        ("The pin was not moused after inspection.", "لم يُثبَّت المسمار بعد الفحص."),
        [("Mouse every shackle pin before lifting", "ثبّت مسمار كل شاكل قبل الرفع")],
        {"activities": ["lifting"], "mechanisms": ["struck_by_falling_object"]}, ["TE-02"],
        at(date(2026, 1, 20), 10), both,
    )  # fmt: skip
    ll2 = _lesson(
        ctx, "LL-2026-002", "ANIA-EXP",
        ("Reversing plant on the apron without a banksman", "رجوع المعدات في الساحة دون مرشد"),
        ("March 2026, ANIA-EXP, airside zone: a roller reversed close to a stand marker.",
         "مارس 2026، ANIA-EXP، منطقة جوية: رجعت مدحلة بالقرب من علامة الموقف."),
        ("Banksman cover was not planned for the night shift.", "لم يُخطط لوجود مرشد في الوردية الليلية."),
        [("Plan banksman cover for every shift", "خطط لوجود مرشد في كل وردية")],
        {"activities": ["driving_transport"], "zone_types": ["airside"],
         "mechanisms": ["struck_by_moving_object"]}, ["OF-02"], at(date(2026, 3, 10), 10), both,
    )  # fmt: skip
    ll4.superseded_by_id = ll2.id
    ll4.archived_at = at(date(2026, 3, 10), 11)
    ll4.status_reason = "Superseded by LL-2026-002"
    ll3 = _lesson(
        ctx, "LL-2026-003", "ANIA-EXP",
        ("Hand caught between paver hopper and truck", "انحشار اليد بين قادوس الرصف والشاحنة"),
        ("May 2026, ANIA-EXP, landside zone: a hand was caught while guiding a truck to the "
         "paver hopper.",
         "مايو 2026، ANIA-EXP، منطقة برية: انحشرت يد عامل أثناء توجيه شاحنة إلى قادوس الرصف."),
        ("Workers stood in the line of fire during truck docking.",
         "وقف العمال في خط الخطر أثناء اقتراب الشاحنة."),
        [("Nobody between truck and hopper during docking",
          "لا أحد بين الشاحنة والقادوس أثناء الاقتراب")],
        {"activities": ["paving_asphalt"], "mechanisms": ["caught_in_between"]}, ["AD-02"],
        at(date(2026, 6, 10), 10), ["ANIA-EXP"], incident_ref="INC-ANIA-EXP-2026-0093",
        due=date(2026, 6, 16),
    )  # fmt: skip
    _items(ctx, ll3, [("ANIA-EXP", s) for s in ("RAWABI", "NAJD", "GULFPAVE", "SAHARA")],
           date(2026, 6, 17), {s: (date(2026, 6, 14), "ahmed.zahrani")
                              for s in ("RAWABI", "NAJD", "GULFPAVE", "SAHARA")})  # fmt: skip
    _lesson(
        ctx, "LL-2026-004", "ANIA-EXP",
        ("Excavation edge collapse near a cable trench", "انهيار حافة حفرية قرب خندق كابلات"),
        ("July 2026, ANIA-EXP, landside zone: an unsupported trench edge collapsed.",
         "يوليو 2026، ANIA-EXP، منطقة برية: انهارت حافة خندق غير مدعمة."),
        ("Spoil was stored at the trench edge.", "خُزنت مخلفات الحفر على حافة الخندق."),
        [("Keep spoil 1 m from the trench edge", "أبعد مخلفات الحفر مسافة 1 م عن الحافة")],
        {"activities": ["excavation"]}, ["TE-05"], at(date(2026, 7, 15), 10), both,
    )  # fmt: skip
    _lesson(
        ctx, "LL-2026-005", "RBT-52",
        ("Isolation not verified before panel work", "عدم التحقق من العزل قبل العمل على اللوحة"),
        ("August 2026, RBT-52, landside zone: a panel was found live during a test.",
         "أغسطس 2026، RBT-52، منطقة برية: وُجدت لوحة مكهربة أثناء الاختبار."),
        ("Test-before-touch was skipped.", "لم يُجرَ الاختبار قبل اللمس."),
        [("Prove dead before touching any conductor", "تحقق من انعدام الجهد قبل اللمس")],
        {"activities": ["electrical"]}, ["AD-04"], at(date(2026, 8, 12), 10), both,
    )  # fmt: skip
    _lesson(
        ctx, "LL-2026-006", "ANIA-EXP",
        ("FOD from unsecured packaging airside", "أجسام غريبة من تغليف غير مثبت في المنطقة الجوية"),
        ("September 2026, ANIA-EXP, airside zone: packaging blew onto a taxiway.",
         "سبتمبر 2026، ANIA-EXP، منطقة جوية: تطاير تغليف إلى ممر الطائرات."),
        ("Material was left unsecured at shift end.", "تُركت المواد دون تثبيت نهاية الوردية."),
        [("Secure or remove packaging before leaving", "ثبّت التغليف أو أزله قبل المغادرة")],
        {"activities": ["housekeeping"], "zone_types": ["airside"]}, ["OF-05"],
        at(date(2026, 9, 2), 10), both,
    )  # fmt: skip
    ll7 = _lesson(
        ctx, "LL-2026-007", "ANIA-EXP",
        ("Unprotected platform edge during scaffold alteration",
         "حافة منصة غير محمية أثناء تعديل السقالة"),
        ("September 2026, ANIA-EXP, landside zone: a guardrail was removed to pass materials and "
         "a worker stepped close to the open platform edge.",
         "سبتمبر 2026، ANIA-EXP، منطقة برية: أُزيل حاجز الحماية لتمرير المواد واقترب عامل من "
         "حافة المنصة المفتوحة."),
        ("The alteration was done without a scaffold-alteration permit and the toe-board was "
         "missing.", "تم التعديل دون تصريح تعديل سقالة وكان لوح القدم مفقوداً."),
        [("Never remove a guardrail without a scaffold-alteration permit",
          "لا تُزل حاجز الحماية دون تصريح تعديل سقالة"),
         ("Fit toe-boards on every working platform", "ركّب ألواح القدم على كل منصة عمل")],
        SCAF, ["AD-01", "OF-04", "TE-08"], at(date(2026, 9, 24), 10), both,
        incident_ref="INC-ANIA-EXP-2026-0147", due=date(2026, 10, 5),
    )  # fmt: skip
    _items(
        ctx, ll7,
        [("ANIA-EXP", "RAWABI"), ("ANIA-EXP", "NAJD"), ("ANIA-EXP", "GULFPAVE"),
         ("ANIA-EXP", "SAHARA"), ("RBT-52", "QIMMA")],
        date(2026, 10, 1),
        {"NAJD": (date(2026, 9, 24), "ahmed.zahrani"), "RAWABI": (date(2026, 9, 25), "ahmed.zahrani"),
         "GULFPAVE": (date(2026, 9, 29), "ahmed.zahrani"), "QIMMA": (date(2026, 9, 30), "yousef.ghamdi")},
    )  # fmt: skip
    _lesson(
        ctx, "LL-2026-008", "ANIA-EXP",
        ("Sling failure during steel erection", "انقطاع حبل الرفع أثناء تركيب الحديد"),
        ("September 2026, ANIA-EXP, landside zone: a web sling parted while lifting a beam.",
         "سبتمبر 2026، ANIA-EXP، منطقة برية: انقطع حبل رفع نسيجي أثناء رفع جسر."),
        ("The sling was not protected at sharp edges.", "لم تتم حماية الحبل عند الحواف الحادة."),
        [("Use edge protection on every web sling", "استخدم واقي الحواف لكل حبل رفع نسيجي")],
        {"activities": ["steel_erection", "lifting"], "mechanisms": ["struck_by_falling_object"]},
        ["TE-02", "AD-05"], None, [], FuLessonStatus.in_review,
        incident_ref="INC-ANIA-EXP-2026-0150", due=date(2026, 10, 12),
    )  # fmt: skip
    # checks: completed outside September 2026 except LL-2026-003 (FU7)
    for no, done in (("LL-2025-005", date(2026, 3, 10)), ("LL-2025-006", date(2026, 3, 28)),
                     ("LL-2026-001", date(2026, 4, 20)), ("LL-2026-002", date(2026, 6, 8))):  # fmt: skip
        ls = ctx.db.scalar(select(FuLesson).where(FuLesson.lesson_no == no))
        assert ls is not None  # noqa: S101
        _check(ctx, ls, done)
    _check(ctx, ll3, date(2026, 9, 8))
    for no in ("LL-2026-004", "LL-2026-005", "LL-2026-006", "LL-2026-007"):
        ls = ctx.db.scalar(select(FuLesson).where(FuLesson.lesson_no == no))
        assert ls is not None  # noqa: S101
        _check(ctx, ls, None)
    _links(ctx, ll7)


def _links(ctx: FCtx, ll7: FuLesson) -> None:
    db = ctx.db
    t = db.scalar(
        select(ToolboxTopic)
        .where(ToolboxTopic.topic_code == "TT-014")
        .order_by(ToolboxTopic.version.desc())
        .limit(1)
    )
    if t is not None:
        refs = list(t.linked_refs or [])
        refs.append({"kind": "lesson", "ref": ll7.lesson_no})
        t.linked_refs = refs
        db.add(FuLessonLink(lesson_id=ll7.id, kind=FuLinkKind.topic, ref="TT-014",
                            created_at=at(date(2026, 9, 24), 11)))  # fmt: skip
    db.add(FuLessonLink(lesson_id=ll7.id, kind=FuLinkKind.campaign, ref="CMP-ANIA-EXP-2026-004",
                        project_id=ctx.pid("ANIA-EXP"), created_at=at(date(2026, 9, 24), 11)))  # fmt: skip
    db.add(
        FuLessonLink(
            lesson_id=ll7.id, kind=FuLinkKind.template_change, ref="SCA", item_code=None,
            proposed_text_en="Toe-boards on every working platform",
            proposed_text_ar="ألواح القدم على كل منصة عمل", status=FuChangeStatus.open,
            created_at=at(date(2026, 9, 24), 11),
        )
    )  # fmt: skip
    db.flush()


# ---- entry point -----------------------------------------------------------------------------------


def seed_followup_data(db: Session) -> None:
    if already_seeded(db):
        return
    from app.models import Project  # noqa: PLC0415

    if db.scalar(select(Project.id).where(Project.code == "ANIA-EXP")) is None:
        return
    from app.services.followup import common as fc  # noqa: PLC0415

    n0 = set(db.scalars(select(Notification.id)))
    e0 = set(db.scalars(select(EmailMessage.id)))
    ctx = FCtx(db)
    try:
        set_now(SEED_CLOCK)
        _settings(ctx)
        inc = _fu2(ctx)
        _fu2_followup(ctx, inc)
        _lessons(ctx)
        _cleanup(db, n0, e0)
        fc.clear_cache(db)
    finally:
        set_now(None)
    assert db.scalar(select(func.count()).select_from(FuLesson)) == 11  # noqa: S101


def main() -> int:  # pragma: no cover - CLI
    from app.db.session import get_sessionmaker  # noqa: PLC0415

    with get_sessionmaker()() as db:
        seed_followup_data(db)
        db.commit()
    print("Phase 6f seed loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
