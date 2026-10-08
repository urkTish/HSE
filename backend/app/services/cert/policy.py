"""Hook policy per project and kind: warn → transition → block (spec 4-third-party-cert §3.14,
§4.8, §6.5, HK4-1, HK4-4…HK4-6).

The Phase 4 providers are registered **per project** (HK4-1): a `HookPolicyState` row with
`provider_registered_on` ≤ the evaluation date means Phase 4 answers the project's
`personnel_certificate` / `equipment_certificate` hooks; without it the Phase 2 behaviour
(HOOK_NOT_AVAILABLE under `warn`) is unchanged."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind
from app.core.cert_enums import HookCodePolicy, HookStage
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, not_implemented, validation_error
from app.models import CertSettings, HookPolicyState
from app.schemas.cert_config import (
    HookCodeState,
    HookDeferralRead,
    HookDeferralRequest,
    HookEarlySwitchRead,
    HookEnableRequest,
    HookPolicyRead,
    HookPolicyStateRead,
    HookSwitchRequest,
)
from app.services import audit, notify, projects
from app.services.access import common as acommon
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.hse_common import Refs, project_role_users
from app.services.permissions import Principal, forbidden_error

C = Capability
KINDS = ref.PHASE4_KINDS
MAX_DEFERRAL_DAYS = 30


def state(db: Session, project_id: uuid.UUID, kind: HookKind) -> HookPolicyState | None:
    return db.scalar(
        select(HookPolicyState).where(
            HookPolicyState.project_id == project_id, HookPolicyState.kind == kind
        )
    )


def active_state(
    db: Session, project_id: uuid.UUID | None, kind: HookKind, d: date
) -> HookPolicyState | None:
    """The state when Phase 4 answers this project's hooks of `kind` on local date d."""
    if project_id is None or kind not in KINDS:
        return None
    cache: dict[tuple[Any, ...], HookPolicyState] = db.info.setdefault("hook_states", {})
    key = (project_id, kind)
    st = cache.get(key)
    if st is None:
        st = state(db, project_id, kind)
        if st is not None:
            cache[key] = st
    if st is None or st.provider_registered_on > d:
        return None
    return st


def clear_cache(db: Session) -> None:
    db.info.pop("hook_states", None)


def enabled(db: Session, project_id: uuid.UUID, kind: HookKind | None = None) -> bool:
    kinds = [kind] if kind else list(KINDS)
    return any(active_state(db, project_id, k, today()) is not None for k in kinds)


def codes_of(db: Session, kind: HookKind) -> list[str]:
    if kind == HookKind.equipment_certificate:
        return list(ref.EQUIPMENT_HOOK_CODE_LIST)
    return list(ref.PERSONNEL_HOOK_CODES) + sorted(
        c for c in cset.custom_types(db) if c not in ref.PCT
    )


def implemented(db: Session, kind: HookKind, code: str) -> bool:
    if kind == HookKind.equipment_certificate:
        return code in ref.EQUIPMENT_HOOK_CODES
    return code in ref.PERSONNEL_HOOK_CODES or cset.is_type(db, code)


def block_from(st: HookPolicyState, s: CertSettings, code: str) -> date:
    return st.critical_block_from if code in cset.critical_codes(s) else st.general_block_from


def code_policy(st: HookPolicyState, s: CertSettings, code: str, at: datetime) -> HookCodePolicy:
    """HK4-4/HK4-5: block from the code's block date (00:00 local) or an early switch."""
    if st.all_switched_at is not None and st.all_switched_at <= at:
        return HookCodePolicy.block
    if code in (st.switched_codes or []):
        for sw in st.early_switches or []:
            if (sw.get("all_codes") or code in sw.get("codes", [])) and datetime.fromisoformat(
                sw["at"]
            ) <= at:
                return HookCodePolicy.block
    d = acommon.local_day(at)
    if d >= block_from(st, s, code):
        return HookCodePolicy.block
    return HookCodePolicy.transition


def compute_dates(registered_on: date, s: CertSettings) -> tuple[date, date]:
    """§6.5."""
    return (
        registered_on + timedelta(days=s.hook_critical_transition_days),
        registered_on + timedelta(days=s.hook_transition_days),
    )


# ---- read -------------------------------------------------------------------------------------


def _view(p: Principal, project_id: uuid.UUID) -> None:
    for cap in (C.cert_register_view, C.cert_kpi_view, C.cert_settings_edit, C.settings_view):
        if p.grant(project_id, cap) is not None:
            return
    raise forbidden_error()


