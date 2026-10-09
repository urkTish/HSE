# ruff: noqa: E501
"""PT-16 blockers and permit warnings, crew eligibility (PT-8, HK3-1…HK3-3) and the automatic
suspension of a live permit that gains a blocker (SH-2).

`evaluate` is side-effect free except for the crew lines' eligibility fields; `refresh` stores
the result on the permit (blockers, warnings, high_risk, critical_lift) and suspends an
Issued/Active permit whose new blockers include an AUTO_SUSPEND code."""

import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    CredentialReason,
    CrewMemberStatus,
    EligibilityContext,
    GateReasonCode,
    HookKind,
    HookSubjectType,
    ObstacleStatus,
    RequirementStatus,
    WapStatus,
)
from app.core.clock import now, today
from app.core.enums import ContractorStatus, NotificationKind, ZoneType
from app.core.ptw_enums import (
    KEY_CREW_ROLES,
    PERMIT_LIVE,
    PERMIT_TERMINAL,
    AppointmentDiscipline,
    AppointmentFunction,
    ChecklistAnswer,
    CrewLineStatus,
    DocumentType,
    EquipmentCategory,
    EquipmentUse,
    ExemptionKind,
    ExemptionStatus,
    Exposure,
    GasTestResult,
    GasTestType,
    JsaStatus,
    PermitBlocker,
    PermitStatus,
    PermitType,
    PermitWarningCode,
    PtwCrewRole,
    StatusReason,
    VoltageClass,
    WorkCondition,
)
from app.models import (
    AccessSettings,
    GasTest,
    ObstacleClearance,
    Permit,
    PermitCrew,
    PermitDocument,
    PermitEquipment,
    PermitExemption,
    PermitRecord,
    PermitShift,
    PermitSuspension,
    Project,
    PtwAppointment,
    Vehicle,
    Wap,
    WapCrew,
    Worker,
)
from app.services.access import common as acommon
from app.services.access import eligibility as elig
from app.services.access import hooks as ahooks
from app.services.access import waps as wap_svc
from app.services.access import windows as wnd
from app.services.ptw import common, rules
from app.services.ptw import config as cfg
from app.services.ptw import facts as facts_mod
from app.services.ptw import reference as ref

B = PermitBlocker
W = PermitWarningCode
T = PermitType
R = PtwCrewRole
RS = RequirementStatus

VEHICLE_EQUIPMENT = {
    "mobile_crane": EquipmentCategory.mobile_crane,
    "crawler_crane": EquipmentCategory.crawler_crane,
    "mewp": EquipmentCategory.mewp,
}
NOTAM_WAP_CODES = {"NOTAM_NOT_ISSUED", "NOTAM_NOT_COVERING_WINDOW"}
POST_ALARM_REASONS = {StatusReason.gas_test_failed, StatusReason.gas_alarm}


@dataclass
class Ctx:
    """Evaluation context. `start` = evaluating the start of a shift (Issue, Start, Revalidate,
    Resume, handover); it adds the time-bound checks (window, gas start validity, personal
    locks, wind reading, midday ban now)."""

    at: datetime
    start: bool = False
    crew_present: list[uuid.UUID] | None = None
    wind_ms: Decimal | None = None
    shift_end: datetime | None = None
    evaluate_crew: bool = True
    gas_after: datetime | None = None


@dataclass
class Result:
    facts: facts_mod.Facts
    blockers: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def add(
        self, code: PermitBlocker, detail: str | None = None, ref_: str | None = None, **extra: Any
    ) -> None:
        for b in self.blockers:
            if b["code"] == code.value and b.get("ref") == ref_ and b.get("detail") == detail:
                return
        row = common.blocker_json(code, detail, ref_)
        row.update(extra)
        self.blockers.append(row)

    def warn(
        self, code: PermitWarningCode, detail: str | None = None, ref_: str | None = None
    ) -> None:
        row = {"code": code.value, "detail": detail, "ref": ref_}
        if row not in self.warnings:
            self.warnings.append(row)

    @property
    def codes(self) -> list[PermitBlocker]:
        out: list[PermitBlocker] = []
        for b in self.blockers:
            c = PermitBlocker(b["code"])
            if c not in out:
                out.append(c)
        return sorted(out, key=lambda c: ref.BLOCKER_ORDER[c])

    def approve_rows(self) -> list[dict[str, Any]]:
        return [b for b in self.blockers if PermitBlocker(b["code"]) in ref.APPROVE_TIME]


# ---- small lookups -------------------------------------------------------------------------------


def records(db: Session, permit_id: uuid.UUID, kind: str) -> list[PermitRecord]:
    return list(
        db.scalars(
            select(PermitRecord)
            .where(PermitRecord.permit_id == permit_id, PermitRecord.kind == kind)
            .order_by(PermitRecord.at, PermitRecord.created_at)
        )
    )


def crew_lines(
    db: Session, permit_id: uuid.UUID, include_removed: bool = False
) -> list[PermitCrew]:
    stmt = select(PermitCrew).where(PermitCrew.permit_id == permit_id)
    if not include_removed:
        stmt = stmt.where(PermitCrew.status != CrewLineStatus.removed)
    return list(db.scalars(stmt.order_by(PermitCrew.created_at)))


def equipment_lines(db: Session, permit_id: uuid.UUID) -> list[PermitEquipment]:
    return list(
        db.scalars(
            select(PermitEquipment)
            .where(PermitEquipment.permit_id == permit_id)
            .order_by(PermitEquipment.created_at)
        )
    )


def documents(db: Session, permit_id: uuid.UUID) -> list[PermitDocument]:
    return list(
        db.scalars(
            select(PermitDocument)
            .where(PermitDocument.permit_id == permit_id)
            .order_by(PermitDocument.added_at)
        )
    )


def current_shift(db: Session, permit: Permit) -> PermitShift | None:
    s = db.get(PermitShift, permit.current_shift_id) if permit.current_shift_id else None
    return s if s is not None and s.ended_at is None else None


def open_suspension(db: Session, permit: Permit) -> PermitSuspension | None:
    return db.scalar(
        select(PermitSuspension)
        .where(PermitSuspension.permit_id == permit.id, PermitSuspension.resumed_at.is_(None))
        .order_by(PermitSuspension.suspended_at.desc())
        .limit(1)
    )


def exemption(
    db: Session, permit: Permit, kind: ExemptionKind, day: date | None = None
) -> PermitExemption | None:
    for e in db.scalars(
        select(PermitExemption).where(
            PermitExemption.permit_id == permit.id,
            PermitExemption.kind == kind,
            PermitExemption.status == ExemptionStatus.granted,
        )
    ):
        if day is None or (
            (e.valid_from is None or e.valid_from <= day)
            and (e.valid_to is None or day <= e.valid_to)
        ):
            return e
    return None


def midday_exempt_all(db: Session, permit: Permit, days: list[date]) -> bool:
    return all(exemption(db, permit, ExemptionKind.midday_ban, d) is not None for d in days)


def worker_no(db: Session, worker_id: uuid.UUID | None) -> str | None:
    w = db.get(Worker, worker_id) if worker_id else None
    return w.worker_no if w else None


def latest_wind(db: Session, permit: Permit) -> Decimal | None:
    rows = records(db, permit.id, "wind")
    return Decimal(str(rows[-1].data["speed_ms"])) if rows else None


def wind_limit(f: facts_mod.Facts) -> Decimal:
    s = f.settings
    return rules.wind_limit(f.sec(T.lifting), s.lift_wind_limit_ms, s.man_basket_wind_limit_ms)


