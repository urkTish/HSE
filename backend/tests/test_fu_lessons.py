# ruff: noqa: E501
"""Phase 6f lessons, distribution, 6d links and effectiveness (6f §9 AC 25-40)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.field_enums import CampaignReason, VersionAction, VersionStatus
from app.core.followup_enums import (
    FuAckResponse,
    FuChangeStatus,
    FuCheckStatus,
    FuEffectResult,
    FuLessonAction,
    FuLessonSource,
    FuLessonStatus,
    FuLinkKind,
)
from app.core.hse_enums import CaSourceType, InvestigationLevel
from app.models import (
    ChecklistTemplate,
    CorrectiveAction,
    FuEffectivenessCheck,
    FuLesson,
    Investigation,
    Site,
    ToolboxTopic,
)
from app.schemas.field import CampaignCreate, TemplateUpdate, VersionTransition
from app.schemas.followup import (
    FuAckRequest,
    FuCheckComplete,
    FuFollowUpCa,
    FuKeyLesson,
    FuLessonCreate,
    FuLessonTransition,
    FuLessonUpdate,
    FuLinkCreate,
    FuSettingsUpdate,
)
from app.services.field import campaigns, library, talks
from app.services.followup import config, effectiveness, lessons
from tests.conftest import Api
from tests.fu_helpers import (
    P,
    eng,
    expect,
    inc,
    item,
    kpi,
    kpis,
    lesson,
    local,
    make_inc,
    notified,
    project,
    tick,
    uid,
)

pytestmark = pytest.mark.usefixtures("fu_seed", "clock")


def approve(db: Session, ref: str, when, level: InvestigationLevel = InvestigationLevel.L3):  # type: ignore[no-untyped-def]
    i = inc(db, ref)
    inv = db.get(Investigation, i.id)
    assert inv is not None
    inv.level = level
    inv.root_causes = [
        {"code": "TE-02", "text": "Sling not protected"},
        {"code": "AD-05", "text": "Lift plan not reviewed"},
    ]
    inv.lessons_learned = "Protect slings at sharp edges\nReview the lift plan before each lift"
    inv.approved_at = when
    inv.approved_by_user_id = uid(db, "faisal.harbi")
    from app.core.clock import set_now

    set_now(when)
    return i, lessons.on_investigation_approved(db, i, inv)


def full(ls_id, db: Session, who: str = "noura.qahtani", **kw):  # type: ignore[no-untyped-def]
    data = dict(  # noqa: C408
        title_en="Title", title_ar="عنوان", what_happened_en="What", what_happened_ar="ماذا",
                why_en="Why", why_ar="لماذا", key_lessons=[FuKeyLesson(text_en="Lesson", text_ar="درس")],
                applicability={"activities": ["lifting"]})  # fmt: skip
    data.update(kw)
    return lessons.update(db, P(db, who), ls_id, FuLessonUpdate(**data))


def test_ac25_ac26_auto_draft(db: Session) -> None:
    i, ls = approve(db, "INC-ANIA-EXP-2026-0276", local(2026, 9, 28, 11, 0))
    assert (
        ls is not None
        and ls.status == FuLessonStatus.draft
        and ls.publish_due_on == date(2026, 10, 12)
    )
    assert (
        ls.root_cause_codes == ["TE-02", "AD-05"]
        and ls.key_lessons[0]["text_en"] == "Protect slings at sharp edges"
    )
    assert ls.author_id == db.get(Investigation, i.id).lead_investigator_id  # type: ignore[union-attr]
    t = tick(2026, 10, 9, 0, 13)
    lessons.daily(db, date(2026, 10, 9))
    assert notified(db, "lesson_publish_due", since=t)
    # AC 26: L2 by default → none; after Faisal adds L2 → created
    tick(2026, 10, 6, 10)
    i2 = make_inc(db, "ANIA-EXP", "S-LAND", local(2026, 10, 5, 9), "NAJD", None)
    inv2 = db.get(Investigation, i2.id)
    assert inv2 is not None
    inv2.level = InvestigationLevel.L2
    inv2.approved_at = local(2026, 10, 6, 9)
    assert lessons.on_investigation_approved(db, i2, inv2) is None
    config.update_settings(
        db,
        P(db, "faisal.harbi"),
        i2.project_id,
        FuSettingsUpdate(lesson_required_levels=[InvestigationLevel.L3, InvestigationLevel.L2]),
    )
    assert lessons.on_investigation_approved(db, i2, inv2) is not None


def test_ac27_completeness_photos_identity(db: Session) -> None:
    tick(2026, 10, 6, 9)
    i = make_inc(db, "ANIA-EXP", "S-LAND", local(2026, 10, 5, 9), "NAJD", [{"cat": "MTC"}])
    inv = db.get(Investigation, i.id)
    assert inv is not None
    inv.approved_at = local(2026, 10, 6, 9)
    ls = lessons.on_investigation_approved(db, i, inv)
    assert ls is not None
    noura = P(db, "noura.qahtani")
    full(ls.id, db, key_lessons=[FuKeyLesson(text_en="Lesson", text_ar="")])
    err = expect(
        "LESSON_INCOMPLETE",
        lambda: lessons.transition(
            db, noura, ls.id, FuLessonTransition(action=FuLessonAction.submit)
        ),
    )
    assert "key_lessons[0].text_ar" in err.meta["missing"]  # type: ignore[index]
    full(ls.id, db)
    ls.photos = [
        {"attachment_id": "00000000-0000-0000-0000-000000000000", "redaction_confirmed": False}
    ]
    expect(
        "REDACTION_NOT_CONFIRMED",
        lambda: lessons.transition(
            db, noura, ls.id, FuLessonTransition(action=FuLessonAction.submit)
        ),
    )
    ls.photos = []
    expect("IDENTITY_IN_TEXT", lambda: full(ls.id, db, what_happened_en="Rashid's hand was cut."))


def test_ac28_ac29_publication_rules(api: Api, db: Session) -> None:
    ll8 = lesson(db, "LL-2026-008")
    faisal, noura = P(db, "faisal.harbi"), P(db, "noura.qahtani")
    expect(
        "NOT_DISTRIBUTED",
        lambda: lessons.transition(
            db, faisal, ll8.id, FuLessonTransition(action=FuLessonAction.publish)
        ),
    )
    expect(
        "FORBIDDEN",
        lambda: lessons.transition(
            db, noura, ll8.id, FuLessonTransition(action=FuLessonAction.publish)
        ),
    )
    own = lessons.create(
        db, faisal, FuLessonCreate(source=FuLessonSource.external, external_ref="TEST-ALERT-9")
    )
    full(own.id, db, who="faisal.harbi", distribution_project_ids=[project(db, "ANIA-EXP").id])
    lessons.transition(db, faisal, own.id, FuLessonTransition(action=FuLessonAction.submit))
    expect(
        "SELF_APPROVAL",
        lambda: lessons.transition(
            db, faisal, own.id, FuLessonTransition(action=FuLessonAction.publish)
        ),
    )
    # AC 29 / FU6: K-129 ANIA-EXP October = 100.0 % at 10-06; LL-2026-008 counts from 10-12
    db.commit()  # release the audit-chain advisory lock before the API session reads
    c = api.as_("faisal.harbi")
    assert kpi(kpis(c, project(db, "ANIA-EXP").id), "K129")["display"] == "100.0 %"
    tick(2026, 10, 12, 10)
    c = api.as_("faisal.harbi")  # a fresh token: the old one expired on the pinned clock
    assert kpi(kpis(c, project(db, "ANIA-EXP").id), "K129")["display"] == "50.0 %"


def test_ac30_publication_distribution(db: Session) -> None:
    ania, rbt = project(db, "ANIA-EXP").id, project(db, "RBT-52").id
    from app.services.followup import common as fc

    codes = {
        pc: [fc.eng_code(db, e) for e in lessons.pairs(db, pid, date(2026, 9, 24))]
        for pc, pid in (("A", ania), ("R", rbt))
    }
    assert "DLIFT" not in codes["R"] and "QIMMA" in codes["R"]
    assert set(codes["A"]) >= {"RAWABI", "NAJD", "GULFPAVE"}
    ll8 = lesson(db, "LL-2026-008")
    lessons.update(
        db, P(db, "faisal.harbi"), ll8.id, FuLessonUpdate(distribution_project_ids=[ania, rbt])
    )
    t = tick(2026, 10, 6, 10, 5)
    lessons.transition(
        db, P(db, "faisal.harbi"), ll8.id, FuLessonTransition(action=FuLessonAction.publish)
    )
    got = notified(db, "lesson_published", since=t)
    assert {
        "noura.qahtani",
        "lina.haddad",
        "omar.siddiqui",
        "ahmed.zahrani",
        "yousef.ghamdi",
    } <= set(got)
    chk = db.scalar(select(FuEffectivenessCheck).where(FuEffectivenessCheck.lesson_id == ll8.id))
    assert chk is not None and chk.due_on == date(2027, 1, 4)


def test_ac31_ac32_acknowledgements(api: Api, db: Session) -> None:
    t = tick(2026, 9, 29, 0, 13)
    lessons.daily(db, date(2026, 9, 29))
    assert "ahmed.zahrani" in notified(db, "lesson_ack_due", since=t)
    t = tick(2026, 10, 2, 0, 13)
    lessons.daily(db, date(2026, 10, 2))
    assert {"ahmed.zahrani", "noura.qahtani"} <= set(notified(db, "lesson_ack_due", since=t))
    tick(2026, 10, 6, 10)
    db.commit()
    c = api.as_("faisal.harbi")
    assert kpi(kpis(c, project(db, "ANIA-EXP").id), "K130")["display"] == "75.0 %"
    assert kpi(kpis(c, project(db, "RBT-52").id), "K130")["display"] == "100.0 %"
    r = c.get(
        "/api/v1/kpi/incident-followup",
        params=[
            ("project_id", str(project(db, "ANIA-EXP").id)),
            ("project_id", str(project(db, "RBT-52").id)),
            ("period", "custom"),
            ("start", "2026-10-01"),
            ("end", "2026-10-31"),
        ],
    )
    assert kpi(r.json(), "K130")["display"] == "80.0 %"
    sah = item(db, "LL-2026-007", "SAHARA")
    expect("ON_BEHALF_NOTE_REQUIRED", lambda: lessons.acknowledge(db, P(db, "noura.qahtani"), sah.id, FuAckRequest(
        response=FuAckResponse.will_brief, on_behalf_note="Briefed by the officer on behalf of SAHARA (TEST).")))  # fmt: skip
    expect(
        "VALIDATION_ERROR",
        lambda: lessons.acknowledge(
            db, P(db, "ahmed.zahrani"), sah.id, FuAckRequest(response=FuAckResponse.not_applicable)
        ),
    )
    assert (
        lessons.acknowledge(
            db, P(db, "ahmed.zahrani"), sah.id, FuAckRequest(response=FuAckResponse.will_brief)
        ).status.value
        == "acknowledged"
    )


def test_ac33_ac34_library_and_similar(db: Session) -> None:
    for who in ("sarah.mitchell", "huda.mansour"):
        for q in ("سقاله", "scaffold platform edge", "السقالة"):
            got = [
                x.lesson_no
                for x in lessons.library(
                    db, P(db, who), q, None, None, None, None, None, None, None, None, None, 1, 20
                ).items
            ]
            assert "LL-2026-007" in got, (who, q)
        drafts = lessons.library(
            db,
            P(db, who),
            None,
            [FuLessonStatus.in_review],
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            1,
            20,
        )
        assert drafts.total == 0
    staff = lessons.library(
        db,
        P(db, "noura.qahtani"),
        None,
        [FuLessonStatus.in_review],
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        1,
        20,
    )
    assert [x.lesson_no for x in staff.items] == ["LL-2026-008"]
    all_ = lessons.library(
        db,
        P(db, "sarah.mitchell"),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        1,
        50,
    )
    assert all_.total == 10 and any(x.archived for x in all_.items)
    tick(2026, 10, 6, 9)
    from app.core.hse_enums import Activity

    i = make_inc(db, "ANIA-EXP", "S-LAND", local(2026, 10, 6, 8), "NAJD", [{"cat": "FAC", "mech": "fall_from_height", "trade": "scaffolder"}],
                 inv_days=None, activity=Activity.scaffolding)  # fmt: skip
    assert "LL-2026-007" in [
        x.lesson_no for x in lessons.similar(db, P(db, "noura.qahtani"), i.id).items
    ]


def test_ac35_ac36_ac37_links(db: Session) -> None:
    ll8, ll7 = lesson(db, "LL-2026-008"), lesson(db, "LL-2026-007")
    noura, faisal = P(db, "noura.qahtani"), P(db, "faisal.harbi")
    lk = lessons.add_link(db, noura, ll8.id, FuLinkCreate(kind=FuLinkKind.topic))
    t = db.scalar(select(ToolboxTopic).where(ToolboxTopic.topic_code == lk.ref))
    assert (
        t is not None
        and t.status == VersionStatus.draft
        and t.key_points_en == ["Use edge protection on every web sling"]
    )
    assert {"kind": "lesson", "ref": "LL-2026-008"} in t.linked_refs
    expect(
        "FORBIDDEN",
        lambda: library.transition_topic(
            db, noura, t.id, VersionTransition(action=VersionAction.publish)
        ),
    )
    # AC 36 (LK-2)
    tt14 = db.scalar(
        select(ToolboxTopic).where(
            ToolboxTopic.topic_code == "TT-014", ToolboxTopic.status == VersionStatus.published
        )
    )
    assert tt14 is not None
    pid = project(db, "ANIA-EXP").id
    site = db.scalar(select(Site.id).where(Site.project_id == pid))

    def cmp(no: str):  # type: ignore[no-untyped-def]
        return lambda: campaigns.create_campaign(db, noura, pid, CampaignCreate(
            topic_id=tt14.id, reason=CampaignReason.lesson, reason_ref=no, message_en="Brief the lesson", site_ids=[site]))  # fmt: skip

    expect("LESSON_NOT_PUBLISHED", cmp("LL-2026-008"))
    assert cmp("LL-2026-007")().reason == CampaignReason.lesson
    # AC 37 (LK-3)
    reqs = lessons.change_requests(db, faisal, "SCA").items
    assert [(r.lesson_no, r.status) for r in reqs] == [("LL-2026-007", FuChangeStatus.open)]
    sca = db.scalar(
        select(ChecklistTemplate).where(
            ChecklistTemplate.template_code == "SCA",
            ChecklistTemplate.status == VersionStatus.published,
        )
    )
    assert sca is not None
    v2 = library.new_version(db, faisal, sca.id)
    library.update_template(db, faisal, v2.id, TemplateUpdate(change_note="LL-2026-007 toe-boards"))
    library.transition_template(db, faisal, v2.id, VersionTransition(action=VersionAction.publish))
    r = lessons.change_requests(db, faisal, "SCA").items[0]
    assert r.status == FuChangeStatus.adopted and r.adopted_version == 2
    assert lessons.read(db, noura, ll7.id).links


def _reopen(db: Session) -> FuEffectivenessCheck:
    ch = db.scalar(
        select(FuEffectivenessCheck).where(
            FuEffectivenessCheck.lesson_id == lesson(db, "LL-2026-003").id
        )
    )
    assert ch is not None
    ch.status, ch.result, ch.completed_on, ch.completed_at = (
        FuCheckStatus.scheduled,
        None,
        None,
        None,
    )
    db.flush()
    tick(2026, 9, 8, 11)
    return ch


def test_ac38_ac39_effectiveness(api: Api, db: Session) -> None:
    ch = db.scalar(
        select(FuEffectivenessCheck).where(
            FuEffectivenessCheck.lesson_id == lesson(db, "LL-2026-003").id
        )
    )
    assert (
        ch is not None
        and ch.suggested_result == FuEffectResult.effective
        and ch.result == FuEffectResult.effective
    )
    assert ch.completed_by_user_id == uid(db, "noura.qahtani") and ch.completed_on == date(
        2026, 9, 8
    )
    body = kpis(
        api.as_("faisal.harbi"), project(db, "ANIA-EXP").id, start="2026-09-01", end="2026-09-30"
    )
    assert kpi(body, "K131")["display"] == "100.0 %"
    ch = _reopen(db)
    noura = P(db, "noura.qahtani")
    expect(
        "RATIONALE_REQUIRED",
        lambda: effectiveness.complete(
            db, noura, ch.id, FuCheckComplete(result=FuEffectResult.partly_effective)
        ),
    )
    from app.core.hse_enums import Activity

    tick(2026, 8, 20, 12)
    make_inc(db, "ANIA-EXP", "S-LAND", local(2026, 8, 20, 11), "GULFPAVE", [{"cat": "MTC", "mech": "caught_in_between", "emp": "GULFPAVE"}],
             inv_days=None, activity=Activity.paving_asphalt, potential_severity=4)  # fmt: skip
    tick(2026, 9, 8, 11)
    assert (
        effectiveness.read_check(db, noura, ch.id).suggested_result == FuEffectResult.not_effective
    )
    expect(
        "FOLLOW_UP_REQUIRED",
        lambda: effectiveness.complete(
            db, noura, ch.id, FuCheckComplete(result=FuEffectResult.not_effective)
        ),
    )
    done = effectiveness.complete(db, noura, ch.id, FuCheckComplete(result=FuEffectResult.not_effective,
                                  follow_up_ca=FuFollowUpCa(owner_id=uid(db, "ahmed.zahrani"))))  # fmt: skip
    ca = db.scalar(select(CorrectiveAction).where(CorrectiveAction.ref == done.follow_up_ca_ref))
    assert (
        ca is not None
        and ca.source_type == CaSourceType.lesson
        and ca.owner_id == uid(db, "ahmed.zahrani")
    )


def test_ac40_tbt_suggestion(db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    site = db.scalar(select(Site.id).where(Site.code == "S-LAND"))
    assert site is not None
    out = talks.suggestions(
        db, P(db, "noura.qahtani"), pid, site, eng(db, "ANIA-EXP", "NAJD").id
    ).items
    srcs = [(s.topic_code, s.source.value) for s in out]
    i = next(n for n, x in enumerate(srcs) if x == ("TT-014", "lesson"))
    assert all(s == "campaign" for _c, s in srcs[:i])
    assert db.scalar(select(FuLesson.id).where(FuLesson.lesson_no == "LL-2026-007")) is not None