def stage_read(
    db: Session, st: HookPolicyState | None, kind: HookKind, s: CertSettings
) -> HookPolicyStateRead:
    refs = Refs(db)
    at = now()
    d = today()
    if st is None:
        return HookPolicyStateRead(
            kind=kind,
            stage=HookStage.warn,
            provider_registered_on=None,
            critical_block_from=None,
            general_block_from=None,
            deferral=None,
            deferral_used=False,
            early_switches=[],
            codes=[
                HookCodeState(
                    code=c,
                    critical=c in cset.critical_codes(s),
                    policy=HookCodePolicy.warn,
                    block_from=None,
                    switched_early_at=None,
                    implemented=True,
                )
                for c in codes_of(db, kind)
            ],
            next_block_date=None,
        )
    codes = []
    for c in codes_of(db, kind):
        sw_at = None
        for sw in st.early_switches or []:
            if sw.get("all_codes") or c in sw.get("codes", []):
                sw_at = datetime.fromisoformat(sw["at"])
                break
        codes.append(
            HookCodeState(
                code=c,
                critical=c in cset.critical_codes(s),
                policy=code_policy(st, s, c, at)
                if st.provider_registered_on <= d
                else HookCodePolicy.warn,
                block_from=block_from(st, s, c),
                switched_early_at=sw_at,
                implemented=True,
            )
        )
    nxt = [x for x in (st.critical_block_from, st.general_block_from) if x > d]
    deferral = None
    if st.deferral:
        deferral = HookDeferralRead(
            original_date=date.fromisoformat(st.deferral["original_date"]),
            new_date=date.fromisoformat(st.deferral["new_date"]),
            reason=st.deferral["reason"],
            by=refs.user(uuid.UUID(st.deferral["by"])) or _system_user(),
            at=datetime.fromisoformat(st.deferral["at"]),
        )
    return HookPolicyStateRead(
        kind=kind,
        stage=current_stage(st, s, at),
        provider_registered_on=st.provider_registered_on,
        critical_block_from=st.critical_block_from,
        general_block_from=st.general_block_from,
        deferral=deferral,
        deferral_used=st.deferral is not None,
        early_switches=[
            HookEarlySwitchRead(
                at=datetime.fromisoformat(sw["at"]),
                by=refs.user(uuid.UUID(sw["by"])) or _system_user(),
                all_codes=bool(sw.get("all_codes")),
                codes=list(sw.get("codes", [])),
            )
            for sw in st.early_switches or []
        ],
        codes=codes,
        next_block_date=min(nxt) if nxt and current_stage(st, s, at) != HookStage.block else None,
    )


def _system_user() -> Any:
    from app.schemas.hse_common import UserRef  # noqa: PLC0415

    return UserRef(id=uuid.UUID(int=0), full_name_en="System", full_name_ar="النظام")


def current_stage(st: HookPolicyState, s: CertSettings, at: datetime) -> HookStage:
    d = acommon.local_day(at)
    if d < st.provider_registered_on:
        return HookStage.warn
    if (st.all_switched_at is not None and st.all_switched_at <= at) or d >= st.general_block_from:
        return HookStage.block
    return HookStage.transition


def policy_read(db: Session, project_id: uuid.UUID) -> HookPolicyRead:
    s = cset.get(db, project_id)
    kinds = [stage_read(db, state(db, project_id, k), k, s) for k in KINDS]
    return HookPolicyRead(
        project_id=project_id,
        enabled=any(k.provider_registered_on is not None for k in kinds),
        as_of=today(),
        kinds=kinds,
    )


def read(db: Session, p: Principal, project_id: uuid.UUID) -> HookPolicyRead:
    project = projects.get_visible(db, p, project_id)
    _view(p, project.id)
    return policy_read(db, project.id)


# ---- enable / switch / defer ---------------------------------------------------------------------


def enable_project(
    db: Session,
    project_id: uuid.UUID,
    registered_on: date,
    actor: Any = audit.SYSTEM,
    seed: bool = False,
) -> list[HookPolicyState]:
    s = cset.get(db, project_id)
    out = []
    crit, gen = compute_dates(registered_on, s)
    for kind in KINDS:
        st = state(db, project_id, kind)
        if st is not None:
            out.append(st)
            continue
        st = HookPolicyState(
            id=uuid.uuid4(),
            project_id=project_id,
            kind=kind,
            provider_registered_on=registered_on,
            critical_block_from=crit,
            general_block_from=gen,
            original_general_block_from=gen,
            early_switches=[],
            switched_codes=[],
            stage=HookStage.transition,
            seed_fake=seed,
        )
        db.add(st)
        db.flush()
        audit.record(
            db,
            AuditAction.create,
            actor,
            entity_type=EntityType.hook_policy_state,
            entity_id=st.id,
            project_id=project_id,
            after={
                "kind": kind.value,
                "provider_registered_on": registered_on,
                "critical_block_from": crit,
                "general_block_from": gen,
                "stage": HookStage.transition.value,
            },
        )
        out.append(st)
    clear_cache(db)
    return out