def ban_dates(f: facts_mod.Facts, after: datetime | None = None) -> list[date]:
    """HT-1/HT-2: ban dates on which a window of an outdoor_direct_sun permit overlaps the ban
    hours (only the window parts after `after` when given: a window already partly worked is
    judged on what remains, so a Resume at 15:00 is allowed)."""
    p = f.permit
    if p.exposure != Exposure.outdoor_direct_sun:
        return []
    s = f.settings
    out: list[date] = []
    for st, en in common.instances(p, start=after):
        d = rules.overlaps_ban(st, en, s.midday_ban_period, s.midday_ban_hours)
        if d is not None and d not in out:
            out.append(d)
    return out


def in_ban_now(f: facts_mod.Facts, at: datetime) -> date | None:
    p = f.permit
    if p.exposure != Exposure.outdoor_direct_sun:
        return None
    s = f.settings
    d = acommon.local_day(at)
    if not rules.in_season(d, s.midday_ban_period["start_mmdd"], s.midday_ban_period["end_mmdd"]):
        return None
    bs, be = rules.ban_interval(d, s.midday_ban_hours)
    return d if bs <= at < be else None


# ---- WAP (AW-2…AW-4) ------------------------------------------------------------------------------


def airside_zone_ids(f: facts_mod.Facts) -> list[uuid.UUID]:
    return [z.id for z in f.zones if z.zone_type == ZoneType.airside]


def linked_wap(db: Session, permit: Permit, f: facts_mod.Facts, at: datetime) -> Wap | None:
    """The WAP the permit relies on: the section's wap_id, else the first linked WAP, else an
    Active WAP of the engagement tree covering every airside zone."""
    ids: list[uuid.UUID] = []
    wid = f.sec(T.airside_works).get("wap_id")
    if wid:
        ids.append(uuid.UUID(str(wid)))
    ids += [i for i in permit.linked_wap_ids or [] if i not in ids]
    for i in ids:
        w = db.get(Wap, i)
        if w is not None:
            return w
    zs = airside_zone_ids(f)
    if not zs:
        return None
    cands = wap_svc.active_at(db, zs[0], permit.engagement_id, at)
    for w in cands:
        if all(z in (w.zone_ids or []) for z in zs):
            return w
    return None


def wap_instances(w: Wap, start: date, end: date) -> list[tuple[datetime, datetime]]:
    return [
        (i.start_utc, i.end_utc)
        for i in wnd.instances(wnd.parse(w.windows or []), w.valid_from, w.valid_to, start, end)
    ]


def outside_wap_windows(permit: Permit, w: Wap, after: datetime | None = None) -> str | None:
    """AW-4: every permit window instance (ending after `after`) lies inside a WAP window
    instance. Returns the first offending instance label."""
    inst = [i for i in common.instances(permit) if after is None or i[1] > after]
    if not inst:
        return None
    d0 = acommon.local_day(inst[0][0]) - timedelta(days=1)
    d1 = acommon.local_day(inst[-1][1]) + timedelta(days=1)
    wi = wap_instances(w, d0, d1)
    for s, e in inst:
        if not any(ws <= s and e <= we for ws, we in wi):
            return str(
                acommon.local_day(s).isoformat()
                + " "
                + s.astimezone(acommon.RIYADH).strftime("%H:%M")
            )
    return None


def _wap_checks(
    db: Session,
    permit: Permit,
    f: facts_mod.Facts,
    ctx: Ctx,
    res: Result,
    crew_ids: list[uuid.UUID],
) -> None:
    zs = airside_zone_ids(f)
    if not zs:
        return
    w = linked_wap(db, permit, f, ctx.at)
    d = acommon.local_day(ctx.at)
    ancestors = acommon.engagement_ancestors(db, permit.engagement_id)
    ok = (
        w is not None
        and w.status == WapStatus.active
        and w.valid_from <= d <= w.valid_to
        and all(z in (w.zone_ids or []) for z in zs)
        and w.engagement_id in ancestors
    )
    if not ok:
        reason = StatusReason.wap_suspended
        if w is not None and w.suspension_reason == CredentialReason.ops_suspension:
            reason = StatusReason.ops_suspension
        res.add(
            B.WAP_NOT_ACTIVE, w.wap_no if w else None, w.wap_no if w else None, reason=reason.value
        )
    if w is None:
        return
    if any(b.get("code") in NOTAM_WAP_CODES for b in w.blockers or []):
        res.add(B.NOTAM_NOT_IN_EFFECT, w.wap_no, w.wap_no)
    if crew_ids:
        on = {
            c.worker_id
            for c in db.scalars(
                select(WapCrew).where(
                    WapCrew.wap_id == w.id,
                    WapCrew.removed_at.is_(None),
                    WapCrew.status == CrewMemberStatus.included,
                )
            )
        }
        for wid in crew_ids:
            if wid not in on:
                res.add(
                    B.WAP_CREW_MISSING,
                    worker_no(db, wid),
                    worker_no(db, wid),
                    reason=StatusReason.wap_suspended.value,
                )
    bad = outside_wap_windows(permit, w, ctx.at)
    if bad:
        res.add(B.OUTSIDE_WAP_WINDOW, f"{w.wap_no} {bad}", w.wap_no)


# ---- obstacle clearance (LF-9) -------------------------------------------------------------------


def obs_matches(
    o: ObstacleClearance, line: PermitEquipment, zone_ids: list[uuid.UUID], days: list[date]
) -> bool:
    if o.status not in (ObstacleStatus.approved, ObstacleStatus.approved_with_conditions):
        return False
    if line.vehicle_id is not None:
        if o.vehicle_id != line.vehicle_id:
            return False
    elif not line.tag or line.tag.lower() not in (o.equipment_desc or "").lower():
        return False
    if o.zone_id is not None and o.zone_id not in zone_ids:
        return False
    if o.valid_from is None or o.valid_to is None:
        return False
    return all(o.valid_from <= d <= o.valid_to for d in days)


def equipment_height(db: Session, line: PermitEquipment) -> tuple[Decimal | None, str]:
    if line.vehicle_id is not None:
        v = db.get(Vehicle, line.vehicle_id)
        h = line.max_working_height_m or (v.max_working_height_m_agl if v else None)
        return (Decimal(str(h)) if h is not None else None), (v.vehicle_no if v else "vehicle")
    h = line.max_working_height_m
    return (Decimal(str(h)) if h is not None else None), line.tag or "equipment"


def obs_required(
    db: Session, permit: Permit, f: facts_mod.Facts
) -> list[tuple[PermitEquipment, str]]:
    """Lifting appliances whose height needs a Phase 2 obstacle clearance (LF-9)."""
    if not f.has(T.lifting):
        return []
    project = db.get(Project, permit.project_id)
    a = db.get(AccessSettings, permit.project_id)
    threshold = Decimal(str(a.obstacle_height_threshold_m)) if a else Decimal("45.00")
    out = []
    for line in equipment_lines(db, permit.id):
        if line.use != EquipmentUse.lifting_appliance:
            continue
        h, label = equipment_height(db, line)
        if h is None:
            continue
        need = False
        for z in f.zone_facts:
            if z.airside and z.max_equipment_height_m is not None and h > z.max_equipment_height_m:
                need = True
        if project is not None and not project.is_airport and h >= threshold:
            need = True
        if need:
            out.append((line, label))
    return out


def _obs_checks(db: Session, permit: Permit, f: facts_mod.Facts, res: Result) -> None:
    need = obs_required(db, permit, f)
    if not need:
        return
    linked = [o for o in (db.get(ObstacleClearance, i) for i in permit.linked_obs_ids or []) if o]
    days = common.permit_days(permit)
    for line, label in need:
        if not any(obs_matches(o, line, list(permit.zone_ids or []), days) for o in linked):
            res.add(B.OBS_CLEARANCE_REQUIRED, label, label)


