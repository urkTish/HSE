"""Phase 6g seed (spec 6g-scorecard-reports Appendix A; fictional, references contain TEST).

Builds on the Phase 0-6f seeds without changing their values. Cards are issued, finalised and
packed through the 6g services at their own times (set_now). Line values are computed by the
engine from the seeded records; the own-card scores of SG3-SG5 are fixture values written over
the computed score, band and grade (DECISIONS D-226), so the integration tests read stored
values. The Phase 1 monthly reports of July-September are rendered from the seeded data and
stored as Published (RBT-52 September stays Draft)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.core.enums import Language, Role, UserStatus
from app.core.hse_enums import MonthlyReportStatus
from app.core.scorecard_enums import (
    RpLanguage,
    RpMemberKind,
    RpStatus,
    RpType,
    ScDisputeReason,
    ScRemarkKind,
    ScRemarkStatus,
    ScScope,
    ScWatchLevel,
    ScWatchStatus,
    XpFormat,
    XpFrequency,
    XpJobStatus,
    XpPurpose,
)
from app.models import (
    EmailMessage,
    MonthlyReport,
    Notification,
    PeriodLock,
    RoleAssignment,
    RpPack,
    RpRecipient,
    ScCard,
    ScRemark,
    ScSettings,
    ScWatchEntry,
    User,
    XpJob,
    XpSubscription,
)
from app.seed_field import _cleanup
from app.seed_heat import Ctx

RIYADH = ZoneInfo("Asia/Riyadh")
D = Decimal
SEED_CLOCK = datetime(2026, 10, 12, 7, 0, tzinfo=UTC)  # 10:00 Riyadh
LIVE = "2026-06-01"
# SG3-SG5 own-card scores (fixture values)
SCORES: dict[str, dict[str, str]] = {
    "2026-07": {"RAWABI": "88.0", "NAJD": "82.0", "GULFPAVE": "83.0", "SAHARA": "68.0"},
    "2026-08": {"RAWABI": "87.5", "NAJD": "81.0", "GULFPAVE": "85.0", "SAHARA": "71.5"},
    "2026-09": {"RAWABI": "88.4", "NAJD": "54903/679", "GULFPAVE": "84.1", "SAHARA": "76.2"},
}


def at(d: date, h: int, mi: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, mi, tzinfo=RIYADH).astimezone(UTC)


def already_seeded(db: Session) -> bool:
    return db.scalar(select(ScCard.id).limit(1)) is not None


def _tariq(ctx: Ctx) -> User:
    db = ctx.db
    u = db.scalar(select(User).where(User.email == "tariq.mutairi@example.com"))
    if u is None:
        f = ctx.users["faisal.harbi"]
        najd = ctx.engs[("ANIA-EXP", "NAJD")]
        u = User(
            id=uuid.uuid4(),
            email="tariq.mutairi@example.com",
            full_name_en="Tariq Al-Mutairi",
            full_name_ar="طارق المطيري",
            mobile="+966500000009",
            employer_type=f.employer_type,
            employer_contractor_id=najd.contractor_id,
            job_title="Contractor HSE Rep",
            preferred_language=Language.ar,
            status=UserStatus.active,
            password_hash=f.password_hash,
            activated_at=f.activated_at,
            privacy_notice_version=f.privacy_notice_version,
            privacy_notice_ack_at=f.privacy_notice_ack_at,
            search_text="tariq al-mutairi طارق المطيري tariq.mutairi@example.com",
        )
        from app.core.enums import EmployerType  # noqa: PLC0415

        u.employer_type = EmployerType.contractor
        db.add(u)
        db.flush()
        db.add(
            RoleAssignment(
                id=uuid.uuid4(),
                user_id=u.id,
                role=Role.contractor_hse_rep,
                project_id=ctx.pid("ANIA-EXP"),
                site_ids=[],
                contractor_engagement_id=najd.id,
                valid_from=date(2026, 1, 1),
                created_at=at(date(2026, 1, 1), 9),
            )
        )
        db.flush()
        ctx.users["tariq.mutairi"] = u
    return u


def _settings(ctx: Ctx) -> None:
    from app.core.scorecard_enums import ScModule  # noqa: PLC0415

    live = {
        m.value: (date(2026, 10, 1).isoformat() if m == ScModule.followup else LIVE)
        for m in ScModule
        if m != ScModule.phase1
    }
    faisal = ctx.uid("faisal.harbi")
    for code, start in (("ANIA-EXP", date(2026, 7, 1)), ("RBT-52", date(2026, 9, 1))):
        values = (
            {"external_distribution_enabled": True, "external_domains": ["example.com"]}
            if code == "ANIA-EXP"
            else {}
        )
        ctx.db.add(
            ScSettings(
                project_id=ctx.pid(code),
                scorecard_from_month=start,
                source_live_from=dict(live),
                values=values,
                sources_confirmed_at=at(date(2026, 6, 30), 9),
                sources_confirmed_by_user_id=faisal,
            )
        )
    ctx.db.flush()


def _lock(ctx: Ctx, code: str, month: date, when: datetime) -> None:
    lk = ctx.db.get(PeriodLock, (ctx.pid(code), month))
    if lk is None:
        lk = PeriodLock(project_id=ctx.pid(code), month=month)
        ctx.db.add(lk)
    lk.locked, lk.locked_at, lk.locked_by_user_id = True, when, ctx.uid("faisal.harbi")
    ctx.db.flush()


def _p1_report(ctx: Ctx, code: str, month: date, published: datetime | None) -> MonthlyReport:
    from app.ai import reports  # noqa: PLC0415

    project = ctx.projects[code]
    sections, _digest = reports.render(ctx.db, project, month)
    r = MonthlyReport(
        id=uuid.uuid4(),
        project_id=project.id,
        month=month,
        status=MonthlyReportStatus.published if published else MonthlyReportStatus.draft,
        sections=sections,
        data_hash=reports.figures_hash(sections),
        created_by_user_id=ctx.uid("noura.qahtani" if code == "ANIA-EXP" else "lina.haddad"),
        created_at=(published or SEED_CLOCK) - timedelta(days=1),
        generated_at=(published or SEED_CLOCK) - timedelta(days=1),
    )
    if published:
        r.reviewed_by_user_id, r.reviewed_at = r.created_by_user_id, published - timedelta(hours=2)
        r.published_by_user_id, r.published_at = ctx.uid("faisal.harbi"), published
    ctx.db.add(r)
    ctx.db.flush()
    return r


def _fixture(ctx: Ctx, code: str, month: date) -> None:
    """Write the SG3-SG5 scores over the computed own-card scores (band and capped grade)."""
    from app.services.scorecard import calc, cards  # noqa: PLC0415
    from app.services.scorecard import common as cm  # noqa: PLC0415

    fx = SCORES.get(cm.mkey(month), {})
    for c in cards.current(ctx.db, ctx.pid(code), month, ScScope.own):
        short = cm.eng_code(ctx.db, c.engagement_id)
        if short not in fx:
            continue
        raw = fx[short]
        c.score = D(raw.split("/")[0]) / D(raw.split("/")[1]) if "/" in raw else D(raw)
        c.band_grade = calc.band(c.score, [(g, D(s)) for g, s in cm.BANDS])
        # fixture caps: only NAJD September keeps its CP-2 (SG1); the other fixture cards have none
        keep = (
            [x for x in c.caps_applied if x["cap_code"] == "CP-2"]
            if short == "NAJD" and cm.mkey(month) == "2026-09"
            else []
        )
        if short == "NAJD" and cm.mkey(month) == "2026-09" and not keep:
            keep = [{"cap_code": "CP-2", "max_grade": "C", "refs": ["SG1 fixture"]}]
        c.caps_applied = keep
        caps = [next(g for cc, g in cm.CAPS if cc.value == x["cap_code"]) for x in keep]
        g = c.band_grade
        for cap in caps:
            if g is not None and cm.GRADE_ORDER[cap] < cm.GRADE_ORDER[g]:
                g = cap
        c.grade = g
        if short == "SAHARA" and c.credibility_z < 1:
            c.credibility_z = D(1)
    cards.rank_month(ctx.db, ctx.pid(code), month)
    for c in cards.current(ctx.db, ctx.pid(code), month, None):
        cards.set_trend(ctx.db, c)
    ctx.db.flush()


def _month(ctx: Ctx, month: date, issue_at: datetime, final_at: datetime | None) -> None:
    from app.services.scorecard import cards  # noqa: PLC0415

    project = ctx.projects["ANIA-EXP"]
    set_now(issue_at)
    cards.issue_month(ctx.db, project, month, issue_at)
    _fixture(ctx, "ANIA-EXP", month)
    if final_at is not None:
        set_now(final_at)
        cs = list(cards.current(ctx.db, project.id, month, None))
        cards.finalise_cards(ctx.db, project, month, cs, ctx.uid("faisal.harbi"), final_at)


def _wl001(ctx: Ctx) -> None:
    w = ScWatchEntry(
        id=uuid.uuid4(),
        project_id=ctx.pid("ANIA-EXP"),
        engagement_id=ctx.engs[("ANIA-EXP", "GULFPAVE")].id,
        year=2026,
        seq=1,
        entry_no="WL-ANIA-EXP-2026-001",
        level=ScWatchLevel.watch,
        trigger_refs=[{"month": "2026-04", "trigger": "WL-1a", "scorecard_no": None}],
        baseline_score=D("58.0"),
        opened_month=date(2026, 4, 1),
        opened_at=at(date(2026, 5, 15), 9),
        opened_reason="Grade D in April 2026 (before 6g cards; TEST history)",
        pip_ca_ids=[],
        closed_reason="Two consecutive months at grade B (June and July 2026) with no cap (WL-6).",
        closed_at=at(date(2026, 8, 16), 10),
        status=ScWatchStatus.closed,
        seed_fake=True,
    )
    ctx.db.add(w)
    ctx.db.flush()


def _distribution(ctx: Ctx) -> None:
    pid = ctx.pid("ANIA-EXP")
    for key in ("faisal.harbi", "noura.qahtani", "sarah.mitchell"):
        ctx.db.add(
            RpRecipient(
                id=uuid.uuid4(),
                project_id=pid,
                report_type=RpType.MCR,
                kind=RpMemberKind.user,
                user_id=ctx.uid(key),
                language=RpLanguage.both,
                seed_fake=True,
            )
        )
    ctx.db.add(
        RpRecipient(
            id=uuid.uuid4(),
            project_id=pid,
            report_type=RpType.MCR,
            kind=RpMemberKind.external,
            display_name_en="PMC HSE Lead",
            display_name_ar="مسؤول السلامة لدى الاستشاري",
            organisation="Gulf PMC Consultants (test)",
            email="pmc.hse@example.com",
            language=RpLanguage.both,
            acknowledged_by_user_id=ctx.uid("faisal.harbi"),
            seed_fake=True,
        )
    )
    ctx.db.flush()


def _mcr(
    ctx: Ctx,
    month: date,
    created: datetime,
    reviewed: datetime,
    issued: datetime,
    provisional: str | None = None,
) -> RpPack:
    from app.services.scorecard import common as cm  # noqa: PLC0415
    from app.services.scorecard import packs  # noqa: PLC0415

    db = ctx.db
    project = ctx.projects["ANIA-EXP"]
    set_now(created)
    pk = packs.new_pack(
        db, RpType.MCR, project, None, None, month, cm.month_end(month), 0, ctx.uid("noura.qahtani")
    )
    pk.status = RpStatus.in_review
    pk.reviewed_by_user_id, pk.reviewed_at = ctx.uid("noura.qahtani"), reviewed
    if provisional:
        pk.scorecards_provisional, pk.provisional_reason = True, provisional
    set_now(issued)
    packs.issue(db, pk, ctx.uid("faisal.harbi"), issued)
    return pk


def _packs(ctx: Ctx) -> None:
    from app.services.scorecard import packs  # noqa: PLC0415

    db = ctx.db
    _mcr(
        ctx,
        date(2026, 7, 1),
        at(date(2026, 8, 12), 7),
        at(date(2026, 8, 12), 15),
        at(date(2026, 8, 13), 10),
        "July scorecards were still in the contractor comment window at issue.",
    )
    rev0 = _mcr(
        ctx,
        date(2026, 8, 1),
        at(date(2026, 9, 12), 7),
        at(date(2026, 9, 14), 16),
        at(date(2026, 9, 15), 11, 20),
    )
    # 2026-09-27: Phase 1 restated August (FAC → MTC) — RP-7 flags the Issued pack
    rev0.revised_since_issue = True
    set_now(at(date(2026, 9, 28), 9))
    reason = "August restated: a first-aid case reclassified to MTC"
    rev1 = packs.new_pack(
        db,
        RpType.MCR,
        ctx.projects["ANIA-EXP"],
        None,
        None,
        rev0.period_start,
        rev0.period_end,
        1,
        ctx.uid("faisal.harbi"),
    )
    rev1.reissue_reason, rev1.due_on = reason, rev0.due_on
    rev1.status = RpStatus.in_review
    rev1.reviewed_by_user_id, rev1.reviewed_at = ctx.uid("noura.qahtani"), at(date(2026, 9, 28), 12)
    t = at(date(2026, 9, 28), 14)
    set_now(t)
    packs.issue(db, rev1, ctx.uid("faisal.harbi"), t)


def _september(ctx: Ctx) -> None:
    from app.services.scorecard import cards, packs  # noqa: PLC0415
    from app.services.scorecard import common as cm  # noqa: PLC0415

    db = ctx.db
    sep = date(2026, 9, 1)
    for code in ("ANIA-EXP", "RBT-52"):
        _lock(ctx, code, sep, at(date(2026, 10, 10), 9))
    # HEAT pack: Draft 2026-10-10 (season ends 09-30), In Review at the clock
    set_now(at(date(2026, 10, 10), 7))
    h = packs.new_pack(
        db,
        RpType.HEAT,
        ctx.projects["ANIA-EXP"],
        None,
        None,
        packs.heat_end(db, ctx.pid("ANIA-EXP"), 2026, True),
        packs.heat_end(db, ctx.pid("ANIA-EXP"), 2026),
        0,
        ctx.uid("faisal.harbi"),
    )
    h.status, h.prepared_by_user_id, h.prepared_at = (
        RpStatus.in_review,
        ctx.uid("noura.qahtani"),
        at(date(2026, 10, 11), 11),
    )
    _p1_report(ctx, "ANIA-EXP", sep, at(date(2026, 10, 11), 9, 12))
    _p1_report(ctx, "RBT-52", sep, None)
    issue_at = at(date(2026, 10, 11), 6)
    set_now(issue_at)
    cards.issue_month(db, ctx.projects["ANIA-EXP"], sep, issue_at)
    cards.issue_month(db, ctx.projects["RBT-52"], sep, issue_at)
    _fixture(ctx, "ANIA-EXP", sep)
    # MCR September Draft by report_pack_daily on 2026-10-12 07:00
    set_now(at(date(2026, 10, 12), 7))
    packs.new_pack(
        db, RpType.MCR, ctx.projects["ANIA-EXP"], None, None, sep, cm.month_end(sep), 0, None
    )
    # Tariq's dispute on NAJD SM-PTW-AUDIT, raised 2026-10-12 08:30
    t = at(date(2026, 10, 12), 8, 30)
    set_now(t)
    najd = db.scalar(
        select(ScCard).where(
            ScCard.engagement_id == ctx.engs[("ANIA-EXP", "NAJD")].id,
            ScCard.month == sep,
            ScCard.scope == ScScope.own,
        )
    )
    assert najd is not None  # noqa: S101
    days = int(cm.cfg(db, najd.project_id)["dispute_resolution_days"])
    db.add(
        ScRemark(
            id=uuid.uuid4(),
            card_id=najd.id,
            project_id=najd.project_id,
            engagement_id=najd.engagement_id,
            target_code="SM-PTW-AUDIT",
            kind=ScRemarkKind.dispute,
            internal=False,
            reason_code=ScDisputeReason.wrong_attribution,
            text="Two of the twelve PTW audits counted for NAJD were of RAWABI permits (TEST).",
            file_ids=[],
            warnings=[],
            raised_by_user_id=ctx.uid("tariq.mutairi"),
            raised_at=t,
            due_at=cm.end_of_day(cm.local_day(t) + timedelta(days=days)),
            status=ScRemarkStatus.open,
            created_by_user_id=ctx.uid("tariq.mutairi"),
            seed_fake=True,
        )
    )
    db.flush()


def _exports(ctx: Ctx) -> None:
    from app.schemas.scorecard import XpExportRequest  # noqa: PLC0415
    from app.services.permissions import build_principal  # noqa: PLC0415
    from app.services.scorecard import exports  # noqa: PLC0415

    db = ctx.db
    noura = ctx.users["noura.qahtani"]
    pid = ctx.pid("ANIA-EXP")
    hist = [
        ("incidents", XpPurpose.gosi),
        ("incidents", XpPurpose.gosi),
        ("observations", None),
        ("corrective_actions", None),
        ("permits", None),
        ("workers", None),
        ("inspections", None),
        ("equipment_certificates", None),
        ("training_records", None),
    ]
    for i, (ds, purpose) in enumerate(hist):
        t = at(date(2026, 8, 3) + timedelta(days=5 * i), 11)
        seq = i + 1
        db.add(
            XpJob(
                id=uuid.uuid4(),
                year=2026,
                seq=seq,
                export_no=f"EXP-2026-{seq:06d}",
                dataset=ds,
                format=XpFormat.xlsx if i % 2 else XpFormat.csv,
                project_id=pid,
                filters={},
                columns=["person_name", "id_number"] if purpose else [],
                notes=[],
                purpose=purpose,
                purpose_text="GOSI occupational injury claim (TEST)" if purpose else None,
                row_count=20 + 7 * i,
                sha256="0" * 64,
                contains_personal=bool(purpose),
                contains_sensitive=bool(purpose),
                status=XpJobStatus.expired,
                expires_at=t + (timedelta(hours=24) if purpose else timedelta(days=7)),
                requested_by_user_id=noura.id if i % 3 else ctx.uid("faisal.harbi"),
                created_at=t,
                ready_at=t,
                seed_fake=True,
            )
        )
    db.flush()
    p = build_principal(db, noura, None)
    for i, ds in enumerate(("permits", "incidents", "heat_patrols")):
        t = at(date(2026, 10, 6) + timedelta(days=i), 14)
        set_now(t)
        exports.new_job(db, p, XpExportRequest(dataset=ds, format=XpFormat.csv, project_id=pid), t)
    db.add(
        XpSubscription(
            id=uuid.uuid4(),
            user_id=noura.id,
            project_id=pid,
            dataset="permits",
            filters={},
            columns=[],
            format=XpFormat.xlsx,
            frequency=XpFrequency.weekly,
            active=True,
            seed_fake=True,
        )
    )
    db.flush()


def seed_scorecard_data(db: Session) -> None:
    if already_seeded(db):
        return
    from app.models import Project  # noqa: PLC0415

    if db.scalar(select(Project.id).where(Project.code == "ANIA-EXP")) is None:
        return
    from app.services.scorecard import config, inputs  # noqa: PLC0415

    n0 = set(db.scalars(select(Notification.id)))
    e0 = set(db.scalars(select(EmailMessage.id)))
    ctx = Ctx(db)
    try:
        set_now(at(date(2026, 6, 30), 9))
        _tariq(ctx)
        config.ensure_org(db)
        _settings(ctx)
        _wl001(ctx)
        _distribution(ctx)
        _p1_report(ctx, "ANIA-EXP", date(2026, 7, 1), at(date(2026, 8, 11), 12))
        _p1_report(ctx, "ANIA-EXP", date(2026, 8, 1), at(date(2026, 9, 11), 12))
        inputs.reset(db)
        _month(ctx, date(2026, 7, 1), at(date(2026, 8, 11), 6), at(date(2026, 8, 15), 9))
        _month(ctx, date(2026, 8, 1), at(date(2026, 9, 11), 6), at(date(2026, 9, 15), 9))
        _packs(ctx)
        _september(ctx)
        _exports(ctx)
        _cleanup(db, n0, e0)
        inputs.reset(db)
    finally:
        set_now(None)
    assert (db.scalar(select(func.count()).select_from(ScWatchEntry)) or 0) >= 2  # noqa: S101


def main() -> int:  # pragma: no cover - CLI
    from app.db.session import get_sessionmaker  # noqa: PLC0415

    with get_sessionmaker()() as db:
        seed_scorecard_data(db)
        db.commit()
    print("Phase 6g seed loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