def enable(
    db: Session, p: Principal, project_id: uuid.UUID, body: HookEnableRequest
) -> HookPolicyRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, C.cert_settings_edit)
    if all(state(db, project.id, k) is not None for k in KINDS):
        from app.services.common import invalid_transition  # noqa: PLC0415

        raise invalid_transition("Hook policy", "transition", "transition")
    enable_project(db, project.id, body.registered_on or today(), p.actor(project.id))
    _alert_change(
        db, project.id, "Phase 4 certificate checks enabled", "تم تفعيل فحوص الشهادات (المرحلة 4)"
    )
    from app.services.cert import events  # noqa: PLC0415

    events.publish(db, "hook_policy.changed", project_id=project.id)
    return policy_read(db, project.id)


def _require_state(db: Session, project_id: uuid.UUID, kind: HookKind) -> HookPolicyState:
    if kind == HookKind.training_course:
        raise not_implemented()  # 5-training §4.7 (Phase 5 stage 2, capability 145)
    if kind not in KINDS:
        raise validation_error("kind", "Only personnel_certificate and equipment_certificate.")
    st = state(db, project_id, kind)
    if st is None:
        raise ApiError(
            409,
            ErrorCode.PHASE4_NOT_ENABLED,
            "Phase 4 is not enabled on this project.",
            "المرحلة 4 غير مفعلة في هذا المشروع.",
        )
    return st


def _snap(st: HookPolicyState) -> dict[str, Any]:
    return {
        "stage": st.stage.value,
        "critical_block_from": st.critical_block_from,
        "general_block_from": st.general_block_from,
        "switched_codes": list(st.switched_codes or []),
        "all_switched_at": st.all_switched_at,
        "deferral": st.deferral,
    }


def switch(
    db: Session, p: Principal, project_id: uuid.UUID, kind: HookKind, body: HookSwitchRequest
) -> HookPolicyRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, C.cert_settings_edit)
    st = _require_state(db, project.id, kind)
    s = cset.get(db, project.id)
    at = now()
    codes = codes_of(db, kind) if body.all_codes else list(body.codes)
    if not codes:
        raise validation_error("codes", "Name the codes to switch, or all_codes.")
    unknown = [c for c in codes if not implemented(db, kind, c)]
    if unknown:
        raise validation_error("codes", f"Unknown codes: {', '.join(unknown)}.")
    if body.policy == "warn":
        blocked = [c for c in codes if code_policy(st, s, c, at) == HookCodePolicy.block]
        raise ApiError(
            422,
            ErrorCode.HOOK_POLICY_LOOSENING,
            "A blocked code cannot return to warn (a spec change is needed)."
            if blocked
            else "Codes can only be switched to block.",
            "لا يمكن إعادة الرمز من الحظر إلى التحذير.",
            meta={"codes": ",".join(blocked or codes)},
        )
    before = _snap(st)
    entry = {
        "at": at.isoformat(),
        "by": str(p.user.id),
        "all_codes": body.all_codes,
        "codes": codes,
    }
    st.early_switches = [*(st.early_switches or []), entry]
    st.switched_codes = sorted(set(st.switched_codes or []) | set(codes))
    if body.all_codes:
        st.all_switched_at = at
    st.stage = current_stage(st, s, at)
    st.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id),
        entity_type=EntityType.hook_policy_state,
        entity_id=st.id,
        project_id=project.id,
        before=before,
        after=_snap(st),
        details={"early_switch": codes, "kind": kind.value},
    )
    scope_en = "all codes" if body.all_codes else ", ".join(codes)
    scope_ar = "كل الرموز" if body.all_codes else "، ".join(codes)
    _alert_change(
        db,
        project.id,
        f"Certificate checks now block ({kind.value}: {scope_en})",
        f"فحوص الشهادات أصبحت مانعة ({scope_ar})",
    )
    clear_cache(db)
    from app.services.cert import events  # noqa: PLC0415

    events.publish(db, "hook_policy.changed", project_id=project.id)
    return policy_read(db, project.id)


