"""Watch list and consequences (spec 6g §3.5, §4.3, WL-1…WL-8): triggers at finalisation, the
review-meeting CA, system proposals confirmed by the HSE Manager (improvement plan, suspension
review, closure), PIP checks, decisions, the prefilled Phase 0 suspension form (the platform
never changes a contractor status itself) and the CPS summary."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, EntityType, NotificationKind
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.hse_enums import HIGHER_CONTROLS, CaSourceType, CaStatus, ControlLevel
from app.core.scorecard_enums import (
    ScCap,
    ScCardStatus,
    ScGrade,
    ScScope,
    ScWatchAction,
    ScWatchDecision,
    ScWatchLevel,
    ScWatchProposal,
    ScWatchStatus,
)
from app.models import (
    Contractor,
    CorrectiveAction,
    Project,
    ProjectEngagement,
    ScCard,
    ScWatchEntry,
    Site,
)
from app.schemas.scorecard import (
    ScCpsMonth,
    ScEngagementRef,
    ScPerformanceSummary,
    ScSuspensionForm,
    ScTriggerRef,
    ScWatchCreate,
    ScWatchPage,
    ScWatchRead,
    ScWatchTransition,
)
from app.services.permissions import Principal, deny, forbidden_error
from app.services.scorecard import common as cm

D = Decimal
GOOD = (ScGrade.A, ScGrade.B)


def _final(db: Session, eng_id: uuid.UUID, month: date) -> ScCard | None:
    return db.scalar(select(ScCard).where(ScCard.engagement_id == eng_id,
                                          ScCard.scope == ScScope.own, ScCard.month == month,
                                          ScCard.status == ScCardStatus.final))  # fmt: skip


def open_entry(db: Session, eng_id: uuid.UUID) -> ScWatchEntry | None:
    return db.scalar(
        select(ScWatchEntry).where(
            ScWatchEntry.engagement_id == eng_id, ScWatchEntry.status == ScWatchStatus.open
        )
    )


def audience(db: Session, project_id: uuid.UUID, eng_id: uuid.UUID) -> set[uuid.UUID]:
    """WL-2: the engagement's reps and those of its parents, HSE Officers, HSE Manager."""
    ids = cm.officers(db, project_id) | cm.managers(db)
    e: ProjectEngagement | None = db.get(ProjectEngagement, eng_id)
    while e is not None:
        ids |= cm.reps(db, project_id, e.id)
        e = db.get(ProjectEngagement, e.parent_engagement_id) if e.parent_engagement_id else None
    return ids


def triggers(db: Session, card: ScCard) -> list[str]:
    """WL-1 (a) grade D, (b) C in M and M − 1 (both Final), (c) CP-1 applied."""
    if card.grade is None:
        return []
    out = []
    if card.grade == ScGrade.D:
        out.append("WL-1a")
    if card.grade == ScGrade.C:
        prev = _final(db, card.engagement_id, cm.add_months(card.month, -1))
        if prev is not None and prev.grade == ScGrade.C:
            out.append("WL-1b")
    if any(c["cap_code"] == ScCap.CP1.value for c in card.caps_applied):
        out.append("WL-1c")
    return out


def _site(db: Session, project_id: uuid.UUID) -> uuid.UUID:
    sid = db.scalar(select(Site.id).where(Site.project_id == project_id).order_by(Site.code))
    assert sid is not None  # noqa: S101
    return sid


def _review_ca(db: Session, project: Project, w: ScWatchEntry, t: datetime) -> CorrectiveAction:
    ca = cm.make_ca(db, project, CaSourceType.scorecard, w.id, _site(db, project.id), None,
                    w.engagement_id, "major", f"HSE performance review meeting — {w.entry_no}",
                    f"Watch-list review meeting for {cm.eng_code(db, w.engagement_id)} "
                    f"({w.entry_no}): agree causes and actions.", ControlLevel.administrative,
                    None, None)  # fmt: skip
    ca.due_date = ca.original_due_date = cm.local_day(t) + timedelta(days=7)
    return ca