# ---- crew eligibility (PT-8) ---------------------------------------------------------------------


def role_hooks(
    db: Session, permit: Permit, f: facts_mod.Facts
) -> dict[PtwCrewRole, list[tuple[HookKind, str]]]:
    out: dict[PtwCrewRole, list[tuple[HookKind, str]]] = {}
    for t in f.types:
        for role, items in cfg.type_lists(db, permit.project_id, PermitType(t))["crew"].items():
            lst = out.setdefault(role, [])
            for pair in items:
                if pair not in lst:
                    lst.append(pair)
    return out


def equipment_hooks(
    db: Session, permit: Permit, f: facts_mod.Facts
) -> dict[EquipmentCategory, list[tuple[HookKind, str]]]:
    out: dict[EquipmentCategory, list[tuple[HookKind, str]]] = {}
    for t in f.types or [T.general.value]:
        for cat, items in cfg.type_lists(db, permit.project_id, PermitType(t))["equip"].items():
            lst = out.setdefault(cat, [])
            for pair in items:
                if pair not in lst:
                    lst.append(pair)
    return out


def _item_json(it: elig.Item, zone_id: uuid.UUID | None) -> dict[str, Any]:
    d = it.to_schema().model_dump(mode="json")
    d["zone_id"] = str(zone_id) if zone_id else None
    return d


def evaluate_line(
    db: Session,
    permit: Permit,
    f: facts_mod.Facts,
    line: PermitCrew,
    at: datetime,
    shift_end: datetime | None,
    hooks_by_role: dict[PtwCrewRole, list[tuple[HookKind, str]]],
    access: AccessSettings,
) -> None:
    w = db.get(Worker, line.worker_id)
    if w is None:
        return
    items: list[tuple[uuid.UUID | None, elig.Item]] = []
    seen: set[tuple[Any, ...]] = set()
    for z in f.zones:
        ev = elig.evaluate(
            db,
            w,
            z,
            at,
            EligibilityContext.ptw,
            escort_ok=bool(line.escort_worker_id),
            with_wap=False,
        )
        for it in ev.items:
            key = (it.kind, it.code, it.status, it.reason)
            if key in seen and it.status == RS.met:
                continue
            seen.add(key)
            items.append((z.id, it))
    extra = list(hooks_by_role.get(line.crew_role, []))
    if (
        f.has(T.work_at_height)
        and rules.wah_arrest(f.sec(T.work_at_height))
        and ref.WAH_ARREST_HOOK not in extra
    ):
        extra.append(ref.WAH_ARREST_HOOK)
    ctx = hook_context(permit, f, crew_role=line.crew_role.value)
    for kind, code in extra:
        items.append(
            (None, elig.hook_item(db, HookSubjectType.worker, w.id, kind, code, at, access, ctx))
        )
    deny: list[str] = []
    for _z, it in items:
        if it.status in (RS.not_met, RS.not_evaluated):
            deny.append((it.reason or GateReasonCode.HOOK_NOT_MET).value)
    if shift_end is not None and not deny:
        end_day = acommon.local_day(shift_end)
        for _z, it in items:
            if (
                it.status in (RS.met, RS.expiring)
                and it.valid_until is not None
                and it.valid_until < end_day
            ):
                deny.append("EXPIRES_DURING_SHIFT")
                break
    from app.services.heat import ptw as heat_ptw  # noqa: PLC0415

    heat_item = heat_ptw.restriction_item(db, permit, w.id, at)  # 6b PH-6
    if heat_item is not None:
        deny.insert(0, "HEAT_RESTRICTION")
    line.eligibility = [_item_json(it, z) for z, it in items] + ([heat_item] if heat_item else [])
    line.eligible = not deny
    line.evaluated_at = at
    key_role = line.crew_role in KEY_CREW_ROLES
    if deny:
        line.excluded_reason = deny[0]
        if not key_role and line.status == CrewLineStatus.listed:
            line.status = CrewLineStatus.excluded
            common.tell(
                db,
                permit,
                common.permit_people(db, permit, issuer=False, reps=True),
                NotificationKind.crew_excluded,
                f"Crew member {w.worker_no} excluded ({deny[0]})",
                f"تم استبعاد عضو الطاقم {w.worker_no} ({deny[0]})",
            )
    else:
        line.excluded_reason = None
        if line.status == CrewLineStatus.excluded:
            line.status = CrewLineStatus.listed


def hook_context(permit: Permit, f: facts_mod.Facts, **kw: Any) -> ahooks.HookContext:
    """HK4-8 / 3-ptw v1.1 §11.4: the context passed on every crew and equipment hook call."""
    return ahooks.HookContext(
        project_id=permit.project_id,
        zone_id=f.zones[0].id if f.zones else None,
        permit_id=permit.id,
        critical=f.critical,
        **kw,
    )


def _lift_capacity(f: facts_mod.Facts) -> Decimal | None:
    sec = f.sec(T.lifting) if f.has(T.lifting) else {}
    v = sec.get("rated_capacity_t")
    return Decimal(str(v)) if v not in (None, "") else None


def _line_eqc(db: Session, line: PermitEquipment, item: Any) -> Any:
    """The Phase 4 category (EQC) of an equipment line: the item's, else mapped from the
    Phase 3 EQ category or the Phase 2 vehicle category (single mapping only)."""
    from app.services.cert import reference as cref  # noqa: PLC0415

    if item is not None:
        return item.category
    if line.category is not None:
        return cref.PTW_TO_EQC.get(line.category)
    if line.vehicle_id is not None:
        v = db.get(Vehicle, line.vehicle_id)
        allowed = cref.VC_TO_EQC.get(v.category) if v else None
        if allowed and len(allowed) == 1:
            return next(iter(allowed))
    return None


def operator_code(db: Session, line: PermitEquipment) -> str | None:
    """HK4-9: the EQC operator code of the line's category (None when it has none)."""
    from app.models import EquipmentItem  # noqa: PLC0415
    from app.services.cert import reference as cref  # noqa: PLC0415

    item = db.get(EquipmentItem, line.equipment_item_id) if line.equipment_item_id else None
    q = _line_eqc(db, line, item)
    e = cref.EQC.get(q) if q is not None else None
    return e.operator_code if e else None


def resolve_line_item(db: Session, permit: Permit, line: PermitEquipment) -> None:
    """§11.4 item 1: equipment_item_id resolved from the tag (or vehicle link) when blank."""
    from app.core.cert_enums import EquipmentDeploymentStatus as Eds  # noqa: PLC0415
    from app.models import EquipmentDeployment, EquipmentItem  # noqa: PLC0415

    if line.equipment_item_id is None:
        item_id = None
        if line.vehicle_id is not None:
            item_id = db.scalar(
                select(EquipmentItem.id).where(EquipmentItem.vehicle_id == line.vehicle_id)
            )
        elif line.tag:
            dep = db.scalar(
                select(EquipmentDeployment)
                .where(
                    EquipmentDeployment.project_id == permit.project_id,
                    func.upper(EquipmentDeployment.tag) == line.tag.strip().upper(),
                    EquipmentDeployment.status.notin_([Eds.demobilised, Eds.cancelled]),
                )
                .limit(1)
            )
            if dep is not None:
                item_id = dep.equipment_id
                line.deployment_id = dep.id
        line.equipment_item_id = item_id
    if line.equipment_item_id is not None and line.deployment_id is None:
        line.deployment_id = db.scalar(
            select(EquipmentDeployment.id)
            .where(
                EquipmentDeployment.equipment_id == line.equipment_item_id,
                EquipmentDeployment.project_id == permit.project_id,
                EquipmentDeployment.status.notin_([Eds.demobilised, Eds.cancelled]),
            )
            .limit(1)
        )


