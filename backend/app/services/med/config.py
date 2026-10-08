"""Phase 6a project settings (spec 6a-occupational-health §3.12), enabling the `medical_fitness`
provider (HK6-1, HK6-2 default attach points, RF-7) and the readiness report (HK6-9)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind
from app.core.cert_enums import HookCodePolicy, HookStage
from app.core.clock import now, today
from app.core.enums import AuditAction, EntityType
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.med_enums import (
    HookBand,
    MedicalProviderKind,
    MedicalProviderStatus,
    ReferralReason,
)
from app.core.ptw_enums import PERMIT_TERMINAL
from app.models import (
    AccessSettings,
    MedicalProvider,
    Permit,
    PermitCrew,
    PersonnelCertificate,
    Project,
    Worker,
    Zone,
    ZoneAccessProfile,
)
from app.schemas.cert_config import (
    HookPolicyRead,
    HookReadinessReport,
    ReadinessAffected,
    ReadinessCode,
    ReadinessSubject,
)
from app.schemas.medical import (
    MedicalHooksEnableRequest,
    MedicalSettingsRead,
    MedicalSettingsUpdate,
    MedicalSettingsUpdateResult,
)
from app.services.common import invalid_transition
from app.services.med import common, engine
from app.services.med import reference as ref
from app.services.permissions import Principal, forbidden_error

C = common.C
MF = HookKind.medical_fitness

# ---- settings ------------------------------------------------------------------------------------


def settings_read(db: Session, project_id: uuid.UUID) -> MedicalSettingsRead:
    s = common.settings(db, project_id)
    return MedicalSettingsRead(
        project_id=project_id,
        medical_register_from=s.medical_register_from,
        fitness_validity_months=dict(s.fitness_validity_months or {}),
        medical_hook_transition_days=s.medical_hook_transition_days,
        medical_hook_critical_transition_days=s.medical_hook_critical_transition_days,
        medical_hook_critical_codes=list(s.medical_hook_critical_codes or []),
        unverified_fitness_acceptance_hours=s.unverified_fitness_acceptance_hours,
        fitness_verification_due_days=s.fitness_verification_due_days,
        referral_assessment_hours=s.referral_assessment_hours,
        signoff_due_hours=s.signoff_due_hours,
        assessment_backdate_max_days=s.assessment_backdate_max_days,
        restriction_review_max_days=s.restriction_review_max_days,
        unfit_review_max_days=s.unfit_review_max_days,
        medical_line_max_due_days=s.medical_line_max_due_days,
        rtw_hold_case_categories=list(s.rtw_hold_case_categories or []),
        heat_illness_natures=list(s.heat_illness_natures or []),
        exposure_group_trade_defaults={
            k: list(v) for k, v in (s.exposure_group_trade_defaults or {}).items()
        },
        medical_compliance_warning_pct=str(
            Decimal(s.medical_compliance_warning_pct).quantize(Decimal("0.1"))
        ),
        health_cell_min=s.health_cell_min,
        fitness_scan_retention_months=s.fitness_scan_retention_months,
        fitness_record_retention_years=s.fitness_record_retention_years,
        surveillance_record_retention_years=s.surveillance_record_retention_years,
        worker_purpose_notice_version=s.worker_purpose_notice_version,
        alert_schedule_long_days=list(s.alert_schedule_long_days or []),
        medical_hooks_enabled=common.registered(db, project_id),
        updated_at=s.updated_at,
    )


def get_settings(db: Session, p: Principal, project_id: uuid.UUID) -> MedicalSettingsRead:
    common.visible_project(db, p, project_id)
    if p.grant(project_id, C.fitness_catalogue_view) is None:
        raise forbidden_error()
    return settings_read(db, project_id)


def _manager(db: Session, p: Principal, project_id: uuid.UUID) -> None:
    common.visible_project(db, p, project_id)
    p.require(project_id, C.medical_settings_edit)


def _loosening(key: str) -> ApiError:
    return ApiError(
        422,
        ErrorCode.SETTING_LOOSENING,
        f"{key} may only be tightened.",
        "يسمح بتشديد هذا الإعداد فقط.",
        meta={"field": key},
    )


def update_settings(
    db: Session, p: Principal, project_id: uuid.UUID, body: MedicalSettingsUpdate
) -> MedicalSettingsUpdateResult:
    _manager(db, p, project_id)
    s = common.settings(db, project_id)
    data = body.model_dump(exclude_unset=True)
    before = common.snap(s)
    codes = common.codes(db)
    changed: list[str] = []
    for k, raw in data.items():
        v: Any = raw
        if v is None and k != "medical_register_from":
            continue
        if k == "medical_register_from":
            if v is None:
                if s.medical_register_from is not None:
                    raise _loosening(k)
                continue
            pr = db.get(Project, project_id)
            if v > today() or (pr is not None and v < pr.start_date):
                raise validation_error(k, "Between the project start and today.")
            if s.medical_register_from is not None and v > s.medical_register_from:
                raise ApiError(
                    422,
                    ErrorCode.MEDICAL_REGISTER_LATER,
                    "The register start may only move earlier.",
                    "يمكن تقديم تاريخ بدء السجل فقط.",
                )
        elif k == "fitness_validity_months":
            for c, m in v.items():
                fc = codes.get(c)
                if fc is None:
                    raise validation_error(k, f"Unknown fitness code {c}.")
                if not 1 <= int(m) <= fc.validity_months:
                    raise _loosening(k)
                old = (s.fitness_validity_months or {}).get(c)
                if old is not None and int(m) > int(old):
                    raise _loosening(k)
            for c in s.fitness_validity_months or {}:
                if c not in v:
                    raise _loosening(k)
            v = {c: int(m) for c, m in v.items()}
        elif k in (
            "medical_hook_critical_codes",
            "rtw_hold_case_categories",
            "heat_illness_natures",
        ):
            if set(getattr(s, k) or []) - set(v):
                raise _loosening(k)
            if k == "medical_hook_critical_codes" and any(c not in codes for c in v):
                raise validation_error(k, "Unknown fitness code.")
            v = sorted(set(v))
        elif k == "exposure_group_trade_defaults":
            prev = s.exposure_group_trade_defaults or {}
            for g, trades in prev.items():
                if set(trades) - set(v.get(g, [])):
                    raise _loosening(k)
            v = {g: sorted(set(t)) for g, t in v.items()}
        elif k == "medical_compliance_warning_pct":
            dv = Decimal(v)
            if not Decimal("80.0") <= dv <= Decimal("100.0"):
                raise validation_error(k, "80.0–100.0.")
            v = dv
        if getattr(s, k) != v:
            setattr(s, k, v)
            changed.append(k)
    if changed:
        s.updated_at = now()
        s.updated_by_user_id = p.user.id
        db.flush()
        common.record(db, p, AuditAction.update, EntityType.medical_settings, s, project_id, before)
        from app.services.cert import events  # noqa: PLC0415

        events.publish(db, "hook_policy.changed", project_id=project_id)
    return MedicalSettingsUpdateResult(settings=settings_read(db, project_id), changed=changed)


# ---- HK6-1 enable --------------------------------------------------------------------------------


def _has_provider(db: Session, project_id: uuid.UUID) -> bool:
    for pv in db.scalars(
        select(MedicalProvider).where(MedicalProvider.status == MedicalProviderStatus.approved)
    ):
        if pv.kind == MedicalProviderKind.external_clinic:
            return True
        if pv.kind == MedicalProviderKind.site_clinic and project_id in (pv.project_ids or []):
            return True
    return False


def _add(
    items: list[dict[str, Any]] | None, item: dict[str, Any]
) -> tuple[list[dict[str, Any]], bool]:
    cur = list(items or [])
    if any(x.get("kind") == item["kind"] and x.get("code") == item["code"] for x in cur):
        return cur, False
    return [*cur, item], True


def seed_attach_points(db: Session, p: Principal | None, project_id: uuid.UUID) -> list[str]:
    """HK6-2 defaults (Phase 2 side; the Phase 3 crew / operator hooks follow registration)."""
    done: list[str] = []
    from app.services.access import common as acommon  # noqa: PLC0415

    acc: AccessSettings = acommon.settings(db, project_id)
    for code in ref.PROJECT_HOOK_CODES:
        acc.project_hook_requirements, added = _add(
            acc.project_hook_requirements, {"kind": MF.value, "code": code, "trades": []}
        )
        if added:
            done.append(f"project:{code}")
    adp = dict(acc.hook_requirements_by_adp_category or {})
    for cat, code in ref.ADP_HOOKS.items():
        adp[cat], added = _add(adp.get(cat), {"kind": MF.value, "code": code, "trades": []})
        if added:
            done.append(f"adp:{cat}:{code}")
    acc.hook_requirements_by_adp_category = adp
    for zcode, items in ref.ZONE_HOOKS.items():
        z = db.scalar(select(Zone).where(Zone.project_id == project_id, Zone.code == zcode))
        zp = db.get(ZoneAccessProfile, z.id) if z is not None else None
        if zp is None:
            continue
        for trade, code in items:
            zp.hook_requirements, added = _add(
                zp.hook_requirements, {"kind": MF.value, "code": code, "trades": [trade]}
            )
            if added:
                done.append(f"zone:{zcode}:{code}")
    db.flush()
    if done:
        from app.services import audit  # noqa: PLC0415

        audit.record(
            db,
            AuditAction.update,
            p.actor(project_id) if p is not None else audit.SYSTEM,
            entity_type=EntityType.medical_settings,
            entity_id=project_id,
            project_id=project_id,
            details={"attach_points_seeded": done},
        )
    return done


def rf7_referrals(db: Session, project_id: uuid.UUID, p: Principal | None) -> int:
    """RF-7: Phase 4 cards with a medical restriction and no review → referral (no removal)."""
    from app.models import FitnessReferral  # noqa: PLC0415
    from app.services.med import holds  # noqa: PLC0415

    n = 0
    for pc in db.scalars(
        select(PersonnelCertificate).where(
            PersonnelCertificate.project_id == project_id,
            PersonnelCertificate.medical_restriction_on_card.is_(True),
            PersonnelCertificate.restriction_reviewed_at.is_(None),
        )
    ):
        if db.scalar(select(FitnessReferral.id).where(FitnessReferral.source_cert_id == pc.id)):
            continue
        dep = common.deployment(db, pc.worker_id, project_id)
        if dep is None:
            continue
        holds.raise_referral(
            db,
            p,
            pc.worker_id,
            project_id,
            ReferralReason.certificate_restriction,
            None,
            False,
            source_cert_id=pc.id,
        )
        n += 1
    return n


def enable_hooks(
    db: Session, p: Principal, project_id: uuid.UUID, body: MedicalHooksEnableRequest
) -> HookPolicyRead:
    from app.services.cert import events, policy  # noqa: PLC0415

    _manager(db, p, project_id)
    s = common.settings(db, project_id)
    if s.medical_register_from is None or s.medical_register_from > today():
        raise ApiError(
            422,
            ErrorCode.MEDICAL_REGISTER_NOT_LIVE,
            "Set medical_register_from (≤ today) before enabling medical hooks.",
            "حدد تاريخ بدء سجل اللياقة (حتى اليوم) قبل تفعيل متطلبات اللياقة.",
        )
    if not _has_provider(db, project_id):
        raise ApiError(
            422,
            ErrorCode.NO_MEDICAL_PROVIDER,
            "Approve a site clinic or an external clinic serving the project first.",
            "اعتمد عيادة موقع أو عيادة خارجية تخدم المشروع أولاً.",
        )
    if policy.state(db, project_id, MF) is not None:
        raise invalid_transition("Hook policy", "transition", "transition")
    on = body.registered_on or today()
    if on > today():
        raise validation_error("registered_on", "Cannot be in the future.")
    enable(db, p, project_id, on)
    policy._alert_change(
        db, project_id, "Fitness requirement checks enabled", "تم تفعيل فحوص متطلبات اللياقة"
    )
    events.publish(db, "hook_policy.changed", project_id=project_id)
    return policy.policy_read(db, project_id)


def enable(db: Session, p: Principal | None, project_id: uuid.UUID, on: date) -> None:
    from app.services import audit  # noqa: PLC0415
    from app.services.cert import policy  # noqa: PLC0415
    from app.services.med import plan  # noqa: PLC0415

    actor = p.actor(project_id) if p is not None else audit.SYSTEM
    policy.enable_project(db, project_id, on, actor, kinds=(MF,))
    db.info.pop("hook_states", None)
    common.clear_cache(db)
    seed_attach_points(db, p, project_id)
    plan.sync_hook_lines(db, project_id, on)
    rf7_referrals(db, project_id, p)


# ---- HK6-9 readiness -----------------------------------------------------------------------------


def _pct(n: int, total: int) -> Decimal | None:
    if total == 0:
        return None
    return (Decimal(n) * 100 / Decimal(total)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _band(chk: engine.Check) -> HookBand:
    if chk.ok:
        return HookBand.restriction_applies if chk.conditions else HookBand.cleared
    return HookBand.not_eligible


def readiness(
    db: Session, p: Principal, project_id: uuid.UUID, on_date: date | None = None
) -> HookReadinessReport:
    """Per hook code: subjects requiring it (counted H requirements and crews of live permits),
    met / expiring counts and the not-met list per caller tier. Never prevents the switch."""
    from app.services.cert import policy  # noqa: PLC0415
    from app.services.med import requirements as rq  # noqa: PLC0415
    from app.services.ptw import reference as pref  # noqa: PLC0415
    from app.services.ptw.common import permit_ref  # noqa: PLC0415

    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.medical_kpi_view)
    if g is None:
        raise forbidden_error()
    d = on_date or today()
    st = policy.state(db, project_id, MF)
    cfg = policy.cfg(db, project_id, MF)
    at = common.noon(d)
    stage = policy.current_stage(st, cfg, at) if st is not None else HookStage.warn
    s = common.settings(db, project_id)
    crit = common.critical_codes(s)
    names = common.names(p, project_id)
    subjects: dict[str, set[uuid.UUID]] = defaultdict(set)
    f = rq.load(db, project_id, d)
    deps = {x.worker_id: x for x in f.deps}
    for dep in f.deps:
        if not common.covers_dep(g, dep):
            continue
        for r in rq.evaluate_dep(f, dep):
            if r.hook_code:
                subjects[r.code].add(dep.worker_id)
    permits = {
        pm.id: pm
        for pm in db.scalars(
            select(Permit).where(
                Permit.project_id == project_id, Permit.status.notin_(list(PERMIT_TERMINAL))
            )
        )
    }
    crew_of: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for c in db.scalars(
        select(PermitCrew).where(PermitCrew.permit_id.in_(list(permits) or [uuid.UUID(int=0)]))
    ):
        crew_of[c.permit_id].add(c.worker_id)
        cdep = deps.get(c.worker_id) or common.deployment(db, c.worker_id, project_id)
        if not common.covers_dep(g, cdep):
            continue
        for code in pref.MEDICAL_CREW_HOOKS.get(c.crew_role, ()):
            subjects[code].add(c.worker_id)
    ctx = engine.ctx_for(db, project_id)
    wfs = engine.load(db, {w for ws in subjects.values() for w in ws})
    failing: set[uuid.UUID] = set()
    codes = []
    for code in sorted(subjects, key=lambda c: (ref.CODES.index(c) if c in ref.CODES else 99, c)):
        ok = 0
        not_met = []
        for wid in sorted(subjects[code], key=str):
            chk = engine.check(ctx, wfs.get(wid), code, at)
            if chk.ok:
                ok += 1
                continue
            failing.add(wid)
            w = wfs[wid].worker if wid in wfs else db.get(Worker, wid)
            t = common.tier(p, project_id, deps.get(wid))
            not_met.append(
                ReadinessSubject(
                    subject_type="worker",
                    subject_id=wid,
                    ref=w.worker_no if w else str(wid),
                    label=w.full_name_en if (w and names) else None,
                    reason_code=chk.reason if t >= 3 else None,
                    band=_band(chk),
                    hard_stop=chk.hard_stop,
                )
            )
        value = _pct(ok, len(subjects[code]))
        codes.append(
            ReadinessCode(
                code=code,
                critical=code in crit,
                policy=policy.code_policy(st, cfg, code, at)
                if st is not None
                else HookCodePolicy.warn,
                block_from=policy.block_from(st, cfg, code) if st is not None else None,
                required=len(subjects[code]),
                in_force=ok,
                readiness_pct=value,
                readiness_display=f"{value} %" if value is not None else "—",
                not_met=not_met,
            )
        )
    affected_permits = [permit_ref(pm) for pid, pm in permits.items() if crew_of[pid] & failing]
    from app.services.train import gaps  # noqa: PLC0415

    _p, waps = gaps.live_work(db, project_id, failing)
    nxt = d
    if st is not None:
        dates = [
            x
            for x, done in (
                (st.critical_block_from, st.critical_switched_at),
                (st.general_block_from, st.general_switched_at),
            )
            if done is None and x >= d
        ]
        nxt = min(dates) if dates else d
    common.sensitive_read(db, p, EntityType.medical_settings, project_id, project_id, ["readiness"])
    return HookReadinessReport(
        project_id=project_id,
        kind=MF,
        as_of=d,
        stage=stage,
        codes=codes,
        affected=[
            ReadinessAffected(
                on_date=nxt,
                permits=affected_permits,
                wap_nos=sorted({x for v in waps.values() for x in v}),
                gate_codes=[],
            )
        ],
    )