def open_new(
    db: Session, project: Project, card: ScCard | None, eng_id: uuid.UUID, month: date,
    trig: list[str], t: datetime, by: uuid.UUID | None = None, reason: str | None = None,
) -> ScWatchEntry:  # fmt: skip
    year = t.year
    seq = cm.next_seq(db, ScWatchEntry, project.id, year)
    w = ScWatchEntry(
        id=uuid.uuid4(), project_id=project.id, engagement_id=eng_id, year=year, seq=seq,
        entry_no=f"WL-{project.code}-{year}-{seq:03d}", level=ScWatchLevel.watch,
        trigger_refs=[{"month": cm.mkey(month), "trigger": x,
                       "scorecard_no": card.scorecard_no if card else None} for x in trig],
        baseline_score=card.score if card else None, opened_month=month, opened_at=t,
        opened_reason=reason, status=ScWatchStatus.open, pip_ca_ids=[], created_by_user_id=by,
    )  # fmt: skip
    db.add(w)
    db.flush()
    w.review_ca_id = _review_ca(db, project, w, t).id
    cm.send(db, audience(db, project.id, eng_id), NotificationKind.watch_list,
            f"{w.entry_no}: {cm.eng_code(db, eng_id)} placed on the watch list "
            f"({', '.join(trig) or 'manual'})",
            f"{w.entry_no}: إدراج {cm.eng_code(db, eng_id)} في قائمة المراقبة", project.id,
            EntityType.watch_list_entry, w.id, email=True)  # fmt: skip
    return w


def _propose(db: Session, w: ScWatchEntry, prop: ScWatchProposal, why: str) -> bool:
    if w.proposal == prop:
        return False
    w.proposal, w.proposal_reason = prop, why[:300]
    cm.send(db, cm.managers(db), NotificationKind.watch_list,
            f"{w.entry_no}: the system proposes {prop.value} ({why})",
            f"{w.entry_no}: يقترح النظام {prop.value}", w.project_id,
            EntityType.watch_list_entry, w.id, email=True)  # fmt: skip
    return prop != ScWatchProposal.close


def _months_after(w: ScWatchEntry, m: date) -> int:
    return (m.year - w.opened_month.year) * 12 + m.month - w.opened_month.month


def evaluate_month(
    db: Session, project: Project, m: date, t: datetime
) -> tuple[list[str], list[str]]:
    """At finalisation of month M (FN-1): returns (entry_nos touched, engagement codes escalated
    by a proposal to improvement_plan / suspension_review, for E25)."""
    touched: list[str] = []
    escalated: list[str] = []
    cards_ = db.scalars(select(ScCard).where(ScCard.project_id == project.id, ScCard.month == m,
                                             ScCard.scope == ScScope.own,
                                             ScCard.status == ScCardStatus.final))  # fmt: skip
    for card in cards_:
        trig = triggers(db, card)
        w = open_entry(db, card.engagement_id)
        code = cm.eng_code(db, card.engagement_id)
        if w is None:
            if trig:
                touched.append(open_new(db, project, card, card.engagement_id, m, trig, t).entry_no)
            continue
        if w.opened_month >= m:
            continue
        if trig:
            w.trigger_refs = [*w.trigger_refs, *({"month": cm.mkey(m), "trigger": x,
                                                  "scorecard_no": card.scorecard_no}
                                                 for x in trig)]  # fmt: skip
        k = _months_after(w, m)
        esc = False
        if w.level == ScWatchLevel.watch:
            if trig and k <= 3:
                esc = _propose(
                    db,
                    w,
                    ScWatchProposal.improvement_plan,
                    "second trigger within 3 Final months (WL-3)",
                )
            elif k == 2 and w.baseline_score is not None:
                prev = _final(db, w.engagement_id, cm.add_months(m, -1))
                scores = [x.score for x in (prev, card) if x is not None]
                if len(scores) == 2 and all(s is not None and s <= w.baseline_score
                                            for s in scores):  # fmt: skip
                    esc = _propose(
                        db,
                        w,
                        ScWatchProposal.improvement_plan,
                        "two Final months at or below the baseline (WL-3)",
                    )
        elif w.level == ScWatchLevel.improvement_plan and card.grade == ScGrade.D:
            esc = _propose(db, w, ScWatchProposal.suspension_review, "another grade D (WL-4)")
        if not esc and w.proposal is None:
            prev = _final(db, w.engagement_id, cm.add_months(m, -1))
            if all(x is not None and x.grade in GOOD and not x.caps_applied and
                   x.month > w.opened_month for x in (prev, card)):  # fmt: skip
                _propose(db, w, ScWatchProposal.close, "two Final months at B or better (WL-6)")
        if esc:
            escalated.append(code)
        touched.append(w.entry_no)
    db.flush()
    return touched, escalated


# ---- reads -----------------------------------------------------------------------------------


