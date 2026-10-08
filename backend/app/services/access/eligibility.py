"""Eligibility function E(worker, zone, at, context) (spec 2-access-permits ZP-3, ZP-4, HK-1…HK-5,
WK-7, IN-10, GC-4) and the hook evaluation used by gates, WAPs and Phase 3 (HK-6)."""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    CrewMemberStatus,
    DeploymentStatus,
    EligibilityContext,
    GateDirection,
    GateReasonCode,
    HookKind,
    HookPolicy,
    HookProviderStatus,
    HookSubjectType,
    InductionResult,
    InductionStatus,
    InductionType,
    RequirementKind,
    RequirementStatus,
    SuspendedContractorGateMode,
    ValidityStatus,
    WapStatus,
    WorkerPersonType,
    WorkerStatus,
)
from app.core.cert_enums import HookReasonCode
from app.core.clock import now
from app.core.enums import ContractorStatus
from app.models import (
    AccessSettings,
    Adp,
    AirportPass,
    Contractor,
    Deployment,
    GateCheck,
    InductionCourse,
    InductionRecord,
    ProjectEngagement,
    Wap,
    WapCrew,
    Worker,
    Zone,
)
from app.schemas.access_common import HookCondition
from app.schemas.inductions import EligibilityItem, EligibilityResult
from app.services.access import common, hooks, lifecycle, profiles, windows
from app.services.access.reasons import GATE_TEXT, hook_message
from app.services.hse_common import Refs

G = GateReasonCode
PHASE4_KINDS = frozenset({HookKind.personnel_certificate, HookKind.equipment_certificate})
RS = RequirementStatus
RK = RequirementKind


@dataclass
class Item:
    kind: RequirementKind
    code: str | None
    status: RequirementStatus
    reason: GateReasonCode | None = None
    valid_until: date | None = None
    ref: str | None = None
    hook_kind: HookKind | None = None
    message: tuple[str, str] | None = None
    # v1.2 (4-third-party-cert HK4-3/HK4-4/HK4-8)
    hard_stop: bool = False
    hook_reason: HookReasonCode | None = None
    conditions: tuple[dict[str, Any], ...] = ()
    swl_t: Decimal | None = None

    def to_schema(self) -> EligibilityItem:
        en, ar = self.message or (GATE_TEXT[self.reason] if self.reason else (None, None))
        return EligibilityItem(
            kind=self.kind,
            code=self.code,
            hook_kind=self.hook_kind,
            status=self.status,
            valid_until=self.valid_until,
            ref=self.ref,
            reason_code=self.reason,
            message_en=en,
            message_ar=ar,
            hard_stop=self.hard_stop,
            hook_reason_code=self.hook_reason,
            conditions=[HookCondition(**c) for c in self.conditions],
            swl_t=self.swl_t,
        )


@dataclass
class Evaluation:
    worker: Worker
    zone: Zone
    at: datetime
    context: EligibilityContext
    items: list[Item] = field(default_factory=list)
    deployment: Deployment | None = None
    pass_: AirportPass | None = None
    escort_required: bool = False
    wap: Wap | None = None
    wap_window: windows.Instance | None = None

    @property
    def deny(self) -> list[GateReasonCode]:
        return [
            i.reason or G.HOOK_NOT_MET
            for i in self.items
            if i.status in (RS.not_met, RS.not_evaluated)
        ]

    @property
    def warn(self) -> list[GateReasonCode]:
        return [i.reason for i in self.items if i.status in (RS.warn, RS.expiring) and i.reason]

    @property
    def eligible(self) -> bool:
        return not self.deny

    def deny_except_escort(self) -> list[GateReasonCode]:
        return [r for r in self.deny if r != G.ESCORT_REQUIRED]


# ---- small lookups -------------------------------------------------------------------------------


def current_deployment(
    db: Session, worker_id: uuid.UUID, project_id: uuid.UUID
) -> Deployment | None:
    return db.scalar(
        select(Deployment)
        .where(
            Deployment.worker_id == worker_id,
            Deployment.project_id == project_id,
            Deployment.status != DeploymentStatus.demobilised,
        )
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )


