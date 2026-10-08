# ruff: noqa: E501
"""Phase 3 additions to the dashboard expiring-items panel (3-ptw §8.2) and action panel (§8.3).

Both are scoped by capability 103's grant (engagement / site scope of the grant) and by the
dashboard filters. Titles carry no person names for callers without capability 46.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import API_PREFIX
from app.core.enums import Capability, EntityType
from app.core.hse_enums import ActionPanelItem, CaStatus, ExpiringItemKind, Severity
from app.core.ptw_enums import (
    PERMIT_LIVE,
    AppointmentStatus,
    DetectorStatus,
    ExemptionKind,
    ExemptionStatus,
    GasTestResult,
    JsaStatus,
    PermitStatus,
    PersonalLockRemoval,
    PtwAuditStatus,
    ShiftEndType,
    SimopsConflictStatus,
)
from app.models import (
    CorrectiveAction,
    GasDetector,
    GasTest,
    IsolationCertificate,
    Jsa,
    Permit,
    PermitExemption,
    PermitShift,
    PermitSuspension,
    PersonalLockEvent,
    Project,
    PtwAppointment,
    PtwAudit,
    SimopsConflict,
    User,
    Worker,
)
from app.schemas.dashboard import ExpiringItem
from app.services.access import common as acommon
from app.services.hse_common import Refs
from app.services.permissions import Grant, Principal

K = ExpiringItemKind
A = ActionPanelItem
S = PermitStatus

LABELS: dict[ActionPanelItem, tuple[str, str]] = {
    A.permits_requested_unreviewed: (
        "Permits requested > 4 h not reviewed",
        "تصاريح مطلوبة > 4 ساعات دون مراجعة",
    ),
    A.permits_approved_not_issued: (
        "Approved permits not issued (window start + 60 min)",
        "تصاريح معتمدة لم تصدر (بداية الفترة + 60 دقيقة)",
    ),
    A.permits_suspended_non_routine: (
        "Non-routine suspended permits",
        "تصاريح موقوفة لأسباب غير اعتيادية",
    ),
    A.shift_lapses_today: ("Shift lapses today", "انقضاء نوبات اليوم"),
    A.post_expiry_checks_pending: (
        "Expired permits with post-expiry check pending",
        "تصاريح منتهية بانتظار فحص ما بعد الانتهاء",
    ),
    A.gas_tests_failed_24h: ("Gas tests failed (24 h)", "اختبارات غاز فاشلة (24 ساعة)"),
    A.simops_open_starting_24h: (
        "Open SIMOPS conflicts starting within 24 h",
        "تعارضات أعمال متزامنة مفتوحة تبدأ خلال 24 ساعة",
    ),
    A.ptw_critical_findings_ca_not_started: (
        "Critical PTW findings whose action is not in progress",
        "ملاحظات حرجة لم يبدأ إجراؤها التصحيحي",
    ),
    A.ptw_audits_behind_plan: (
        "PTW audits behind plan this week",
        "تدقيقات التصاريح متأخرة عن الخطة هذا الأسبوع",
    ),
    A.orphan_isolations: (
        "Orphan isolations (no live permit > 24 h)",
        "عزل دون تصريح ساري > 24 ساعة",
    ),
    A.quarantined_detectors_on_live_permits: (
        "Quarantined detectors on live permits",
        "كواشف معزولة على تصاريح سارية",
    ),
    A.midday_exemptions_active: ("Active midday-ban exemptions", "استثناءات حظر الظهيرة السارية"),
    A.lock_cuts_7d: ("Lock cuts (7 days)", "قص الأقفال (7 أيام)"),
}

_FILE_PATHS = {
    EntityType.permit: "/permits/{}",
    EntityType.gas_detector: "/gas-detectors/{}",
    EntityType.ptw_appointment: "/ptw-appointments/{}",
    EntityType.isolation_certificate: "/isolations/{}",
    EntityType.jsa: "/jsas/{}",
}


class _Ctx:
    def __init__(self, db: Session, p: Principal, project: Project, day: date) -> None:
        self.db = db
        self.p = p
        self.project = project
        self.day = day
        self.at = now()
        self.grant: Grant | None = p.grant(project.id, Capability.ptw_kpi_view)
        self.names = acommon.can_see_names(p, project.id)
        self.refs = Refs(db)

    def ok(self, eng: uuid.UUID | None, sites: list[uuid.UUID] | None = None) -> bool:
        g = self.grant
        if g is None:
            return False
        if g.engagement_ids is not None and (eng is None or eng not in g.engagement_ids):
            return False
        return g.site_ids is None or sites is None or bool(set(sites) & set(g.site_ids))

    def permit_ok(self, x: Permit) -> bool:
        return self.ok(x.engagement_id, [x.site_id])


def _item(
    c: _Ctx,
    kind: ExpiringItemKind,
    et: EntityType,
    eid: uuid.UUID,
    ref: str | None,
    title: tuple[str, str],
    due: date,
    eng: uuid.UUID | None,
    due_at: datetime | None = None,
) -> ExpiringItem:
    return ExpiringItem(
        kind=kind,
        entity_type=et,
        entity_id=eid,
        ref=ref,
        title_en=title[0],
        title_ar=title[1],
        due_date=due,
        days_left=(due - c.day).days,
        engagement=c.refs.eng(eng) if eng else None,
        detail_path=f"{API_PREFIX}{_FILE_PATHS[et].format(eid)}",
        due_at=due_at,
        minutes_left=int((due_at - c.at).total_seconds() // 60) if due_at is not None else None,
    )


def _holder(c: _Ctx, a: PtwAppointment) -> tuple[str, str] | None:
    if not c.names:
        return None
    if a.holder_user_id:
        u = c.db.get(User, a.holder_user_id)
        return (u.full_name_en, u.full_name_ar or u.full_name_en) if u else None
    if a.holder_worker_id:
        w = c.db.get(Worker, a.holder_worker_id)
        return (w.full_name_en, w.full_name_ar) if w else None
    return None


def expiring(
    db: Session,
    p: Principal,
    project: Project,
    day: date,
    horizon: date,
    include_overdue: bool,
) -> list[ExpiringItem]:
    """§8.2 kinds (empty without capability 103)."""
    from app.services.ptw import facts as facts_mod  # noqa: PLC0415
    from app.services.ptw import gas, isolations, lifecycle  # noqa: PLC0415

    c = _Ctx(db, p, project, day)
    if c.grant is None:
        return []
    pid = project.id
    lo = date.min if include_overdue else day
    out: list[ExpiringItem] = []

    def keep(d: date | None) -> bool:
        return d is not None and lo <= d <= horizon

    def ld(at: datetime) -> date:
        return acommon.local_day(at)

    permits = [
        x
        for x in db.scalars(
            select(Permit)
            .where(Permit.project_id == pid, Permit.status.in_([S.approved, *PERMIT_LIVE]))
            .order_by(Permit.permit_no)
        )
        if c.permit_ok(x)
    ]
    for x in permits:
        if keep(ld(x.valid_to_at)):
            out.append(
                _item(
                    c,
                    K.ptw_valid_to,
                    EntityType.permit,
                    x.id,
                    x.permit_no,
                    (
                        f"Permit valid to {acommon.local(x.valid_to_at).strftime('%H:%M')}: {x.title}",
                        f"صلاحية التصريح حتى {acommon.local(x.valid_to_at).strftime('%H:%M')}: {x.title}",
                    ),
                    ld(x.valid_to_at),
                    x.engagement_id,
                    x.valid_to_at,
                )
            )
        fw = lifecycle.fire_watch_until(x)
        if fw is not None and keep(ld(fw)) and (include_overdue or fw >= c.at):
            out.append(
                _item(
                    c,
                    K.fire_watch_end,
                    EntityType.permit,
                    x.id,
                    x.permit_no,
                    ("Fire watch ends", "انتهاء مراقبة الحريق"),
                    ld(fw),
                    x.engagement_id,
                    fw,
                )
            )
        if x.status != S.active:
            continue
        sh = lifecycle.current_shift(db, x)
        if sh is not None and sh.ended_at is None and keep(ld(sh.planned_end_at)):
            out.append(
                _item(
                    c,
                    K.ptw_shift_end,
                    EntityType.permit,
                    x.id,
                    x.permit_no,
                    (f"Shift {sh.shift_no} ends", f"انتهاء النوبة {sh.shift_no}"),
                    ld(sh.planned_end_at),
                    x.engagement_id,
                    sh.planned_end_at,
                )
            )
        f = facts_mod.compute(db, x)
        if f.gas_required and f.interval:
            st = gas.state(db, x, f.interval, True, c.at)
            if st.next_due_at is not None and keep(ld(st.next_due_at)):
                out.append(
                    _item(
                        c,
                        K.gas_retest_due,
                        EntityType.permit,
                        x.id,
                        x.permit_no,
                        ("Gas re-test due", "إعادة اختبار الغاز مستحقة"),
                        ld(st.next_due_at),
                        x.engagement_id,
                        st.next_due_at,
                    )
                )
    for d in db.scalars(
        select(GasDetector).where(
            GasDetector.project_id == pid,
            GasDetector.status != DetectorStatus.retired,
            GasDetector.calibration_due_on <= horizon,
        )
    ):
        if keep(d.calibration_due_on) and c.ok(d.engagement_id):
            out.append(
                _item(
                    c,
                    K.gas_detector_calibration_due,
                    EntityType.gas_detector,
                    d.id,
                    d.detector_no,
                    (f"Calibration due: {d.make_model}", f"معايرة مستحقة: {d.make_model}"),
                    d.calibration_due_on,
                    d.engagement_id,
                )
            )
    restricted = c.grant.engagement_ids is not None
    for a in db.scalars(
        select(PtwAppointment).where(
            PtwAppointment.project_id == pid,
            PtwAppointment.status == AppointmentStatus.active,
            PtwAppointment.valid_to <= horizon,
        )
    ):
        if not keep(a.valid_to):
            continue
        if restricted and a.holder_worker_id is None:
            continue  # contractor scope: worker-held appointments only
        if (
            c.grant.site_ids is not None
            and a.site_ids
            and not set(a.site_ids) & set(c.grant.site_ids)
        ):
            continue
        h = _holder(c, a)
        fn = a.function.value
        title = (
            f"Appointment {fn} expires" + (f": {h[0]}" if h else ""),
            f"انتهاء تعيين {fn}" + (f": {h[1]}" if h else ""),
        )
        out.append(
            _item(
                c,
                K.ptw_appointment_expiry,
                EntityType.ptw_appointment,
                a.id,
                a.appointment_no,
                title,
                a.valid_to,
                None,
            )
        )
    for iso in db.scalars(
        select(IsolationCertificate).where(
            IsolationCertificate.project_id == pid,
            IsolationCertificate.status.in_(list(isolations.OPEN_STATUSES)),
        )
    ):
        due = isolations.review_due_at(db, iso)
        if due is not None and keep(ld(due)) and c.ok(iso.engagement_id):
            out.append(
                _item(
                    c,
                    K.isolation_review_due,
                    EntityType.isolation_certificate,
                    iso.id,
                    iso.iso_no,
                    ("Long-term isolation weekly review", "المراجعة الأسبوعية للعزل طويل الأمد"),
                    ld(due),
                    iso.engagement_id,
                )
            )
    for j in db.scalars(
        select(Jsa).where(
            Jsa.project_id == pid,
            Jsa.is_template.is_(True),
            Jsa.status == JsaStatus.approved,
            Jsa.review_due_on.is_not(None),
            Jsa.review_due_on <= horizon,
        )
    ):
        if keep(j.review_due_on) and (j.engagement_id is None or c.ok(j.engagement_id)):
            assert j.review_due_on is not None  # noqa: S101
            out.append(
                _item(
                    c,
                    K.jsa_template_review_due,
                    EntityType.jsa,
                    j.id,
                    j.jsa_no,
                    (
                        f"JSA template review: {j.title_en}",
                        f"مراجعة قالب تحليل السلامة: {j.title_ar or j.title_en}",
                    ),
                    j.review_due_on,
                    j.engagement_id,
                )
            )
    return out


Adder = Callable[..., None]


def action_items(
    db: Session,
    p: Principal,
    project: Project,
    day: date,
    engs: frozenset[uuid.UUID] | None,
    sites: frozenset[uuid.UUID] | None,
    zones: frozenset[uuid.UUID] | None,
    add: Adder,
    link: Callable[[str, str, dict[str, Any]], object],
    flt: dict[str, list[str]],
) -> None:
    """Appends the §8.3 entries via the dashboard's ``add(key, count, severity, link, by)``."""
    from app.services.ptw import audits, common, gas, isolations  # noqa: PLC0415

    c = _Ctx(db, p, project, day)
    if c.grant is None:
        return
    pid = project.id
    base = f"/projects/{pid}"
    at = c.at
    pflt = {k: v for k, v in flt.items() if k == "engagement_id"}
    if "site_id" in flt and len(flt["site_id"]) == 1:
        pflt["site_id"] = flt["site_id"]

    def ok(
        eng: uuid.UUID | None, s: list[uuid.UUID] | None = None, z: list[uuid.UUID] | None = None
    ) -> bool:
        if engs is not None and (eng is None or eng not in engs):
            return False
        if sites is not None and s is not None and not set(s) & sites:
            return False
        if zones is not None and z is not None and not set(z) & zones:
            return False
        return c.ok(eng, s)

    def pok(x: Permit | None) -> bool:
        return x is not None and ok(x.engagement_id, [x.site_id], list(x.zone_ids or []))

    def by_status(*st: PermitStatus) -> list[Permit]:
        return [
            x
            for x in db.scalars(
                select(Permit).where(Permit.project_id == pid, Permit.status.in_(list(st)))
            )
            if pok(x)
        ]

    x: Permit | None = None
    permits_link = f"{base}/permits"
    # 1. requested > 4 h not reviewed
    req: Counter[uuid.UUID | None] = Counter(
        x.engagement_id
        for x in by_status(S.requested)
        if x.requested_at and at - x.requested_at >= timedelta(hours=4)
    )
    add(A.permits_requested_unreviewed, sum(req.values()), Severity.warning,
        link("permits", permits_link, {"status": [S.requested.value], **pflt}), req)  # fmt: skip
    # 2. approved not issued at window start + 60 min
    ni: Counter[uuid.UUID | None] = Counter()
    for x in by_status(S.approved):
        inst = common.current_instance(x, at)
        if inst is not None and at >= inst[0] + timedelta(minutes=60):
            ni[x.engagement_id] += 1
    add(A.permits_approved_not_issued, sum(ni.values()), Severity.warning,
        link("permits", permits_link, {"status": [S.approved.value], **pflt}), ni)  # fmt: skip
    # 3. non-routine suspended
    susp: Counter[uuid.UUID | None] = Counter()
    for x in by_status(S.suspended):
        sp = db.scalars(
            select(PermitSuspension)
            .where(PermitSuspension.permit_id == x.id, PermitSuspension.resumed_at.is_(None))
            .order_by(PermitSuspension.suspended_at.desc())
        ).first()
        if sp is None or not sp.routine:
            susp[x.engagement_id] += 1
    add(A.permits_suspended_non_routine, sum(susp.values()), Severity.critical,
        link("permit_suspensions", f"{base}/permit-suspensions", {"open_only": "true", **{k: v for k, v in pflt.items() if k == "engagement_id"}}), susp)  # fmt: skip
    # 4. shift lapses today
    start = acommon.local_midnight_utc(day)
    lapses: Counter[uuid.UUID | None] = Counter()
    for sh in db.scalars(
        select(PermitShift).where(
            PermitShift.project_id == pid,
            PermitShift.end_type == ShiftEndType.lapsed,
            PermitShift.ended_at >= start,
            PermitShift.ended_at < start + timedelta(days=1),
        )
    ):
        x = db.get(Permit, sh.permit_id)
        if x is not None and pok(x):
            lapses[x.engagement_id] += 1
    add(A.shift_lapses_today, sum(lapses.values()), Severity.warning, None, lapses)
    # 5. expired with post-expiry check pending
    pe: Counter[uuid.UUID | None] = Counter(
        x.engagement_id for x in by_status(S.expired) if x.post_expiry_check is None
    )
    add(A.post_expiry_checks_pending, sum(pe.values()), Severity.critical,
        link("permits", permits_link, {"status": [S.expired.value], **pflt}), pe)  # fmt: skip
    # 6. gas tests failed (24 h)
    since = at - timedelta(hours=24)
    gf: Counter[uuid.UUID | None] = Counter()
    for t in db.scalars(
        select(GasTest).where(
            GasTest.project_id == pid,
            GasTest.result == GasTestResult.fail,
            GasTest.superseded.is_(False),
            GasTest.tested_at >= since,
        )
    ):
        x = db.get(Permit, t.permit_id)
        if pok(x):
            assert x is not None  # noqa: S101
            gf[x.engagement_id] += 1
    add(A.gas_tests_failed_24h, sum(gf.values()), Severity.critical,
        link("gas_tests", f"{base}/gas-tests", {"result": GasTestResult.fail.value, "date_from": acommon.local_day(since).isoformat()}), gf)  # fmt: skip
    # 7. open SIMOPS conflicts with a permit starting within 24 h (or already live)
    soon = at + timedelta(hours=24)
    sim: Counter[uuid.UUID | None] = Counter()
    for k in db.scalars(
        select(SimopsConflict).where(
            SimopsConflict.project_id == pid, SimopsConflict.status == SimopsConflictStatus.open
        )
    ):
        pair = [db.get(Permit, k.permit_a_id), db.get(Permit, k.permit_b_id)]
        visible = [x for x in pair if x is not None and pok(x)]
        if not visible:
            continue
        starting = False
        for x in pair:
            if x is None or x.status in (S.closed, S.cancelled, S.expired):
                continue
            inst = common.current_instance(x, at) or common.next_instance(x, at)
            if inst is not None and inst[0] <= soon:
                starting = True
        if starting:
            sim[visible[0].engagement_id] += 1
    add(A.simops_open_starting_24h, sum(sim.values()), Severity.critical,
        link("simops_conflicts", f"{base}/simops-conflicts", {"status": [SimopsConflictStatus.open.value]}), sim)  # fmt: skip
    # 8. critical findings whose CA is not In Progress (none, or still Open)
    crit: Counter[uuid.UUID | None] = Counter()
    for a in db.scalars(
        select(PtwAudit).where(
            PtwAudit.project_id == pid,
            PtwAudit.critical_count > 0,
            PtwAudit.status != PtwAuditStatus.draft,
        )
    ):
        if not ok(a.engagement_id, [a.site_id], [a.zone_id] if a.zone_id else None):
            continue
        links, missing = audits.match_cas(db, a)
        crit_codes = {
            str(i.get("code"))
            for i in a.items or []
            if i.get("severity") == "critical" and i.get("answer") == "non_compliant"
        }
        n = len([m for m in missing if m in crit_codes])
        for ca_id, code in links.items():
            if code in crit_codes:
                ca = db.get(CorrectiveAction, ca_id)
                if ca is not None and ca.status == CaStatus.open:
                    n += 1
        if n:
            crit[a.engagement_id] += n
    add(A.ptw_critical_findings_ca_not_started, sum(crit.values()), Severity.critical,
        link("ptw_audits", f"{base}/ptw-audits", {"status": [PtwAuditStatus.completed.value, PtwAuditStatus.locked.value], **{k: v for k, v in pflt.items() if k == "engagement_id"}}), crit)  # fmt: skip
    # 9. audits behind plan this week (project level; HSE scope only)
    if c.grant.engagement_ids is None:
        bp = audits.behind_plan(db, pid, at)
        add(A.ptw_audits_behind_plan, 1 if bp else 0, Severity.warning,
            link("ptw_audits", f"{base}/ptw-audits", {"audit_type": ["field"], "date_from": common_week_start(db, pid, day).isoformat()}), None)  # fmt: skip
    # 10. orphan isolations
    orph: Counter[uuid.UUID | None] = Counter()
    for iso in db.scalars(
        select(IsolationCertificate).where(
            IsolationCertificate.project_id == pid,
            IsolationCertificate.status.in_(list(isolations.OPEN_STATUSES)),
        )
    ):
        if ok(iso.engagement_id) and isolations.is_orphan(db, iso, at):
            orph[iso.engagement_id] += 1
    add(A.orphan_isolations, sum(orph.values()), Severity.warning,
        link("isolations", f"{base}/isolations", {"status": sorted(s.value for s in isolations.OPEN_STATUSES)}), orph)  # fmt: skip
    # 11. quarantined detectors still listed on live permits
    qd: Counter[uuid.UUID | None] = Counter()
    for d in db.scalars(
        select(GasDetector).where(
            GasDetector.project_id == pid, GasDetector.status == DetectorStatus.quarantined
        )
    ):
        if ok(d.engagement_id) and gas._detector_permits(db, d):
            qd[d.engagement_id] += 1
    add(A.quarantined_detectors_on_live_permits, sum(qd.values()), Severity.critical,
        link("gas_detectors", f"{base}/gas-detectors", {"status": [DetectorStatus.quarantined.value]}), qd)  # fmt: skip
    # 12. active midday-ban exemptions
    mx: Counter[uuid.UUID | None] = Counter()
    for e in db.scalars(
        select(PermitExemption).where(
            PermitExemption.project_id == pid,
            PermitExemption.kind == ExemptionKind.midday_ban,
            PermitExemption.status == ExemptionStatus.granted,
        )
    ):
        if (e.valid_from and e.valid_from > day) or (e.valid_to and e.valid_to < day):
            continue
        x = db.get(Permit, e.permit_id)
        if pok(x) and x is not None and x.status in (S.approved, *PERMIT_LIVE):
            mx[x.engagement_id] += 1
    add(A.midday_exemptions_active, sum(mx.values()), Severity.info, None, mx)
    # 13. lock cuts (7 days)
    cuts: Counter[uuid.UUID | None] = Counter()
    for ev in db.scalars(
        select(PersonalLockEvent).where(
            PersonalLockEvent.project_id == pid,
            PersonalLockEvent.removed_by == PersonalLockRemoval.cut,
            PersonalLockEvent.removed_at >= at - timedelta(days=7),
        )
    ):
        eng: uuid.UUID | None = None
        x = db.get(Permit, ev.permit_id) if ev.permit_id else None
        if x is not None:
            eng = x.engagement_id
        elif ev.certificate_id:
            cert = db.get(IsolationCertificate, ev.certificate_id)
            eng = cert.engagement_id if cert else None
        if ok(eng):
            cuts[eng] += 1
    add(A.lock_cuts_7d, sum(cuts.values()), Severity.critical, None, cuts)


def common_week_start(db: Session, project_id: uuid.UUID, day: date) -> date:
    from app.core.enums import WeekStart  # noqa: PLC0415
    from app.kpi.periods import week_start  # noqa: PLC0415
    from app.models import ProjectSettings  # noqa: PLC0415

    ps = db.get(ProjectSettings, project_id)
    return week_start(day, ps.week_start if ps else WeekStart.sunday)
