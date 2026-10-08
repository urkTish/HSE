"""Phase 4 hook providers for `equipment_certificate` and `personnel_certificate` (spec
4-third-party-cert HK4-1…HK4-12, SF-1, SF-6, PC-7, PC-8, PC-13, EC-8, EC-9, EC-11, EC-12).

`check()` returns the HK-3 result {status, valid_until, ref, reason_code, hard_stop,
conditions[], swl_t}. The project's stage (transition / block) is applied by the caller
(`eligibility.hook_item`), except that hard stops block in every stage."""

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, HookProviderStatus, HookSubjectType
from app.core.cert_enums import (
    CertLevel,
    EquipmentCertCategory,
    EquipmentDeploymentStatus,
    HookReasonCode,
    LimitationCode,
    PersonnelLimitationCode,
    ScaffoldStatus,
    ScaffoldTagStatus,
    ServiceStatus,
)
from app.core.ptw_enums import EquipmentCategory
from app.models import (
    CertSettings,
    EquipmentCertificate,
    EquipmentDeployment,
    EquipmentItem,
    PermitEquipment,
    Scaffold,
)
from app.services.access import common as acommon
from app.services.access.hooks import HookCheck, HookContext
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.cert import validity

log = logging.getLogger(__name__)
R = HookReasonCode
P = HookProviderStatus
Q = EquipmentCertCategory
LEVEL_RANK = {
    CertLevel.level_1: 1,
    CertLevel.level_2: 2,
    CertLevel.level_3: 3,
    CertLevel.level_i: 1,
    CertLevel.level_ii: 2,
    CertLevel.level_iii: 3,
    CertLevel.basic: 1,
    CertLevel.advanced: 2,
}


def _no(reason: HookReasonCode, hard: bool = False, **kw: Any) -> HookCheck:
    return HookCheck(P.not_met, reason_code=reason.value, hard_stop=hard, **kw)


def condition(code: str, value: Any, en: str, ar: str, source: str | None) -> dict[str, Any]:
    return {
        "code": code,
        "value": None if value is None else str(value),
        "text_en": en,
        "text_ar": ar,
        "source_ref": source,
    }


def line_conditions(limitations: list[dict[str, Any]], source: str | None) -> list[dict[str, Any]]:
    out = []
    for x in limitations or []:
        code = LimitationCode(x["code"])
        en, ar = ref.LIM_TEXT[code]
        val = x.get("value")
        txt = x.get("text")
        en2 = f"{en}: {val}" if val is not None else en
        ar2 = f"{ar}: {val}" if val is not None else ar
        if txt:
            en2, ar2 = f"{en2} — {txt}", f"{ar2} — {txt}"
        out.append(condition(code.value, val, en2, ar2, source))
    return out


def derated_swl(line_swl: Decimal | None, limitations: list[dict[str, Any]]) -> Decimal | None:
    out = line_swl
    for x in limitations or []:
        if x.get("code") == LimitationCode.derated_swl.value and x.get("value") is not None:
            v = Decimal(str(x["value"]))
            out = v if out is None else min(out, v)
    return out


def colour_now(s: CertSettings, d: date) -> str | None:
    scheme = s.lifting_gear_colour_scheme or {}
    if not scheme.get("enabled"):
        return None
    md = d.strftime("%m-%d")
    for per in scheme.get("periods", []):
        a, b = per["from_mmdd"], per["to_mmdd"]
        if (a <= md <= b) if a <= b else (md >= a or md <= b):
            return str(per["colour"])
    return None


# ---- equipment resolution ------------------------------------------------------------------------


