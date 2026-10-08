"""Requirement status per deployment, the gap register, its summary and the refresher plan
(spec 5-training §3.10, §3.14, §6.2, §6.7, GP-1…GP-8), plus AT-5 re-training notes."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import CrewMemberStatus, WapStatus
from app.core.clock import now, today
from app.core.enums import AuditAction, EntityType, Role
from app.core.hse_enums import Trade
from app.core.ptw_enums import PERMIT_TERMINAL, CrewLineStatus
from app.core.train_enums import (
    MatrixLevel,
    RefresherPlanState,
    RequirementState,
)
from app.models import (
    Deployment,
    HseSettings,
    Permit,
    PermitCrew,
    TrainingRecord,
    TrainingRetrainingNote,
    Wap,
    WapCrew,
    Worker,
)
from app.schemas.hse_common import EngagementRef
from app.schemas.training_matrix import (
    DeploymentRequirements,
    GapPage,
    GapRow,
    GapSummary,
    GapSummaryRow,
    RefresherPlanItem,
    RefresherPlanPage,
    RequirementStatus,
    RetrainingNoteCreate,
    RetrainingNoteRead,
)
from app.services.cert import common as cc
from app.services.hse_common import Refs
from app.services.permissions import Grant, Principal, engagement_descendants, forbidden_error
from app.services.ptw import common as pcommon
from app.services.train import common
from app.services.train import matrix as tmatrix
from app.services.train import requirements as reqs

C = common.C
RS = RequirementState
PS = RefresherPlanState
ACTIVE_WAP = (WapStatus.active, WapStatus.approved, WapStatus.suspended)


def _eng_ref(refs: Refs, eid: uuid.UUID | None) -> EngagementRef:
    if eid is None:
        out: EngagementRef = tmatrix._no_eng()
        return out
    return refs.eng_required(eid)


def requirement_status(db: Session, r: reqs.Req) -> RequirementStatus:
    code = r.course_code
    any_of = None if code else list(r.codes)
    return RequirementStatus(
        line_nos=r.line_nos,
        requirement=tmatrix.requirement_read(db, code, any_of),
        level=r.level,
        kpi_counted=r.kpi_counted,
        hook_code=r.hook_code,
        critical=r.critical,
        applies_from=r.applies_from,
        due_date=r.due_date,
        state=r.state,
        counted=r.counted,
        satisfied_by_record=common.record_ref(r.record, r.valid_until)
        if r.record is not None and r.state in (RS.met, RS.expiring)
        else None,
        satisfied_by_induction_no=r.induction.induction_no if r.induction is not None else None,
        valid_until=r.valid_until,
        booked_session=common.session_ref(r.booked) if r.booked is not None else None,
        exemption_id=r.exemption_id,
        not_met_reason=r.reason.value if r.reason is not None and r.state == RS.gap else None,
    )


def get_requirements(
    db: Session, p: Principal, deployment_id: uuid.UUID, as_of: date | None
) -> DeploymentRequirements:
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        from app.core.errors import not_found  # noqa: PLC0415

        raise not_found("Deployment")
    common.visible_project(db, p, dep.project_id)
    if not common.covers_dep(p.grant(dep.project_id, C.training_record_view), dep):
        raise forbidden_error()
    d = as_of or today()
    f = reqs.load(
        db, dep.project_id, d, deployment_ids=[dep.id], mobilised_only=False, enforcement=True,
        bookings=True,
    )  # fmt: skip
    rows = reqs.evaluate_dep(f, dep, include_enforcement=True)
    w = db.get(Worker, dep.worker_id)
    assert w is not None  # noqa: S101
    refs = Refs(db)
    return DeploymentRequirements(
        deployment_id=dep.id,
        project_id=dep.project_id,
        as_of=d,
        worker=common.worker_ref(w, common.names(p, dep.project_id)),
        engagement=_eng_ref(refs, dep.engagement_id),
        deployment_status=dep.status,
        kpi_population=common.is_contractor_worker(w),
        requirements=[requirement_status(db, r) for r in rows],
    )


# ---- scope ---------------------------------------------------------------------------------------


def engagement_filter(
    db: Session, g: Grant | None, engagement_id: uuid.UUID | None, include_subs: bool
) -> set[uuid.UUID] | None:
    """Engagement ids to keep (None = all): the caller's C scope ∩ the requested contractor."""
    keep: set[uuid.UUID] | None = None
    if g is not None and g.engagement_ids is not None:
        keep = set(g.engagement_ids)
    if engagement_id is not None:
        want = engagement_descendants(db, engagement_id) if include_subs else {engagement_id}
        keep = want if keep is None else keep & want
    return keep