def contractor_of(db: Session, engagement_id: uuid.UUID | None) -> Contractor | None:
    if engagement_id is None:
        return None
    e = db.get(ProjectEngagement, engagement_id)
    return e.contractor if e else None


def hook_item(
    db: Session,
    subject_type: HookSubjectType,
    subject_id: uuid.UUID,
    kind: HookKind,
    code: str,
    at: datetime,
    s: AccessSettings,
    ctx: hooks.HookContext | None = None,
) -> Item:
    """HK-3/HK-4. v1.2: kinds answered by Phase 4 on the project (HK4-1) go to the Phase 4
    provider with the context (HK4-8) and the project's stage (HK4-4)."""
    if kind in PHASE4_KINDS:
        from app.services.cert import policy as cpolicy  # noqa: PLC0415

        st = cpolicy.active_state(db, s.project_id, kind, common.local_day(at))
        if st is not None:
            return phase4_hook_item(db, subject_type, subject_id, kind, code, at, s, ctx, st)
    policy = HookPolicy((s.hook_policy or {}).get(kind.value, HookPolicy.warn.value))
    provider = hooks.provider_for(kind)
    if provider is None:
        if policy == HookPolicy.warn:
            return Item(
                RK.hook, code, RS.warn, G.HOOK_NOT_AVAILABLE, hook_kind=kind,
                message=hook_message(kind),
            )  # fmt: skip
        return Item(
            RK.hook, code, RS.not_evaluated, G.HOOK_NOT_MET, hook_kind=kind,
            message=hook_message(kind),
        )  # fmt: skip
    res = provider.check(subject_type, subject_id, kind, code, at)
    if res.status == HookProviderStatus.met:
        return Item(RK.hook, code, RS.met, None, res.valid_until, res.ref, kind)
    if res.status == HookProviderStatus.expiring:
        return Item(RK.hook, code, RS.expiring, G.EXPIRING_7D, res.valid_until, res.ref, kind)
    return Item(RK.hook, code, RS.not_met, G.HOOK_NOT_MET, res.valid_until, res.ref, kind)


def phase4_hook_item(
    db: Session,
    subject_type: HookSubjectType,
    subject_id: uuid.UUID,
    kind: HookKind,
    code: str,
    at: datetime,
    s: AccessSettings,
    ctx: hooks.HookContext | None,
    st: Any,
) -> Item:
    """HK4-3/HK4-4: hard stops block in every stage; in `transition` a not_met becomes warn
    HOOK_NOT_MET_WARN with the detail reason; `block` passes not_met through."""
    from app.core.cert_enums import HookCodePolicy  # noqa: PLC0415
    from app.services.cert import policy as cpolicy  # noqa: PLC0415
    from app.services.cert import providers  # noqa: PLC0415
    from app.services.cert import reference as cref  # noqa: PLC0415
    from app.services.cert import settings as cset  # noqa: PLC0415

    if ctx is None:
        ctx = hooks.HookContext(project_id=s.project_id)
    cs = cset.get(db, s.project_id)
    if not cpolicy.implemented(db, kind, code):
        res = hooks.HookCheck(
            HookProviderStatus.not_met, reason_code=HookReasonCode.UNKNOWN_CODE.value
        )
    else:
        res = providers.check(db, subject_type, subject_id, kind, code, at, ctx, s.project_id)
    reason = HookReasonCode(res.reason_code) if res.reason_code else None
    detail = cref.REASON_TEXT.get(reason) if reason else None
    extra: dict[str, Any] = {
        "hook_kind": kind,
        "hard_stop": res.hard_stop,
        "hook_reason": reason,
        "conditions": res.conditions,
        "swl_t": res.swl_t,
    }

    def msg(g: GateReasonCode) -> tuple[str, str]:
        en, ar = GATE_TEXT[g]
        return (f"{en}: {detail[0]}", f"{ar}: {detail[1]}") if detail else (en, ar)

    if res.status == HookProviderStatus.met:
        return Item(
            RK.hook, code, RS.met, None, res.valid_until, res.ref,
            message=detail, **extra,
        )  # fmt: skip
    if res.status == HookProviderStatus.expiring:
        return Item(
            RK.hook, code, RS.expiring, G.EXPIRING_7D, res.valid_until, res.ref,
            message=msg(G.EXPIRING_7D), **extra,
        )  # fmt: skip
    blocked = res.hard_stop or cpolicy.code_policy(st, cs, code, at) == HookCodePolicy.block
    if blocked:
        return Item(
            RK.hook, code, RS.not_met, G.HOOK_NOT_MET, res.valid_until, res.ref,
            message=msg(G.HOOK_NOT_MET), **extra,
        )  # fmt: skip
    return Item(
        RK.hook, code, RS.warn, G.HOOK_NOT_MET_WARN, res.valid_until, res.ref,
        message=msg(G.HOOK_NOT_MET_WARN), **extra,
    )  # fmt: skip