def defer(
    db: Session, p: Principal, project_id: uuid.UUID, kind: HookKind, body: HookDeferralRequest
) -> HookPolicyRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, C.cert_settings_edit)
    st = _require_state(db, project.id, kind)
    s = cset.get(db, project.id)
    crit = [c for c in body.codes if c in cset.critical_codes(s)]
    if crit:
        raise ApiError(
            422,
            ErrorCode.CRITICAL_CODE_NO_DEFERRAL,
            f"Critical codes cannot be deferred ({', '.join(crit)}).",
            "لا يمكن تأجيل الرموز الحرجة.",
        )
    if st.deferral is not None:
        raise ApiError(
            422,
            ErrorCode.DEFERRAL_USED,
            "The one deferral for this project and kind has been used.",
            "تم استخدام التأجيل الوحيد المسموح.",
        )
    at = now()
    if code_policy(st, s, "__general__", at) == HookCodePolicy.block or st.all_switched_at:
        raise ApiError(
            422,
            ErrorCode.HOOK_POLICY_LOOSENING,
            "The general codes already block; they cannot return to warn.",
            "الرموز العامة أصبحت مانعة ولا يمكن إعادتها إلى التحذير.",
        )
    orig = st.general_block_from
    if body.new_date <= orig:
        raise validation_error(
            "new_date", "The new date must be later than the current block date."
        )
    if body.new_date > orig + timedelta(days=MAX_DEFERRAL_DAYS):
        raise ApiError(
            422,
            ErrorCode.DEFERRAL_TOO_LONG,
            f"At most {MAX_DEFERRAL_DAYS} days: the latest date is "
            f"{orig + timedelta(days=MAX_DEFERRAL_DAYS)}.",
            "الحد الأقصى للتأجيل 30 يوماً.",
            meta={"max_date": str(orig + timedelta(days=MAX_DEFERRAL_DAYS))},
        )
    before = _snap(st)
    st.deferral = {
        "original_date": orig.isoformat(),
        "new_date": body.new_date.isoformat(),
        "reason": body.reason,
        "by": str(p.user.id),
        "at": at.isoformat(),
    }
    st.general_block_from = body.new_date
    st.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(project.id),
        entity_type=EntityType.hook_policy_state,
        entity_id=st.id,
        project_id=project.id,
        before=before,
        after=_snap(st),
        details={"deferral": True, "kind": kind.value},
    )
    _alert_change(
        db,
        project.id,
        f"General certificate block date deferred to {body.new_date}",
        f"تم تأجيل تاريخ الحظر العام للشهادات إلى {body.new_date}",
    )
    clear_cache(db)
    return policy_read(db, project.id)


def _alert_change(db: Session, project_id: uuid.UUID, en: str, ar: str) -> None:
    users = set(project_role_users(db, project_id, Role.hse_officer, Role.contractor_hse_rep))
    notify.notify(
        db,
        users,
        NotificationKind.hook_policy_changed,
        en,
        ar,
        entity_type=EntityType.hook_policy_state,
        project_id=project_id,
    )


# ---- job (00:00:30, HK4-5) -----------------------------------------------------------------------


def switch_due(db: Session, at: datetime | None = None) -> dict[str, int]:
    """Automatic switch on critical_block_from / general_block_from (actor null = system);
    audited and alerted; live permits are re-evaluated by the caller (events)."""
    at = at or now()
    d = acommon.local_day(at)
    switched = 0
    for st in db.scalars(select(HookPolicyState)):
        s = cset.get(db, st.project_id)
        before = _snap(st)
        changed: list[str] = []
        if st.critical_switched_at is None and d >= st.critical_block_from:
            st.critical_switched_at = at
            changed.append("critical")
        if st.general_switched_at is None and d >= st.general_block_from:
            st.general_switched_at = at
            changed.append("general")
        new_stage = current_stage(st, s, at)
        if new_stage != st.stage:
            st.stage = new_stage
        if not changed:
            continue
        switched += 1
        audit.record(
            db,
            AuditAction.status_change,
            audit.SYSTEM,
            entity_type=EntityType.hook_policy_state,
            entity_id=st.id,
            project_id=st.project_id,
            before=before,
            after=_snap(st),
            details={"automatic_switch": changed, "kind": st.kind.value},
        )
        mark = f"hook_switch:{st.id}:{'+'.join(changed)}"
        from app.services.cert import alerts  # noqa: PLC0415

        if alerts.once(db, mark):
            users = set(
                project_role_users(
                    db, st.project_id, Role.hse_manager, Role.hse_officer, Role.contractor_hse_rep
                )
            )
            scope_en = "critical codes" if changed == ["critical"] else "all codes"
            scope_ar = "الرموز الحرجة" if changed == ["critical"] else "كل الرموز"
            notify.notify(
                db,
                users,
                NotificationKind.hook_block_approaching,
                f"Certificate checks now block ({st.kind.value}, {scope_en})",
                f"فحوص الشهادات أصبحت مانعة ({scope_ar})",
                entity_type=EntityType.hook_policy_state,
                entity_id=st.id,
                project_id=st.project_id,
            )
        from app.services.cert import events  # noqa: PLC0415

        events.publish(db, "hook_policy.changed", project_id=st.project_id)
    clear_cache(db)
    return {"switched": switched}