def _site_ok(g: Grant | None, dep: Deployment) -> bool:
    return g is None or g.site_ids is None or bool(set(dep.site_ids or []) & set(g.site_ids))


def live_work(
    db: Session, project_id: uuid.UUID, worker_ids: set[uuid.UUID]
) -> tuple[dict[uuid.UUID, list[Permit]], dict[uuid.UUID, list[str]]]:
    permits: dict[uuid.UUID, list[Permit]] = defaultdict(list)
    waps: dict[uuid.UUID, list[str]] = defaultdict(list)
    if not worker_ids:
        return permits, waps
    for line, pm in db.execute(
        select(PermitCrew, Permit)
        .join(Permit, Permit.id == PermitCrew.permit_id)
        .where(
            Permit.project_id == project_id,
            Permit.status.notin_(list(PERMIT_TERMINAL)),
            PermitCrew.worker_id.in_(list(worker_ids)),
        )
    ):
        if line.status != CrewLineStatus.removed and pm not in permits[line.worker_id]:
            permits[line.worker_id].append(pm)
    for wc, wap in db.execute(
        select(WapCrew, Wap)
        .join(Wap, Wap.id == WapCrew.wap_id)
        .where(
            Wap.project_id == project_id,
            Wap.status.in_(ACTIVE_WAP),
            WapCrew.worker_id.in_(list(worker_ids)),
        )
    ):
        if wc.status != CrewMemberStatus.removed and wap.wap_no not in waps[wc.worker_id]:
            waps[wc.worker_id].append(wap.wap_no)
    return permits, waps


# ---- gap register --------------------------------------------------------------------------------


def list_gaps(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    as_of: date | None,
    states: list[RequirementState] | None,
    engagement_id: uuid.UUID | None,
    include_subs: bool,
    trades: list[Trade] | None,
    course_codes: list[str] | None,
    hook_code: bool | None,
    on_live_work: bool | None,
    counted_only: bool,
) -> GapPage:
    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.training_record_view)
    if g is None:
        raise forbidden_error()
    d = as_of or today()
    want = set(states or [RS.gap, RS.due, RS.expiring])
    keep = engagement_filter(db, g, engagement_id, include_subs)
    pe = reqs.evaluate_project(
        db, project_id, d, engagement_ids=keep, bookings=True, enforcement=True
    )
    rows: list[reqs.Req] = []
    for r in pe.reqs:
        if r.state not in want or not _site_ok(g, r.dep):
            continue
        if counted_only and not r.counted:
            continue
        if trades and r.dep.trade not in trades:
            continue
        if course_codes and not set(r.codes) & set(course_codes):
            continue
        if hook_code is not None and r.hook_code != hook_code:
            continue
        rows.append(r)
    wids = {r.dep.worker_id for r in rows}
    permits, waps = live_work(db, project_id, wids)
    if on_live_work is not None:
        rows = [
            r for r in rows
            if bool(permits.get(r.dep.worker_id) or waps.get(r.dep.worker_id)) == on_live_work
        ]  # fmt: skip
    order = {RS.gap: 0, RS.expiring: 1, RS.due: 2, RS.met: 3, RS.exempt: 4}
    rows.sort(key=lambda r: (order[r.state], r.due_date, r.dep.worker_id.int, r.key))
    total = len(rows)
    chunk = rows[(page - 1) * page_size : page * page_size]
    refs = Refs(db)
    show = common.names(p, project_id)
    items = []
    for r in chunk:
        w = pe.f.workers.get(r.dep.worker_id)
        assert w is not None  # noqa: S101
        code = r.course_code
        items.append(
            GapRow(
                deployment_id=r.dep.id,
                worker=common.worker_ref(w, show),
                engagement=_eng_ref(refs, r.dep.engagement_id),
                trade=r.dep.trade,
                line_nos=r.line_nos,
                requirement=tmatrix.requirement_read(db, code, None if code else list(r.codes)),
                level=r.level,
                hook_code=r.hook_code,
                critical=r.critical,
                due_date=r.due_date,
                state=r.state,
                days_overdue=(d - r.due_date).days if r.state == RS.gap else None,
                valid_until=r.valid_until,
                booked_session=common.session_ref(r.booked) if r.booked is not None else None,
                live_permits=[pcommon.permit_ref(pm) for pm in permits.get(r.dep.worker_id, [])]
                if r.hook_code
                else [],
                live_wap_nos=waps.get(r.dep.worker_id, []) if r.hook_code else [],
            )
        )
    return GapPage(items=items, total=total, page=page, page_size=page_size)