def _expiring(until: date | None, d: date) -> bool:
    return until is not None and until <= d + timedelta(days=7)


# ---- inductions ----------------------------------------------------------------------------------


def _any_course(
    db: Session,
    worker_id: uuid.UUID,
    project_id: uuid.UUID,
    courses: dict[str, InductionCourse],
    kind: InductionType,
    at: datetime,
    s: AccessSettings,
) -> list[Item]:
    """GC-4 site gate / visitors: any Valid induction of an active course of that type
    (code GEN preferred); when none is valid, the preferred course's failure is reported."""
    cands = sorted(
        (c for c in courses.values() if c.induction_type == kind and c.active),
        key=lambda c: (c.code != "GEN", c.created_at),
    )
    if not cands:
        return [Item(RK.induction, "GEN" if kind == InductionType.general_site else None,
                     RS.not_met, G.INDUCTION_MISSING)]  # fmt: skip
    first: list[Item] | None = None
    for c in cands:
        res = induction_item(db, worker_id, project_id, c, c.code, at, s)
        if all(i.status != RS.not_met for i in res):
            return res
        first = first if first is not None else res
    return first or []


def induction_item(
    db: Session,
    worker_id: uuid.UUID,
    project_id: uuid.UUID,
    course: InductionCourse | None,
    code: str,
    at: datetime,
    s: AccessSettings,
) -> list[Item]:
    d = common.local_day(at)
    if course is None:
        return [Item(RK.induction, code, RS.not_met, G.INDUCTION_MISSING)]
    recs = list(
        db.scalars(
            select(InductionRecord)
            .where(
                InductionRecord.worker_id == worker_id,
                InductionRecord.course_id == course.id,
                InductionRecord.result == InductionResult.passed,
                InductionRecord.delivered_at <= at,
            )
            .order_by(InductionRecord.delivered_at.desc())
        )
    )
    for r in recs:
        until = lifecycle.induction_valid_until(r)
        live = r.status in (InductionStatus.valid, InductionStatus.superseded)
        if (
            r.status == InductionStatus.valid
            and r.valid_from
            and until
            and r.valid_from <= d <= until
        ):
            out: list[Item] = []
            if (
                course.induction_type == InductionType.general_site
                and s.reinduction_absence_days
                and _absent(db, worker_id, project_id, at, s.reinduction_absence_days, r)
            ):
                return [
                    Item(RK.induction, code, RS.not_met, G.INDUCTION_ABSENCE, until, r.induction_no)
                ]
            if _expiring(until, d):
                out.append(
                    Item(RK.induction, code, RS.expiring, G.EXPIRING_7D, until, r.induction_no)
                )
            else:
                out.append(Item(RK.induction, code, RS.met, None, until, r.induction_no))
            if r.language_mismatch:
                out.append(
                    Item(RK.induction, code, RS.warn, G.LANGUAGE_MISMATCH, until, r.induction_no)
                )
            return out
        if r.status == InductionStatus.suspended and until and d <= until:
            return [
                Item(RK.induction, code, RS.not_met, G.INDUCTION_SUSPENDED, until, r.induction_no)
            ]
        if live or r.status == InductionStatus.expired:
            return [
                Item(RK.induction, code, RS.not_met, G.INDUCTION_EXPIRED, until, r.induction_no)
            ]
    return [Item(RK.induction, code, RS.not_met, G.INDUCTION_MISSING)]  # fmt: skip