def to_read(db: Session, w: ScWatchEntry) -> ScWatchRead:
    def ref(cid: uuid.UUID | None) -> str | None:
        ca = db.get(CorrectiveAction, cid) if cid else None
        return ca.ref if ca else None

    return ScWatchRead(
        id=w.id, entry_no=w.entry_no, project_id=w.project_id, engagement_id=w.engagement_id,
        engagement_code=cm.eng_code(db, w.engagement_id), level=w.level,
        trigger_refs=[ScTriggerRef(**x) for x in w.trigger_refs],
        baseline_score=cm.s(w.baseline_score), opened_at=w.opened_at,
        opened_reason=w.opened_reason, proposal=w.proposal, proposal_reason=w.proposal_reason,
        review_ca_ref=ref(w.review_ca_id),
        pip_ca_refs=[r for r in (ref(c) for c in w.pip_ca_ids or []) if r],
        pip_due_on=w.pip_due_on, pip_submitted_at=w.pip_submitted_at,
        pip_accepted_at=w.pip_accepted_at, decision=w.decision, decision_text=w.decision_text,
        contractor_status_ref=w.contractor_status_ref, closed_reason=w.closed_reason,
        closed_at=w.closed_at, status=w.status,
    )  # fmt: skip


def _get(db: Session, p: Principal, entry_id: uuid.UUID) -> ScWatchEntry:
    w = db.get(ScWatchEntry, entry_id)
    g = p.grant(w.project_id, cm.C.scorecard_view) if w is not None else None
    if w is None or g is None or not g.covers_engagement(w.engagement_id):
        raise deny(db, p, EntityType.watch_list_entry, entry_id, w.project_id if w else None,
                   "Watch-list entry")  # fmt: skip
    return w


def list_entries(
    db: Session, p: Principal, project_id: uuid.UUID, status: ScWatchStatus | None, page: int,
    size: int,
) -> ScWatchPage:  # fmt: skip
    g = cm.view_grant(db, p, project_id)
    stmt = select(ScWatchEntry).where(ScWatchEntry.project_id == project_id)
    if status is not None:
        stmt = stmt.where(ScWatchEntry.status == status)
    rows = [w for w in db.scalars(stmt.order_by(ScWatchEntry.entry_no.desc()))
            if g.covers_engagement(w.engagement_id)]  # fmt: skip
    return ScWatchPage(items=[to_read(db, w) for w in rows[(page - 1) * size : page * size]],
                       total=len(rows), page=page, page_size=size)  # fmt: skip


def read(db: Session, p: Principal, entry_id: uuid.UUID) -> ScWatchRead:
    return to_read(db, _get(db, p, entry_id))


def open_manual(
    db: Session, p: Principal, project_id: uuid.UUID, body: ScWatchCreate
) -> ScWatchRead:
    project = cm.project(db, p, project_id)
    cm.require_manager(p)
    e = cm.eng(db, body.engagement_id)
    if e.project_id != project_id:
        raise validation_error("engagement_id", "The engagement is not on this project.")
    text = cm.reason(body.reason, 20)
    if open_entry(db, e.id) is not None:
        raise cm.code_err(ErrorCode.WATCH_ENTRY_OPEN, "The engagement already has an open entry.",
                          "يوجد إدراج مفتوح لهذا المقاول.", "engagement_id")  # fmt: skip
    t = now()
    m = cm.add_months(cm.local_day(t).replace(day=1), -1)
    w = open_new(db, project, None, e.id, m, [], t, p.user.id, text)
    cm.record(db, p, AuditAction.create, EntityType.watch_list_entry, w, project_id)
    db.flush()
    return to_read(db, w)


def _check_pip(db: Session, w: ScWatchEntry, ids: list[uuid.UUID]) -> None:
    """WL-3: ≥ 3 CAs with source `scorecard`, each due ≤ 30 days, at least one at engineering
    level or higher (D-223: always required)."""
    cas = [db.get(CorrectiveAction, i) for i in dict.fromkeys(ids)]
    ok = [c for c in cas if c is not None and c.project_id == w.project_id
          and c.source_type == CaSourceType.scorecard
          and (c.due_date - c.created_date).days <= 30]  # fmt: skip
    if len(ok) < 3 or len(ok) != len(cas) or not any(c.control_level in HIGHER_CONTROLS
                                                     for c in ok):  # fmt: skip
        raise cm.code_err(ErrorCode.PIP_INCOMPLETE,
                          "A PIP needs at least 3 scorecard CAs due within 30 days, one of them "
                          "an engineering control or higher (WL-3).",
                          "تحتاج خطة التحسين إلى 3 إجراءات على الأقل منها إجراء هندسي.",
                          "pip_ca_ids")  # fmt: skip