def resolve_item(
    db: Session,
    subject_type: HookSubjectType,
    subject_id: uuid.UUID,
    ctx: HookContext | None,
) -> tuple[EquipmentItem | None, HookReasonCode | None, str | None]:
    """→ (item, failure reason, PTW EQ category used). HK4-8 resolution order."""
    if ctx is not None and ctx.equipment_item_id is not None:
        return db.get(EquipmentItem, ctx.equipment_item_id), None, ctx.equipment_category
    if subject_type == HookSubjectType.vehicle or (ctx is not None and ctx.vehicle_id):
        vid = subject_id if subject_type == HookSubjectType.vehicle else ctx.vehicle_id  # type: ignore[union-attr]
        item = db.scalar(select(EquipmentItem).where(EquipmentItem.vehicle_id == vid))
        return (item, None if item else R.EQUIPMENT_NOT_REGISTERED, None)
    if subject_type == HookSubjectType.equipment_tag:
        if ctx is None or ctx.project_id is None:
            log.warning("equipment_tag hook call without project_id (caller error) %s", subject_id)
            return None, R.EQUIPMENT_NOT_REGISTERED, None
        cat, tag = ctx.equipment_category, ctx.equipment_tag
        if tag is None:
            line = db.get(PermitEquipment, subject_id)
            if line is not None:
                if line.equipment_item_id:
                    return (
                        db.get(EquipmentItem, line.equipment_item_id),
                        None,
                        (line.category.value if line.category else None),
                    )
                cat = line.category.value if line.category else cat
                tag = line.tag
        if not tag:
            return None, R.EQUIPMENT_NOT_REGISTERED, cat
        dep = db.scalar(
            select(EquipmentDeployment)
            .where(
                EquipmentDeployment.project_id == ctx.project_id,
                func.upper(EquipmentDeployment.tag) == tag.strip().upper(),
                EquipmentDeployment.status.notin_(
                    [EquipmentDeploymentStatus.demobilised, EquipmentDeploymentStatus.cancelled]
                ),
            )
            .limit(1)
        )
        if dep is None:
            return None, R.EQUIPMENT_NOT_REGISTERED, cat
        return db.get(EquipmentItem, dep.equipment_id), None, cat
    return None, R.EQUIPMENT_NOT_REGISTERED, None


def _category_ok(item: EquipmentItem, ptw_cat: str | None, code: str) -> bool:
    if ptw_cat:
        try:
            want = ref.PTW_TO_EQC.get(EquipmentCategory(ptw_cat))
        except ValueError:
            want = None
        if want is not None and want != item.category:
            return False
    return item.category in ref.EQUIPMENT_HOOK_CODES.get(code, frozenset())


