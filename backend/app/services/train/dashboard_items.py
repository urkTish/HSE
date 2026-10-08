"""Phase 5 additions to the dashboard expiring-items panel (5-training §8.2) and action panel
(§8.3).

Both need capability 143 and are scoped by its grant (engagement / site scope) and the dashboard
filters. They appear only on projects where training hooks exist (a hook policy state of kind
training_course), so the Phase 1–4 panels are unchanged elsewhere. Titles carry worker_no,
course, record and session numbers only — never names, scores or failure details (P5-4).
Viewer/Client sees counts only (TK-5): its expiring items carry no ref, entity id or link.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, HookKind
from app.core.cert_enums import VerificationStatus
from app.core.config import API_PREFIX
from app.core.enums import Capability, EntityType
from app.core.hse_enums import ActionPanelItem, ExpiringItemKind, Severity
from app.core.train_enums import (
    RefresherPlanState,
    SessionStatus,
    TrainerAuthorisationStatus,
    TrainingRecordStatus,
)
from app.models import (
    Deployment,
    HookPolicyState,
    Project,
    TrainerAuthorisation,
    TrainingRecord,
    TrainingSession,
    Worker,
)
from app.schemas.dashboard import ExpiringItem
from app.services.hse_common import Refs
from app.services.permissions import Grant, Principal

K = ExpiringItemKind
A = ActionPanelItem
RS = TrainingRecordStatus
VS = VerificationStatus
LIVE = (RS.submitted, RS.accepted)
Adder = Callable[..., None]

LABELS: dict[ActionPanelItem, tuple[str, str]] = {
    A.training_records_awaiting_review: (
        "Training records awaiting review > 24 h",
        "سجلات تدريب بانتظار المراجعة > 24 ساعة",
    ),
    A.training_verifications_overdue: ("Training verifications overdue", "تحقق التدريب متأخر"),
    A.training_verification_failed_undecided: (
        "Training verification failed — no decision recorded",
        "فشل التحقق من التدريب دون قرار مسجل",
    ),
    A.training_unable_to_verify: (
        "Training records unable to verify",
        "سجلات تدريب تعذر التحقق منها",
    ),
    A.training_sessions_not_closed: (
        "Training sessions delivered and not closed after the deadline",
        "جلسات تدريب منفذة ولم تُغلق بعد الموعد",
    ),
    A.training_hook_gaps_on_live_work: (
        "Training gaps on hook codes for workers on live permits / WAPs",
        "نقص تدريب على رموز المتطلبات لعمال على تصاريح نشطة",
    ),
    A.training_expiring_7d_not_booked: (
        "Training expiring ≤ 7 days, not booked",
        "تدريب ينتهي خلال 7 أيام دون حجز",
    ),
    A.training_hook_block_soon_not_ready: (
        "Training hook block date ≤ 7 days with readiness < 100 %",
        "موعد حظر متطلبات التدريب خلال 7 أيام والجاهزية أقل من 100 %",
    ),
    A.training_sessions_not_allowed: (
        "Scheduled sessions whose trainer or provider no longer allows them",
        "جلسات مجدولة لم يعد مدربها أو جهتها مسموحاً",
    ),
    A.training_holders_not_linked: (
        "Appointment holders not linked to a worker record",
        "أصحاب تعيينات غير مرتبطين بسجل عامل",
    ),
}

_PATHS = {
    EntityType.training_record: "/training-records/{}",
    EntityType.trainer_authorisation: "/trainer-authorisations/{}",
    EntityType.training_session: "/training-sessions/{}",
}

KIND_TITLES: dict[ExpiringItemKind, tuple[str, str]] = {
    K.training_record_expiry: ("Training record expiry", "انتهاء سجل تدريب"),
    K.trainer_authorisation_expiry: ("Trainer authorisation expiry", "انتهاء تفويض مدرب"),
    K.training_verification_due: ("Training verification due", "موعد التحقق من التدريب"),
    K.training_session_close_due: ("Training session close due", "موعد إغلاق جلسة تدريب"),
}


def enabled(db: Session, project_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(HookPolicyState.id)
            .where(
                HookPolicyState.project_id == project_id,
                HookPolicyState.kind == HookKind.training_course,
            )
            .limit(1)
        )
        is not None
    )


class _Ctx:
    def __init__(self, db: Session, p: Principal, project: Project, day: date) -> None:
        self.db = db
        self.p = p
        self.project = project
        self.day = day
        self.grant: Grant | None = p.grant(project.id, Capability.training_kpi_view)
        scope = p.projects.get(project.id)
        self.counts_only = bool(scope and scope.read_only and not p.is_manager)
        self.refs = Refs(db)
        self._mob: dict[uuid.UUID, Deployment] | None = None

    def ok(self, eng: uuid.UUID | None, sites: list[uuid.UUID] | None = None) -> bool:
        g = self.grant
        if g is None:
            return False
        if g.engagement_ids is not None and (eng is None or eng not in g.engagement_ids):
            return False
        return g.site_ids is None or sites is None or bool(set(sites) & set(g.site_ids))

    def mobilised(self, worker_id: uuid.UUID) -> Deployment | None:
        if self._mob is None:
            self._mob = {
                d.worker_id: d
                for d in self.db.scalars(
                    select(Deployment).where(
                        Deployment.project_id == self.project.id,
                        Deployment.status == DeploymentStatus.mobilised,
                    )
                )
            }
        return self._mob.get(worker_id)

    def item(
        self,
        kind: ExpiringItemKind,
        et: EntityType,
        eid: uuid.UUID,
        ref: str | None,
        title: tuple[str, str],
        due: date,
        eng: uuid.UUID | None,
    ) -> ExpiringItem:
        if self.counts_only:
            en, ar = KIND_TITLES[kind]
            return ExpiringItem(
                kind=kind, entity_type=et, entity_id=None, ref=None, title_en=en, title_ar=ar,
                due_date=due, days_left=(due - self.day).days, engagement=None, detail_path=None,
            )  # fmt: skip
        return ExpiringItem(
            kind=kind,
            entity_type=et,
            entity_id=eid,
            ref=ref,
            title_en=title[0],
            title_ar=title[1],
            due_date=due,
            days_left=(due - self.day).days,
            engagement=self.refs.eng(eng) if eng else None,
            detail_path=f"{API_PREFIX}{_PATHS[et].format(eid)}",
        )


def expiring(
    db: Session,
    p: Principal,
    project: Project,
    day: date,
    horizon: date,
    include_overdue: bool,
) -> list[ExpiringItem]:
    """§8.2 kinds (empty without capability 143 or before training hooks exist)."""
    from app.services.train import sessions  # noqa: PLC0415

    c = _Ctx(db, p, project, day)
    if c.grant is None or not enabled(db, project.id):
        return []
    pid = project.id
    lo = date.min if include_overdue else day
    out: list[ExpiringItem] = []

    def keep(d: date | None) -> bool:
        return d is not None and lo <= d <= horizon

    # training records of mobilised holders
    for r, wno in db.execute(
        select(TrainingRecord, Worker.worker_no)
        .join(Worker, Worker.id == TrainingRecord.worker_id)
        .join(Deployment, Deployment.worker_id == TrainingRecord.worker_id)
        .where(
            Deployment.project_id == pid,
            Deployment.status == DeploymentStatus.mobilised,
            TrainingRecord.status == RS.accepted,
            TrainingRecord.valid_until.is_not(None),
            TrainingRecord.valid_until <= horizon,
            TrainingRecord.valid_until >= lo,
        )
    ).all():
        if not keep(r.valid_until):
            continue
        dep = c.mobilised(r.worker_id)
        if dep is None or not c.ok(dep.engagement_id, list(dep.site_ids or [])):
            continue
        assert r.valid_until is not None  # noqa: S101
        out.append(
            c.item(
                K.training_record_expiry, EntityType.training_record, r.id, r.record_no,
                (f"{wno}: {r.course_code} {r.record_no} valid until {r.valid_until}",
                 f"{wno}: {r.course_code} {r.record_no} ساري حتى {r.valid_until}"),
                r.valid_until, dep.engagement_id,
            )
        )  # fmt: skip
    # trainer authorisations (project-level; full-scope grants only)
    if c.grant.engagement_ids is None:
        for ta in db.scalars(
            select(TrainerAuthorisation).where(
                TrainerAuthorisation.project_id == pid,
                TrainerAuthorisation.status == TrainerAuthorisationStatus.active,
                TrainerAuthorisation.valid_to <= horizon,
            )
        ):
            if not keep(ta.valid_to):
                continue
            out.append(
                c.item(
                    K.trainer_authorisation_expiry, EntityType.trainer_authorisation, ta.id,
                    ta.authorisation_no,
                    (f"Trainer authorisation {ta.authorisation_no} valid until {ta.valid_to}",
                     f"تفويض المدرب {ta.authorisation_no} ساري حتى {ta.valid_to}"),
                    ta.valid_to, None,
                )
            )  # fmt: skip
        for s in db.scalars(
            select(TrainingSession).where(
                TrainingSession.project_id == pid,
                TrainingSession.status == SessionStatus.delivered,
            )
        ):
            due = sessions._close_due(db, s)
            if not keep(due):
                continue
            assert due is not None  # noqa: S101
            out.append(
                c.item(
                    K.training_session_close_due, EntityType.training_session, s.id,
                    s.session_no,
                    (f"Session {s.session_no} ({s.course_code}): close by {due}",
                     f"الجلسة {s.session_no} ({s.course_code}): الإغلاق قبل {due}"),
                    due, None,
                )
            )  # fmt: skip
    # verification due
    for r in db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.project_id == pid,
            TrainingRecord.status.in_(LIVE),
            TrainingRecord.verification_status.in_([VS.not_verified, VS.unable_to_verify]),
            TrainingRecord.verification_due_on.is_not(None),
            TrainingRecord.verification_due_on <= horizon,
        )
    ):
        if not keep(r.verification_due_on) or not c.ok(r.engagement_id):
            continue
        assert r.verification_due_on is not None  # noqa: S101
        out.append(
            c.item(
                K.training_verification_due, EntityType.training_record, r.id, r.record_no,
                (f"{r.record_no} ({r.course_code}): verification due {r.verification_due_on}",
                 f"{r.record_no} ({r.course_code}): التحقق مستحق {r.verification_due_on}"),
                r.verification_due_on, r.engagement_id,
            )
        )  # fmt: skip
    return out


def action_items(
    db: Session,
    p: Principal,
    project: Project,
    day: date,
    engs: frozenset[uuid.UUID] | None,
    sites: frozenset[uuid.UUID] | None,
    add: Adder,
    link: Callable[[str, str, dict[str, Any]], object],
    flt: dict[str, list[str]],
    facts: Any = None,
) -> None:
    """Appends the §8.3 entries via the dashboard's ``add(key, count, severity, link, by)``.
    ``facts`` (the KPI request's Facts) shares the requirement evaluation with the KPI cache."""
    from app.core.clock import now  # noqa: PLC0415
    from app.services.train import gaps, sessions  # noqa: PLC0415

    c = _Ctx(db, p, project, day)
    if c.grant is None or not enabled(db, project.id):
        return
    pid = project.id
    base = f"/projects/{pid}"
    eflt = {k: v for k, v in flt.items() if k == "engagement_id"}

    def ok(eng: uuid.UUID | None) -> bool:
        if engs is not None and (eng is None or eng not in engs):
            return False
        return c.ok(eng)

    recs = [
        r
        for r in db.scalars(
            select(TrainingRecord).where(
                TrainingRecord.project_id == pid, TrainingRecord.status.in_(LIVE)
            )
        )
        if ok(r.engagement_id)
    ]
    rlink = f"{base}/training-records"
    at = now()

    def counted(pred: Callable[[TrainingRecord], bool]) -> Counter[uuid.UUID | None]:
        return Counter(r.engagement_id for r in recs if pred(r))

    review = counted(
        lambda r: (
            r.status == RS.submitted
            and r.submitted_at is not None
            and at - r.submitted_at > timedelta(hours=24)
        )
    )
    add(A.training_records_awaiting_review, sum(review.values()), Severity.warning,
        link("training_records", rlink, {"awaiting_review": "true", **eflt}), review)  # fmt: skip
    overdue = counted(
        lambda r: (
            r.verification_status == VS.not_verified
            and r.verification_due_on is not None
            and r.verification_due_on < day
        )
    )
    add(A.training_verifications_overdue, sum(overdue.values()), Severity.warning,
        link("training_records", rlink, {"verification_overdue": "true", **eflt}),
        overdue)  # fmt: skip
    failed = counted(lambda r: r.verification_status == VS.failed)
    add(A.training_verification_failed_undecided, sum(failed.values()), Severity.critical,
        link("training_records", rlink, {"verification_status": "failed", **eflt}),
        failed)  # fmt: skip
    unable = counted(lambda r: r.verification_status == VS.unable_to_verify)
    add(A.training_unable_to_verify, sum(unable.values()), Severity.warning,
        link("training_records", rlink, {"verification_status": "unable_to_verify", **eflt}),
        unable)  # fmt: skip
    # sessions
    late = 0
    not_allowed = 0
    for s in db.scalars(
        select(TrainingSession).where(
            TrainingSession.project_id == pid,
            TrainingSession.status.in_([SessionStatus.delivered, SessionStatus.scheduled]),
        )
    ):
        if s.status == SessionStatus.delivered:
            due = sessions._close_due(db, s)
            if due is not None and day > due:
                late += 1
        elif sessions.blockers(db, s):
            not_allowed += 1
    slink = f"{base}/training-sessions"
    add(A.training_sessions_not_closed, late, Severity.warning,
        link("training_sessions", slink, {"close_overdue": "true"}))  # fmt: skip
    add(A.training_sessions_not_allowed, not_allowed, Severity.warning,
        link("training_sessions", slink, {"status": "scheduled"}))  # fmt: skip
    # requirement-based items (one evaluation)
    from app.services.train import requirements as reqs  # noqa: PLC0415

    tf = facts.train if facts is not None else None
    if tf is not None and pid in tf.pids:
        pe = tf.with_db(db).peval_full(pid, day)
    else:
        pe = reqs.evaluate_project(db, pid, day, bookings=True, enforcement=True)
    hooked = [
        r
        for r in pe.reqs
        # GP-7: enforcement lines (crew roles, appointments) count here though not in KPIs
        if r.state.value == "gap" and r.hook_code and ok(r.dep.engagement_id)
    ]
    hooked = list({(r.dep.id, r.key): r for r in hooked}.values())
    permits, waps = gaps.live_work(db, pid, {r.dep.worker_id for r in hooked})
    live = Counter(
        r.dep.engagement_id
        for r in hooked
        if permits.get(r.dep.worker_id) or waps.get(r.dep.worker_id)
    )
    add(A.training_hook_gaps_on_live_work, sum(live.values()), Severity.critical,
        link("training_gaps", f"{base}/training-gaps",
             {"on_live_work": "true", "hook_code": "true", **eflt}), live)  # fmt: skip
    seen: set[uuid.UUID] = set()
    soon: Counter[uuid.UUID | None] = Counter()
    for r in pe.reqs:
        rec = r.record
        if rec is None or rec.id in seen or r.valid_until is None:
            continue
        if not (day <= r.valid_until <= day + timedelta(days=7)):
            continue
        if gaps.plan_state(r) != RefresherPlanState.not_booked or not ok(r.dep.engagement_id):
            continue
        seen.add(rec.id)
        soon[r.dep.engagement_id] += 1
    add(A.training_expiring_7d_not_booked, sum(soon.values()), Severity.warning,
        link("refresher_plan", f"{base}/refresher-plan",
             {"state": "not_booked", "due_within_days": "7", **eflt}), soon)  # fmt: skip
    # hook block date ≤ 7 days with training readiness < 100 % (HK5-9)
    from app.core.cert_enums import HookStage  # noqa: PLC0415

    not_ready = 0
    st = db.scalar(
        select(HookPolicyState).where(
            HookPolicyState.project_id == pid, HookPolicyState.kind == HookKind.training_course
        )
    )
    if st is not None and st.stage != HookStage.block and not c.counts_only:
        due_soon = [
            w for w, done in ((st.critical_block_from, st.critical_switched_at),
                              (st.general_block_from, st.general_switched_at))
            if w is not None and done is None and day <= w <= day + timedelta(days=7)
        ]  # fmt: skip
        if due_soon:
            not_ready = soon_not_ready(db, pe, st, set(due_soon))
    add(A.training_hook_block_soon_not_ready, not_ready, Severity.warning,
        link("hook_readiness", f"{base}/hook-readiness", {"kind": "training_course"}))  # fmt: skip
    # appointment holders without a linked worker (HK5-7: a configuration error)
    add(A.training_holders_not_linked, holders_not_linked(db, pid, day), Severity.warning,
        link("ptw_appointments", f"{base}/ptw-appointments", {}))  # fmt: skip


def soon_not_ready(db: Session, pe: Any, st: HookPolicyState, soon: set[date]) -> int:
    """Codes whose block date is in ``soon`` with readiness < 100 %: HK5-9 readiness computed on
    the panel's own requirement evaluation (Mobilised deployments, enforcement lines)."""
    from app.services.cert import policy  # noqa: PLC0415

    cfg = policy.cfg(db, st.project_id, HookKind.training_course)
    good = ("met", "expiring", "exempt")
    per_code: dict[str, dict[uuid.UUID, bool]] = {}
    for r in pe.reqs:
        if not r.hook_code:
            continue
        for code in r.codes:
            if code in pe.f.hook_codes:
                cur = per_code.setdefault(code, {})
                cur[r.dep.worker_id] = cur.get(r.dep.worker_id, False) or r.state.value in good
    n = 0
    for code in policy.codes_of(db, HookKind.training_course):
        subj = per_code.get(code, {})
        if subj and policy.block_from(st, cfg, code) in soon and not all(subj.values()):
            n += 1
    return n


def holders_not_linked(db: Session, project_id: uuid.UUID, day: date) -> int:
    """Active appointments of a function that a training line hooks (`appointment:<function>`)
    whose holder is a user with no linked worker record."""
    from app.core.ptw_enums import AppointmentStatus  # noqa: PLC0415
    from app.core.train_enums import MatrixAppliesTo  # noqa: PLC0415
    from app.models import PtwAppointment  # noqa: PLC0415
    from app.services.train import requirements as reqs  # noqa: PLC0415

    functions = {
        v
        for ln in reqs.lines_at(db, project_id, day)
        if ln.row.applies_to_kind == MatrixAppliesTo.appointment_function
        for v in ln.row.applies_to_values or []
    }
    if not functions:
        return 0
    linked = set(db.scalars(select(Worker.user_id).where(Worker.user_id.is_not(None))))
    n = 0
    for a in db.scalars(
        select(PtwAppointment).where(
            PtwAppointment.project_id == project_id,
            PtwAppointment.status == AppointmentStatus.active,
            PtwAppointment.valid_from <= day,
            PtwAppointment.valid_to >= day,
        )
    ):
        if a.function.value not in functions or a.holder_worker_id is not None:
            continue
        if a.holder_user_id is not None and a.holder_user_id not in linked:
            n += 1
    return n