def transition(
    db: Session, p: Principal, entry_id: uuid.UUID, body: ScWatchTransition
) -> ScWatchRead:
    w = _get(db, p, entry_id)
    if w.status != ScWatchStatus.open:
        raise cm.err(409, ErrorCode.INVALID_TRANSITION, "The entry is closed.", "الإدراج مغلق.")
    t = now()
    a = body.action
    bad = cm.err(409, ErrorCode.INVALID_TRANSITION, "Not allowed at this level.",
                 "غير مسموح في هذا المستوى.")  # fmt: skip
    if a == ScWatchAction.submit_pip:
        g = p.grant(w.project_id, cm.C.scorecard_comment)
        if not p.is_manager and (g is None or not g.covers_engagement(w.engagement_id)
                                 or cm.staff(db, p, w.project_id)):  # fmt: skip
            raise forbidden_error("The engagement's rep submits the PIP.")
        if w.level != ScWatchLevel.improvement_plan or w.pip_accepted_at is not None:
            raise bad
        _check_pip(db, w, body.pip_ca_ids or [])
        w.pip_ca_ids = list(dict.fromkeys(body.pip_ca_ids or []))
        w.pip_submitted_at = t
        cm.send(db, cm.managers(db), NotificationKind.pip_due,
                f"{w.entry_no}: PIP submitted for acceptance", f"{w.entry_no}: قُدّمت خطة التحسين",
                w.project_id, EntityType.watch_list_entry, w.id)  # fmt: skip
    else:
        cm.require_manager(p)
        if a == ScWatchAction.confirm_escalation:
            if w.proposal not in (ScWatchProposal.improvement_plan,
                                  ScWatchProposal.suspension_review):  # fmt: skip
                raise bad
            w.level = ScWatchLevel(w.proposal.value)
            w.escalated_at = t
            if w.level == ScWatchLevel.improvement_plan:
                days = int(cm.cfg(db, w.project_id)["pip_submit_days"])
                w.pip_due_on = cm.local_day(t) + timedelta(days=days)
            w.proposal, w.proposal_reason = None, None
            cm.send(db, audience(db, w.project_id, w.engagement_id), NotificationKind.watch_list,
                    f"{w.entry_no}: escalated to {w.level.value}",
                    f"{w.entry_no}: تصعيد إلى {w.level.value}", w.project_id,
                    EntityType.watch_list_entry, w.id, email=True)  # fmt: skip
        elif a == ScWatchAction.accept_pip:
            if w.pip_submitted_at is None or w.pip_accepted_at is not None:
                raise bad
            w.pip_accepted_at = t
        elif a == ScWatchAction.decide:
            if w.level != ScWatchLevel.suspension_review or body.decision is None:
                raise bad
            w.decision = body.decision
            w.decision_text = cm.reason(body.reason, 20)
            w.decided_at = t
        else:
            w.closed_reason = cm.reason(body.reason, 20)
            w.closed_at = t
            w.status = ScWatchStatus.closed
            w.proposal = None
    w.updated_by_user_id = p.user.id
    cm.record(db, p, AuditAction.status_change, EntityType.watch_list_entry, w, w.project_id,
              details={"action": a.value})  # fmt: skip
    db.flush()
    return to_read(db, w)


def suspension_form(db: Session, p: Principal, entry_id: uuid.UUID) -> ScSuspensionForm:
    """WL-5: the Phase 0 Approved → Suspended form, prefilled. Nothing is submitted here."""
    w = _get(db, p, entry_id)
    cm.require_manager(p)
    if w.decision != ScWatchDecision.suspend:
        raise cm.err(409, ErrorCode.INVALID_TRANSITION, "Record the decision `suspend` first.",
                     "سجّل قرار الإيقاف أولاً.")  # fmt: skip
    e = cm.eng(db, w.engagement_id)
    c = db.get(Contractor, e.contractor_id)
    assert c is not None  # noqa: S101
    engs = db.scalars(select(ProjectEngagement).where(ProjectEngagement.contractor_id == c.id))
    return ScSuspensionForm(
        contractor_id=c.id, contractor_code=c.short_code, current_status=c.status.value,
        target_status="suspended", status_reason=f"HSE performance — {w.entry_no}",
        warning_en="Suspension applies to the contractor master on every project (Phase 0 "
        "rule 28).",
        warning_ar="يسري الإيقاف على المقاول في جميع المشاريع (القاعدة 28).",
        engagements=[ScEngagementRef(project_code=cm.pcode(db, x.project_id),
                                     engagement_code=c.short_code, tier=x.tier,
                                     demobilisation_date=x.demobilisation_date) for x in engs],
        submit_path=f"/api/v1/contractors/{c.id}/transitions",
    )  # fmt: skip


