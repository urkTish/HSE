"""Heat-illness log (spec 6b-heat-stress §3.11, §4.4, §5.8 HI-1…HI-6, §6.7, P6b-2).

Entries come from Phase 1 injury cases (HI-1) and 6a referrals (HI-2); a case following a
referral for the same worker within `heat_case_merge_hours` takes over the referral's entry. The
entry stores no clinical data: nature and category stay in Phase 1."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookSubjectType
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import not_found, validation_error
from app.core.heat_enums import (
    AcclimatisationBasis,
    HeatLogSource,
    HeatLogStatus,
    RecordStatus,
    ReviewAnswer,
    ReviewQuestion,
)
from app.models import (
    FitnessHold,
    FitnessReferral,
    HeatIllnessEntry,
    HeatWelfareCheck,
    Incident,
    InjuryCase,
    Investigation,
    Permit,
    RestStation,
    Worker,
    Zone,
)
from app.schemas.heat import HeatLogPage, HeatLogRead, HeatReviewInput, HeatReviewRead, ReopenInput
from app.services.common import invalid_transition
from app.services.heat import common as hc
from app.services.heat import plans, state
from app.services.heat import welfare as hwelfare
from app.services.permissions import Grant, Principal, forbidden_error

C = Capability
LS = HeatLogStatus
K = NotificationKind


# ---- context snapshot (§6.7) ---------------------------------------------------------------------


def _band(start: date | None, d: date) -> str | None:
    if start is None:
        return None
    n = (d - start).days
    return "<7" if n < 7 else "7-30" if n <= 30 else "31-90" if n <= 90 else ">90"


def context(
    db: Session,
    project_id: uuid.UUID,
    event_at: datetime,
    zone_id: uuid.UUID | None,
    worker_id: uuid.UUID | None,
    case: InjuryCase | None = None,
    hold: FitnessHold | None = None,
) -> dict[str, Any]:
    cfg = hc.cfg(db, project_id)
    t = hc.table(db)
    d = hc.local_day(event_at)
    out: dict[str, Any] = {"state": "unknown", "reading_no": None, "wbgt_c": None}
    dep = None
    if worker_id is not None:
        from app.services.med import common as mcommon  # noqa: PLC0415

        dep = mcommon.deployment(db, worker_id, project_id)
    trade = dep.trade.value if dep else (case.trade.value if case else None)
    wl = cfg.trade_workload(trade)
    out["workload"] = wl.value
    st = plans.status_of(db, dep, d) if dep is not None else None
    out["acclimatisation"] = st.status.value if st else "n.a."
    out["basis"] = st.basis.value if st else "acclimatised"
    out["plan_no"] = st.plan.plan_no if st and st.plan else None
    out["plan_day"] = st.day["day_no"] if st and st.day else None
    if st and st.day:
        out["plan_day_confirmed"] = bool(st.day.get("confirmed_at"))
        out["plan_day_followed"] = st.day.get("followed")
    if zone_id is not None:
        zs = state.zone_state(db, project_id, zone_id, event_at)
        out["state"] = zs.state.value
        if zs.latest is not None:
            out["reading_no"] = zs.latest.reading_no
            out["wbgt_c"] = str(zs.latest.wbgt)
        basis = st.basis if st else AcclimatisationBasis.acclimatised
        out["regime"] = zs.regime(t, cfg.offset, basis, wl).value
    ban = cfg.in_ban(event_at)
    out["ban_in_force"] = ban
    out["possible_ban_breach"] = bool(
        ban and zone_id is not None and zone_id in hc.required_zone_ids(db, project_id)
    )
    if case is not None:
        inv = db.get(Investigation, case.incident_id)
        ids = list(inv.ptw_ids or []) if inv else []
        out["permit_nos"] = (
            [pm.permit_no for pm in db.scalars(select(Permit).where(Permit.id.in_(ids)))]
            if ids
            else []
        )
        out["days_on_site_band"] = _band(case.site_start_date, d)
    out["heat_awr_in_force"] = _heat_awr(db, project_id, worker_id, event_at)
    out["welfare"] = _welfare(db, project_id, zone_id, event_at)
    if hold is not None:
        out["hold_no"] = hold.hold_no
        out["hold_status"] = hold.status.value
    return out


def _heat_awr(
    db: Session, project_id: uuid.UUID, worker_id: uuid.UUID | None, at: datetime
) -> bool | None:
    if worker_id is None:
        return None
    from app.services.train import hook  # noqa: PLC0415

    try:
        r = hook.check(db, HookSubjectType.worker, worker_id, "HEAT-AWR", at, None, project_id)
    except Exception:
        return None
    return r.status.value in ("met", "expiring")


def _welfare(
    db: Session, project_id: uuid.UUID, zone_id: uuid.UUID | None, at: datetime
) -> dict[str, Any]:
    if zone_id is None:
        return {"result": "none"}
    stations = [
        s.id
        for s in db.scalars(select(RestStation).where(RestStation.project_id == project_id))
        if zone_id in (s.zone_ids or [])
    ]
    if not stations:
        return {"result": "none"}
    x = db.scalar(
        select(HeatWelfareCheck)
        .where(
            HeatWelfareCheck.station_id.in_(stations),
            HeatWelfareCheck.status == RecordStatus.valid,
            HeatWelfareCheck.checked_at <= at,
            HeatWelfareCheck.checked_at >= at - timedelta(hours=24),
        )
        .order_by(HeatWelfareCheck.checked_at.desc())
    )
    if x is None:
        return {"result": "none"}
    st = db.get(RestStation, x.station_id)
    return {
        "result": "critical_fail" if hwelfare.critical_fail(x.items) else "pass",
        "check_no": x.check_no,
        "station_code": st.station_code if st else None,
        "checked_at": x.checked_at.isoformat(),
    }


def control_gap(ctx: dict[str, Any], review: dict[str, Any] | None) -> bool:
    """HI-5."""
    if review and any(v == ReviewAnswer.no.value for v in (review.get("answers") or {}).values()):
        return True
    if ctx.get("state") in ("stale", "unknown"):
        return True
    if ctx.get("plan_day") is not None and (
        not ctx.get("plan_day_confirmed") or ctx.get("plan_day_followed") is False
    ):
        return True
    if ctx.get("heat_awr_in_force") is False or ctx.get("possible_ban_breach"):
        return True
    return (ctx.get("welfare") or {}).get("result") == "critical_fail"


# ---- creation (HI-1, HI-2) -----------------------------------------------------------------------


def _natures(db: Session, project_id: uuid.UUID) -> set[str]:
    from app.services.med import common as mcommon  # noqa: PLC0415

    return set(mcommon.settings(db, project_id).heat_illness_natures or [])


def _hold_for(db: Session, source_type: str, source_id: uuid.UUID) -> FitnessHold | None:
    return db.scalar(
        select(FitnessHold).where(
            FitnessHold.source_type == source_type, FitnessHold.source_id == source_id
        )
    )


def _new(
    db: Session,
    project_id: uuid.UUID,
    source_type: HeatLogSource,
    source_id: uuid.UUID,
    worker_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
    event_at: datetime,
    zone_id: uuid.UUID | None,
    ctx: dict[str, Any],
    hold_id: uuid.UUID | None,
    heat_stroke: bool,
) -> HeatIllnessEntry:
    y = hc.local_day(event_at).year
    seq = hc.next_seq(db, HeatIllnessEntry, project_id, y)
    e = HeatIllnessEntry(
        id=uuid.uuid4(),
        year=y,
        seq=seq,
        entry_no=f"HIL-{hc.pcode(db, project_id)}-{y}-{seq:03d}",
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        worker_id=worker_id,
        engagement_id=engagement_id,
        event_at=event_at,
        zone_id=zone_id,
        context=ctx,
        review=None,
        control_gap=control_gap(ctx, None),
        status=LS.open,
        hold_id=hold_id,
        alerts_sent=[],
    )
    db.add(e)
    db.flush()
    hc.record(db, None, AuditAction.create, EntityType.heat_illness_entry, e, project_id)
    from app.services.med import alerts as malerts  # noqa: PLC0415

    users = hc.officers(db, project_id) | malerts.oh(db, project_id)
    if heat_stroke:
        users |= hc.managers(db)
    hc.send(  # P6b-5: the entry number, never the worker
        db,
        users,
        K.heat_illness_entry,
        f"Heat-illness log entry {e.entry_no} created; review within "
        f"{hc.cfg(db, project_id)['heat_illness_review_days']} days",
        f"تم إنشاء سجل إجهاد حراري {e.entry_no}",
        project_id,
        EntityType.heat_illness_entry,
        e.id,
        email=True,
    )
    return e


def on_case(db: Session, c: InjuryCase) -> None:
    """HI-1 (and §4.4 voids) after a Phase 1 injury case is created or changed."""
    if not hc.enabled(db, c.project_id):
        return
    inc = db.get(Incident, c.incident_id)
    if inc is None:
        return
    e = db.scalar(
        select(HeatIllnessEntry).where(
            HeatIllnessEntry.source_type == HeatLogSource.injury_case,
            HeatIllnessEntry.source_id == c.id,
        )
    )
    heat = c.nature.value in _natures(db, c.project_id) and inc.work_related
    voided = inc.status.value == "voided"
    if e is not None:
        if (voided or not heat) and e.status != LS.voided:
            if not voided and e.related_referral_id is not None:
                return  # a linked heat referral keeps the entry (§4.4)
            before = {"status": e.status.value}
            e.status = LS.voided
            db.flush()
            hc.record(
                db, None, AuditAction.status_change, EntityType.heat_illness_entry, e,
                e.project_id, before,
            )  # fmt: skip
        elif (
            heat
            and not voided
            and e.status == LS.open
            and (e.event_at != inc.occurred_at or e.zone_id != inc.zone_id)
        ):
            e.event_at, e.zone_id = inc.occurred_at, inc.zone_id
            e.context = context(
                db, c.project_id, inc.occurred_at, inc.zone_id, c.worker_id, c,
                db.get(FitnessHold, e.hold_id) if e.hold_id else None,
            )  # fmt: skip
            e.control_gap = control_gap(e.context, e.review)
            db.flush()
        return
    if not heat or voided:
        return
    hold = _hold_for(db, "injury_case", c.id)
    eng = c.employer_engagement_id
    # HI-2 merge: a referral entry for the same worker within heat_case_merge_hours
    if c.worker_id is not None:
        hours = int(hc.cfg(db, c.project_id)["heat_case_merge_hours"])
        created = c.created_at or now()
        for re in db.scalars(
            select(HeatIllnessEntry).where(
                HeatIllnessEntry.project_id == c.project_id,
                HeatIllnessEntry.source_type == HeatLogSource.referral,
                HeatIllnessEntry.worker_id == c.worker_id,
                HeatIllnessEntry.status != LS.voided,
            )
        ):
            if timedelta(0) <= created - re.event_at <= timedelta(hours=hours):
                re.related_referral_id = re.source_id
                re.source_type, re.source_id = HeatLogSource.injury_case, c.id
                re.event_at, re.zone_id = inc.occurred_at, inc.zone_id
                if hold is not None:
                    re.hold_id = hold.id
                if re.status == LS.open:
                    re.context = context(
                        db, c.project_id, inc.occurred_at, inc.zone_id, c.worker_id, c,
                        db.get(FitnessHold, re.hold_id) if re.hold_id else None,
                    )  # fmt: skip
                    re.control_gap = control_gap(re.context, re.review)
                db.flush()
                return
    ctx = context(db, c.project_id, inc.occurred_at, inc.zone_id, c.worker_id, c, hold)
    _new(
        db, c.project_id, HeatLogSource.injury_case, c.id, c.worker_id, eng, inc.occurred_at,
        inc.zone_id, ctx, hold.id if hold else None, c.nature.value == "heat_stroke",
    )  # fmt: skip


def on_referral(db: Session, r: FitnessReferral) -> None:
    """HI-2: a referral `heat_illness_episode` creates an entry when raised."""
    if r.reason.value != "heat_illness_episode" or not hc.enabled(db, r.project_id):
        return
    hold = db.get(FitnessHold, r.hold_id) if r.hold_id else None
    ctx = context(db, r.project_id, r.raised_at, None, r.worker_id, None, hold)
    _new(
        db, r.project_id, HeatLogSource.referral, r.id, r.worker_id, r.engagement_id,
        r.raised_at, None, ctx, hold.id if hold else None, False,
    )  # fmt: skip


# ---- reads (P6b-2) -------------------------------------------------------------------------------


def _source_ref(db: Session, e: HeatIllnessEntry) -> str | None:
    if e.source_type == HeatLogSource.injury_case:
        c = db.get(InjuryCase, e.source_id)
        inc = db.get(Incident, c.incident_id) if c else None
        return f"{inc.ref}-P{c.person_no}" if inc and c else None
    r = db.get(FitnessReferral, e.source_id)
    return r.referral_no if r else None


def review_due(db: Session, e: HeatIllnessEntry) -> datetime:
    days = int(hc.cfg(db, e.project_id)["heat_illness_review_days"])
    return e.created_at + timedelta(days=days)


def entry_read(db: Session, p: Principal | None, e: HeatIllnessEntry) -> HeatLogRead:
    from app.services.access import common as acommon  # noqa: PLC0415

    w = db.get(Worker, e.worker_id) if e.worker_id else None
    names = p is None or p.grant(e.project_id, C.injury_identity_view) is not None
    contractor = p is not None and _contractor_view(p, e.project_id)
    rv = e.review or None
    rel = db.get(FitnessReferral, e.related_referral_id) if e.related_referral_id else None
    hold = db.get(FitnessHold, e.hold_id) if e.hold_id else None
    z = db.get(Zone, e.zone_id) if e.zone_id else None
    return HeatLogRead(
        id=e.id,
        entry_no=e.entry_no,
        project_id=e.project_id,
        source_type=e.source_type,
        source_ref=_source_ref(db, e),
        related_referral_no=rel.referral_no if rel else None,
        worker=acommon.worker_ref(w, names) if w else None,
        event_at=e.event_at,
        zone_id=e.zone_id,
        zone_code=z.code if z else None,
        context=dict(e.context or {}),
        review=HeatReviewRead(
            answers={ReviewQuestion(k): ReviewAnswer(v) for k, v in rv["answers"].items()},
            factors_text=None if contractor else rv.get("factors_text"),
            reviewed_by=hc.user_ref(db, uuid.UUID(rv["by"])) if rv.get("by") else None,
            reviewed_at=datetime.fromisoformat(rv["at"]) if rv.get("at") else None,
        )
        if rv
        else None,
        control_gap=e.control_gap,
        status=e.status,
        hold_no=hold.hold_no if hold else None,
        review_due_at=review_due(db, e),
    )


def _contractor_view(p: Principal, project_id: uuid.UUID) -> bool:
    if p.is_manager:
        return False
    s = p.projects.get(project_id)
    roles = s.roles if s else set()
    return Role.contractor_hse_rep in roles and not (
        {Role.hse_officer, Role.site_engineer, Role.oh_practitioner} & roles
    )


def _visible(db: Session, g: Grant, e: HeatIllnessEntry) -> bool:
    if g.engagement_ids is not None and e.engagement_id not in g.engagement_ids:
        return False
    if g.site_ids is not None:
        z = db.get(Zone, e.zone_id) if e.zone_id else None
        if z is None or z.site_id not in g.site_ids:
            return False
    return True


def _read_audit(db: Session, p: Principal, e: HeatIllnessEntry) -> None:
    from app.services.med import common as mcommon  # noqa: PLC0415

    mcommon.sensitive_read(
        db, p, EntityType.heat_illness_entry, e.id, e.project_id,
        ["source", "context", "review", "control_gap"],
    )  # fmt: skip


def list_entries(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: HeatLogStatus | None,
) -> HeatLogPage:
    hc.project(db, p, project_id)
    g = hc.need(p, project_id, C.heat_log_view, write=False)
    stmt = select(HeatIllnessEntry).where(HeatIllnessEntry.project_id == project_id)
    if status:
        stmt = stmt.where(HeatIllnessEntry.status == status)
    if g.engagement_ids is not None:
        stmt = stmt.where(HeatIllnessEntry.engagement_id.in_(list(g.engagement_ids)))
    stmt = stmt.order_by(HeatIllnessEntry.entry_no.desc())
    rows = [e for e in db.scalars(stmt) if _visible(db, g, e)]
    total = len(rows)
    rows = rows[(page - 1) * page_size : page * page_size]
    for e in rows:
        _read_audit(db, p, e)
    return HeatLogPage(
        items=[entry_read(db, p, e) for e in rows], total=total, page=page, page_size=page_size
    )


def _entry(db: Session, p: Principal, entry_id: uuid.UUID) -> HeatIllnessEntry:
    e = db.get(HeatIllnessEntry, entry_id)
    if e is None or not p.can_see_project(e.project_id):
        raise not_found("Heat-illness entry")
    g = hc.need(p, e.project_id, C.heat_log_view, write=False)
    if not _visible(db, g, e):
        raise not_found("Heat-illness entry")
    return e


def read_entry(db: Session, p: Principal, entry_id: uuid.UUID) -> HeatLogRead:
    e = _entry(db, p, entry_id)
    _read_audit(db, p, e)
    return entry_read(db, p, e)


def _reviewer(p: Principal, project_id: uuid.UUID) -> None:
    p.ensure_writer()
    if p.is_manager:
        return
    s = p.projects.get(project_id)
    if s is None or Role.hse_officer not in s.roles:
        raise forbidden_error()


def review(db: Session, p: Principal, entry_id: uuid.UUID, body: HeatReviewInput) -> HeatLogRead:
    e = _entry(db, p, entry_id)
    _reviewer(p, e.project_id)
    if e.status != LS.open:
        raise invalid_transition("Heat-illness entry", e.status, LS.reviewed)
    missing = [q.value for q in ReviewQuestion if q not in body.answers]
    if missing:
        raise validation_error("answers", "Answer every question: " + ", ".join(missing))
    before = {"status": e.status.value}
    e.review = {
        "answers": {k.value: v.value for k, v in body.answers.items()},
        "factors_text": (body.factors_text or "").strip() or None,
        "by": str(p.user.id),
        "at": now().isoformat(),
    }
    e.control_gap = control_gap(e.context or {}, e.review)
    e.status = LS.reviewed
    db.flush()
    hc.record(
        db, p, AuditAction.status_change, EntityType.heat_illness_entry, e, e.project_id, before
    )
    return entry_read(db, p, e)


def reopen(db: Session, p: Principal, entry_id: uuid.UUID, body: ReopenInput) -> HeatLogRead:
    e = _entry(db, p, entry_id)
    _reviewer(p, e.project_id)
    why = hc.reason(body.reason, 20)
    if e.status != LS.reviewed:
        raise invalid_transition("Heat-illness entry", e.status, LS.open)
    before = {"status": e.status.value}
    e.status = LS.open
    db.flush()
    hc.record(
        db, p, AuditAction.status_change, EntityType.heat_illness_entry, e, e.project_id, before,
        {"reason": why},
    )  # fmt: skip
    return entry_read(db, p, e)


def overdue_alerts(db: Session, project_id: uuid.UUID, at: datetime) -> int:
    """HI-4: overdue reviews alert the HSE Officers, then the HSE Manager after 2 more days."""
    n = 0
    for e in db.scalars(
        select(HeatIllnessEntry).where(
            HeatIllnessEntry.project_id == project_id, HeatIllnessEntry.status == LS.open
        )
    ):
        due = review_due(db, e)
        sent = list(e.alerts_sent or [])
        for step, when, users in (
            ("officer", due, hc.officers(db, project_id)),
            ("manager", due + timedelta(days=2), hc.managers(db)),
        ):
            if at >= when and step not in sent:
                sent.append(step)
                n += hc.send(
                    db,
                    users,
                    K.heat_review_overdue,
                    f"Heat-illness review overdue: {e.entry_no}",
                    f"مراجعة سجل الإجهاد الحراري متأخرة: {e.entry_no}",
                    project_id,
                    EntityType.heat_illness_entry,
                    e.id,
                    email=True,
                )
        e.alerts_sent = sent
    db.flush()
    return n