def check_equipment(
    db: Session,
    subject_type: HookSubjectType,
    subject_id: uuid.UUID,
    code: str,
    at: datetime,
    ctx: HookContext | None,
) -> HookCheck:
    if code not in ref.EQUIPMENT_HOOK_CODES:
        return HookCheck(P.unknown_code, reason_code=R.UNKNOWN_CODE.value)
    if code == "SCAFFOLD-TAG":
        return check_scaffold(db, subject_id, at, ctx)
    item, why, ptw_cat = resolve_item(db, subject_type, subject_id, ctx)
    if item is None:
        return _no(why or R.EQUIPMENT_NOT_REGISTERED)
    if not _category_ok(item, ptw_cat, code):
        return _no(R.CATEGORY_MISMATCH, ref=item.equipment_no)
    if item.service_status == ServiceStatus.blacklisted:
        return _no(R.EQUIPMENT_BLACKLISTED, True, ref=item.equipment_no)
    if item.service_status == ServiceStatus.retired:
        return _no(R.EQUIPMENT_RETIRED, True, ref=item.equipment_no)
    if item.service_status == ServiceStatus.out_of_service:
        return _no(R.EQUIPMENT_OUT_OF_SERVICE, True, ref=item.equipment_no)
    project_id = ctx.project_id if ctx else None
    dep = None
    if project_id is not None:
        dep = db.scalar(
            select(EquipmentDeployment)
            .where(
                EquipmentDeployment.equipment_id == item.id,
                EquipmentDeployment.project_id == project_id,
                EquipmentDeployment.status.in_(
                    [EquipmentDeploymentStatus.approved, EquipmentDeploymentStatus.on_site]
                ),
            )
            .limit(1)
        )
        if dep is None:
            return _no(R.EQUIPMENT_NOT_DEPLOYED, ref=item.equipment_no)
        if dep.status == EquipmentDeploymentStatus.on_site and not dep.arrival_inspection_passed:
            return _no(R.ARRIVAL_INSPECTION_MISSING, ref=dep.tag)
    ic = validity.current_line(db, item.id, at, project_id)
    if ic.cert is None or ic.line is None or not ic.ev.in_force:
        return _no(
            ic.ev.reason or R.CERT_MISSING,
            ic.ev.hard_stop,
            ref=ic.cert.cert_no if ic.cert else None,
            valid_until=ic.ev.valid_until,
        )
    c: EquipmentCertificate = ic.cert
    line = ic.line
    lims = list(line.limitations or [])
    swl = derated_swl(line.swl_t, lims)
    conds = tuple(line_conditions(lims, c.cert_no))
    common_kw: dict[str, Any] = {"ref": c.cert_no, "valid_until": ic.ev.valid_until, "swl_t": swl}
    if ctx is not None:
        if ctx.rated_capacity_t is not None and swl is not None and ctx.rated_capacity_t > swl:
            return _no(R.SWL_LIMITATION, conditions=conds, **common_kw)
        if ctx.use == "personnel_lift" and any(
            x.get("code") == LimitationCode.no_personnel_lifting.value for x in lims
        ):
            return _no(R.LIMITATION_CONFLICT, conditions=conds, **common_kw)
        lifting_use = ctx.use == "lifting_appliance"
        needs_duty = item.category in (Q.excavator, Q.wheel_loader) or (
            item.category == Q.telehandler and item.lifting_duty
        )
        if lifting_use and needs_duty and not (line.lifting_duty_certified and line.swl_t):
            return _no(R.LIFTING_DUTY_NOT_CERTIFIED, conditions=conds, **common_kw)
    if item.category == Q.lifting_accessory:
        s = cset.get(db, project_id or c.project_id)
        now_colour = colour_now(s, acommon.local_day(at))
        if now_colour is not None and (
            line.colour_code is None or line.colour_code.value != now_colour
        ):
            return _no(R.COLOUR_CODE_OUT_OF_PERIOD, conditions=conds, **common_kw)
    status = P.expiring if ic.ev.expiring else P.met
    reason = R.CERT_UNVERIFIED.value if ic.ev.window_until else None
    return HookCheck(status, reason_code=reason, conditions=conds, **common_kw)


# ---- scaffolds (SF-1, SF-5, SF-6) ----------------------------------------------------------------


def find_scaffold(db: Session, project_id: uuid.UUID, tag: str) -> Scaffold | None:
    return db.scalar(
        select(Scaffold)
        .where(
            Scaffold.project_id == project_id,
            func.upper(Scaffold.tag) == tag.strip().upper(),
            Scaffold.status != ScaffoldStatus.dismantled,
        )
        .limit(1)
    )


def scaffold_state(sc: Scaffold, d: date) -> ScaffoldTagStatus:
    """Tag status on local date d (the job sets `expired`; reads do not wait for it)."""
    ts = sc.tag_status
    if ts in (ScaffoldTagStatus.green, ScaffoldTagStatus.yellow) and (
        sc.tag_valid_until is None or sc.tag_valid_until < d
    ):
        return ScaffoldTagStatus.expired
    return ts


def check_scaffold(
    db: Session, subject_id: uuid.UUID, at: datetime, ctx: HookContext | None
) -> HookCheck:
    if ctx is None or ctx.project_id is None:
        log.warning("SCAFFOLD-TAG hook call without project_id (caller error) %s", subject_id)
        return _no(R.SCAFFOLD_NOT_REGISTERED)
    tag = ctx.equipment_tag
    if tag is None:
        line = db.get(PermitEquipment, subject_id)
        tag = line.tag if line else None
    sc = find_scaffold(db, ctx.project_id, tag) if tag else None
    if sc is None:
        return _no(R.SCAFFOLD_NOT_REGISTERED, ref=tag)
    return scaffold_result(sc, at)