def performance_summary(
    db: Session, p: Principal, contractor_id: uuid.UUID
) -> ScPerformanceSummary:
    """WL-8 CPS: the last 12 Final months on all projects, man-hour-weighted."""
    cm.require_manager(p)
    c = db.get(Contractor, contractor_id)
    if c is None:
        raise not_found("Contractor")
    engs = {
        e.id: e
        for e in db.scalars(
            select(ProjectEngagement).where(ProjectEngagement.contractor_id == c.id)
        )
    }
    since = cm.add_months(cm.local_day().replace(day=1), -12)
    cards_ = list(
        db.scalars(
            select(ScCard)
            .where(
                ScCard.engagement_id.in_(list(engs) or [uuid.uuid4()]),
                ScCard.scope == ScScope.own,
                ScCard.status == ScCardStatus.final,
                ScCard.month >= since,
            )
            .order_by(ScCard.month)
        )
    )
    num = sum((x.score * x.month_man_hours for x in cards_ if x.score is not None), D(0))
    den = sum((x.month_man_hours for x in cards_ if x.score is not None), D(0))
    mean = num / den if den else None
    mix: dict[str, int] = {}
    for x in cards_:
        k = x.grade.value if x.grade else "—"
        mix[k] = mix.get(k, 0) + 1
    entries = db.scalars(select(ScWatchEntry).where(ScWatchEntry.engagement_id.in_(
        list(engs) or [uuid.uuid4()])).order_by(ScWatchEntry.entry_no))  # fmt: skip
    return ScPerformanceSummary(
        contractor_id=c.id, contractor_code=c.short_code, weighted_mean_score=cm.s(mean),
        weighted_mean_display=cm.d1(mean), grade_mix=mix,
        caps_applied=sum(len(x.caps_applied) for x in cards_),
        months=[ScCpsMonth(project_code=cm.pcode(db, x.project_id), month=cm.mkey(x.month),
                           score_display=cm.d1(x.score), grade=x.grade,
                           caps=[ScCap(k["cap_code"]) for k in x.caps_applied],
                           profile=f"{x.profile_code} v{x.profile_version}") for x in cards_],
        watch_entries=[to_read(db, w) for w in entries],
    )  # fmt: skip


def daily(db: Session, t: datetime) -> int:
    """PIP due (pip_due_on − 2, reps) / overdue (day after, Manager) and the WL-4 proposals."""
    today = cm.local_day(t)
    n = 0
    for w in db.scalars(select(ScWatchEntry).where(ScWatchEntry.status == ScWatchStatus.open)):
        if w.level != ScWatchLevel.improvement_plan:
            continue
        if w.pip_due_on and w.pip_submitted_at is None:
            if today >= w.pip_due_on - timedelta(days=2) and cm.once(db, f"pip_due:{w.id}"):
                n += cm.send(
                    db,
                    cm.reps(db, w.project_id, w.engagement_id),
                    NotificationKind.pip_due,
                    f"{w.entry_no}: the PIP is due on {w.pip_due_on}",
                    f"{w.entry_no}: موعد خطة التحسين {w.pip_due_on}",
                    w.project_id,
                    EntityType.watch_list_entry,
                    w.id,
                    email=True,
                )
            if today > w.pip_due_on:
                if cm.once(db, f"pip_overdue:{w.id}"):
                    n += cm.send(db, cm.managers(db), NotificationKind.pip_due,
                                 f"{w.entry_no}: PIP not submitted by {w.pip_due_on}",
                                 f"{w.entry_no}: لم تُقدَّم خطة التحسين", w.project_id,
                                 EntityType.watch_list_entry, w.id, email=True)  # fmt: skip
                _propose(db, w, ScWatchProposal.suspension_review, "PIP not submitted (WL-4)")
        if w.pip_ca_ids:
            late = db.scalar(select(CorrectiveAction.id).where(
                CorrectiveAction.id.in_(w.pip_ca_ids),
                CorrectiveAction.status.in_([CaStatus.open, CaStatus.in_progress]),
                CorrectiveAction.due_date < today - timedelta(days=14)))  # fmt: skip
            if late is not None:
                _propose(
                    db,
                    w,
                    ScWatchProposal.suspension_review,
                    "a PIP CA is overdue by more than 14 days (WL-4)",
                )
    db.flush()
    return n
