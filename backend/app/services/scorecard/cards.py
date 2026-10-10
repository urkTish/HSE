"""Engagement scorecards (spec 6g §3.2, §3.3, §4.1, SG, RK, FN, SC-1, E25): issue after the month
lock, ranking, provisional cards on read, finalisation, re-issue, restatement and the daily
alerts. Nobody types a score (SG-2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, EntityType, NotificationKind, ProjectStatus
from app.core.errors import ErrorCode, not_found
from app.core.scorecard_enums import (
    ScCap,
    ScCardStatus,
    ScGrade,
    ScLineStatus,
    ScPillar,
    ScRankStatus,
    ScRemarkKind,
    ScRemarkStatus,
    ScScope,
    ScTrend,
    ScWatchStatus,
    ScWindow,
)
from app.models import (
    PeriodLock,
    Project,
    ProjectEngagement,
    ScCard,
    ScLine,
    ScProfile,
    ScRemark,
    ScWatchEntry,
)
from app.schemas.scorecard import (
    ScCapApplied,
    ScCardPage,
    ScCardRead,
    ScFinaliseResult,
    ScLineRead,
    ScPillarRead,
    ScRankInfo,
    ScRanking,
    ScRankingRow,
)
from app.services import hse_settings
from app.services.permissions import Principal, deny, forbidden_error
from app.services.scorecard import calc, inputs
from app.services.scorecard import common as cm
from app.services.scorecard import config as sconfig

D = Decimal
ZERO = D(0)
CURRENT = (ScCardStatus.issued, ScCardStatus.final)
BANNER = "Provisional — changes until issue / مبدئية — تتغير حتى الإصدار"


# ---- building --------------------------------------------------------------------------------


def scorecard_no(project: Project, short: str, month: date, scope: ScScope) -> str:
    tail = "-TREE" if scope == ScScope.tree else ""
    return f"SCR-{project.code}-{short}-{month.year}-{month.month:02d}{tail}"


def card_scopes(db: Session, e: ProjectEngagement) -> list[ScScope]:
    """SG-1: tier-1 engagements and tier-2 engagements with subcontractors also get a tree card."""
    out = [ScScope.own]
    if e.tier == 1 or (e.tier == 2 and cm.has_children(db, e.id)):
        out.append(ScScope.tree)
    return out


def build(
    db: Session,
    project: Project,
    profile: ScProfile,
    eng_id: uuid.UUID,
    month: date,
    scope: ScScope,
    excluded: list[str] | None = None,
) -> tuple[inputs.CardInputs, calc.CardResult]:
    ctx = inputs.context(db, project)
    inp = inputs.card_inputs(ctx, profile, eng_id, month, scope, excluded)
    return inp, inputs.compute(ctx, profile, inp)


def _apply(card: ScCard, inp: inputs.CardInputs, res: calc.CardResult, db: Session) -> None:
    card.month_man_hours = inp.month_mh
    card.r12_man_hours = inp.r12_mh
    card.credibility_z = inp.z
    card.score = res.score
    card.coverage_pct = res.coverage
    card.band_grade = res.band_grade
    card.grade = res.grade
    card.caps_applied = [{"cap_code": c.value, "max_grade": g.value, "refs": refs}
                         for c, g, refs in inp.caps]  # fmt: skip
    card.pillars = [
        {"pillar_code": pr.pillar_code, "weight": str(pr.weight),
         "effective_weight": str(pr.effective_weight),
         "score": None if pr.score is None else str(pr.score), "redistributed": pr.redistributed}
        for pr in res.pillars
    ]  # fmt: skip
    card.inputs_hash = inp.hash()
    for old in db.scalars(select(ScLine).where(ScLine.card_id == card.id)):
        db.delete(old)
    db.flush()
    for ln in res.lines:
        md = cm.METRIC_BY_CODE[ln.metric_code]
        x = ln.extra
        db.add(
            ScLine(
                card_id=card.id, metric_code=ln.metric_code, pillar_code=ln.pillar_code,
                kpi_ref=md.kpi, window=md.window, value=ln.value,
                numerator=_dec(x.get("numerator")), denominator=_dec(x.get("denominator")),
                base=x.get("base"), own_value=x.get("own_value"),
                project_value=x.get("project_value"), points=ln.points, line_status=ln.status,
                original_weight=ln.weight, effective_weight=ln.effective_weight,
                contribution=ln.contribution,
            )
        )  # fmt: skip
    db.flush()


def _dec(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return D(str(v))
    except Exception:
        return None


def new_card(
    db: Session,
    project: Project,
    e: ProjectEngagement,
    month: date,
    scope: ScScope,
    revision: int,
    issued_at: datetime,
    excluded: list[str] | None = None,
) -> ScCard:
    profile = sconfig.profile_for(db, project, month)
    inp, res = build(db, project, profile, e.id, month, scope, excluded)
    c = cm.cfg(db, project.id)
    days = int(c["scorecard_comment_days"])
    card = ScCard(
        id=uuid.uuid4(), project_id=project.id, engagement_id=e.id, month=month,
        revision=revision, scope=scope,
        scorecard_no=scorecard_no(project, e.contractor.short_code, month, scope),
        profile_code=profile.profile_code, profile_version=profile.version,
        month_man_hours=ZERO, r12_man_hours=ZERO, credibility_z=ZERO, coverage_pct=ZERO,
        inputs_hash="", status=ScCardStatus.issued, issued_at=issued_at,
        comment_until=cm.end_of_day(cm.to_local(issued_at).date() + timedelta(days=days)),
        excluded_metrics=list(excluded or []), caps_applied=[], pillars=[],
    )  # fmt: skip
    db.add(card)
    db.flush()
    _apply(card, inp, res, db)
    return card


def current(
    db: Session, project_id: uuid.UUID, month: date, scope: ScScope | None = ScScope.own
) -> list[ScCard]:
    stmt = select(ScCard).where(
        ScCard.project_id == project_id, ScCard.month == month, ScCard.status.in_(CURRENT)
    )
    if scope is not None:
        stmt = stmt.where(ScCard.scope == scope)
    return list(db.scalars(stmt))


def _short(db: Session, eng_id: uuid.UUID) -> str:
    return cm.eng_code(db, eng_id)


def trir_of(db: Session, card: ScCard) -> Decimal:
    v = db.scalar(select(ScLine.value).where(ScLine.card_id == card.id,
                                             ScLine.metric_code == "SM-TRIR"))  # fmt: skip
    return v if v is not None else D(10**9)


def rank_month(db: Session, project_id: uuid.UUID, month: date) -> None:
    """RK-1: own cards with a grade and Z = 1, by unrounded score; ties → lower R12 TRIR, higher
    month man-hours, short code. Others: low_exposure or low_coverage."""
    cards = current(db, project_id, month, ScScope.own)
    ranked = [
        c for c in cards if c.grade is not None and c.credibility_z >= 1 and c.score is not None
    ]
    ranked.sort(key=lambda c: (-(c.score or ZERO), trir_of(db, c), -c.month_man_hours,
                               _short(db, c.engagement_id)))  # fmt: skip
    for i, c in enumerate(ranked, start=1):
        c.rank, c.rank_of, c.rank_status = i, len(ranked), ScRankStatus.ranked
    for c in cards:
        if c in ranked:
            continue
        c.rank, c.rank_of = None, len(ranked)
        c.rank_status = (ScRankStatus.low_coverage if c.grade is None
                         else ScRankStatus.low_exposure)  # fmt: skip
    for c in current(db, project_id, month, ScScope.tree):
        c.rank, c.rank_of, c.rank_status = None, None, None
    db.flush()


def _score_of(db: Session, eng_id: uuid.UUID, scope: ScScope, month: date,
              final_only: bool) -> Decimal | None:  # fmt: skip
    sts = [ScCardStatus.final] if final_only else list(CURRENT)
    c = db.scalar(select(ScCard).where(ScCard.engagement_id == eng_id, ScCard.scope == scope,
                                       ScCard.month == month, ScCard.status.in_(sts)))  # fmt: skip
    return c.score if c is not None else None


def set_trend(db: Session, card: ScCard) -> None:
    """§6.6."""
    prev = _score_of(db, card.engagement_id, card.scope, cm.add_months(card.month, -1), False)
    prior = [_score_of(db, card.engagement_id, card.scope, cm.add_months(card.month, -k), True)
             for k in (3, 2, 1)]  # fmt: skip
    pts = cm.cfg(db, card.project_id).dec("scorecard_trend_points")
    delta, label = calc.trend(card.score, prev, [x for x in prior if x is not None], pts)
    card.trend_delta = delta
    card.trend_label = ScTrend(label) if label else None


# ---- issue (SC-1, §4.1) --------------------------------------------------------------------------


def issue_month(db: Session, project: Project, month: date, t: datetime) -> list[ScCard]:
    """Provisional → Issued for every engagement with month man-hours > 0 (SG-1). 422
    SOURCES_NOT_CONFIRMED (with an alert to the HSE Manager) before the map is confirmed."""
    c = cm.cfg(db, project.id)
    if not c.confirmed:
        if cm.once(db, f"sc_sources:{project.id}:{cm.local_day(t)}"):
            cm.send(db, cm.managers(db), NotificationKind.scorecard_sources,
                    f"{project.code}: confirm the scorecard source dates before the first issue",
                    f"{project.code}: أكّد تواريخ بدء المصادر قبل إصدار بطاقات الأداء",
                    project.id, email=True)  # fmt: skip
        raise cm.code_err(ErrorCode.SOURCES_NOT_CONFIRMED,
                          "Confirm the source live-from dates first (SN-5).",
                          "أكّد تواريخ بدء المصادر أولاً.")  # fmt: skip
    if current(db, project.id, month, None):
        return []
    inputs.reset(db)
    ctx = inputs.context(db, project)
    out: list[ScCard] = []
    engs = db.scalars(select(ProjectEngagement).where(ProjectEngagement.project_id == project.id))
    for e in sorted(engs, key=lambda x: x.contractor.short_code):
        if inputs.month_mh(ctx, frozenset({e.id}), month) <= 0:
            continue
        for scope in card_scopes(db, e):
            out.append(new_card(db, project, e, month, scope, 0, t))
    rank_month(db, project.id, month)
    for card in out:
        set_trend(db, card)
    db.flush()
    _alert_issued(db, project, month, out)
    return out


def _alert_issued(db: Session, project: Project, month: date, out: list[ScCard]) -> None:
    mk = cm.mkey(month)
    for card in out:
        if card.scope != ScScope.own:
            continue
        cm.send(db, cm.reps(db, project.id, card.engagement_id), NotificationKind.scorecard_issued,
                f"{card.scorecard_no} issued for comment until "
                f"{cm.to_local(card.comment_until or now()):%Y-%m-%d %H:%M}",
                f"صدرت بطاقة الأداء {card.scorecard_no} للملاحظات", project.id,
                EntityType.scorecard, card.id, email=True)  # fmt: skip
    if out:
        cm.send(db, cm.officers(db, project.id), NotificationKind.scorecard_issued,
                f"{project.code} {mk}: {len(out)} scorecards issued for comment",
                f"{project.code} {mk}: صدرت {len(out)} بطاقات أداء للملاحظات", project.id,
                email=True)  # fmt: skip


def run_monthly(db: Session, t: datetime) -> dict[str, int]:
    """`scorecard_monthly` (daily 06:00 from day month_lock_day + 1 until the previous month is
    issued); SC-1 alert from month_lock_day + 2 while the month is not Locked."""
    today = cm.local_day(t)
    month = cm.add_months(today.replace(day=1), -1)
    issued = alerts = 0
    for project in db.scalars(select(Project).where(Project.status != ProjectStatus.closed)):
        c = cm.cfg(db, project.id)
        if c.from_month is None or month < c.from_month:
            continue
        lock_day = hse_settings.get(db, project.id).month_lock_day
        if today.day < lock_day + 1 or current(db, project.id, month, None):
            continue
        lock = db.get(PeriodLock, (project.id, month))
        if lock is None or not lock.locked:
            if today.day >= lock_day + 2 and cm.once(db, f"sc_unlocked:{project.id}:{today}"):
                alerts += cm.send(
                    db, cm.managers(db), NotificationKind.scorecard_month_not_locked,
                    f"{project.code}: {cm.mkey(month)} is not Locked; scorecards cannot be issued",
                    f"{project.code}: لم يُقفل شهر {cm.mkey(month)}؛ لا يمكن إصدار بطاقات الأداء",
                    project.id)  # fmt: skip
            continue
        try:
            issued += len(issue_month(db, project, month, t))
        except Exception as exc:
            if getattr(exc, "code", None) != ErrorCode.SOURCES_NOT_CONFIRMED:
                raise
    return {"issued": issued, "alerts": alerts}


# ---- visibility --------------------------------------------------------------------------------


def visible(db: Session, p: Principal, card: ScCard) -> bool:
    if p.is_manager:
        return True
    g = p.grant(card.project_id, cm.C.scorecard_view)
    if g is None or not g.covers_engagement(card.engagement_id):
        return False
    if cm.is_viewer(p, card.project_id):
        return card.status == ScCardStatus.final
    if cm.is_site_engineer(db, p, card.project_id):
        return card.status in CURRENT
    return True


def get_card(db: Session, p: Principal, card_id: uuid.UUID) -> ScCard:
    card = db.get(ScCard, card_id)
    if card is None or not visible(db, p, card):
        raise deny(db, p, EntityType.scorecard, card_id, card.project_id if card else None,
                   "Scorecard")  # fmt: skip
    return card


# ---- read models -------------------------------------------------------------------------------


def _median(db: Session, project_id: uuid.UUID, month: date) -> Decimal | None:
    xs = [c.score for c in current(db, project_id, month, ScScope.own)
          if c.rank_status == ScRankStatus.ranked and c.score is not None]  # fmt: skip
    return calc.median(xs)


def watch_level(db: Session, eng_id: uuid.UUID) -> Any:
    w = db.scalar(
        select(ScWatchEntry).where(
            ScWatchEntry.engagement_id == eng_id, ScWatchEntry.status == ScWatchStatus.open
        )
    )
    return w.level if w is not None else None


def line_read(ln: ScLine | calc.Line) -> ScLineRead:
    if isinstance(ln, ScLine):
        md = cm.METRIC_BY_CODE[ln.metric_code]
        v, pts, st = ln.value, ln.points, ln.line_status
        num, den, base = ln.numerator, ln.denominator, ln.base
        own, proj = ln.own_value, ln.project_value
        ow, ew, contrib = ln.original_weight, ln.effective_weight, ln.contribution
    else:
        md = cm.METRIC_BY_CODE[ln.metric_code]
        v, pts, st = ln.value, ln.points, ln.status
        num, den = _dec(ln.extra.get("numerator")), _dec(ln.extra.get("denominator"))
        base = ln.extra.get("base")
        own, proj = ln.extra.get("own_value"), ln.extra.get("project_value")
        ow, ew, contrib = ln.weight, ln.effective_weight, ln.contribution
    rate = md.window == ScWindow.r12_rate
    return ScLineRead(
        metric_code=ln.metric_code, pillar_code=ScPillar(ln.pillar_code), kpi_ref=md.kpi,
        window=md.window, value=cm.s(v),
        value_display=(cm.d2(v) if rate else cm.d1(v)) if st == ScLineStatus.scored else "—",
        numerator=cm.s(num), denominator=cm.s(den), base=base, own_value=cm.s(own),
        project_value=cm.s(proj), points=cm.s(pts),
        points_display=cm.d1(pts) if st == ScLineStatus.scored else "—", line_status=st,
        original_weight=cm.s(ow) or "0", effective_weight=cm.s(ew) or "0",
        effective_weight_display=cm.d1(ew), contribution=cm.s(contrib) or "0",
    )  # fmt: skip


def _grade_display(card: ScCard) -> str:
    if card.grade is None:
        return "—"
    if card.band_grade is not None and card.band_grade != card.grade:
        caps = ", ".join(c["cap_code"] for c in card.caps_applied)
        return f"{card.band_grade.value} → {card.grade.value} ({caps})"
    return card.grade.value


def to_read(db: Session, card: ScCard, detail: bool = True) -> ScCardRead:
    med = _median(db, card.project_id, card.month) if card.scope == ScScope.own else None
    lines = list(db.scalars(select(ScLine).where(ScLine.card_id == card.id)))
    order = {m.code.value: i for i, m in enumerate(cm.METRICS)}
    lines.sort(key=lambda x: order.get(x.metric_code, 99))
    opens = len(list(db.scalars(select(ScRemark.id).where(
        ScRemark.card_id == card.id, ScRemark.kind == ScRemarkKind.dispute,
        ScRemark.status == ScRemarkStatus.open))))  # fmt: skip
    indicative = card.grade is None and card.score is not None
    return ScCardRead(
        id=card.id, scorecard_no=card.scorecard_no, revision=card.revision,
        project_id=card.project_id, engagement_id=card.engagement_id,
        engagement_code=cm.eng_code(db, card.engagement_id), month=cm.mkey(card.month),
        scope=card.scope, profile_code=card.profile_code, profile_version=card.profile_version,
        month_man_hours=cm.s(card.month_man_hours) or "0",
        r12_man_hours=cm.s(card.r12_man_hours) or "0",
        credibility_z=cm.s(card.credibility_z) or "0",
        credibility_z_display=cm.d4(card.credibility_z), score=cm.s(card.score),
        score_display=cm.d1(card.score) + (" (indicative)" if indicative else ""),
        indicative=indicative, coverage_pct=cm.s(card.coverage_pct) or "0",
        coverage_display=f"{cm.d1(card.coverage_pct)} %", band_grade=card.band_grade,
        grade=card.grade, grade_display=_grade_display(card),
        caps_applied=[ScCapApplied(cap_code=ScCap(c["cap_code"]),
                                   max_grade=ScGrade(c["max_grade"]), refs=c["refs"])
                      for c in card.caps_applied],
        trend_delta=cm.s(card.trend_delta), trend_label=card.trend_label,
        ranking=ScRankInfo(rank=card.rank, rank_of=card.rank_of, rank_status=card.rank_status,
                           median=cm.s(med), median_display=cm.d1(med)),
        commended=card.commended, inputs_hash=card.inputs_hash,
        comment_until=card.comment_until, status=card.status,
        revised_since_final=card.revised_since_final,
        recomputed_score=cm.s(card.recomputed_score), issued_at=card.issued_at,
        finalised_at=card.finalised_at, reissue_reason=card.reissue_reason,
        watch_level=watch_level(db, card.engagement_id), open_disputes=opens,
        pillars=[ScPillarRead(pillar_code=ScPillar(x["pillar_code"]), weight=x["weight"],
                              effective_weight=x["effective_weight"],
                              effective_weight_display=cm.d1(D(x["effective_weight"])),
                              score=x["score"],
                              score_display=cm.d1(D(x["score"])) if x["score"] else "—",
                              redistributed=x["redistributed"])
                 for x in card.pillars] if detail else [],
        lines=[line_read(x) for x in lines] if detail else [],
    )  # fmt: skip


def provisional(
    db: Session, project: Project, e: ProjectEngagement, month: date, scope: ScScope
) -> ScCardRead | None:
    """SG-5: computed on read, never stored, never ranked."""
    ctx = inputs.context(db, project)
    engs = inputs.engs_of(ctx, e.id, scope)
    if inputs.month_mh(ctx, engs, month) <= 0:
        return None
    profile = sconfig.profile_for(db, project, month)
    inp, res = build(db, project, profile, e.id, month, scope)
    caps = [ScCapApplied(cap_code=c, max_grade=g, refs=r) for c, g, r in inp.caps]
    grade_disp = res.grade.value if res.grade else "—"
    return ScCardRead(
        id=None, scorecard_no=scorecard_no(project, e.contractor.short_code, month, scope),
        revision=0, project_id=project.id, engagement_id=e.id,
        engagement_code=e.contractor.short_code, month=cm.mkey(month), scope=scope,
        profile_code=profile.profile_code, profile_version=profile.version,
        month_man_hours=cm.s(inp.month_mh) or "0", r12_man_hours=cm.s(inp.r12_mh) or "0",
        credibility_z=cm.s(inp.z) or "0", credibility_z_display=cm.d4(inp.z),
        score=cm.s(res.score), score_display=cm.d1(res.score), indicative=res.indicative,
        coverage_pct=cm.s(res.coverage) or "0", coverage_display=f"{cm.d1(res.coverage)} %",
        band_grade=res.band_grade, grade=res.grade, grade_display=grade_disp, caps_applied=caps,
        trend_delta=None, trend_label=None,
        ranking=ScRankInfo(rank=None, rank_of=None, rank_status=None, median=None,
                           median_display="—"),
        commended=False, inputs_hash=inp.hash(), comment_until=None,
        status=ScCardStatus.provisional, revised_since_final=False, recomputed_score=None,
        issued_at=None, finalised_at=None, reissue_reason=None,
        watch_level=watch_level(db, e.id), open_disputes=0, banner=BANNER,
        pillars=[ScPillarRead(pillar_code=ScPillar(x.pillar_code), weight=cm.s(x.weight) or "0",
                              effective_weight=cm.s(x.effective_weight) or "0",
                              effective_weight_display=cm.d1(x.effective_weight),
                              score=cm.s(x.score), score_display=cm.d1(x.score),
                              redistributed=x.redistributed) for x in res.pillars],
        lines=[line_read(x) for x in res.lines],
    )  # fmt: skip


def list_cards(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    month: str | None,
    engagement_id: uuid.UUID | None,
    grade: ScGrade | None,
    status: ScCardStatus | None,
    scope: ScScope | None,
    cap: str | None,
    want_provisional: bool,
    page: int,
    size: int,
) -> ScCardPage:
    project = cm.project(db, p, project_id)
    g = cm.view_grant(db, p, project_id)
    m = cm.parse_month(month) if month else None
    stmt = select(ScCard).where(ScCard.project_id == project_id)
    if m is not None:
        stmt = stmt.where(ScCard.month == m)
    if engagement_id is not None:
        stmt = stmt.where(ScCard.engagement_id == engagement_id)
    if grade is not None:
        stmt = stmt.where(ScCard.grade == grade)
    if status is not None and status != ScCardStatus.provisional:
        stmt = stmt.where(ScCard.status == status)
    if scope is not None:
        stmt = stmt.where(ScCard.scope == scope)
    rows = [c for c in db.scalars(stmt.order_by(ScCard.month.desc(), ScCard.scorecard_no,
                                                ScCard.revision.desc()))
            if visible(db, p, c) and (cap is None or any(x["cap_code"] == cap
                                                         for x in c.caps_applied))]  # fmt: skip
    items = [to_read(db, c, detail=False) for c in rows]
    if (want_provisional or status == ScCardStatus.provisional) and m is not None and not rows:
        if cm.is_viewer(p, project_id):
            raise forbidden_error("Provisional cards are not shown to Viewer / Client (RK-4).")
        engs = db.scalars(
            select(ProjectEngagement).where(ProjectEngagement.project_id == project_id)
        )
        for e in sorted(engs, key=lambda x: x.contractor.short_code):
            if not g.covers_engagement(e.id) or (engagement_id and e.id != engagement_id):
                continue
            for sc in card_scopes(db, e):
                if scope is not None and sc != scope:
                    continue
                x = provisional(db, project, e, m, sc)
                if x is not None:
                    items.append(x)
    total = len(items)
    return ScCardPage(items=items[(page - 1) * size : page * size], total=total, page=page,
                      page_size=size)  # fmt: skip


def read(db: Session, p: Principal, card_id: uuid.UUID) -> ScCardRead:
    return to_read(db, get_card(db, p, card_id))


def line(db: Session, p: Principal, card_id: uuid.UUID, metric_code: str) -> ScLineRead:
    card = get_card(db, p, card_id)
    ln = db.scalar(select(ScLine).where(ScLine.card_id == card.id,
                                        ScLine.metric_code == metric_code))  # fmt: skip
    if ln is None:
        raise not_found("Scorecard line")
    return line_read(ln)


def ranking(db: Session, p: Principal, project_id: uuid.UUID, month: str) -> ScRanking:
    cm.project(db, p, project_id)
    g = cm.view_grant(db, p, project_id)
    m = cm.parse_month(month)
    cards = [c for c in current(db, project_id, m, ScScope.own) if visible(db, p, c)]
    trees = {c.engagement_id: c for c in current(db, project_id, m, ScScope.tree)
             if visible(db, p, c)}  # fmt: skip
    cards.sort(key=lambda c: (c.rank is None, c.rank or 0, _short(db, c.engagement_id)))
    rows = [
        ScRankingRow(
            engagement_id=c.engagement_id, engagement_code=_short(db, c.engagement_id),
            card_id=c.id, score=cm.s(c.score), score_display=cm.d1(c.score), grade=c.grade,
            band_grade=c.band_grade, caps=[ScCap(x["cap_code"]) for x in c.caps_applied],
            trend_label=c.trend_label, coverage_display=f"{cm.d1(c.coverage_pct)} %",
            rank=c.rank, rank_status=c.rank_status, watch_level=watch_level(db, c.engagement_id),
            commended=c.commended,
            tree_score_display=cm.d1(trees[c.engagement_id].score)
            if c.engagement_id in trees else None,
        )
        for c in cards
        if g.covers_engagement(c.engagement_id)
    ]  # fmt: skip
    all_cards = current(db, project_id, m, ScScope.own)
    med = _median(db, project_id, m)
    st = all_cards[0].status if all_cards else None
    prof = f"{all_cards[0].profile_code} v{all_cards[0].profile_version}" if all_cards else "—"
    return ScRanking(
        project_id=project_id, month=month, status=st, rows=rows,
        ranked_count=sum(1 for c in all_cards if c.rank_status == ScRankStatus.ranked),
        median=cm.s(med), median_display=cm.d1(med), profile=prof,
    )  # fmt: skip


# ---- finalisation (FN-1, WL-7, E25) --------------------------------------------------------


def _commend(db: Session, card: ScCard) -> None:
    """WL-7: grade A in three consecutive Final months with no cap."""
    if card.scope != ScScope.own:
        return
    months = [cm.add_months(card.month, -k) for k in (2, 1)]
    prior = [db.scalar(select(ScCard).where(ScCard.engagement_id == card.engagement_id,
                                            ScCard.scope == ScScope.own, ScCard.month == mm,
                                            ScCard.status == ScCardStatus.final))
             for mm in months]  # fmt: skip
    chain = [*prior, card]
    card.commended = all(x is not None and x.grade == ScGrade.A and not x.caps_applied
                         for x in chain)  # fmt: skip


def e25(db: Session, project: Project, month: date, escalated: list[str]) -> list[dict[str, Any]]:
    """§6.8 E25 at finalisation: grade D; a drop of ≥ scorecard_drop_points below the mean of the
    three prior Final months; or a watch-list escalation in the month. No names (T13 inputs)."""
    drop = cm.cfg(db, project.id).dec("scorecard_drop_points")
    out: list[dict[str, Any]] = []
    for c in current(db, project.id, month, ScScope.own):
        code = _short(db, c.engagement_id)
        prior = [_score_of(db, c.engagement_id, ScScope.own, cm.add_months(month, -k), True)
                 for k in (3, 2, 1)]  # fmt: skip
        reasons = []
        if c.grade == ScGrade.D:
            reasons.append("grade_d")
        if c.score is not None and all(x is not None for x in prior):
            mean = sum((x for x in prior if x is not None), ZERO) / 3
            if c.score <= mean - drop:
                reasons.append("drop")
        if code in escalated:
            reasons.append("escalation")
        if reasons:
            out.append({"engagement": code, "score": cm.d1(c.score),
                        "grade": c.grade.value if c.grade else "—",
                        "caps": [x["cap_code"] for x in c.caps_applied], "reasons": reasons,
                        "threshold": str(drop)})  # fmt: skip
    if out:
        ids = cm.managers(db) | cm.officers(db, project.id)
        cm.send(db, ids, NotificationKind.scorecard_finalise_due,
                f"E25 contractor performance decline — {project.code} {cm.mkey(month)}: "
                + ", ".join(f"{x['engagement']} {x['score']} {x['grade']}" for x in out),
                f"E25 تراجع أداء المقاول — {project.code} {cm.mkey(month)}", project.id,
                email=True)  # fmt: skip
    return out


def finalise(db: Session, p: Principal, project_id: uuid.UUID, month: str) -> ScFinaliseResult:
    project = cm.project(db, p, project_id)
    cm.require_manager(p)
    m = cm.parse_month(month)
    t = now()
    cards = [c for c in current(db, project_id, m, None) if c.status == ScCardStatus.issued]
    if any(c.comment_until is not None and t <= c.comment_until for c in cards):
        raise cm.code_err(ErrorCode.COMMENT_WINDOW_OPEN,
                          "The comment window is still open (FN-1).",
                          "فترة الملاحظات ما زالت مفتوحة.")  # fmt: skip
    ids = [c.id for c in cards]
    if ids and db.scalar(select(ScRemark.id).where(
            ScRemark.card_id.in_(ids), ScRemark.kind == ScRemarkKind.dispute,
            ScRemark.status == ScRemarkStatus.open)):  # fmt: skip
        raise cm.code_err(ErrorCode.DISPUTES_OPEN, "Resolve the open disputes first (FN-1).",
                          "يجب البت في الاعتراضات المفتوحة أولاً.")  # fmt: skip
    return finalise_cards(db, project, m, cards, p.user.id, t)


def finalise_cards(
    db: Session, project: Project, m: date, cards: list[ScCard], by: uuid.UUID | None,
    t: datetime,
) -> ScFinaliseResult:  # fmt: skip
    from app.services.scorecard import packs, watch  # noqa: PLC0415

    for c in cards:
        c.status = ScCardStatus.final
        c.finalised_at = t
        c.finalised_by_user_id = by
        audit_status(db, c, by)
    rank_month(db, project.id, m)
    for c in cards:
        _commend(db, c)
    db.flush()
    scp = 0
    for c in cards:
        if c.scope == ScScope.own:
            packs.issue_scp(db, c, t)
            scp += 1
    entries, escalated = watch.evaluate_month(db, project, m, t)
    warns = e25(db, project, m, escalated)
    return ScFinaliseResult(month=cm.mkey(m), finalised=len(cards), scp_issued=scp,
                            watch_entries=entries,
                            warnings=[f"E25 {w['engagement']}: {', '.join(w['reasons'])}"
                                      for w in warns])  # fmt: skip


def audit_status(db: Session, c: ScCard, by: uuid.UUID | None) -> None:
    from app.services import audit  # noqa: PLC0415

    audit.record(db, AuditAction.status_change, audit.SYSTEM if by is None else
                 audit.AuditActor(by, None, c.project_id),
                 entity_type=EntityType.scorecard, entity_id=c.id, project_id=c.project_id,
                 after={"status": c.status.value, "revision": c.revision})  # fmt: skip


# ---- re-issue and restatement (FN-4) --------------------------------------------------------


def reissue(db: Session, p: Principal, card_id: uuid.UUID, reason: str) -> ScCardRead:
    card = get_card(db, p, card_id)
    cm.require_manager(p)
    if card.status != ScCardStatus.final:
        raise cm.err(409, ErrorCode.INVALID_TRANSITION, "Only a Final card can be re-issued.",
                     "تُعاد إصدار البطاقات المعتمدة فقط.")  # fmt: skip
    text = cm.reason(reason, 20)
    project = cm.project_by_id(db, card.project_id)
    e = cm.eng(db, card.engagement_id)
    inputs.reset(db)
    t = now()
    card.status = ScCardStatus.superseded
    card.superseded_at = t
    db.flush()
    new = new_card(db, project, e, card.month, card.scope, card.revision + 1, t,
                   list(card.excluded_metrics or []))  # fmt: skip
    new.reissue_reason = text
    rank_month(db, project.id, card.month)
    set_trend(db, new)
    cm.record(db, p, AuditAction.status_change, EntityType.scorecard, new, project.id,
              details={"reissue_of": card.scorecard_no, "reason": text})  # fmt: skip
    db.flush()
    return to_read(db, new)


def recompute(db: Session, card: ScCard) -> calc.CardResult:
    """An Issued card recomputed from current data (DP-3 / DP-4); the revision is unchanged."""
    project = cm.project_by_id(db, card.project_id)
    profile = db.scalar(
        select(ScProfile).where(
            ScProfile.profile_code == card.profile_code, ScProfile.version == card.profile_version
        )
    )
    assert profile is not None  # noqa: S101
    inputs.reset(db)
    inp, res = build(db, project, profile, card.engagement_id, card.month, card.scope,
                     list(card.excluded_metrics or []))  # fmt: skip
    _apply(card, inp, res, db)
    rank_month(db, card.project_id, card.month)
    set_trend(db, card)
    return res


def restatement(db: Session, t: datetime) -> int:
    """FN-4: Final cards of the last 12 months recomputed; a changed inputs hash flags the card,
    stores the recomputed score and alerts the HSE Manager once per revision."""
    today = cm.local_day(t)
    since = cm.add_months(today.replace(day=1), -12)
    n = 0
    inputs.reset(db)
    for card in db.scalars(select(ScCard).where(ScCard.status == ScCardStatus.final,
                                                ScCard.month >= since)):  # fmt: skip
        project = cm.project_by_id(db, card.project_id)
        profile = db.scalar(
            select(ScProfile).where(
                ScProfile.profile_code == card.profile_code,
                ScProfile.version == card.profile_version,
            )
        )
        if profile is None:
            continue
        inp, res = build(db, project, profile, card.engagement_id, card.month, card.scope,
                         list(card.excluded_metrics or []))  # fmt: skip
        if inp.hash() == card.inputs_hash:
            continue
        card.revised_since_final = True
        card.recomputed_score = res.score
        if cm.once(db, f"sc_revised:{card.id}:{card.revision}"):
            cm.send(db, cm.managers(db), NotificationKind.scorecard_revised,
                    f"{card.scorecard_no} R{card.revision}: numbers changed after Final "
                    f"({cm.d1(card.score)} → {cm.d1(res.score)})",
                    f"تغيّرت أرقام {card.scorecard_no} بعد الاعتماد", card.project_id,
                    EntityType.scorecard, card.id, email=True)  # fmt: skip
            n += 1
    db.flush()
    return n


def run_daily(db: Session, t: datetime) -> dict[str, int]:
    """`scorecard_daily` 00:20: comment window closes in 24 h, dispute due / overdue, finalise due
    (FN-2), PIP due (WL), restatement (FN-4)."""
    from app.services.scorecard import remarks, watch  # noqa: PLC0415

    alerts = 0
    for card in db.scalars(select(ScCard).where(ScCard.status == ScCardStatus.issued,
                                                ScCard.scope == ScScope.own)):  # fmt: skip
        cu = card.comment_until
        if cu is None:
            continue
        if cu - timedelta(hours=24) <= t < cu and cm.once(db, f"sc_window:{card.id}"):
            alerts += cm.send(db, cm.reps(db, card.project_id, card.engagement_id),
                              NotificationKind.scorecard_comment_window,
                              f"{card.scorecard_no}: the comment window closes in 24 h",
                              f"{card.scorecard_no}: تغلق فترة الملاحظات خلال 24 ساعة",
                              card.project_id, EntityType.scorecard, card.id)  # fmt: skip
        if t >= cu + timedelta(days=2) and cm.once(
            db, f"sc_finalise:{card.project_id}:{card.month}:{cm.local_day(t)}"
        ):
            alerts += cm.send(
                db,
                cm.managers(db),
                NotificationKind.scorecard_finalise_due,
                f"{cm.pcode(db, card.project_id)} {cm.mkey(card.month)}: "
                "scorecards await finalisation",
                f"{cm.pcode(db, card.project_id)} {cm.mkey(card.month)}: "
                "بطاقات الأداء بانتظار الاعتماد",
                card.project_id,
                email=True,
            )
    alerts += remarks.daily(db, t)
    alerts += watch.daily(db, t)
    revised = restatement(db, t)
    return {"alerts": alerts, "revised": revised}


__all__ = ["ScWatchEntry", "uuid"]