def _merge_conditions(dst: list[dict[str, Any]], items: list[dict[str, Any]]) -> None:
    for it in items:
        for c in it.get("conditions") or []:
            if c not in dst:
                dst.append(c)


def evaluate_equipment(
    db: Session,
    line: PermitEquipment,
    at: datetime,
    hooks: dict[EquipmentCategory, list[tuple[HookKind, str]]],
    access: AccessSettings,
    permit: Permit | None = None,
    f: facts_mod.Facts | None = None,
) -> None:
    """HK3-2 equipment hooks with the HK-3 context (HK4-8) and the operator binding (HK4-9).
    Results, limitations and the certified SWL are kept on the line (§11.4)."""
    cat = line.category
    subject = HookSubjectType.equipment_tag
    sid = line.id
    v = db.get(Vehicle, line.vehicle_id) if line.vehicle_id is not None else None
    if line.vehicle_id is not None:
        cat = VEHICLE_EQUIPMENT.get(v.category.value) if v else None
        subject = HookSubjectType.vehicle
        sid = line.vehicle_id
    ctx = None
    p4 = False
    if permit is not None and f is not None:
        from app.services.cert import policy as cpolicy  # noqa: PLC0415

        p4 = cpolicy.enabled(db, permit.project_id)
        if p4:
            resolve_line_item(db, permit, line)
        use = line.use.value
        if (
            line.use == EquipmentUse.lifting_appliance
            and f.has(T.lifting)
            and f.sec(T.lifting).get("personnel_lift")
        ):
            use = "personnel_lift"
        ctx = hook_context(
            permit,
            f,
            use=use,
            vehicle_id=line.vehicle_id,
            equipment_category=line.category.value if line.category else None,
            equipment_tag=line.tag,
            equipment_item_id=line.equipment_item_id,
            rated_capacity_t=_lift_capacity(f)
            if line.use == EquipmentUse.lifting_appliance
            else None,
            operator_worker_id=line.operator_worker_id,
        )
    out = []
    for kind, code in hooks.get(cat, []) if cat else []:
        out.append(_item_json(elig.hook_item(db, subject, sid, kind, code, at, access, ctx), None))
    line.hooks = out
    ops: list[dict[str, Any]] = []
    op = operator_code(db, line) if p4 else None
    if op and line.operator_worker_id is not None and ctx is not None:
        octx = replace(ctx, crew_role="crane_operator" if op == "CRANE-OPERATOR" else "driver")
        ops.append(
            _item_json(
                elig.hook_item(
                    db,
                    HookSubjectType.worker,
                    line.operator_worker_id,
                    HookKind.personnel_certificate,
                    op,
                    at,
                    access,
                    octx,
                ),
                None,
            )
        )
    mcode = (
        ref.MEDICAL_OPERATOR_CODES.get(line.category.value)
        if line.category is not None and line.operator_worker_id is not None and permit is not None
        else None
    )
    if mcode and permit is not None and line.operator_worker_id is not None:
        from app.services.med import common as mcommon  # noqa: PLC0415

        if mcommon.registered(db, permit.project_id):
            mctx = ctx or ahooks.HookContext(project_id=permit.project_id)
            ops.append(
                _item_json(
                    elig.hook_item(
                        db, HookSubjectType.worker, line.operator_worker_id,
                        HookKind.medical_fitness, mcode, at, access, mctx,
                    ),
                    None,
                )
            )  # fmt: skip
    line.operator_hooks = ops
    conds: list[dict[str, Any]] = []
    _merge_conditions(conds, out)
    _merge_conditions(conds, ops)
    line.conditions = conds
    swl = next((it.get("swl_t") for it in out if it.get("swl_t") is not None), None)
    line.swl_t = Decimal(str(swl)) if swl is not None else None


def evaluate_scaffold(
    db: Session, permit: Permit, f: facts_mod.Facts, at: datetime, access: AccessSettings
) -> None:
    """SF-1 / §11.4 item 4: the WAH scaffold_tag_ref resolved on the Phase 4 scaffold register
    of the permit's project; yellow-tag restrictions are copied into permit conditions."""
    from app.services.cert import policy as cpolicy  # noqa: PLC0415

    tag = f.sec(T.work_at_height).get("scaffold_tag_ref") if f.has(T.work_at_height) else None
    if not tag or not cpolicy.enabled(db, permit.project_id, HookKind.equipment_certificate):
        permit.scaffold_hooks = []
        return
    ctx = hook_context(permit, f, equipment_category=EquipmentCategory.scaffold.value,
                       equipment_tag=str(tag), use=EquipmentUse.access_equipment.value)  # fmt: skip
    it = elig.hook_item(
        db,
        HookSubjectType.equipment_tag,
        permit.id,
        HookKind.equipment_certificate,
        "SCAFFOLD-TAG",
        at,
        access,
        ctx,
    )
    permit.scaffold_hooks = [_item_json(it, None)]


def _crew_checks(
    db: Session, permit: Permit, f: facts_mod.Facts, ctx: Ctx, res: Result, lines: list[PermitCrew]
) -> None:
    if permit.status == PermitStatus.draft and not ctx.start:
        return
    access = acommon.settings(db, permit.project_id)
    if ctx.evaluate_crew:
        hooks = role_hooks(db, permit, f)
        for line in lines:
            evaluate_line(db, permit, f, line, ctx.at, ctx.shift_end, hooks, access)
        eh = equipment_hooks(db, permit, f)
        conds: list[dict[str, Any]] = []
        for e in equipment_lines(db, permit.id):
            evaluate_equipment(db, e, ctx.at, eh, access, permit, f)
            _merge_conditions(conds, [{"conditions": e.conditions or []}])
        evaluate_scaffold(db, permit, f, ctx.at, access)
        _merge_conditions(conds, list(permit.scaffold_hooks or []))
        for line in lines:
            _merge_conditions(conds, [i for i in line.eligibility or [] if i.get("conditions")])
        permit.hook_conditions = conds
        db.flush()
    evaluated = [x for x in lines if x.eligible is not None]
    for line in lines:
        wno = worker_no(db, line.worker_id)
        for it in line.eligibility or []:
            if it.get("reason_code") == "HOOK_NOT_AVAILABLE":
                res.warn(W.HOOK_NOT_AVAILABLE, it.get("code"), wno)
            elif it.get("reason_code") == "HOOK_NOT_MET_WARN":
                res.warn(W.HOOK_NOT_MET_WARN, _warn_detail(it), wno)
            elif it.get("status") == RS.expiring.value:
                res.warn(W.EXPIRING_7D, it.get("code") or it.get("kind"), wno)
        if line.eligible is False:
            if line.crew_role in KEY_CREW_ROLES:
                reasons = [
                    i.get("reason_code")
                    for i in line.eligibility or []
                    if i.get("status") in (RS.not_met.value, RS.not_evaluated.value)
                ]
                if reasons and all(r in (None, "HOOK_NOT_MET") for r in reasons):
                    res.add(B.HOOK_NOT_MET, f"{line.crew_role.value} {wno}", wno)
                else:
                    res.add(
                        B.KEY_ROLE_INELIGIBLE,
                        f"{line.crew_role.value} {wno} ({line.excluded_reason})",
                        wno,
                    )
            else:
                res.warn(W.CREW_EXCLUDED, line.excluded_reason, wno)
            if line.excluded_reason == "EXPIRES_DURING_SHIFT":
                res.warn(W.EXPIRES_DURING_SHIFT, line.crew_role.value, wno)
    if evaluated and not any(x.eligible for x in evaluated):
        res.add(B.NO_ELIGIBLE_CREW)
    for e in equipment_lines(db, permit.id):
        label = e.tag or ("vehicle" if e.vehicle_id else "equipment")
        if e.vehicle_id:
            v = db.get(Vehicle, e.vehicle_id)
            label = v.vehicle_no if v else label
        _hook_results(res, list(e.hooks or []), label)
        if e.operator_worker_id is not None:
            _hook_results(res, list(e.operator_hooks or []), worker_no(db, e.operator_worker_id))
    _hook_results(res, list(permit.scaffold_hooks or []), "scaffold")


