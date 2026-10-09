"""Phase 3 integration (spec 6b-heat-stress §5.9 PH-1…PH-8, 3-ptw v1.3 §11.4): the WBGT stop
and reading blockers, crew heat checks, the shift reading and regime, and resume after a heat
stop by the receiver. Applies only from `heat_ptw_enforcement_from` (§11.4 item 9)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.access_enums import HookKind
from app.core.clock import now
from app.core.heat_enums import (
    AcclimatisationBasis,
    AcclimatisationStatus,
    Clothing,
    Regime,
    Workload,
)
from app.core.ptw_enums import (
    CrewLineStatus,
    Exposure,
    PermitBlocker,
    PermitStatus,
    PermitType,
    PermitWarningCode,
    StatusReason,
)
from app.models import Permit, PermitShift, Worker, Zone
from app.schemas.permits import PermitRead
from app.services.heat import common as hc
from app.services.heat import plans, state

B = PermitBlocker
W = PermitWarningCode
AB = AcclimatisationBasis
OUTDOOR = (Exposure.outdoor_direct_sun, Exposure.outdoor_shaded)
# 3-ptw v1.3 §3.2: heat_workload default per permit type (heaviest wins)
TYPE_WORKLOAD = {
    PermitType.hot_work: Workload.moderate,
    PermitType.confined_space: Workload.heavy,
    PermitType.work_at_height: Workload.moderate,
    PermitType.excavation: Workload.heavy,
    PermitType.electrical_isolation: Workload.light,
    PermitType.lifting: Workload.moderate,
    PermitType.radiography: Workload.light,
    PermitType.airside_works: Workload.heavy,
    PermitType.general: Workload.moderate,
}


def default_workload(work_types: list[str]) -> Workload:
    out = Workload.light
    for t in work_types:
        w = TYPE_WORKLOAD.get(PermitType(t), Workload.moderate)
        if hc.WL_RANK[w] > hc.WL_RANK[out]:
            out = w
    return out


def workload(permit: Permit) -> Workload:
    return (
        Workload(permit.heat_workload)
        if permit.heat_workload
        else default_workload(list(permit.work_types or []))
    )


def clothing(permit: Permit) -> Clothing:
    return Clothing(permit.heat_clothing) if permit.heat_clothing else Clothing.work_clothes


def applies(db: Session, permit: Permit, at: datetime) -> bool:
    if permit.exposure not in OUTDOOR or not hc.enabled(db, permit.project_id):
        return False
    return hc.cfg(db, permit.project_id).enforced_on(hc.local_day(at))


@dataclass
class PermitHeat:
    zones: list[tuple[Zone, state.ZState]]
    regime: Regime

    def worst(
        self, basis: AB, wl: Workload, cl: Clothing, hood: bool, t: hc.Table, off: Any
    ) -> Regime:
        return hc.worst(
            zs.regime(t, off, basis, wl, cl, hood) for _z, zs in self.zones if zs.latest is not None
        )


def permit_heat(db: Session, permit: Permit, at: datetime) -> PermitHeat:
    cfg = hc.cfg(db, permit.project_id)
    t = hc.table(db)
    zmap = hc.zone_map(db, permit.project_id)
    zones = [
        (zmap[z], state.zone_state(db, permit.project_id, z, at))
        for z in permit.zone_ids or []
        if z in zmap
    ]
    ph = PermitHeat(zones, Regime.unknown)
    ph.regime = ph.worst(
        AB.acclimatised, workload(permit), clothing(permit), permit.heat_hood, t, cfg.offset
    )
    return ph


def check(db: Session, permit: Permit, ctx: Any, res: Any, lines: list[Any]) -> None:
    """Called from `ptw.evaluation.evaluate` (PH-2, PH-3, PH-5, PH-7)."""
    at = ctx.at
    if not applies(db, permit, at):
        return
    cfg = hc.cfg(db, permit.project_id)
    t = hc.table(db)
    d = hc.local_day(at)
    ph = permit_heat(db, permit, at)
    live = ctx.start or permit.status == PermitStatus.active
    if (
        ctx.start
        and permit.exposure == Exposure.outdoor_direct_sun
        and cfg.in_controls(d)
        and cfg.in_monitoring(at)
    ):
        for z, zs in ph.zones:
            if zs.state != state.S.current:
                res.add(B.WBGT_READING_REQUIRED, f"{z.code} ({zs.state.value})", z.code)
    if not live:
        return
    if ph.regime == Regime.R4:
        wl, cl = workload(permit), clothing(permit)
        hits = [
            z.code
            for z, zs in ph.zones
            if zs.latest is not None
            and zs.regime(t, cfg.offset, AB.acclimatised, wl, cl, permit.heat_hood) == Regime.R4
        ]
        hit = hits[0] if hits else None
        res.add(
            B.HEAT_STOP,
            f"{hit or ''} {workload(permit).value} R4",
            hit,
            reason=StatusReason.heat_stress_stop.value,
        )
        return
    if ph.regime != Regime.unknown:
        res.warn(W.HEAT_REGIME, f"{ph.regime.value} rest {hc.REST_MIN[ph.regime]} min/h")
    _crew(db, permit, ctx, res, lines, ph, t, cfg)


def _crew(
    db: Session, permit: Permit, ctx: Any, res: Any, lines: list[Any], ph: PermitHeat,
    t: hc.Table, cfg: hc.Cfg,
) -> None:  # fmt: skip
    from app.services.med import common as mcommon  # noqa: PLC0415

    d = hc.local_day(ctx.at)
    removed: list[uuid.UUID] = []
    for line in lines:
        if line.status == CrewLineStatus.excluded:
            continue
        dep = mcommon.deployment(db, line.worker_id, permit.project_id)
        if dep is None:
            continue
        st = plans.status_of(db, dep, d)
        w = db.get(Worker, line.worker_id)
        wno = w.worker_no if w else None
        if st.status == AcclimatisationStatus.acclimatising and st.day is not None:
            res.warn(
                W.WORKER_ACCLIMATISING,
                f"day {st.day['day_no']}, max {st.day['max_minutes']} min",
                wno,
            )
        if st.basis != AB.unacclimatised:
            continue
        ur = ph.worst(
            AB.unacclimatised, workload(permit), clothing(permit), permit.heat_hood, t, cfg.offset
        )
        present = ctx.crew_present or []
        if ur == Regime.R4 and line.worker_id in present:
            present.remove(line.worker_id)
            removed.append(line.worker_id)
            res.warn(W.HEAT_STOP_FOR_WORKER, "Not for heat work now — acclimatising", wno)
    if removed and permit.status == PermitStatus.active:
        from app.services.ptw import evaluation  # noqa: PLC0415

        sh = evaluation.current_shift(db, permit)
        if sh is not None and sh.ended_at is None:
            sh.crew_present = [x for x in sh.crew_present or [] if x not in removed]
            db.flush()


# ---- PH-6 crew restriction -----------------------------------------------------------------------


def restriction_item(
    db: Session, permit: Permit, worker_id: uuid.UUID, at: datetime
) -> dict[str, Any] | None:
    """`no_heat_exposure` keeps the worker off outdoor_direct_sun permits on any date and off
    outdoor_shaded permits in the controls period (PH-6). The item is a medical item, so tier 1
    sees "Not eligible — HSE check" (6a HK6-7)."""
    if not applies(db, permit, at):
        return None
    cfg = hc.cfg(db, permit.project_id)
    if permit.exposure == Exposure.outdoor_shaded and not cfg.in_controls(hc.local_day(at)):
        return None
    if not plans.restricted(db, worker_id, permit.project_id, at):
        return None
    return {
        "kind": "hook",
        "code": "no_heat_exposure",
        "hook_kind": HookKind.medical_fitness.value,
        "status": "not_met",
        "valid_until": None,
        "ref": None,
        "reason_code": "HEAT_RESTRICTION",
        "hook_reason_code": "RESTRICTION_CONFLICT",
        "message_en": "No heat exposure (restriction)",
        "message_ar": "لا تعرض للحرارة (قيد)",
        "zone_id": None,
    }


# ---- shift reading and regime (PH-1, PH-4, §11.4 item 2) -----------------------------------------


def shift_reading(db: Session, permit: Permit, at: datetime) -> uuid.UUID | None:
    if not applies(db, permit, at):
        return None
    ph = permit_heat(db, permit, at)
    best = None
    for _z, zs in ph.zones:
        if zs.latest is not None and (best is None or zs.latest.wbgt > best.wbgt):
            best = zs.latest
    return best.id if best else None


def shift_regime(
    db: Session, permit: Permit | None, s: PermitShift
) -> tuple[Regime | None, int | None]:
    if permit is None or s.ended_at is not None:
        return None, None
    at = now()
    if not applies(db, permit, at):
        return None, None
    r = permit_heat(db, permit, at).regime
    return r, hc.REST_MIN.get(r)


# ---- resume after heat_stress_stop (PH-3) --------------------------------------------------------


def heat_resume(db: Session, p: Any, permit_id: uuid.UUID, body: Any) -> PermitRead:
    """The receiver resumes a permit suspended `heat_stress_stop` once HEAT_STOP clears; no issuer
    cause text; the GT-4 test where gas testing applies (via the shift checks)."""
    from app.core.errors import ErrorCode  # noqa: PLC0415
    from app.core.ptw_enums import SignaturePurpose, SimopsCheckTrigger  # noqa: PLC0415
    from app.services.ptw import common as pcommon  # noqa: PLC0415
    from app.services.ptw import evaluation, lifecycle  # noqa: PLC0415

    permit = pcommon.get_permit(db, p, permit_id)
    lifecycle._need(permit, "resume", PermitStatus.suspended)
    if permit.status_reason != StatusReason.heat_stress_stop:
        raise pcommon.err(
            ErrorCode.INVALID_TRANSITION,
            "Only a permit suspended for heat stress is resumed by the receiver (PH-3).",
            "يستأنف المستلم فقط التصريح الموقوف بسبب الإجهاد الحراري.",
            status=409,
        )
    lifecycle._receiver_only(p, permit, "resumes after a heat stop")
    at = now()
    sp = evaluation.open_suspension(db, permit)
    s = pcommon.settings(db, permit.project_id)
    gas_after = None
    if sp is not None and at - sp.suspended_at >= timedelta(minutes=s.gas_break_retest_minutes):
        gas_after = sp.suspended_at
    lifecycle._simops(db, permit, SimopsCheckTrigger.resume, at)
    chk = lifecycle.shift_checks(db, permit, body, at, gas_after=gas_after, gas_start=True)
    lifecycle.save_wind(db, p, permit, body.wind_reading)
    if sp is not None:
        sp.resumed_at = at
        sp.resumed_by_user_id = p.user.id
        sp.resume_gas_test_id = chk.gas_test_id
    assert permit.issuer_user_id is not None  # noqa: S101
    lifecycle.open_shift(
        db,
        permit,
        at,
        receiver_id=permit.receiver_user_id,
        issuer_id=permit.issuer_user_id,
        crew=chk.crew,
        ambient=body.ambient_temp_c,
        gas_test_id=chk.gas_test_id,
        end=chk.planned_end,
    )
    lifecycle._set_status(db, p, permit, PermitStatus.active, details={"heat_resume": True})
    pcommon.sign(db, permit, SignaturePurpose.resume, "receiver", user_id=p.user.id, at=at)
    evaluation.store(permit, chk.result)
    lifecycle._refresh(db, permit, at)
    return lifecycle._view(db, p, permit)


# ---- job: SH-2 within 60 s -----------------------------------------------------------------------


def refresh_outdoor(db: Session, project_id: uuid.UUID, at: datetime) -> int:
    """heat_minute: re-evaluate Active / Issued outdoor permits so HEAT_STOP suspends them."""
    from sqlalchemy import select  # noqa: PLC0415

    from app.services.ptw import evaluation  # noqa: PLC0415

    cfg = hc.cfg(db, project_id)
    if not cfg.enforced_on(hc.local_day(at)):
        return 0
    n = 0
    for pm in db.scalars(
        select(Permit).where(
            Permit.project_id == project_id,
            Permit.status == PermitStatus.active,
            Permit.exposure.in_(OUTDOOR),
        )
    ):
        evaluation.refresh(db, pm, run_simops=False, at=at, evaluate_crew=False)
        n += 1
    return n
