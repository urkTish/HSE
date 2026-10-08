# ruff: noqa: E501
"""SIMOPS conflict check, conflicts and coordination (spec 3-ptw §3.12, §4.8, SM-1…SM-8, §6.4,
§6.5). The checked permit is compared with every other permit of the project in
Requested…Suspended whose remaining window instances overlap (DECISIONS); every matching rule
of the project matrix is stored as one conflict per (A, B, rule)."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, ZoneType
from app.core.errors import ErrorCode, not_found
from app.core.ptw_enums import (
    PERMIT_LIVE,
    PERMIT_TERMINAL,
    AppointmentFunction,
    CoordinationSignerRole,
    CoordinationStatus,
    DistanceBasis,
    EquipmentUse,
    PermitBlocker,
    PermitStatus,
    PermitType,
    PermitWarningCode,
    SignaturePurpose,
    SimopsCheckTrigger,
    SimopsCondition,
    SimopsConflictStatus,
    SimopsResult,
    SimopsTypeSelector,
    VerticalRelation,
    WorkCondition,
)
from app.models import (
    Permit,
    PermitEquipment,
    SimopsConflict,
    SimopsCoordination,
    SimopsRule,
    Zone,
)
from app.schemas.simops import (
    CoordinationCreate,
    CoordinationRead,
    CoordinationSignature,
    CoordinationSignInput,
    SimopsCheckResult,
    SimopsConflictPage,
    SimopsConflictRead,
    SimopsMatch,
    SimopsPreviewRequest,
)
from app.services import audit
from app.services.access import common as acommon
from app.services.access import windows
from app.services.hse_common import Refs, make_ref, next_seq
from app.services.permissions import Principal, forbidden_error
from app.services.ptw import common, rules
from app.services.ptw import config as cfg
from app.services.ptw import reference as ref

C = Capability
SEL = SimopsTypeSelector
COND = SimopsCondition
CHECK_STATUSES = (
    PermitStatus.requested,
    PermitStatus.reviewed,
    PermitStatus.approved,
    PermitStatus.issued,
    PermitStatus.active,
    PermitStatus.suspended,
)
SYMMETRIC = {COND.same_zone, COND.slew_overlap}
SKIP_IF = {"SM-R05b": "SM-R05a", "SM-R04": "SM-R02"}
Point = tuple[Decimal, Decimal]


# ---- subjects ------------------------------------------------------------------------------------


@dataclass
class Subject:
    id: uuid.UUID | None
    permit: Permit | None
    project_id: uuid.UUID
    site_id: uuid.UUID
    zone_ids: list[uuid.UUID]
    engagement_id: uuid.UUID
    contractor_id: uuid.UUID | None
    types: set[str]
    grid: Point | None
    elevation: Decimal | None
    flammables: bool
    combustion: bool
    hw_height: Decimal
    landing: Point | None
    exclusion: Decimal | None
    appliance: Point | None
    slew: Decimal | None
    barrier: Decimal | None
    depth: Decimal | None
    energized: bool
    gas_required: bool
    crane: bool
    plant: bool
    movement_zones: set[uuid.UUID] = field(default_factory=set)
    airside: bool = False
    instances: list[tuple[datetime, datetime]] = field(default_factory=list)
    valid_to: datetime | None = None
    label: str = ""


def _pt(x: Any, y: Any) -> Point | None:
    if x is None or y is None:
        return None
    return Decimal(str(x)), Decimal(str(y))


def _d(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _zones(db: Session, ids: list[uuid.UUID]) -> list[Zone]:
    zs = {z.id: z for z in db.scalars(select(Zone).where(Zone.id.in_(ids)))} if ids else {}
    return [zs[i] for i in ids if i in zs]


def _contractor(db: Session, engagement_id: uuid.UUID) -> uuid.UUID | None:
    c = acommon.engagement_contractor(db, engagement_id)
    return c.id if c else None


def subject_of(db: Session, p: Permit, at: datetime) -> Subject:
    from app.services.ptw import facts  # noqa: PLC0415

    sec = p.sections or {}
    lf = sec.get(PermitType.lifting.value) or {}
    ex = sec.get(PermitType.excavation.value) or {}
    hw = sec.get(PermitType.hot_work.value) or {}
    rg = sec.get(PermitType.radiography.value) or {}
    el = sec.get(PermitType.electrical_isolation.value) or {}
    types = set(p.work_types or [])
    equip = list(db.scalars(select(PermitEquipment).where(PermitEquipment.permit_id == p.id)))
    crane_eq = any(
        e.category in ref.CRANE_CATEGORIES
        or (e.vehicle_id and e.use == EquipmentUse.lifting_appliance)
        for e in equip
    )
    zones = _zones(db, list(p.zone_ids or []))
    f = facts.compute(db, p)
    landing = _pt(lf.get("landing_grid_x_m"), lf.get("landing_grid_y_m"))
    return Subject(
        id=p.id,
        permit=p,
        project_id=p.project_id,
        site_id=p.site_id,
        zone_ids=list(p.zone_ids or []),
        engagement_id=p.engagement_id,
        contractor_id=_contractor(db, p.engagement_id),
        types=types,
        grid=_pt(p.grid_x_m, p.grid_y_m) or landing,
        elevation=_d(p.elevation_m),
        flammables=bool(p.flammables_in_use),
        combustion=bool(p.combustion_engine_plant),
        hw_height=_d(hw.get("work_height_above_floor_m")) or Decimal(0),
        landing=landing,
        exclusion=_d(lf.get("exclusion_radius_m")),
        appliance=_pt(lf.get("appliance_grid_x_m"), lf.get("appliance_grid_y_m")),
        slew=_d(lf.get("slew_radius_m")),
        barrier=_d(rg.get("planned_barrier_m")),
        depth=_d(ex.get("max_depth_m")),
        energized=el.get("work_condition") == WorkCondition.energized.value,
        gas_required=f.gas_required,
        crane=PermitType.lifting.value in types
        and (
            crane_eq
            or lf.get("slew_radius_m") is not None
            or lf.get("appliance_grid_x_m") is not None
        ),
        plant=PermitType.lifting.value in types
        or (PermitType.excavation.value in types and ex.get("method") == "mechanical")
        or any(e.use == EquipmentUse.excavating_plant for e in equip),
        movement_zones={
            z.id for z in zones if z.zone_type == ZoneType.airside and z.in_movement_area
        },
        airside=any(z.zone_type == ZoneType.airside for z in zones),
        instances=common.instances(p, start=at),
        valid_to=p.valid_to_at,
        label=p.permit_no,
    )


def subject_of_preview(
    db: Session, body: SimopsPreviewRequest, project_id: uuid.UUID, at: datetime
) -> Subject:

    types = {t.value for t in body.work_types}
    zones = _zones(db, body.zone_ids)
    zf = common.zone_facts(db, zones)
    s = common.settings(db, project_id)
    sections: dict[str, dict[str, Any]] = {}
    if body.excavation_max_depth_m is not None:
        sections[PermitType.excavation.value] = {"max_depth_m": str(body.excavation_max_depth_m)}
    gas = rules.gas_types(
        sorted(types), sections, zf, body.flammables_in_use, s.ex_protective_system_depth_m
    )
    defs = windows.parse([w.model_dump(mode="json") for w in body.windows])
    landing = _pt(body.lifting_landing_grid_x_m, body.lifting_landing_grid_y_m)
    appliance = _pt(body.lifting_appliance_grid_x_m, body.lifting_appliance_grid_y_m)
    return Subject(
        id=body.permit_id,
        permit=None,
        project_id=project_id,
        site_id=body.site_id,
        zone_ids=list(body.zone_ids),
        engagement_id=body.engagement_id,
        contractor_id=_contractor(db, body.engagement_id),
        types=types,
        grid=_pt(body.grid_x_m, body.grid_y_m) or landing,
        elevation=body.elevation_m,
        flammables=body.flammables_in_use,
        combustion=body.combustion_engine_plant,
        hw_height=body.hot_work_height_above_floor_m or Decimal(0),
        landing=landing,
        exclusion=body.lifting_exclusion_radius_m,
        appliance=appliance,
        slew=body.lifting_slew_radius_m,
        barrier=body.radiography_planned_barrier_m,
        depth=body.excavation_max_depth_m,
        energized=body.electrical_energized,
        gas_required=bool(gas),
        crane=PermitType.lifting.value in types
        and (body.lifting_slew_radius_m is not None or appliance is not None),
        plant=PermitType.lifting.value in types or PermitType.excavation.value in types,
        movement_zones={
            z.id for z in zones if z.zone_type == ZoneType.airside and z.in_movement_area
        },
        airside=any(z.zone_type == ZoneType.airside for z in zones),
        instances=common.instances_between(defs, body.valid_from_at, body.valid_to_at, start=at),
        valid_to=body.valid_to_at,
        label="(draft)",
    )


# ---- matching ------------------------------------------------------------------------------------


def _sel_a(sel: SimopsTypeSelector, a: Subject) -> bool:
    if sel == SEL.any:
        return True
    if sel == SEL.crane:
        return a.crane
    if sel == SEL.energized_electrical:
        return PermitType.electrical_isolation.value in a.types and a.energized
    if sel.value in {t.value for t in PermitType}:
        return sel.value in a.types
    return _sel_b(sel, a, a)


def _sel_b(sel: SimopsTypeSelector, b: Subject, a: Subject) -> bool:
    if sel == SEL.any:
        return True
    if sel == SEL.flammables_in_use:
        return b.flammables
    if sel == SEL.gas_test_required:
        return b.gas_required
    if sel == SEL.lifting_or_excavating_plant:
        return b.plant
    if sel == SEL.combustion_engine_plant:
        return b.combustion or PermitType.excavation.value in b.types
    if sel == SEL.crane:
        return b.crane
    if sel == SEL.energized_electrical:
        return PermitType.electrical_isolation.value in b.types and b.energized
    if sel == SEL.other_contractor_movement_area:
        return b.contractor_id != a.contractor_id and bool(a.movement_zones & b.movement_zones)
    return sel.value in b.types


def _zone_distance(db: Session, a: Subject, b: Subject) -> tuple[Decimal | None, DistanceBasis]:
    if set(a.zone_ids) & set(b.zone_ids):
        return Decimal(0), DistanceBasis.same_zone
    best: Decimal | None = None
    for za in a.zone_ids:
        for zb in b.zone_ids:
            adj = cfg.adjacency(db, za, zb)
            if adj is not None and (best is None or adj.distance_m < best):
                best = Decimal(str(adj.distance_m))
    return best, DistanceBasis.adjacency


def _distance(
    db: Session, pa: Point | None, pb: Point | None, a: Subject, b: Subject
) -> tuple[Decimal | None, DistanceBasis]:
    """SM-2: both grid points → horizontal distance; else same zone → 0; adjacency → its
    distance; other zones → no match (None)."""
    if pa is not None and pb is not None:
        return rules.distance(pa[0], pa[1], pb[0], pb[1]), DistanceBasis.grid
    return _zone_distance(db, a, b)


def _above(db: Session, a: Subject, b: Subject, vsep: Decimal) -> tuple[bool, str | None]:
    if a.elevation is not None and b.elevation is not None:
        ok = a.elevation >= b.elevation + vsep
        return ok, f"A above B ({a.elevation} ≥ {b.elevation} + {vsep})" if ok else None
    if set(a.zone_ids) & set(b.zone_ids):
        return True, "same zone, vertical relation unknown (treated as above)"
    for za in a.zone_ids:
        for zb in b.zone_ids:
            adj = cfg.adjacency(db, za, zb)
            if adj is None:
                continue
            rel = adj.vertical_relation
            if rel == VerticalRelation.overlapping:
                return True, "zones overlap vertically"
            a_is_first = adj.zone_a_id == za
            if (rel == VerticalRelation.a_above_b and a_is_first) or (
                rel == VerticalRelation.b_above_a and not a_is_first
            ):
                return True, "zone above (adjacency)"
    return False, None


@dataclass
class Hit:
    rule: SimopsRule
    a: Subject
    b: Subject
    distance: Decimal | None
    basis: DistanceBasis
    vertical: str | None
    overlap: tuple[datetime, datetime]


def _condition(
    db: Session, r: SimopsRule, a: Subject, b: Subject, s: Any
) -> tuple[bool, Decimal | None, DistanceBasis, str | None]:
    thr = _d(r.threshold_m)
    cond = r.condition

    def within(
        pa: Point | None, limit: Decimal | None, pb: Point | None = None
    ) -> tuple[bool, Decimal | None, DistanceBasis]:
        d, basis = _distance(db, pa, b.grid if pb is None else pb, a, b)
        if d is None or limit is None:
            return False, d, basis
        return d <= limit, d, basis

    if cond == COND.within_barrier:
        lim = a.barrier if thr is None else max(a.barrier or Decimal(0), thr)
        ok, d, basis = within(a.grid, lim)
        return ok, d, basis, None
    if cond == COND.within_threshold:
        ok, d, basis = within(a.grid, thr)
        return ok, d, basis, None
    if cond == COND.within_combustible_clearance:
        lim = Decimal(str(s.hw_combustible_clearance_m))
        ok, d, basis = within(a.grid, max(lim, thr) if thr else lim)
        return ok, d, basis, None
    if cond == COND.within_exclusion_radius:
        ok, d, basis = within(a.landing or a.grid, a.exclusion)
        return ok, d, basis, None
    if cond == COND.within_slew_radius:
        ok, d, basis = within(a.appliance, a.slew)
        return ok, d, basis, None
    if cond == COND.above_within_drop_zone:
        up, note = _above(db, a, b, Decimal(str(s.vertical_separation_m)))
        if not up:
            return False, None, DistanceBasis.grid, None
        lim = Decimal(str(s.drop_zone_radius_m))
        ok, d, basis = within(a.grid, max(lim, thr) if thr else lim)
        return ok, d, basis, note
    if cond == COND.hot_work_above_within_clearance:
        if a.hw_height <= 0:
            return False, None, DistanceBasis.grid, None
        up, note = _above(db, a, b, Decimal(str(s.vertical_separation_m)))
        if not up:
            return False, None, DistanceBasis.grid, None
        lim = Decimal(str(s.hw_combustible_clearance_m))
        ok, d, basis = within(a.grid, max(lim, thr) if thr else lim)
        return ok, d, basis, note
    if cond == COND.within_surcharge_zone:
        ok, d, basis = within(a.grid, a.depth)
        return ok, d, basis, None
    if cond == COND.same_zone:
        shared = set(a.zone_ids) & set(b.zone_ids)
        return bool(shared), Decimal(0) if shared else None, DistanceBasis.same_zone, None
    if cond == COND.slew_overlap:
        if a.slew is None or b.slew is None:
            return False, None, DistanceBasis.grid, None
        ok, d, basis = within(a.appliance, a.slew + b.slew, b.appliance)
        return ok, d, basis, None
    return False, None, DistanceBasis.grid, None


def _hits(db: Session, x: Subject, others: list[Subject], rule_rows: list[SimopsRule]) -> list[Hit]:
    s = common.settings(db, x.project_id)
    out: list[Hit] = []
    for y in others:
        ov = common.overlap(x.instances, y.instances)
        if ov is None:
            continue
        pair_hits: list[Hit] = []
        for a, b in ((x, y), (y, x)):
            matched: set[str] = set()
            for r in rule_rows:
                if not r.active or r.result == SimopsResult.allowed:
                    continue
                if r.rule_code in SKIP_IF and SKIP_IF[r.rule_code] in matched:
                    continue
                if not (_sel_a(r.type_a, a) and _sel_b(r.type_b, b, a)):
                    continue
                ok, d, basis, note = _condition(db, r, a, b, s)
                if not ok:
                    continue
                if r.condition in SYMMETRIC and any(
                    h.rule.rule_code == r.rule_code for h in pair_hits
                ):
                    continue
                matched.add(r.rule_code)
                pair_hits.append(Hit(r, a, b, d, basis, note, ov))
        out.extend(pair_hits)
    return out


def _candidates(db: Session, x: Subject, at: datetime) -> list[Subject]:
    stmt = select(Permit).where(
        Permit.project_id == x.project_id,
        Permit.status.in_(list(CHECK_STATUSES)),
        Permit.valid_to_at > at,
    )
    if x.id is not None:
        stmt = stmt.where(Permit.id != x.id)
    return [subject_of(db, p, at) for p in db.scalars(stmt.order_by(Permit.permit_no))]


def _rules(db: Session, project_id: uuid.UUID) -> list[SimopsRule]:
    rows = cfg.ensure_rules(db, project_id)
    return sorted(rows, key=lambda r: cfg._code_key(r.rule_code))


# ---- conflicts -----------------------------------------------------------------------------------


def conflicts_of(
    db: Session, permit_id: uuid.UUID, include_closed: bool = False
) -> list[SimopsConflict]:
    stmt = select(SimopsConflict).where(
        or_(SimopsConflict.permit_a_id == permit_id, SimopsConflict.permit_b_id == permit_id)
    )
    if not include_closed:
        stmt = stmt.where(SimopsConflict.status != SimopsConflictStatus.closed)
    return list(db.scalars(stmt.order_by(SimopsConflict.conflict_no)))


def _q(v: Decimal | None) -> Decimal | None:
    return None if v is None else v.quantize(Decimal("0.001"))


def check(
    db: Session,
    permit: Permit,
    trigger: SimopsCheckTrigger,
    at: datetime | None = None,
    *,
    store: bool = True,
) -> SimopsCheckResult:
    """SM-1/SM-4: run the check, store conflicts, resolve the ones that no longer match."""
    at = at or now()
    x = subject_of(db, permit, at)
    hits = _hits(db, x, _candidates(db, x, at), _rules(db, permit.project_id))
    existing = {(c.permit_a_id, c.permit_b_id, c.rule_code): c for c in conflicts_of(db, permit.id)}
    seen: set[tuple[Any, Any, str]] = set()
    matches = []
    new_rows: list[SimopsConflict] = []
    for h in hits:
        assert h.a.id is not None and h.b.id is not None  # noqa: S101
        key = (h.a.id, h.b.id, h.rule.rule_code)
        seen.add(key)
        c = existing.get(key)
        if store:
            if c is None:
                year = acommon.local_day(at).year
                seq = next_seq(db, SimopsConflict, permit.project_id, year)
                c = SimopsConflict(
                    id=uuid.uuid4(),
                    project_id=permit.project_id,
                    year=year,
                    seq=seq,
                    conflict_no=make_ref(
                        "SIM", common.project_code(db, permit.project_id), year, seq, 4
                    ),
                    permit_a_id=h.a.id,
                    permit_b_id=h.b.id,
                    rule_code=h.rule.rule_code,
                    result=h.rule.result,
                    status=SimopsConflictStatus.open,
                    detected_at=at,
                )
                db.add(c)
                new_rows.append(c)
            elif c.status == SimopsConflictStatus.resolved_by_change:
                c.status = SimopsConflictStatus.open
                c.resolved_at = None
            c.distance_m = _q(h.distance)
            c.distance_basis = h.basis
            c.vertical_note = h.vertical
            c.overlap_from, c.overlap_to = h.overlap
            c.result = h.rule.result
            c.required_controls_en = h.rule.required_controls_en
            c.required_controls_ar = h.rule.required_controls_ar
        matches.append((h, c))
    resolved = []
    if store:
        for key, c in existing.items():
            if key not in seen and c.status in (
                SimopsConflictStatus.open,
                SimopsConflictStatus.coordinated,
            ):
                c.status = SimopsConflictStatus.resolved_by_change
                c.resolved_at = at
                resolved.append(c.conflict_no)
        db.flush()
        for c in new_rows:
            _audit(
                db,
                None,
                c,
                AuditAction.create,
                None,
                {"conflict_no": c.conflict_no, "rule": c.rule_code, "result": c.result.value},
            )
            _notify_new(db, c)
    return SimopsCheckResult(
        trigger=trigger,
        checked_at=at,
        permit=common.permit_ref(permit),
        matches=[_match(db, permit.id, h, c) for h, c in matches],
        prohibited=sum(1 for h, _ in matches if h.rule.result == SimopsResult.prohibited),
        conditional=sum(1 for h, _ in matches if h.rule.result == SimopsResult.conditional),
        resolved_by_change=resolved,
    )


def _match(
    db: Session, checked_id: uuid.UUID | None, h: Hit, c: SimopsConflict | None
) -> SimopsMatch:
    other = h.b if h.a.id == checked_id or (checked_id is None and h.a.permit is None) else h.a
    assert other.permit is not None  # noqa: S101
    return SimopsMatch(
        rule_code=h.rule.rule_code,
        result=h.rule.result,
        other_permit=common.permit_ref(other.permit),
        checked_is_a=other is h.b,
        distance_m=None if h.distance is None else rules.q1(h.distance),
        distance_basis=h.basis,
        vertical_note=h.vertical,
        overlap_from=h.overlap[0],
        overlap_to=h.overlap[1],
        required_controls_en=h.rule.required_controls_en,
        required_controls_ar=h.rule.required_controls_ar,
        conflict_id=c.id if c else None,
        conflict_status=c.status if c else None,
        coordinated=bool(c and c.status == SimopsConflictStatus.coordinated),
    )


def preview(
    db: Session, p: Principal, project_id: uuid.UUID, body: SimopsPreviewRequest
) -> SimopsCheckResult:
    common.view_grant(db, p, project_id)
    at = now()
    x = subject_of_preview(db, body, project_id, at)
    hits = _hits(db, x, _candidates(db, x, at), _rules(db, project_id))
    permit = db.get(Permit, body.permit_id) if body.permit_id else None
    return SimopsCheckResult(
        trigger=SimopsCheckTrigger.preview,
        checked_at=at,
        permit=common.permit_ref(permit) if permit else None,
        matches=[_match(db, None, h, None) for h in hits],
        prohibited=sum(1 for h in hits if h.rule.result == SimopsResult.prohibited),
        conditional=sum(1 for h in hits if h.rule.result == SimopsResult.conditional),
        resolved_by_change=[],
    )


def run_for_permit(db: Session, p: Principal, permit_id: uuid.UUID) -> SimopsCheckResult:
    permit = common.get_permit(db, p, permit_id)
    if permit.status in PERMIT_TERMINAL:
        raise common.err(
            ErrorCode.PERMIT_READ_ONLY, "The permit is closed.", "التصريح مغلق.", status=409
        )
    res = check(db, permit, SimopsCheckTrigger.manual)
    _refresh_pair(db, permit)
    return res


def _refresh_pair(db: Session, permit: Permit) -> None:
    """Re-evaluate both permits of every conflict (no recursive SIMOPS check)."""
    from app.services.ptw import evaluation  # noqa: PLC0415

    ids = {permit.id}
    for c in conflicts_of(db, permit.id, include_closed=True):
        ids.update({c.permit_a_id, c.permit_b_id})
    for pid in ids:
        x = db.get(Permit, pid)
        if x is not None and x.status not in PERMIT_TERMINAL:
            evaluation.refresh(db, x, run_simops=False)


def close_for(db: Session, permit: Permit, at: datetime | None = None) -> None:
    """§4.8: any → Closed when either permit is terminal; coordination records expire."""
    at = at or now()
    for c in conflicts_of(db, permit.id):
        c.status = SimopsConflictStatus.closed
        c.resolved_at = c.resolved_at or at
        co = _coordination(db, c.id)
        if co and co.status == CoordinationStatus.signed:
            co.status = CoordinationStatus.expired
    db.flush()


def _notify_new(db: Session, c: SimopsConflict) -> None:
    a, b = db.get(Permit, c.permit_a_id), db.get(Permit, c.permit_b_id)
    if a is None or b is None:
        return
    users = common.permit_people(db, a, area=True) | common.permit_people(db, b)
    for x in (a, b):
        common.tell(
            db,
            x,
            users,
            NotificationKind.simops_conflict,
            f"SIMOPS {c.result.value} conflict {c.conflict_no} ({c.rule_code}) with {(b if x is a else a).permit_no}",
            f"تعارض عمليات متزامنة {c.conflict_no} ({c.rule_code}) مع {(b if x is a else a).permit_no}",
        )
        users = set()


# ---- blockers for evaluation (SM-5 … SM-7) -------------------------------------------------------


def _applies_to(db: Session, c: SimopsConflict, permit: Permit) -> bool:
    """SM-7: when one permit was already live (issued) before the other, the blocker belongs to
    the later one only."""
    other_id = c.permit_b_id if c.permit_a_id == permit.id else c.permit_a_id
    other = db.get(Permit, other_id)
    if other is None:
        return False
    me_live = permit.status in PERMIT_LIVE and permit.first_issued_at is not None
    other_live = other.status in PERMIT_LIVE and other.first_issued_at is not None
    if me_live and not other_live:
        return False
    if me_live and other_live and permit.first_issued_at and other.first_issued_at:
        return permit.first_issued_at >= other.first_issued_at
    return True


def blockers_for(
    db: Session, permit: Permit, at: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers, warns = [], []
    for c in conflicts_of(db, permit.id):
        if c.overlap_to is not None and c.overlap_to <= at:
            continue
        if c.status == SimopsConflictStatus.coordinated:
            warns.append(
                {
                    "code": PermitWarningCode.SIMOPS_CONDITIONAL.value,
                    "detail": f"{c.conflict_no} {c.rule_code}",
                    "ref": c.conflict_no,
                }
            )
            continue
        if c.status != SimopsConflictStatus.open or not _applies_to(db, c, permit):
            continue
        if c.result == SimopsResult.prohibited:
            blockers.append(
                common.blocker_json(
                    PermitBlocker.SIMOPS_PROHIBITED, f"{c.conflict_no} {c.rule_code}", c.conflict_no
                )
            )
        elif c.result == SimopsResult.conditional:
            blockers.append(
                common.blocker_json(
                    PermitBlocker.SIMOPS_COORDINATION_REQUIRED,
                    f"{c.conflict_no} {c.rule_code}",
                    c.conflict_no,
                )
            )
    return blockers, warns


# ---- read models ---------------------------------------------------------------------------------


def _coordination(db: Session, conflict_id: uuid.UUID) -> SimopsCoordination | None:
    return db.scalars(
        select(SimopsCoordination).where(SimopsCoordination.conflict_id == conflict_id)
    ).first()


@dataclass
class Signer:
    role: CoordinationSignerRole
    user_id: uuid.UUID | None
    permit: Permit


def required_signers(db: Session, c: SimopsConflict) -> list[Signer]:
    a, b = db.get(Permit, c.permit_a_id), db.get(Permit, c.permit_b_id)
    assert a is not None and b is not None  # noqa: S101
    out = [Signer(CoordinationSignerRole.issuer_a, a.issuer_user_id, a)]
    if not (a.issuer_user_id and a.issuer_user_id == b.issuer_user_id):
        out.append(Signer(CoordinationSignerRole.issuer_b, b.issuer_user_id, b))
    out.append(Signer(CoordinationSignerRole.area_authority, a.area_authority_user_id, a))
    return out


def _signed(co: SimopsCoordination | None) -> dict[str, dict[str, Any]]:
    return {s["role"]: s for s in (co.signatures if co else []) if s.get("signed_at")}


def conflict_read(db: Session, c: SimopsConflict, refs: Refs | None = None) -> SimopsConflictRead:
    refs = refs or Refs(db)
    a, b = db.get(Permit, c.permit_a_id), db.get(Permit, c.permit_b_id)
    assert a is not None and b is not None  # noqa: S101
    co = _coordination(db, c.id)
    signed = _signed(co)
    req = []
    for s in required_signers(db, c):
        done = signed.get(s.role.value)
        uid = uuid.UUID(done["user_id"]) if done else s.user_id
        u = refs.user(uid)
        if u is None:
            continue
        req.append(
            CoordinationSignature(
                role=s.role,
                user=u,
                signed_at=datetime.fromisoformat(done["signed_at"]) if done else None,
            )
        )
    co_read = None
    if co is not None:
        sigs = []
        for sg in co.signatures:
            u = refs.user(uuid.UUID(sg["user_id"]))
            if u:
                sigs.append(
                    CoordinationSignature(
                        role=CoordinationSignerRole(sg["role"]),
                        user=u,
                        signed_at=datetime.fromisoformat(sg["signed_at"])
                        if sg.get("signed_at")
                        else None,
                    )
                )
        created = refs.user(co.created_by_user_id)
        assert created is not None  # noqa: S101
        co_read = CoordinationRead(
            id=co.id,
            conflict_id=c.id,
            agreed_controls_en=co.agreed_controls_en,
            agreed_controls_ar=co.agreed_controls_ar,
            signatures=sigs,
            status=co.status,
            signed_at=co.signed_at,
            valid_until=co.valid_until,
            created_by=created,
            created_at=co.created_at,
        )
    return SimopsConflictRead(
        id=c.id,
        project_id=c.project_id,
        conflict_no=c.conflict_no,
        permit_a=common.permit_ref(a),
        permit_b=common.permit_ref(b),
        rule_code=c.rule_code,
        result=c.result,
        distance_m=None if c.distance_m is None else rules.q1(Decimal(str(c.distance_m))),
        distance_basis=c.distance_basis,
        overlap_from=c.overlap_from,
        overlap_to=c.overlap_to,
        required_controls_en=c.required_controls_en,
        required_controls_ar=c.required_controls_ar,
        status=c.status,
        detected_at=c.detected_at,
        resolved_at=c.resolved_at,
        coordination=co_read,
        required_signers=req,
    )


def _get(db: Session, p: Principal, conflict_id: uuid.UUID) -> SimopsConflict:
    c = db.get(SimopsConflict, conflict_id)
    if c is None:
        raise not_found("SIMOPS conflict")
    g = common.view_grant(db, p, c.project_id)
    a, b = db.get(Permit, c.permit_a_id), db.get(Permit, c.permit_b_id)
    if not any(x and acommon.grant_covers(g, [x.site_id], x.engagement_id) for x in (a, b)):
        raise forbidden_error("This conflict is outside your scope.")
    return c


def read(db: Session, p: Principal, conflict_id: uuid.UUID) -> SimopsConflictRead:
    return conflict_read(db, _get(db, p, conflict_id))


def list_conflicts(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    size: int,
    statuses: list[SimopsConflictStatus] | None,
    result: SimopsResult | None,
    permit_id: uuid.UUID | None,
    zone_ids: list[uuid.UUID] | None,
    awaiting_me: bool,
    detected_from: datetime | None,
    detected_to: datetime | None,
) -> SimopsConflictPage:
    g = common.view_grant(db, p, project_id)
    stmt = select(SimopsConflict).where(SimopsConflict.project_id == project_id)
    if statuses:
        stmt = stmt.where(SimopsConflict.status.in_(statuses))
    if result:
        stmt = stmt.where(SimopsConflict.result == result)
    if permit_id:
        stmt = stmt.where(
            or_(SimopsConflict.permit_a_id == permit_id, SimopsConflict.permit_b_id == permit_id)
        )
    if detected_from:
        stmt = stmt.where(SimopsConflict.detected_at >= detected_from)
    if detected_to:
        stmt = stmt.where(SimopsConflict.detected_at < detected_to)
    rows = []
    for c in db.scalars(
        stmt.order_by(SimopsConflict.detected_at.desc(), SimopsConflict.conflict_no.desc())
    ):
        a, b = db.get(Permit, c.permit_a_id), db.get(Permit, c.permit_b_id)
        if not any(x and acommon.grant_covers(g, [x.site_id], x.engagement_id) for x in (a, b)):
            continue
        if zone_ids and not any(x and set(x.zone_ids) & set(zone_ids) for x in (a, b)):
            continue
        if awaiting_me:
            if c.status != SimopsConflictStatus.open or c.result != SimopsResult.conditional:
                continue
            signed = _signed(_coordination(db, c.id))
            if not any(
                s.role.value not in signed and _can_sign(db, p, s) for s in required_signers(db, c)
            ):
                continue
        rows.append(c)
    total = len(rows)
    chunk = rows[(page - 1) * size : page * size]
    refs = Refs(db)
    return SimopsConflictPage(
        items=[conflict_read(db, c, refs) for c in chunk], total=total, page=page, page_size=size
    )


# ---- coordination (SM-6) -------------------------------------------------------------------------


def _can_sign_as(db: Session, user_id: uuid.UUID, s: Signer) -> bool:
    if s.user_id is not None:
        return s.user_id == user_id
    if s.role == CoordinationSignerRole.area_authority:
        return False
    x = s.permit
    return (
        common.find_appointment(
            db,
            x.project_id,
            AppointmentFunction.issuer,
            x.work_types,
            x.site_id,
            [],
            common.permit_days(x),
            user_id=user_id,
        )
        is not None
    )


def _can_sign(db: Session, p: Principal, s: Signer) -> bool:
    return _can_sign_as(db, p.user.id, s)


def _sign_roles(
    db: Session, user_id: uuid.UUID, c: SimopsConflict, signed: dict[str, Any]
) -> list[CoordinationSignerRole]:
    return [
        s.role
        for s in required_signers(db, c)
        if s.role.value not in signed and _can_sign_as(db, user_id, s)
    ]


def _add_signatures(
    db: Session,
    co: SimopsCoordination,
    c: SimopsConflict,
    user_id: uuid.UUID,
    roles: list[CoordinationSignerRole],
    at: datetime,
    device: uuid.UUID | None,
) -> None:
    sigs = [s for s in co.signatures if s.get("signed_at")]
    a = db.get(Permit, c.permit_a_id)
    for role in roles:
        sigs.append({"role": role.value, "user_id": str(user_id), "signed_at": at.isoformat()})
        common.sign(
            db,
            a,
            SignaturePurpose.simops_coordination,
            role.value,
            user_id=user_id,
            entity_id=co.id,
            co_device=device,
            at=at,
        )
    co.signatures = sigs


def _complete(
    db: Session, p: Principal, co: SimopsCoordination, c: SimopsConflict, at: datetime
) -> None:
    signed = _signed(co)
    if all(s.role.value in signed for s in required_signers(db, c)):
        co.status = CoordinationStatus.signed
        co.signed_at = at
        before = c.status
        c.status = SimopsConflictStatus.coordinated
        c.coordinated_at = at
        db.flush()
        _audit(
            db, p, c, AuditAction.status_change, {"status": before.value}, {"status": "coordinated"}
        )
        a = db.get(Permit, c.permit_a_id)
        if a is not None:
            _refresh_pair(db, a)


def create_coordination(
    db: Session, p: Principal, conflict_id: uuid.UUID, body: CoordinationCreate
) -> SimopsConflictRead:
    from app.services import auth  # noqa: PLC0415

    c = _get(db, p, conflict_id)
    acommon.require_cap(p, c.project_id, C.simops_coordinate)
    if c.result != SimopsResult.conditional or c.status != SimopsConflictStatus.open:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            "Coordination records are made for open conditional conflicts only.",
            "سجلات التنسيق للتعارضات المشروطة المفتوحة فقط.",
            status=409,
        )
    if _coordination(db, c.id) is not None:
        raise common.err(
            ErrorCode.DUPLICATE_VALUE,
            "A coordination record already exists; sign it instead.",
            "يوجد سجل تنسيق بالفعل؛ وقّع عليه.",
            status=409,
        )
    roles = _sign_roles(db, p.user.id, c, {})
    if not roles:
        raise forbidden_error(
            "Only the issuers of both permits and the area authority of permit A sign (SM-6)."
        )
    common.require_reauth(db, p, c.project_id)
    a, b = db.get(Permit, c.permit_a_id), db.get(Permit, c.permit_b_id)
    assert a is not None and b is not None  # noqa: S101
    at = now()
    co = SimopsCoordination(
        id=uuid.uuid4(),
        conflict_id=c.id,
        agreed_controls_en=body.agreed_controls_en,
        agreed_controls_ar=body.agreed_controls_ar,
        signatures=[],
        status=CoordinationStatus.pending_signatures,
        valid_until=min(a.valid_to_at, b.valid_to_at),
        created_by_user_id=p.user.id,
        created_at=at,
    )
    db.add(co)
    db.flush()
    _add_signatures(db, co, c, p.user.id, roles, at, None)
    for cs in body.cosigners:
        u = auth.check_cosigner(db, cs.user_id, cs.password)
        more = _sign_roles(db, u.id, c, _signed(co))
        if not more:
            raise common.err(
                ErrorCode.COSIGNER_INVALID,
                "The co-signer is not a required signer of this conflict.",
                "الموقّع المشارك ليس من الموقعين المطلوبين.",
                status=401,
            )
        _add_signatures(db, co, c, u.id, more, at, p.user.id)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(c.project_id),
        entity_type=EntityType.simops_coordination,
        entity_id=co.id,
        project_id=c.project_id,
        after={"conflict_no": c.conflict_no, "signatures": [s["role"] for s in co.signatures]},
    )
    _complete(db, p, co, c, at)
    return conflict_read(db, c)


def sign(
    db: Session, p: Principal, coordination_id: uuid.UUID, body: CoordinationSignInput
) -> SimopsConflictRead:
    co = db.get(SimopsCoordination, coordination_id)
    if co is None:
        raise not_found("Coordination record")
    c = _get(db, p, co.conflict_id)
    acommon.require_cap(p, c.project_id, C.simops_coordinate)
    if co.status != CoordinationStatus.pending_signatures:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            f"The record is {co.status.value}.",
            "السجل غير مفتوح للتوقيع.",
            status=409,
        )
    roles = _sign_roles(db, p.user.id, c, _signed(co))
    if not roles:
        raise forbidden_error("You are not a pending signer of this coordination record.")
    common.require_reauth(db, p, c.project_id)
    at = now()
    _add_signatures(db, co, c, p.user.id, roles, at, None)
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(c.project_id),
        entity_type=EntityType.simops_coordination,
        entity_id=co.id,
        project_id=c.project_id,
        after={"signed_as": [r.value for r in roles]},
        details={"note": body.note} if body.note else None,
    )
    _complete(db, p, co, c, at)
    return conflict_read(db, c)


def _audit(
    db: Session,
    p: Principal | None,
    c: SimopsConflict,
    action: AuditAction,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    audit.record(
        db,
        action,
        p.actor(c.project_id) if p else audit.SYSTEM,
        entity_type=EntityType.simops_conflict,
        entity_id=c.id,
        project_id=c.project_id,
        before=before,
        after=after,
    )