def _warn_detail(it: dict[str, Any]) -> str:
    if it.get("hook_kind") == HookKind.medical_fitness.value:  # P6-7: never the medical reason
        return f"{it.get('code')} (HSE check)"
    return f"{it.get('code')} ({it.get('hook_reason_code') or 'HOOK_NOT_MET'})"


def _hook_results(res: Result, items: list[dict[str, Any]], label: str | None) -> None:
    """HK4-4: not_met (block stage or hard stop) → blocker HOOK_NOT_MET; transition-stage
    warn → warning HOOK_NOT_MET_WARN; expiring → EXPIRING_7D."""
    for it in items:
        if it.get("reason_code") == "HOOK_NOT_AVAILABLE":
            res.warn(W.HOOK_NOT_AVAILABLE, it.get("code"), label)
        elif it.get("status") in (RS.not_met.value, RS.not_evaluated.value):
            res.add(B.HOOK_NOT_MET, f"{it.get('code')} {label}", label)
        elif it.get("reason_code") == "HOOK_NOT_MET_WARN":
            res.warn(W.HOOK_NOT_MET_WARN, f"{_warn_detail(it)} {label}", label)
        elif it.get("status") == RS.expiring.value:
            res.warn(W.EXPIRING_7D, it.get("code"), label)


# ---- roles and appointments (PR-2…PR-4, §3.1) ------------------------------------------------------


def role_appointment_types(
    role: PtwCrewRole, f: facts_mod.Facts, appt: PtwAppointment | None = None
) -> list[str]:
    if role == R.gas_tester:
        return list(f.gas_types) or [t for t in f.types if t != T.airside_works.value][:1]
    if role == R.competent_person:
        if (
            appt is not None
            and appt.discipline == AppointmentDiscipline.fall_protection_competent_person
        ):
            return [T.work_at_height.value]
        return [T.excavation.value] if f.has(T.excavation) else [T.work_at_height.value]
    if role == R.rpo:
        return [T.radiography.value]
    if role == R.lift_supervisor:
        return [T.lifting.value]
    return []


def appointment_day(permit: Permit, at: datetime) -> date:
    days = common.permit_days(permit)
    d = acommon.local_day(at)
    return min(max(d, days[0]), days[-1]) if days else d


def check_role_appointment(
    db: Session, permit: Permit, f: facts_mod.Facts, line: PermitCrew, day: date
) -> str | None:
    """PR-4: returns an error text, or None when valid."""
    need = ref.ROLE_APPOINTMENT.get(line.crew_role)
    if need is None:
        return None
    if line.appointment_id is None:
        return "appointment required"
    a = db.get(PtwAppointment, line.appointment_id)
    if a is None or a.function != need[0]:
        return "wrong appointment"
    if need[1] and (a.discipline is None or a.discipline.value not in need[1]):
        return "wrong discipline"
    holder_ok = a.holder_worker_id == line.worker_id
    if not holder_ok and a.holder_user_id is not None:
        w = db.get(Worker, line.worker_id)
        holder_ok = bool(w and w.user_id == a.holder_user_id)
    if not holder_ok:
        return "appointment of another person"
    types = role_appointment_types(line.crew_role, f, a)
    if not common.appointment_covers(a, types, permit.site_id, list(permit.zone_ids or []), [day]):
        return f"{a.appointment_no} not valid"
    return None


def has_rpo(db: Session, permit: Permit, lines: list[PermitCrew], day: date) -> bool:
    for x in lines:
        if x.status != CrewLineStatus.listed:
            continue
        if x.crew_role == R.rpo:
            return True
        if common.find_appointment(
            db,
            permit.project_id,
            AppointmentFunction.authorised_person,
            [T.radiography.value],
            permit.site_id,
            permit.zone_ids or [],
            [day],
            worker_id=x.worker_id,
            disciplines=["radiation_protection_officer"],
        ):
            return True
    return False


def _roles_checks(
    db: Session, permit: Permit, f: facts_mod.Facts, ctx: Ctx, res: Result, lines: list[PermitCrew]
) -> None:
    listed = [x for x in lines if x.status == CrewLineStatus.listed]
    have = {x.crew_role for x in listed}
    day = appointment_day(permit, ctx.at)
    for role in f.roles:
        if role == R.rpo:
            if not has_rpo(db, permit, lines, day):
                res.add(B.ROLE_MISSING, role.value)
            continue
        if role == R.supervisor and (role in have or permit.supervisor_worker_id):
            continue
        if role not in have:
            res.add(B.ROLE_MISSING, role.value)
    if f.has(T.lifting) and not (have & {R.rigger, R.signaller}):
        res.add(B.ROLE_MISSING, "rigger / signaller")
    if ctx.start and ctx.crew_present is not None:
        present = set(ctx.crew_present)
        for role in (R.fire_watch, R.standby_person):
            if role in f.roles and not any(
                x.crew_role == role and x.worker_id in present for x in listed
            ):
                res.add(B.ROLE_MISSING, f"{role.value} present")
    # PR-4 crew appointments
    for x in listed:
        msg = check_role_appointment(db, permit, f, x, day)
        if msg:
            res.add(
                B.APPOINTMENT_INVALID,
                f"{x.crew_role.value} {worker_no(db, x.worker_id)}: {msg}",
                worker_no(db, x.worker_id),
            )
        elif x.appointment_id:
            a = db.get(PtwAppointment, x.appointment_id)
            days = common.permit_days(permit)
            if a is not None and days and a.valid_to < days[-1]:
                res.warn(
                    W.APPOINTMENT_EXPIRES,
                    f"{a.appointment_no} {a.valid_to.isoformat()}",
                    a.appointment_no,
                )
    # area authority (PR-3) and issuer (PR-2)
    if (
        permit.area_authority_user_id
        and permit.status != PermitStatus.draft
        and (
            common.find_appointment(
                db,
                permit.project_id,
                AppointmentFunction.area_authority,
                [],
                None,
                permit.zone_ids or [],
                [day],
                user_id=permit.area_authority_user_id,
            )
            is None
            or not _covers_zone_sites(db, permit, permit.area_authority_user_id, day)
        )
    ):
        res.add(B.APPOINTMENT_INVALID, "area authority")
    if permit.issuer_user_id and permit.status not in (
        PermitStatus.draft,
        PermitStatus.requested,
        PermitStatus.reviewed,
    ):
        a = issuer_appointment(db, permit, permit.issuer_user_id, day)
        if a is None:
            res.add(B.APPOINTMENT_INVALID, "issuer")
        elif a.valid_to < common.permit_days(permit)[-1]:
            res.warn(
                W.APPOINTMENT_EXPIRES,
                f"{a.appointment_no} {a.valid_to.isoformat()}",
                a.appointment_no,
            )
    _training_role_checks(db, permit, f, ctx, res)
    # electrical authorised person (EL-2)
    if f.has(T.electrical_isolation):
        el = f.sec(T.electrical_isolation)
        hv = (
            bool(el.get("system_voltage_v"))
            and rules.voltage_class(int(el["system_voltage_v"]), bool(el.get("dc")))
            == VoltageClass.hv
        )
        disc = ["electrical_hv"] if hv else ["electrical_lv", "electrical_hv"]
        if (
            common.find_appointment(
                db,
                permit.project_id,
                AppointmentFunction.authorised_person,
                [T.electrical_isolation.value],
                permit.site_id,
                permit.zone_ids or [],
                [day],
                disciplines=disc,
            )
            is None
        ):
            res.add(B.APPOINTMENT_INVALID, "authorised person (electrical)")