def _row(key: str, en: str, ar: str) -> dict[str, Any]:
    return {"key": key, "label_en": en, "label_ar": ar, "counted": 0, "met": 0, "expiring": 0,
            "gap": 0, "due": 0, "exempt": 0}  # fmt: skip


def _bump(row: dict[str, Any], r: reqs.Req) -> None:
    if r.counted:
        row["counted"] += 1
    row[r.state.value] += 1


def gap_summary(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    as_of: date | None,
    engagement_id: uuid.UUID | None,
    include_subs: bool,
) -> GapSummary:
    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.training_record_view) or p.grant(project_id, C.training_kpi_view)
    if g is None:
        raise forbidden_error()
    d = as_of or today()
    keep = engagement_filter(db, g, engagement_id, include_subs)
    pe = reqs.evaluate_project(db, project_id, d, engagement_ids=keep)
    refs = Refs(db)
    total = _row("all", "All", "الكل")
    by_course: dict[str, dict[str, Any]] = {}
    by_con: dict[str, dict[str, Any]] = {}
    by_trade: dict[str, dict[str, Any]] = {}
    for r in pe.reqs:
        if r.level != MatrixLevel.mandatory or not r.kpi_counted:
            continue
        w = pe.f.workers.get(r.dep.worker_id)
        if w is None or not common.is_contractor_worker(w) or not _site_ok(g, r.dep):
            continue
        _bump(total, r)
        key = r.course_code or r.key
        if key not in by_course:
            c = common.course(db, key) if r.course_code else None
            by_course[key] = _row(
                key,
                c.name_en if c else " / ".join(r.codes),
                c.name_ar if c else " / ".join(r.codes),
            )
        _bump(by_course[key], r)
        ek = "—"
        if r.dep.engagement_id is not None:
            e = refs.eng_required(r.dep.engagement_id)
            ek = e.short_code
            if ek not in by_con:
                by_con[ek] = _row(ek, e.name_en, e.name_ar)
        else:
            by_con.setdefault(ek, _row(ek, "—", "—"))
        _bump(by_con[ek], r)
        tk = r.dep.trade.value
        by_trade.setdefault(tk, _row(tk, tk.replace("_", " "), tk.replace("_", " ")))
        _bump(by_trade[tk], r)
    return GapSummary(
        project_id=project_id,
        as_of=d,
        totals=GapSummaryRow(**total),
        by_course=[GapSummaryRow(**v) for _k, v in sorted(by_course.items())],
        by_contractor=[GapSummaryRow(**v) for _k, v in sorted(by_con.items())],
        by_trade=[GapSummaryRow(**v) for _k, v in sorted(by_trade.items())],
    )


# ---- refresher plan (§6.7) -----------------------------------------------------------------------


def due_from(
    db: Session,
    project_id: uuid.UUID,
    course_code: str,
    vu: date,
    pre: tuple[Any, Any] | None = None,
) -> date:
    s, hs = pre if pre is not None else (common.settings(db, project_id), None)
    out = vu - timedelta(days=s.refresher_planning_days)
    if course_code == "HEAT-AWR":
        if pre is None:
            hs = db.get(HseSettings, project_id)
        start = (hs.heat_season_start if hs else None) or "06-01"
        mm, dd = (int(x) for x in start.split("-"))
        season = date(vu.year, mm, dd)
        end_s = (hs.heat_season_end if hs else None) or "09-30"
        em, ed = (int(x) for x in end_s.split("-"))
        season_end = date(vu.year, em, ed)
        if vu <= season_end:  # the coming season is this year's (GP-6)
            out = min(out, season - timedelta(days=60))
    return out


def plan_state(r: reqs.Req) -> RefresherPlanState:
    if r.booked is None:
        return PS.not_booked
    if r.valid_until is None or r.booked.last_day <= r.valid_until:
        return PS.booked_in_time
    return PS.booked_late


