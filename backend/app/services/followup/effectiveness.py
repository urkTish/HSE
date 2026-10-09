"""6f effectiveness checks (spec 6f §3.9, EF-1…EF-5)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, NotificationKind
from app.core.enums import EntityType as ET  # noqa: N817
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.followup_enums import (
    FuCheckStatus,
    FuDistributionStatus,
    FuEffectResult,
    FuLessonStatus,
    FuLinkKind,
)
from app.core.hse_enums import CaPriority, CaSourceType, CaStatus, ControlLevel, IncidentStatus
from app.models import (
    BriefingCampaign,
    CorrectiveAction,
    FuDistribution,
    FuEffectivenessCheck,
    FuLesson,
    FuLessonLink,
    Incident,
    InjuryCase,
    Investigation,
    Site,
    User,
)
from app.schemas.followup import FuCheckComplete, FuCheckPage, FuCheckRead
from app.services.common import invalid_transition
from app.services.followup import common as fc
from app.services.permissions import Principal

C = fc.C
CS = FuCheckStatus
R = FuEffectResult
ACK_MIN = fc.D("90.0")


def check_of(db: Session, lesson_id: uuid.UUID) -> FuEffectivenessCheck | None:
    return db.scalar(
        select(FuEffectivenessCheck).where(FuEffectivenessCheck.lesson_id == lesson_id)
    )


def schedule(db: Session, ls: FuLesson, day: date) -> FuEffectivenessCheck:
    """EF-1: due_on = publication date + `lesson_effectiveness_days`."""
    ch = check_of(db, ls.id)
    if ch is not None:
        return ch
    ids = list(ls.distribution_project_ids or [])
    pid = ls.source_project_id or (ids[0] if ids else None)
    days = int(fc.cfg(db, pid)["lesson_effectiveness_days"]) if pid else 90
    ch = FuEffectivenessCheck(lesson_id=ls.id, project_id=pid, due_on=day + timedelta(days=days),
                              facts={}, status=CS.scheduled, alerts_sent=[])  # fmt: skip
    db.add(ch)
    db.flush()
    return ch


# ---- facts (EF-2) and suggestion (EF-3) ----------------------------------------------------------


def recurrences(db: Session, ls: FuLesson, day: date) -> list[Incident]:
    """EF-2: non-voided incidents on a distributed project, occurred after publication and on or
    before `day`, matching by (activity and mechanism), (do_category) or (activity and a shared
    root-cause code)."""
    if ls.published_at is None:
        return []
    a = ls.applicability or {}
    acts, mechs, dos = (set(a.get(k, [])) for k in ("activities", "mechanisms", "do_categories"))
    codes = set(ls.root_cause_codes or [])
    out: list[Incident] = []
    for inc in db.scalars(
        select(Incident)
        .where(
            Incident.project_id.in_(list(ls.distribution_project_ids or [])),
            Incident.occurred_at > ls.published_at,
            Incident.occurred_date <= day,
            Incident.status.not_in([IncidentStatus.voided, IncidentStatus.draft]),
        )
        .order_by(Incident.occurred_at)
    ):
        if inc.id == ls.incident_id:
            continue
        act = inc.activity is not None and inc.activity.value in acts
        cm = {
            c.mechanism.value
            for c in db.scalars(select(InjuryCase).where(InjuryCase.incident_id == inc.id))
        }
        inv = db.get(Investigation, inc.id)
        rcs = {str(r.get("code")) for r in (inv.root_causes if inv else None) or []}
        if (
            (act and cm & mechs)
            or (inc.do_category is not None and inc.do_category.value in dos)
            or (act and rcs & codes)
        ):
            out.append(inc)
    return out


def facts(db: Session, ls: FuLesson, day: date) -> dict[str, Any]:
    from app.services.field.campaigns import pair_states  # noqa: PLC0415
    from app.services.followup.lessons import corrective_for  # noqa: PLC0415

    rec = recurrences(db, ls, day)
    items = [
        i
        for i in db.scalars(select(FuDistribution).where(FuDistribution.lesson_id == ls.id))
        if i.status != FuDistributionStatus.withdrawn
    ]
    done = sum(
        1
        for i in items
        if i.status in (FuDistributionStatus.acknowledged, FuDistributionStatus.not_applicable)
    )
    met = total = 0
    for k in db.scalars(
        select(FuLessonLink).where(
            FuLessonLink.lesson_id == ls.id, FuLessonLink.kind == FuLinkKind.campaign
        )
    ):
        c = db.scalar(select(BriefingCampaign).where(BriefingCampaign.campaign_no == k.ref))
        if c is None:
            continue
        st = pair_states(db, c)
        total += len(st)
        met += sum(1 for s in st if s.met_on is not None and s.met_on <= day)
    cas = [ca for ca in corrective_for(db, ls) if ca.status != CaStatus.cancelled]
    rate = fc.q1(fc.D(done) * 100 / fc.D(len(items))) if items else None
    return {
        "as_of": day.isoformat(),
        "recurrences": [
            {
                "ref": i.ref,
                "potential_severity": i.potential_severity,
                "occurred_date": i.occurred_date.isoformat(),
            }
            for i in rec
        ],
        "ack_done": done,
        "ack_total": len(items),
        "ack_rate_pct": str(rate) if rate is not None else None,
        "campaign_pairs_met": met,
        "campaign_pairs_total": total,
        "cas_closed": sum(1 for ca in cas if ca.status == CaStatus.closed),
        "cas_total": len(cas),
    }


def suggest(f: dict[str, Any]) -> FuEffectResult:
    """EF-3."""
    rec = f["recurrences"]
    if any((r.get("potential_severity") or 0) >= 4 for r in rec):
        return R.not_effective
    low_ack = f["ack_total"] > 0 and fc.D(f["ack_done"]) * 100 / fc.D(f["ack_total"]) < ACK_MIN
    if (
        rec
        or low_ack
        or f["campaign_pairs_met"] < f["campaign_pairs_total"]
        or f["cas_closed"] < f["cas_total"]
    ):
        return R.partly_effective
    return R.effective


# ---- reads ---------------------------------------------------------------------------------------


def check_read(db: Session, ch: FuEffectivenessCheck) -> FuCheckRead:
    ls = db.get(FuLesson, ch.lesson_id)
    assert ls is not None  # noqa: S101
    today = fc.local_day()
    if ch.status == CS.scheduled:
        f = facts(db, ls, today)
        sug: FuEffectResult | None = suggest(f)
    else:
        f, sug = dict(ch.facts or {}), ch.suggested_result
    ca = db.get(CorrectiveAction, ch.follow_up_ca_id) if ch.follow_up_ca_id else None
    fl = db.get(FuLesson, ch.follow_up_lesson_id) if ch.follow_up_lesson_id else None
    return FuCheckRead(
        id=ch.id, lesson_id=ch.lesson_id, lesson_no=ls.lesson_no, project_id=ch.project_id,
        due_on=ch.due_on, facts=f, suggested_result=sug, result=ch.result,
        rationale=ch.rationale, follow_up_ca_ref=ca.ref if ca else None,
        follow_up_lesson_no=fl.lesson_no if fl else None,
        completed_by=fc.user_ref(db, ch.completed_by_user_id), completed_at=ch.completed_at,
        status=ch.status, overdue=ch.status == CS.scheduled and today > ch.due_on,
    )  # fmt: skip


def _get(db: Session, p: Principal, check_id: uuid.UUID) -> FuEffectivenessCheck:
    ch = db.get(FuEffectivenessCheck, check_id)
    if ch is None or ch.project_id is None or not p.can_see_project(ch.project_id):
        raise not_found("Effectiveness check")
    fc.view_grant(db, p, ch.project_id)
    return ch


def list_checks(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    statuses: list[FuCheckStatus] | None,
    page: int,
    size: int,
) -> FuCheckPage:
    fc.view_grant(db, p, project_id)
    stmt = select(FuEffectivenessCheck).where(FuEffectivenessCheck.project_id == project_id)
    if statuses:
        stmt = stmt.where(FuEffectivenessCheck.status.in_(statuses))
    rows = list(db.scalars(stmt.order_by(FuEffectivenessCheck.due_on)))
    items = [check_read(db, c) for c in rows[(page - 1) * size : page * size]]
    return FuCheckPage(items=items, total=len(rows), page=page, page_size=size)


def read_check(db: Session, p: Principal, check_id: uuid.UUID) -> FuCheckRead:
    return check_read(db, _get(db, p, check_id))


# ---- completion (EF-4, EF-5) ---------------------------------------------------------------------


def complete(db: Session, p: Principal, check_id: uuid.UUID, body: FuCheckComplete) -> FuCheckRead:
    ch = _get(db, p, check_id)
    assert ch.project_id is not None  # noqa: S101
    p.require(ch.project_id, C.lesson_effectiveness)
    if ch.status != CS.scheduled:
        raise invalid_transition("Effectiveness check", ch.status, CS.completed)
    ls = db.get(FuLesson, ch.lesson_id)
    assert ls is not None  # noqa: S101
    day = fc.local_day()
    f = facts(db, ls, day)
    sug = suggest(f)
    why = (body.rationale or "").strip()
    if body.result != sug and len(why) < 20:
        raise fc.code_err(ErrorCode.RATIONALE_REQUIRED,
                          f"The suggested result is {sug.value}: give a rationale of at least 20 "
                          "characters (EF-4).",
                          "النتيجة تختلف عن المقترحة: اكتب مبرراً لا يقل عن 20 حرفاً.",
                          "rationale", suggested=sug.value)  # fmt: skip
    if body.result == R.not_effective:
        if body.follow_up_ca is None and body.follow_up_lesson_id is None:
            raise fc.code_err(ErrorCode.FOLLOW_UP_REQUIRED,
                              "A not-effective lesson needs a follow-up CA or a new lesson (EF-5).",
                              "يتطلب الدرس غير الفعال إجراءً تصحيحياً أو درساً جديداً.",
                              "follow_up_ca")  # fmt: skip
        if body.follow_up_lesson_id is not None:
            new = db.get(FuLesson, body.follow_up_lesson_id)
            if new is None or new.id == ls.id:
                raise validation_error("follow_up_lesson_id", "Choose the new lesson.")
            ch.follow_up_lesson_id = new.id
            if new.status == FuLessonStatus.published:
                ls.superseded_by_id = new.id
        if body.follow_up_ca is not None:
            ch.follow_up_ca_id = _make_ca(db, p, ch, ls, body).id
    ch.facts = f
    ch.suggested_result = sug
    ch.result = body.result
    ch.rationale = why or None
    ch.completed_by_user_id = p.user.id
    ch.completed_at = now()
    ch.completed_on = day
    ch.status = CS.completed
    db.flush()
    fc.record(db, p, AuditAction.status_change, ET.lesson_effectiveness, ch, ch.project_id,
              before={"status": CS.scheduled.value},
              details={"lesson_no": ls.lesson_no, "result": body.result.value})  # fmt: skip
    return check_read(db, ch)


def _make_ca(
    db: Session, p: Principal, ch: FuEffectivenessCheck, ls: FuLesson, body: FuCheckComplete
) -> CorrectiveAction:
    """EF-5: a Phase 1 CA, source `lesson` (source_id = the check), priority high, owner chosen."""
    from app.services import hse_settings  # noqa: PLC0415
    from app.services.hse_common import make_ref, next_seq  # noqa: PLC0415

    fu = body.follow_up_ca
    assert fu is not None and ch.project_id is not None  # noqa: S101
    if db.get(User, fu.owner_id) is None:
        raise validation_error("follow_up_ca.owner_id", "Unknown user.")
    pr = fc.project(db, p, ch.project_id)
    inc = db.get(Incident, ls.incident_id) if ls.incident_id else None
    site_id = inc.site_id if inc is not None and inc.project_id == pr.id else db.scalar(
        select(Site.id).where(Site.project_id == pr.id).order_by(Site.code).limit(1))  # fmt: skip
    if site_id is None:
        raise validation_error("follow_up_ca", "The project has no site.")
    created = fc.local_day()
    s = hse_settings.get(db, pr.id)
    due = fu.due_date or created + timedelta(days=hse_settings.ca_due_days(s, CaPriority.high))
    offs = sorted(fc.officers(db, pr.id)) or sorted(fc.managers(db))
    verifier = next((u for u in offs if u != fu.owner_id), None) or sorted(fc.managers(db))[0]
    seq = next_seq(db, CorrectiveAction, pr.id, created.year)
    ca = CorrectiveAction(
        id=uuid.uuid4(), project_id=pr.id, ref=make_ref("CA", pr.code, created.year, seq, 5),
        year=created.year, seq=seq, source_type=CaSourceType.lesson, source_id=ch.id,
        site_id=site_id,
        zone_id=inc.zone_id if inc is not None and inc.site_id == site_id else None,
        responsible_engagement_id=inc.responsible_engagement_id if inc is not None else None,
        title=(fu.title or f"{ls.lesson_no} not effective: follow-up")[:150],
        description=f"Follow-up of effectiveness check for {ls.lesson_no} (EF-5).",
        control_level=ControlLevel.administrative, priority=CaPriority.high,
        owner_id=fu.owner_id, verifier_id=verifier, created_date=created, due_date=due,
        original_due_date=due, status=CaStatus.open, created_by_user_id=p.user.id,
        alerts_sent=[],
    )  # fmt: skip
    db.add(ca)
    db.flush()
    fc.record(db, p, AuditAction.create, ET.corrective_action, ca, pr.id,
              details={"source_type": "lesson", "lesson_no": ls.lesson_no})  # fmt: skip
    fc.send(db, [fu.owner_id], NotificationKind.ca_assigned,
            f"{ca.ref} assigned to you: {ca.title}", f"تم إسناد {ca.ref} إليك", pr.id,
            ET.corrective_action, ca.id, email=True)  # fmt: skip
    return ca


# ---- job (EF-1 alerts) ---------------------------------------------------------------------------


def daily(db: Session, today: date) -> None:
    for ch in db.scalars(
        select(FuEffectivenessCheck).where(
            FuEffectivenessCheck.status == CS.scheduled, FuEffectivenessCheck.due_on <= today
        )
    ):
        if ch.project_id is None:
            continue
        week = (today - ch.due_on).days // 7
        if not fc.once(db, f"fu:ef:{ch.id}:{week}"):
            continue
        ls = db.get(FuLesson, ch.lesson_id)
        no = ls.lesson_no if ls else ""
        fc.send(db, fc.officers(db, ch.project_id), NotificationKind.lesson_effectiveness_due,
                f"The effectiveness check of lesson {no} is due ({ch.due_on.isoformat()}).",
                f"حان موعد التحقق من فعالية الدرس {no}.", ch.project_id,
                ET.lesson_effectiveness, ch.id, email=True)  # fmt: skip