def _training_role_checks(
    db: Session, permit: Permit, f: facts_mod.Facts, ctx: Ctx, res: Result
) -> None:
    """3-ptw v1.2 §11.4 / 5-training HK5-7: PTW-RECEIVER for the receiver and PTW-ISSUER for
    the issuer through the holder's linked worker (worker.user_id), once Phase 5 registered its
    provider on the project. not_met → KEY_ROLE_INELIGIBLE; transition → HOOK_NOT_MET_WARN."""
    from app.services.ptw import config as pcfg  # noqa: PLC0415

    if not pcfg.training_registered(db, permit.project_id):
        return
    access = acommon.settings(db, permit.project_id)
    checks: list[tuple[str, uuid.UUID, tuple[HookKind, str]]] = []
    if permit.receiver_user_id:
        checks.append(("receiver", permit.receiver_user_id, ref.RECEIVER_HOOK))
    if permit.issuer_user_id and permit.status not in (
        PermitStatus.draft,
        PermitStatus.requested,
        PermitStatus.reviewed,
    ):
        for hk in ref.APPOINTMENT_HOOKS.get(AppointmentFunction.issuer, ()):
            checks.append(("issuer", permit.issuer_user_id, hk))
    for label, uid, (kind, code) in checks:
        wid = db.scalar(select(Worker.id).where(Worker.user_id == uid).limit(1))
        hctx = hook_context(permit, f, extra={"role": label})
        it = elig.hook_item(
            db, HookSubjectType.worker, wid or uid, kind, code, ctx.at, access, hctx
        )
        row = _item_json(it, None)
        if (
            it.status in (RS.not_met, RS.not_evaluated)
            and it.reason != GateReasonCode.HOOK_NOT_MET_WARN
        ):
            res.add(B.KEY_ROLE_INELIGIBLE, f"{label} ({_warn_detail(row)})", label)
        elif it.reason == GateReasonCode.HOOK_NOT_MET_WARN:
            res.warn(W.HOOK_NOT_MET_WARN, f"{_warn_detail(row)} {label}", label)
        elif it.reason == GateReasonCode.HOOK_NOT_AVAILABLE:
            res.warn(W.HOOK_NOT_AVAILABLE, code, label)
        elif it.status == RS.expiring:
            res.warn(W.EXPIRING_7D, code, label)


def _covers_zone_sites(db: Session, permit: Permit, user_id: uuid.UUID, day: date) -> bool:
    for a in common.appointments_of(
        db, permit.project_id, AppointmentFunction.area_authority, user_id=user_id
    ):
        if a.site_ids and permit.site_id not in a.site_ids:
            continue
        if common.appointment_covers(a, [], None, permit.zone_ids or [], [day]):
            return True
    return False


def issuer_appointment(
    db: Session, permit: Permit, user_id: uuid.UUID, day: date | None = None
) -> PtwAppointment | None:
    days = [day] if day else common.permit_days(permit)
    return common.find_appointment(
        db,
        permit.project_id,
        AppointmentFunction.issuer,
        list(permit.work_types or []),
        permit.site_id,
        [],
        days,
        user_id=user_id,
    )


# ---- documents / checklists ---------------------------------------------------------------------


def missing_documents(db: Session, permit: Permit, f: facts_mod.Facts) -> list[str]:
    have = {
        d.doc_type
        for d in documents(db, permit.id)
        if d.valid_until is None or d.valid_until >= today()
    }
    out = [d.value for d in f.documents if d not in have]
    el = f.sec(T.electrical_isolation)
    if (
        f.has(T.electrical_isolation)
        and el.get("work_condition", WorkCondition.electrically_safe.value)
        != WorkCondition.energized.value
        and not permit.isolation_cert_ids
    ):
        out.append("isolation_certificate")
    cs = f.sec(T.confined_space)
    if f.has(T.confined_space) and cs.get("isolations_required") and not permit.isolation_cert_ids:
        out.append("isolation_certificate")
    if (
        f.has(T.hot_work)
        and f.sec(T.hot_work).get("fire_system_impairment")
        and DocumentType.fire_impairment_notice not in have
    ):
        pass  # HW-8 is covered by FIRE_IMPAIRMENT_NOT_APPROVED
    return out


def pre_issue_items(db: Session, permit: Permit) -> list[Any]:
    out: list[Any] = []
    types = list(dict.fromkeys([T.general.value, *(permit.work_types or [])]))
    for t in types:
        for c in cfg.type_lists(db, permit.project_id, PermitType(t))["pre"]:
            if c not in out:
                out.append(c)
    return out


def closure_items(db: Session, permit: Permit) -> list[Any]:
    out: list[Any] = []
    for t in permit.work_types or []:
        for c in cfg.type_lists(db, permit.project_id, PermitType(t))["closure"]:
            if c not in out:
                out.append(c)
    return out


def checklist_gaps(db: Session, permit: Permit, kind: str) -> list[str]:
    items = pre_issue_items(db, permit) if kind == "pre_issue" else closure_items(db, permit)
    answers = (permit.checklists or {}).get(kind) or {}
    gaps = []
    for c in items:
        a = answers.get(c.value)
        ans = a.get("answer") if a else None
        na_ok = ref.PRE_ISSUE[c][2] if kind == "pre_issue" else True
        if ans == ChecklistAnswer.yes.value or (ans == ChecklistAnswer.na.value and na_ok):
            continue
        gaps.append(c.value)
    return gaps


# ---- the evaluation ------------------------------------------------------------------------------