def scaffold_result(sc: Scaffold, at: datetime) -> HookCheck:
    d = acommon.local_day(at)
    ts = scaffold_state(sc, d)
    kw: dict[str, Any] = {"ref": sc.tag, "valid_until": sc.tag_valid_until}
    if ts == ScaffoldTagStatus.inspection_required:
        return _no(R.SCAFFOLD_INSPECTION_REQUIRED, True, **kw)
    if ts in (ScaffoldTagStatus.red, ScaffoldTagStatus.none) or sc.status != ScaffoldStatus.in_use:
        return _no(R.SCAFFOLD_TAG_RED, True, **kw)
    if ts == ScaffoldTagStatus.expired:
        return _no(R.SCAFFOLD_INSPECTION_OVERDUE, **kw)
    if ts == ScaffoldTagStatus.yellow:
        en, ar = ref.REASON_TEXT[R.SCAFFOLD_YELLOW_TAG]
        cond = condition(
            R.SCAFFOLD_YELLOW_TAG.value,
            None,
            sc.restrictions_en or en,
            sc.restrictions_ar or sc.restrictions_en or ar,
            sc.scaffold_no,
        )
        return HookCheck(P.met, reason_code=R.SCAFFOLD_YELLOW_TAG.value, conditions=(cond,), **kw)
    return HookCheck(P.met, **kw)


# ---- personnel (PC-7, PC-8, PC-13) ---------------------------------------------------------------


def _ctx_item(db: Session, ctx: HookContext) -> EquipmentItem | None:
    if ctx.equipment_item_id:
        return db.get(EquipmentItem, ctx.equipment_item_id)
    if ctx.vehicle_id:
        return db.scalar(select(EquipmentItem).where(EquipmentItem.vehicle_id == ctx.vehicle_id))
    if ctx.equipment_tag and ctx.project_id:
        dep = db.scalar(
            select(EquipmentDeployment)
            .where(
                EquipmentDeployment.project_id == ctx.project_id,
                func.upper(EquipmentDeployment.tag) == ctx.equipment_tag.strip().upper(),
                EquipmentDeployment.status.notin_(
                    [EquipmentDeploymentStatus.demobilised, EquipmentDeploymentStatus.cancelled]
                ),
            )
            .limit(1)
        )
        return db.get(EquipmentItem, dep.equipment_id) if dep else None
    return None