def _absent(
    db: Session,
    worker_id: uuid.UUID,
    project_id: uuid.UUID,
    at: datetime,
    days: int,
    rec: InductionRecord,
) -> bool:
    """IN-10: no `in` gate check on the project for `days` days (since the induction)."""
    since = at - timedelta(days=days)
    if rec.delivered_at >= since:
        return False
    last = db.scalar(
        select(func.max(GateCheck.occurred_at)).where(
            GateCheck.worker_id == worker_id,
            GateCheck.project_id == project_id,
            GateCheck.direction == GateDirection.in_,
        )
    )
    return last is None or last < since


# ---- passes / ADP --------------------------------------------------------------------------------


def pass_item(
    db: Session, worker_id: uuid.UUID, project_id: uuid.UUID, area: str, d: date
) -> tuple[Item, AirportPass | None]:
    passes = list(
        db.scalars(
            select(AirportPass)
            .where(AirportPass.worker_id == worker_id, AirportPass.project_id == project_id)
            .order_by(AirportPass.escorted, AirportPass.issued_on.desc())
        )
    )
    valid = [p for p in passes if lifecycle.live_valid(p, d)]
    for p in valid:
        if area in (p.area_codes or []):
            st = RS.expiring if _expiring(p.effective_valid_until, d) else RS.met
            return Item(
                RK.airport_pass, area, st, G.EXPIRING_7D if st == RS.expiring else None,
                p.effective_valid_until, p.pass_no,
            ), p  # fmt: skip
    if valid:
        return Item(RK.airport_pass, area, RS.not_met, G.PASS_AREA_NOT_COVERED), None
    if any(p.validity_status == ValidityStatus.suspended for p in passes):
        return Item(RK.airport_pass, area, RS.not_met, G.PASS_SUSPENDED), None
    if any(
        p.validity_status == ValidityStatus.expired
        or (p.validity_status == ValidityStatus.active and not lifecycle.live_valid(p, d))
        for p in passes
    ):
        return Item(RK.airport_pass, area, RS.not_met, G.PASS_EXPIRED), None
    return Item(RK.airport_pass, area, RS.not_met, G.PASS_MISSING), None


def adp_item(
    db: Session, worker_id: uuid.UUID, project_id: uuid.UUID, need: str | None, d: date
) -> tuple[Item, Adp | None]:
    adps = list(
        db.scalars(
            select(Adp).where(
                Adp.worker_id == worker_id,
                Adp.project_id == project_id,
                Adp.validity_status.in_([ValidityStatus.active, ValidityStatus.suspended]),
            )
        )
    )
    valid = [a for a in adps if lifecycle.live_valid(a, d)]
    for a in valid:
        if profiles.covers(a.category, need):
            st = RS.expiring if _expiring(a.effective_valid_until, d) else RS.met
            return Item(
                RK.adp, a.category.value, st, G.EXPIRING_7D if st == RS.expiring else None,
                a.effective_valid_until, a.adp_no,
            ), a  # fmt: skip
    if valid:
        return Item(RK.adp, need, RS.not_met, G.ADP_CATEGORY), None
    if any(a.validity_status == ValidityStatus.suspended for a in adps):
        return Item(RK.adp, need, RS.not_met, G.ADP_SUSPENDED), None
    return Item(RK.adp, need, RS.not_met, G.ADP_MISSING), None


# ---- WAP (step 7) --------------------------------------------------------------------------------