def evaluate(db: Session, permit: Permit, ctx: Ctx | None = None) -> Result:
    from app.services.ptw import gas, isolations, jsa, simops  # noqa: PLC0415

    ctx = ctx or Ctx(at=now())
    at = ctx.at
    f = facts_mod.compute(db, permit)
    res = Result(facts=f)
    lines = crew_lines(db, permit.id)
    shift = current_shift(db, permit)
    if ctx.crew_present is None and shift is not None:
        ctx.crew_present = list(shift.crew_present or [])
    if ctx.shift_end is None and shift is not None:
        ctx.shift_end = shift.planned_end_at
    active = permit.status == PermitStatus.active

    # JSA (JS-1, JS-6, JS-7)
    j = jsa.current_for_permit(db, permit)
    if j is None:
        res.add(B.JSA_MISSING)
    else:
        early = permit.status in (PermitStatus.draft, PermitStatus.requested, PermitStatus.reviewed)
        if j.status in (JsaStatus.draft, JsaStatus.superseded) or (
            j.status == JsaStatus.submitted and not early
        ):
            res.add(B.JSA_NOT_APPROVED, j.jsa_no, j.jsa_no)
        if jsa.has_extreme(j):
            res.add(B.JSA_RESIDUAL_EXTREME, j.jsa_no, j.jsa_no)
        missing = jsa.missing_acceptances(j)
        if missing:
            res.add(B.RESIDUAL_ACCEPTANCE_MISSING, ", ".join(missing), j.jsa_no)
        for h in jsa._lines(j):
            if jsa.line_facts(h)["warnings"]:
                res.warn(W.SEVERITY_REDUCED_WITHOUT_HIGHER_CONTROL, h.get("hazard_code"), j.jsa_no)
    # HSE review (PT-9)
    if f.high_risk_reasons and not (
        permit.hse_review and permit.hse_review.get("decision") == "accepted"
    ):
        res.add(B.HSE_REVIEW_MISSING, "; ".join(f.high_risk_reasons))
    # documents
    for d in missing_documents(db, permit, f):
        res.add(B.DOCUMENT_MISSING, d)
    # checklist (list C; EL-02 test for dead)
    gaps = checklist_gaps(db, permit, "pre_issue")
    if f.has(T.electrical_isolation):
        el = f.sec(T.electrical_isolation)
        if el.get(
            "work_condition", WorkCondition.electrically_safe.value
        ) == WorkCondition.electrically_safe.value and not el.get("test_for_dead"):
            gaps = [*gaps, "EL-02"] if "EL-02" not in gaps else gaps
    if gaps:
        res.add(B.CHECKLIST_INCOMPLETE, ", ".join(gaps))
    # roles / appointments
    _roles_checks(db, permit, f, ctx, res, lines)
    # crew eligibility and hooks
    _crew_checks(db, permit, f, ctx, res, lines)
    # gas (GT-1 … GT-6)
    if f.gas_required:
        tests = gas.tests_of(db, permit.id)
        latest = tests[-1] if tests else None
        passes = [t for t in tests if t.result == GasTestResult.pass_]
        if latest is not None and latest.result == GasTestResult.fail:
            res.add(B.GAS_TEST_FAILED, latest.test_no, latest.test_no)
        elif not active:
            susp = open_suspension(db, permit) if permit.status == PermitStatus.suspended else None
            need_post_alarm = susp is not None and susp.reason in POST_ALARM_REASONS
            if not passes:
                res.add(B.GAS_TEST_REQUIRED)
            elif (
                need_post_alarm
                and susp is not None
                and not any(
                    t.test_type == GasTestType.post_alarm and t.tested_at >= susp.suspended_at
                    for t in passes
                )
            ):
                res.add(B.GAS_TEST_REQUIRED, "post_alarm")
            elif f.has(T.confined_space) and not any(_cse_entry_test(t) for t in passes):
                res.add(B.GAS_TEST_REQUIRED, "pre_entry (3 points)")
            elif (
                ctx.start
                and gas.valid_for_start(
                    db, permit, at, f.settings.gas_pre_start_validity_minutes, after=ctx.gas_after
                )
                is None
            ):
                res.add(B.GAS_TEST_EXPIRED)
    # isolations (IS-5, IS-6)
    certs = isolations.certs_of(db, permit)
    for c in certs:
        if not isolations.is_effective(db, c):
            res.add(B.ISOLATION_NOT_VERIFIED, c.iso_no, c.iso_no)
    if ctx.start and certs and ctx.crew_present:
        for c in certs:
            locked = {e.worker_id for e in isolations.active_personal_locks(db, c.lockbox_id)}
            missing_w = [w for w in ctx.crew_present if w not in locked]
            if missing_w:
                res.add(
                    B.PERSONAL_LOCKS_MISSING,
                    f"{c.iso_no}: {len(missing_w)} of {len(ctx.crew_present)}",
                    c.iso_no,
                )
    # SIMOPS (SM-5 … SM-7)
    sb, sw = simops.blockers_for(db, permit, at)
    for b in sb:
        res.add(PermitBlocker(b["code"]), b.get("detail"), b.get("ref"))
    for w in sw:
        res.warn(W.SIMOPS_CONDITIONAL, w.get("detail"), w.get("ref"))
    # WAP / NOTAM (AW-2 … AW-4)
    crew_ids = list(ctx.crew_present or []) if (ctx.start or active) else []
    _wap_checks(db, permit, f, ctx, res, crew_ids)
    # obstacle clearance (LF-9)
    _obs_checks(db, permit, f, res)
    # wind (LF-6, WH-7)
    reading = (
        ctx.wind_ms
        if ctx.wind_ms is not None
        else (latest_wind(db, permit) if (active or not ctx.start) else None)
    )
    if f.has(T.lifting) and reading is not None and reading > wind_limit(f):
        res.add(
            B.WIND_LIMIT_EXCEEDED,
            f"{reading} > {wind_limit(f)} m/s",
            reason=StatusReason.wind_limit.value,
        )
    elif (
        f.has(T.work_at_height)
        and ctx.wind_ms is not None
        and ctx.wind_ms > rules.WAH_WIND_LIMIT_MS
    ):
        res.add(
            B.WIND_LIMIT_EXCEEDED,
            f"{ctx.wind_ms} > {rules.WAH_WIND_LIMIT_MS} m/s",
            reason=StatusReason.weather.value,
        )
    # midday ban (HT-1 … HT-4)
    bd = [
        d
        for d in ban_dates(f, after=at if permit.status != PermitStatus.draft else None)
        if exemption(db, permit, ExemptionKind.midday_ban, d) is None
    ]
    if bd:
        res.add(B.MIDDAY_BAN, f"window overlaps the ban on {bd[0].isoformat()}")
    if ctx.start:
        bnow = in_ban_now(f, at)
        if bnow is not None and exemption(db, permit, ExemptionKind.midday_ban, bnow) is None:
            res.add(B.MIDDAY_BAN, "now inside the ban hours")
    # heat stress (6b PH-2, PH-3, PH-5, PH-7; 3-ptw v1.3 §11.4)
    from app.services.heat import ptw as heat_ptw  # noqa: PLC0415

    heat_ptw.check(db, permit, ctx, res, lines)
    # window (PT-12)
    if ctx.start and common.current_instance(permit, at) is None:
        res.add(B.OUTSIDE_WINDOW)
    # contractor (PT-6)
    con = acommon.engagement_contractor(db, permit.engagement_id)
    if con is not None and con.status in (ContractorStatus.suspended, ContractorStatus.blacklisted):
        reason = (
            StatusReason.contractor_blacklisted
            if con.status == ContractorStatus.blacklisted
            else StatusReason.contractor_suspended
        )
        res.add(B.CONTRACTOR_SUSPENDED, con.short_code, con.short_code, reason=reason.value)
    # radiography (RG-1, RG-3)
    if f.has(T.radiography):
        rg = f.sec(T.radiography)
        days = common.permit_days(permit)
        until = rg.get("licence_valid_until")
        if not until or (days and date.fromisoformat(str(until)) < days[-1]):
            res.add(B.LICENCE_INVALID, rg.get("nrrc_licence_no"))
        if not _rpo_appointment(db, permit, lines):
            res.add(B.LICENCE_INVALID, "RPO appointment")
        if ctx.start or active:
            surveys = records(db, permit.id, "barrier_survey")
            if (
                not surveys
                or Decimal(str(surveys[-1].data["max_usv_h"])) > f.settings.rg_barrier_limit_usv_h
            ):
                res.add(B.BARRIER_NOT_VERIFIED)
    # hot work fire impairment (HW-8)
    if f.has(T.hot_work):
        hw = f.sec(T.hot_work)
        if hw.get("fire_system_impairment"):
            ok = exemption(db, permit, ExemptionKind.fire_impairment) is not None and hw.get(
                "impairment_ref"
            )
            hours = rules.dec(hw.get("impairment_hours_24h")) or Decimal(0)
            if hours > 4 and not hw.get("civil_defense_notified_at"):
                ok = False
            if not ok:
                res.add(B.FIRE_IMPAIRMENT_NOT_APPROVED)
        late = _hot_work_late(f)
        if late:
            res.warn(W.HOT_WORK_LATE, late)
    # excavation (EX-3)
    if f.has(T.excavation) and not f.sec(T.excavation).get("utility_clearance_ref"):
        res.add(B.UTILITY_CLEARANCE_MISSING)
    # fall clearance (WH-5)
    if f.has(T.work_at_height) and rules.clearance_ok(f.sec(T.work_at_height)) is False:
        req = rules.required_clearance(f.sec(T.work_at_height))
        res.add(B.FALL_CLEARANCE_INSUFFICIENT, f"required {req} m" if req is not None else None)
    # exemptions active (PT-17)
    for e in db.scalars(
        select(PermitExemption).where(
            PermitExemption.permit_id == permit.id,
            PermitExemption.status == ExemptionStatus.granted,
        )
    ):
        if e.valid_to is None or e.valid_to >= acommon.local_day(at):
            res.warn(W.EXEMPTION_ACTIVE, e.kind.value)
    # midday prewarn (HT-3)
    if active and permit.exposure == Exposure.outdoor_direct_sun:
        st = f.settings
        today = acommon.local_day(at)
        if rules.in_season(
            today, st.midday_ban_period["start_mmdd"], st.midday_ban_period["end_mmdd"]
        ):
            bs, _be = rules.ban_interval(today, st.midday_ban_hours)
            if (
                bs - timedelta(minutes=st.midday_ban_prewarn_minutes) <= at < bs
                and exemption(db, permit, ExemptionKind.midday_ban, today) is None
            ):
                res.warn(W.MIDDAY_BAN_PREWARN, bs.astimezone(acommon.RIYADH).strftime("%H:%M"))
    return res