def check_personnel(
    db: Session,
    worker_id: uuid.UUID,
    code: str,
    at: datetime,
    ctx: HookContext | None,
    project_id: uuid.UUID | None,
) -> HookCheck:
    custom = cset.custom_types(db)
    if code not in ref.PERSONNEL_HOOK_CODES and code not in custom:
        return HookCheck(P.unknown_code, reason_code=R.UNKNOWN_CODE.value)
    types = ref.satisfying_types(code) or [code]
    s = cset.get(db, project_id) if project_id else None
    critical_code = code in cset.critical_codes(s) if s else code in ref.DEFAULT_CRITICAL_CODES
    pcs = validity.best_personnel(db, worker_id, types, at, project_id, critical_code or None)
    pc, ev = pcs.cert, pcs.ev
    if pc is None or not ev.in_force:
        return _no(
            ev.reason or R.CERT_MISSING,
            ev.hard_stop,
            ref=pc.cert_no if pc else None,
            valid_until=ev.valid_until,
        )
    kw: dict[str, Any] = {"ref": pc.cert_no, "valid_until": ev.valid_until}
    limitations = list(pc.limitations or [])
    conds = []
    for x in limitations:
        lc = PersonnelLimitationCode(x["code"])
        en, ar = ref.LIMP_TEXT[lc]
        if x.get("text"):
            en, ar = f"{en} — {x['text']}", f"{ar} — {x['text']}"
        conds.append(condition(lc.value, None, en, ar, pc.cert_no))
    kw["conditions"] = tuple(conds)
    critical = bool(ctx and ctx.critical)
    role = ctx.crew_role if ctx else None
    # PC-7 scope with the context
    if ctx is not None:
        item = (
            _ctx_item(db, ctx)
            if (ctx.equipment_item_id or ctx.vehicle_id or ctx.equipment_tag)
            else None
        )
        if item is not None and code in ref.OPERATOR_CODES:
            if pc.scope_categories and item.category.value not in pc.scope_categories:
                return HookCheck(P.not_met, reason_code=R.CERT_SCOPE_MISMATCH.value, **kw)
            cap = ctx.rated_capacity_t or item.rated_capacity_t
            if pc.max_capacity_t is not None and cap is not None and cap > pc.max_capacity_t:
                return HookCheck(P.not_met, reason_code=R.CERT_SCOPE_MISMATCH.value, **kw)
        if pc.cert_type == "RIGGER" and critical and s is not None:
            lvl = LEVEL_RANK.get(pc.level) if pc.level else 0
            if (lvl or 0) < s.rigger_level_critical_min:
                return HookCheck(P.not_met, reason_code=R.CERT_SCOPE_MISMATCH.value, **kw)
        if code == "SCAFFOLDER" and ctx.scaffold_design and pc.level != CertLevel.advanced:
            return HookCheck(P.not_met, reason_code=R.CERT_SCOPE_MISMATCH.value, **kw)
    # PC-8
    key_lift_role = role in ref.KEY_LIFT_ROLES
    restricted = [
        x
        for x in limitations
        if x.get("code")
        in (
            PersonnelLimitationCode.supervised_only.value,
            PersonnelLimitationCode.trainee_logbook.value,
        )
    ]
    if restricted and key_lift_role and critical:
        return HookCheck(P.not_met, reason_code=R.CERT_LIMITATION.value, **kw)
    status = P.expiring if ev.expiring else P.met
    reason = None
    # PC-13: card restriction pointer for key roles until reviewed (no medical detail)
    if (
        pc.medical_restriction_on_card
        and pc.restriction_reviewed_at is None
        and (role is None or key_lift_role or role in _KEY_ROLES)
    ):
        reason = R.CARD_RESTRICTION_REVIEW.value
    elif ev.window_until is not None:
        reason = R.CERT_UNVERIFIED.value
    return HookCheck(status, reason_code=reason, **kw)


def avp_hook_until(
    db: Session, vehicle_id: uuid.UUID, project_id: uuid.UUID, at: datetime
) -> date | None:
    """HK4-11: valid_until of the linked item's current certificate line joins the AVP
    effective validity (Phase 2 X3) as limiting factor `equipment_certificate` once the
    equipment provider is registered on the project; None when there is nothing to join."""
    from app.services.cert import policy as cpolicy  # noqa: PLC0415

    d = acommon.local_day(at)
    if cpolicy.active_state(db, project_id, HookKind.equipment_certificate, d) is None:
        return None
    item = db.scalar(select(EquipmentItem).where(EquipmentItem.vehicle_id == vehicle_id))
    if item is None:
        return None
    return validity.current_line(db, item.id, at, project_id).ev.valid_until


def _key_roles() -> set[str]:
    from app.core.ptw_enums import KEY_CREW_ROLES  # noqa: PLC0415

    return {r.value for r in KEY_CREW_ROLES}


_KEY_ROLES = _key_roles()


def check(
    db: Session,
    subject_type: HookSubjectType,
    subject_id: uuid.UUID,
    kind: HookKind,
    code: str,
    at: datetime,
    ctx: HookContext | None,
    project_id: uuid.UUID | None,
) -> HookCheck:
    if kind == HookKind.equipment_certificate:
        return check_equipment(db, subject_type, subject_id, code, at, ctx)
    if subject_type != HookSubjectType.worker:
        return _no(R.CERT_MISSING)
    return check_personnel(db, subject_id, code, at, ctx, project_id)