def plan_items(
    db: Session, project_id: uuid.UUID, d: date, keep: set[uuid.UUID] | None = None
) -> list[tuple[reqs.Req, date, str]]:
    """GP-3: (requirement, refresher_due_from, reason) per record still required at d."""
    pe = reqs.evaluate_project(
        db, project_id, d, engagement_ids=keep, bookings=True, enforcement=True
    )
    seen: dict[uuid.UUID, tuple[reqs.Req, date, str]] = {}
    pre = (common.settings(db, project_id), db.get(HseSettings, project_id))
    for r in pe.reqs:
        if r.level != MatrixLevel.mandatory or r.record is None or r.valid_until is None:
            continue
        if r.state not in (RS.met, RS.expiring):
            continue
        enforcement = all(ln.enforcement for ln in r.lines)
        if not enforcement and not r.counted:
            continue
        df = due_from(db, project_id, r.record.course_code, r.valid_until, pre)
        if d < df:
            continue
        why = f"matrix {', '.join(r.line_nos)}"
        if enforcement:
            why = f"permit / appointment role ({', '.join(r.line_nos)})"
        prev = seen.get(r.record.id)
        if prev is None or (prev[0].booked is None and r.booked is not None):
            seen[r.record.id] = (r, df, why)
    return list(seen.values())


def refresher_plan(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    as_of: date | None,
    states: list[RefresherPlanState] | None,
    course_codes: list[str] | None,
    engagement_id: uuid.UUID | None,
    due_within_days: int | None,
) -> RefresherPlanPage:
    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.training_kpi_view)
    if g is None or common.viewer_only(p, project_id):
        raise forbidden_error()
    d = as_of or today()
    keep = engagement_filter(db, g, engagement_id, True)
    items = []
    for r, df, why in plan_items(db, project_id, d, keep):
        assert r.record is not None and r.valid_until is not None  # noqa: S101
        st = plan_state(r)
        if states and st not in states:
            continue
        if course_codes and r.record.course_code not in course_codes:
            continue
        if due_within_days is not None and r.valid_until > d + timedelta(days=due_within_days):
            continue
        if not _site_ok(g, r.dep):
            continue
        items.append((r, df, why, st))
    items.sort(key=lambda x: (x[0].valid_until, x[0].record.record_no if x[0].record else ""))
    total = len(items)
    refs = Refs(db)
    show = common.names(p, project_id)
    out = []
    for r, df, why, st in items[(page - 1) * page_size : page * page_size]:
        assert r.record is not None and r.valid_until is not None  # noqa: S101
        w = db.get(Worker, r.dep.worker_id)
        assert w is not None  # noqa: S101
        c = common.course_or_404(db, r.record.course_code)
        out.append(
            RefresherPlanItem(
                record=common.record_ref(r.record, r.valid_until),
                worker=common.worker_ref(w, show),
                engagement=_eng_ref(refs, r.dep.engagement_id),
                language=w.primary_language,
                course=common.course_ref(c),
                valid_until=r.valid_until,
                days_left=(r.valid_until - d).days,
                refresher_due_from=df,
                reason_required=why,
                booked_session=common.session_ref(r.booked) if r.booked is not None else None,
                state=st,
            )
        )
    return RefresherPlanPage(items=out, total=total, page=page, page_size=page_size)


# ---- re-training notes (AT-5) --------------------------------------------------------------------


def create_note(
    db: Session, p: Principal, worker_id: uuid.UUID, body: RetrainingNoteCreate
) -> RetrainingNoteRead:
    w = common.active_worker(db, worker_id)
    common.visible_project(db, p, body.project_id)
    p.require(body.project_id, C.training_record_review)
    if not (p.is_manager or Role.hse_officer in common.roles_on(p, body.project_id)):
        raise forbidden_error()
    common.course_or_404(db, body.course_code)
    n = TrainingRetrainingNote(
        id=uuid.uuid4(),
        worker_id=w.id,
        project_id=body.project_id,
        course_code=body.course_code,
        note=body.note,
        created_by_user_id=p.user.id,
        created_at=now(),
    )
    db.add(n)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.training_retraining_note, n, body.project_id)
    u = Refs(db).user(p.user.id)
    assert u is not None  # noqa: S101
    return RetrainingNoteRead(
        id=n.id,
        worker_id=w.id,
        project_id=n.project_id,
        course_code=n.course_code,
        note=n.note,
        created_by=u,
        created_at=n.created_at,
    )


def records_of(db: Session, worker_id: uuid.UUID) -> list[TrainingRecord]:
    return list(db.scalars(select(TrainingRecord).where(TrainingRecord.worker_id == worker_id)))