def _cse_entry_test(t: GasTest) -> bool:
    if t.test_type not in (GasTestType.pre_entry, GasTestType.pre_issue):
        return False
    pts = {r.get("point") for r in t.readings or []}
    return {"top", "middle", "bottom"} <= pts


def _rpo_appointment(db: Session, permit: Permit, lines: list[PermitCrew]) -> bool:
    day = appointment_day(permit, now())
    for x in lines:
        if x.status == CrewLineStatus.removed:
            continue
        if common.find_appointment(
            db,
            permit.project_id,
            AppointmentFunction.authorised_person,
            [T.radiography.value],
            permit.site_id,
            permit.zone_ids or [],
            [day],
            worker_id=x.worker_id,
            disciplines=["radiation_protection_officer"],
        ):
            return True
    return False


def _hot_work_late(f: facts_mod.Facts) -> str | None:
    hw = f.sec(T.hot_work)
    ended = hw.get("hot_work_ended_at")
    if not ended:
        return None
    end = datetime.fromisoformat(str(ended))
    latest = f.permit.valid_to_at - timedelta(minutes=f.settings.fire_watch_post_minutes)
    return end.astimezone(acommon.RIYADH).strftime("%H:%M") if end > latest else None


# ---- store and auto-suspend (SH-2) ---------------------------------------------------------------


def suspend_reason(rows: list[dict[str, Any]]) -> tuple[StatusReason, str] | None:
    """First AUTO_SUSPEND blocker (list B order) → (reason, detail). A contractor suspension
    is the root cause of the crew exclusions it cascades (Phase 2 LC-8), so it goes first
    (AC13, DECISIONS #74)."""
    items = sorted(
        (b for b in rows if PermitBlocker(b["code"]) in ref.AUTO_SUSPEND),
        key=lambda b: (
            PermitBlocker(b["code"]) != B.CONTRACTOR_SUSPENDED,
            ref.BLOCKER_ORDER[PermitBlocker(b["code"])],
        ),
    )
    if not items:
        return None
    b = items[0]
    code = PermitBlocker(b["code"])
    reason = StatusReason(b["reason"]) if b.get("reason") else ref.BLOCKER_REASON[code]
    detail = code.value + (f": {b['detail']}" if b.get("detail") else "")
    return reason, detail


def store(permit: Permit, res: Result) -> None:
    permit.blockers = sorted(
        res.blockers, key=lambda b: ref.BLOCKER_ORDER[PermitBlocker(b["code"])]
    )
    permit.warnings = res.warnings
    permit.high_risk = bool(res.facts.high_risk_reasons)
    permit.critical_lift = res.facts.critical


def refresh(
    db: Session,
    permit: Permit,
    run_simops: bool = True,
    at: datetime | None = None,
    evaluate_crew: bool = True,
    auto_suspend: bool = True,
) -> Result | None:
    """Recompute and store blockers/warnings (PT-16); a live permit with a new AUTO_SUSPEND
    blocker is suspended (SH-2). Terminal permits are left untouched."""
    if permit.status in PERMIT_TERMINAL:
        return None
    at = at or now()
    if run_simops and permit.status not in (PermitStatus.draft,):
        from app.services.ptw import simops  # noqa: PLC0415

        simops.check(db, permit, _trigger(), at=at)
    res = evaluate(db, permit, Ctx(at=at, evaluate_crew=evaluate_crew))
    store(permit, res)
    db.flush()
    if auto_suspend and permit.status in (PermitStatus.issued, PermitStatus.active):
        sr = suspend_reason(res.blockers)
        if sr is not None:
            from app.services.ptw import lifecycle  # noqa: PLC0415

            lifecycle.auto_suspend(db, permit, sr[0], sr[1], _source_ref(res.blockers, sr[0]))
    return res


def _source_ref(rows: list[dict[str, Any]], reason: StatusReason) -> str | None:
    for b in rows:
        code = PermitBlocker(b["code"])
        if code in ref.AUTO_SUSPEND and (
            b.get("reason") == reason.value or ref.BLOCKER_REASON[code] == reason
        ):
            return b.get("ref")
    return None


def _trigger() -> Any:
    from app.core.ptw_enums import SimopsCheckTrigger  # noqa: PLC0415

    return SimopsCheckTrigger.change


def refresh_many(db: Session, permits: list[Permit], at: datetime | None = None) -> int:
    n = 0
    for p in permits:
        if refresh(db, p, at=at) is not None:
            n += 1
    return n


def live_permits_of_engagements(db: Session, engagement_ids: list[uuid.UUID]) -> list[Permit]:
    if not engagement_ids:
        return []
    return list(
        db.scalars(
            select(Permit).where(
                Permit.engagement_id.in_(engagement_ids),
                Permit.status.in_([*PERMIT_LIVE, PermitStatus.approved]),
            )
        )
    )


def permits_of_worker(db: Session, worker_id: uuid.UUID) -> list[Permit]:
    ids = {
        c.permit_id
        for c in db.scalars(
            select(PermitCrew).where(
                PermitCrew.worker_id == worker_id, PermitCrew.status != CrewLineStatus.removed
            )
        )
    }
    if not ids:
        return []
    return [
        p
        for p in db.scalars(select(Permit).where(Permit.id.in_(ids)))
        if p.status not in PERMIT_TERMINAL and p.status != PermitStatus.draft
    ]


def permits_of_wap(db: Session, wap: Wap) -> list[Permit]:
    rows = db.scalars(
        select(Permit).where(
            Permit.project_id == wap.project_id,
            Permit.status.in_(list(PERMIT_LIVE)),
            Permit.zone_ids.overlap(list(wap.zone_ids or [])),
        )
    )
    return list(rows)