def wap_item(
    db: Session, worker_id: uuid.UUID, zone: Zone, at: datetime
) -> tuple[Item, Wap | None, windows.Instance | None]:
    rows = db.execute(
        select(Wap, WapCrew)
        .join(WapCrew, WapCrew.wap_id == Wap.id)
        .where(
            WapCrew.worker_id == worker_id,
            WapCrew.removed_at.is_(None),
            Wap.project_id == zone.project_id,
            Wap.revision_of_id.is_(None),
            Wap.zone_ids.contains([zone.id]),
        )
    ).all()
    return best_wap(rows, at, lambda c: c.status == CrewMemberStatus.excluded)


def best_wap(
    rows: Sequence[Any], at: datetime, excluded: Callable[[WapCrew], bool]
) -> tuple[Item, Wap | None, windows.Instance | None]:
    reasons: list[GateReasonCode] = []
    for wap, member in rows:
        if wap.status == WapStatus.active:
            inst = windows.current(windows.parse(wap.windows), wap.valid_from, wap.valid_to, at)
            if inst is None:
                reasons.append(G.WAP_OUTSIDE_WINDOW)
                continue
            if member is not None and excluded(member):
                reasons.append(G.CREW_EXCLUDED)
                continue
            return (
                Item(RK.work_area_permit, wap.wap_no, RS.met, None, wap.valid_to, wap.wap_no),
                wap,
                inst,
            )
        if wap.status == WapStatus.suspended:
            reasons.append(G.WAP_SUSPENDED)
        elif wap.status in (WapStatus.approved, WapStatus.submitted, WapStatus.draft):
            reasons.append(G.WAP_NOT_ACTIVE)
    order = [G.CREW_EXCLUDED, G.WAP_OUTSIDE_WINDOW, G.WAP_SUSPENDED, G.WAP_NOT_ACTIVE]
    for r in order:
        if r in reasons:
            return Item(RK.work_area_permit, None, RS.not_met, r), None, None
    return Item(RK.work_area_permit, None, RS.not_met, G.WAP_MISSING), None, None


# ---- evaluation ----------------------------------------------------------------------------------


def evaluate(
    db: Session,
    worker: Worker,
    zone: Zone,
    at: datetime,
    context: EligibilityContext,
    *,
    site_only: bool = False,
    escort_ok: bool | None = None,
    crew_role: str | None = None,
    with_wap: bool | None = None,
) -> Evaluation:
    """ZP-4 steps (1)…(8). `site_only` = site gate (steps 1-5 with the GEN course, GC-4); the
    zone may then be an unsaved stand-in carrying only project_id and site_id.
    `escort_ok`: True when a valid escort is present (WA-11/GC-8). `with_wap` overrides
    whether step 7 runs (default: context gate)."""
    s = common.settings(db, zone.project_id)
    ev = Evaluation(worker, zone, at, context)
    d = common.local_day(at)
    items = ev.items
    # (1) deployment
    dep = current_deployment(db, worker.id, zone.project_id)
    if (
        dep is None
        or dep.status != DeploymentStatus.mobilised
        or zone.site_id not in (dep.site_ids or [])
    ):
        items.append(Item(RK.deployment, None, RS.not_met, G.WORKER_NOT_DEPLOYED))
    else:
        items.append(Item(RK.deployment, None, RS.met))
        ev.deployment = dep
    # (2) worker status
    if worker.status == WorkerStatus.banned:
        items.append(Item(RK.worker_status, None, RS.not_met, G.WORKER_BANNED))
    else:
        items.append(Item(RK.worker_status, None, RS.met))
    # (3) contractor
    con = contractor_of(db, dep.engagement_id) if dep else None
    if con is not None and con.status == ContractorStatus.blacklisted:
        items.append(
            Item(RK.contractor_status, con.short_code, RS.not_met, G.CONTRACTOR_BLACKLISTED)
        )
    elif con is not None and con.status == ContractorStatus.suspended:
        warn = s.suspended_contractor_gate == SuspendedContractorGateMode.warn
        items.append(
            Item(
                RK.contractor_status, con.short_code, RS.warn if warn else RS.not_met,
                G.CONTRACTOR_SUSPENDED,
            )
        )  # fmt: skip
    else:
        items.append(Item(RK.contractor_status, con.short_code if con else None, RS.met))
    # (4) ID
    if (
        worker.id_expiry_date is not None
        and s.id_expiry_blocks_access
        and worker.id_expiry_date < d
    ):
        items.append(Item(RK.id_validity, None, RS.not_met, G.ID_EXPIRED, worker.id_expiry_date))
    elif _expiring(worker.id_expiry_date, d):
        items.append(Item(RK.id_validity, None, RS.expiring, G.EXPIRING_7D, worker.id_expiry_date))
    else:
        items.append(Item(RK.id_validity, None, RS.met, None, worker.id_expiry_date))
    # (5) inductions
    courses = {
        c.code: c
        for c in db.scalars(
            select(InductionCourse).where(InductionCourse.project_id == zone.project_id)
        )
    }
    if worker.person_type == WorkerPersonType.visitor or site_only:
        kind = (
            InductionType.visitor
            if worker.person_type == WorkerPersonType.visitor
            else InductionType.general_site
        )
        items.extend(_any_course(db, worker.id, zone.project_id, courses, kind, at, s))
    else:
        for code in list(profiles.ensure(db, zone).required_inductions or []):
            items.extend(
                induction_item(db, worker.id, zone.project_id, courses.get(code), code, at, s)
            )
    if site_only:
        return ev
    prof = profiles.ensure(db, zone)
    # (6) airport pass and escort
    if prof.airport_pass_area_code:
        it, ps = pass_item(db, worker.id, zone.project_id, prof.airport_pass_area_code, d)
        items.append(it)
        ev.pass_ = ps
        if ps is not None and ps.escorted:
            ev.escort_required = True
            if escort_ok:
                items.append(Item(RK.escort, None, RS.met))
            else:
                items.append(Item(RK.escort, None, RS.not_met, G.ESCORT_REQUIRED))
    # (7) WAP
    run_wap = with_wap if with_wap is not None else context == EligibilityContext.gate
    if run_wap and prof.access_permit_required:
        it, wap, inst = wap_item(db, worker.id, zone, at)
        items.append(it)
        ev.wap, ev.wap_window = wap, inst
    # (8) hooks (zone profile, filtered by trade; WAP crew role)
    reqs = [
        h for h in prof.hook_requirements or []
        if not h.get("trades") or (dep is not None and dep.trade.value in h["trades"])
    ]  # fmt: skip
    if crew_role:
        reqs += list((s.hook_requirements_by_crew_role or {}).get(crew_role, []))
    hctx = hooks.HookContext(project_id=s.project_id, zone_id=zone.id, crew_role=crew_role)
    for h in reqs:
        items.append(
            hook_item(
                db, HookSubjectType.worker, worker.id, HookKind(h["kind"]), h["code"], at, s, hctx
            )
        )
    return ev


def to_result(
    db: Session, ev: Evaluation, names: bool, refs: Refs | None = None
) -> EligibilityResult:
    refs = refs or Refs(db)
    zr = refs.zone(ev.zone.id)
    assert zr is not None  # noqa: S101
    return EligibilityResult(
        worker=common.worker_ref(ev.worker, names),
        zone=zr,
        at=ev.at,
        context=ev.context,
        eligible=ev.eligible,
        escort_required=ev.escort_required,
        items=[i.to_schema() for i in ev.items],
    )


def eligibility(
    db: Session,
    worker_id: uuid.UUID,
    zone_id: uuid.UUID,
    at: datetime | None = None,
    context: EligibilityContext = EligibilityContext.check,
) -> Evaluation | None:
    w = db.get(Worker, worker_id)
    z = db.get(Zone, zone_id)
    if w is None or z is None:
        return None
    return evaluate(db, w, z, at or now(), context)
