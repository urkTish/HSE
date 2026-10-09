"""Emergency organisation (spec 6c-emergency-drills §3.6, §3.7, EO-1…EO-7, RT-1…RT-3): roster
assignments with the Phase 5 matrix role (EO-2), rescue teams and their readiness (§6.6),
coverage per site, shift and date (§6.2)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cert_enums import EquipmentCertCategory, ServiceStatus
from app.core.emergency_enums import (
    ActiveStatus,
    AssetType,
    DrillShift,
    DrillStatus,
    EmergencyRole,
    TeamReason,
    TeamType,
)
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found, validation_error
from app.models import (
    Deployment,
    Drill,
    EmergencyAsset,
    EquipmentItem,
    RescueTeam,
    RosterAssignment,
)
from app.schemas.emergency import (
    CoverageList,
    CoverageRow,
    RosterCreate,
    RosterCreated,
    RosterEnd,
    RosterPage,
    RosterRead,
    TeamCreate,
    TeamMember,
    TeamPage,
    TeamRead,
    TeamReadiness,
    TeamUpdate,
)
from app.services.access import common as acommon
from app.services.common import invalid_transition
from app.services.emergency import common as ec
from app.services.emergency import reference as ref
from app.services.permissions import Principal
from app.services.train.validity import add_months

C = Capability
TEAM_DRILL = {TeamType.confined_space: ref.DT.cse_rescue, TeamType.height: ref.DT.height_rescue}


# ---- roster --------------------------------------------------------------------------------------


def _qual(db: Session, a: RosterAssignment, d: date) -> tuple[bool | None, str | None, str | None]:
    code = ref.ROLES[a.role][2]
    if code is None or a.deployment_id is None:
        return None, None, None
    w = ec.worker_of(db, a.deployment_id)
    if w is None:
        return False, code, "TRAINING_MISSING"
    b = ec.Quals(db, a.project_id).best(w.id, code, d)
    return b.met, code, None if b.met else (b.reason.value if b.reason else "TRAINING_MISSING")


def roster_read(db: Session, a: RosterAssignment, d: date | None = None) -> RosterRead:
    d = d or ec.local_day()
    w = ec.worker_of(db, a.deployment_id)
    dep = db.get(Deployment, a.deployment_id) if a.deployment_id else None
    q, code, why = _qual(db, a, d)
    return RosterRead(
        id=a.id,
        assignment_no=a.assignment_no,
        project_id=a.project_id,
        role=a.role,
        deployment_id=a.deployment_id,
        worker=acommon.worker_ref(w, True) if w else None,
        user=ec.user_ref(db, a.user_id) if a.user_id else None,
        engagement_code=ec.eng_code(db, dep.engagement_id) if dep else None,
        site_id=a.site_id,
        site_code=ec.site_code(db, a.site_id) or "",
        zone_ids=list(a.zone_ids or []),
        zone_codes=ec.codes(db, a.zone_ids or []),
        shift=a.shift,
        valid_from=a.valid_from,
        valid_to=a.valid_to,
        active=a.valid_from <= d and (a.valid_to is None or a.valid_to >= d),
        qualified_today=q,
        qualification_code=code,
        qualification_reason=why,
    )


def list_roster(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None,
    role: EmergencyRole | None,
    active_only: bool,
    page: int,
    size: int,
) -> RosterPage:
    """P6c-2: roster names are visible to every project user with 178."""
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    d = ec.local_day()
    q = select(RosterAssignment).where(RosterAssignment.project_id == project_id)
    if site_id is not None:
        q = q.where(RosterAssignment.site_id == site_id)
    if role is not None:
        q = q.where(RosterAssignment.role == role)
    if active_only:
        q = q.where(
            RosterAssignment.valid_from <= d,
            (RosterAssignment.valid_to.is_(None)) | (RosterAssignment.valid_to >= d),
        )
    rows = list(db.scalars(q.order_by(RosterAssignment.seq)))
    items = [roster_read(db, a, d) for a in rows[(page - 1) * size : page * size]]
    return RosterPage(items=items, total=len(rows), page=page, page_size=size)


def add_matrix_role(db: Session, p: Principal | None, dep: Deployment, role: str) -> bool:
    """EO-2: add the Phase 5 matrix role if missing (audited `matrix_role_added_by_6c`)."""
    from app.services.train import matrix  # noqa: PLC0415

    pr = matrix.profile_row(db, dep)
    cur = sorted(pr.matrix_roles or []) if pr else []
    if role in cur:
        return False
    matrix.set_profile(db, p, dep, matrix_roles=sorted([*cur, role]))
    ec.audit_change(
        db, p, EntityType.training_profile, dep.id, dep.project_id,
        {"matrix_roles": cur}, {"matrix_roles": sorted([*cur, role]),
                                "matrix_role_added_by_6c": role},
    )  # fmt: skip
    return True


def create_assignment(
    db: Session, p: Principal, project_id: uuid.UUID, body: RosterCreate
) -> RosterCreated:
    pr = ec.project(db, p, project_id)
    g = p.require(project_id, C.emergency_roster_manage)
    ec.site_or_422(db, project_id, body.site_id)
    if not g.covers_site(body.site_id):
        from app.services.permissions import forbidden_error  # noqa: PLC0415

        raise forbidden_error()
    dep = None
    if body.role == EmergencyRole.emergency_coordinator and body.user_id is not None:
        if body.deployment_id is not None:
            raise validation_error("user_id", "Give a deployment or a user, not both.")
    else:
        if body.user_id is not None:
            raise validation_error("user_id", "A user is only for the emergency coordinator.")
        if body.deployment_id is None:
            raise validation_error("deployment_id", "Choose the worker deployment.")
        dep = ec.mobilised(db, body.deployment_id, project_id, "deployment_id")
        if not ec.covers_dep(g, dep):
            from app.services.permissions import forbidden_error  # noqa: PLC0415

            raise forbidden_error()  # EO-1: Contractor HSE Reps in their C scope
        if body.site_id not in (dep.site_ids or []):
            raise validation_error("site_id", "The site must be a site of the deployment.")
    if body.role == EmergencyRole.fire_warden and not body.zone_ids:
        raise validation_error("zone_ids", "A fire warden needs at least one zone of the site.")
    ec.zones_of_site(db, body.site_id, body.zone_ids)
    if body.valid_to is not None and body.valid_to < body.valid_from:
        raise validation_error("valid_to", "On or after valid_from.")
    seq = (
        int(
            db.scalar(
                select(func.max(RosterAssignment.seq)).where(
                    RosterAssignment.project_id == project_id
                )
            )
            or 0
        )
        + 1
    )
    a = RosterAssignment(
        id=uuid.uuid4(),
        assignment_no=f"EOR-{pr.code}-{seq:05d}",
        project_id=project_id,
        seq=seq,
        role=body.role,
        deployment_id=body.deployment_id,
        user_id=body.user_id,
        site_id=body.site_id,
        zone_ids=list(dict.fromkeys(body.zone_ids)),
        shift=body.shift,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        designated_by_user_id=p.user.id,
        created_by_user_id=p.user.id,
    )
    db.add(a)
    db.flush()
    ec.record(db, p, AuditAction.create, EntityType.emergency_roster, a, project_id)
    added = False
    mr = ref.MATRIX_ROLE.get(body.role)
    if mr is not None and dep is not None:
        added = add_matrix_role(db, p, dep, mr)
    return RosterCreated(assignment=roster_read(db, a), matrix_role_added=added)


def end_assignment(
    db: Session, p: Principal, assignment_id: uuid.UUID, body: RosterEnd
) -> RosterRead:
    a = db.get(RosterAssignment, assignment_id)
    if a is None or not p.can_see_project(a.project_id):
        raise not_found("Roster assignment")
    g = p.require(a.project_id, C.emergency_roster_manage)
    dep = db.get(Deployment, a.deployment_id) if a.deployment_id else None
    if not g.covers_site(a.site_id) or (dep is not None and not ec.covers_dep(g, dep)):
        from app.services.permissions import forbidden_error  # noqa: PLC0415

        raise forbidden_error()
    if a.valid_to is not None and a.valid_to < ec.local_day():
        raise invalid_transition("Roster assignment", "ended", "ended")
    if body.valid_to < a.valid_from:
        raise validation_error("valid_to", "On or after valid_from.")
    before = {"valid_to": a.valid_to.isoformat() if a.valid_to else None}
    a.valid_to = body.valid_to
    a.ended_reason = body.reason
    a.updated_by_user_id = p.user.id
    db.flush()
    ec.audit_change(
        db, p, EntityType.emergency_roster, a.id, a.project_id, before,
        {"valid_to": body.valid_to.isoformat(), "reason": body.reason},
    )  # fmt: skip
    return roster_read(db, a)


# ---- rescue teams (§3.7, RT-1, RT-2) -------------------------------------------------------------


@dataclass
class Readiness:
    current: bool
    reasons: list[TeamReason] = field(default_factory=list)
    last_drill_on: date | None = None
    current_until: date | None = None
    qualified: set[uuid.UUID] = field(default_factory=set)
    first_aiders: set[uuid.UUID] = field(default_factory=set)


def last_team_drill(db: Session, t: RescueTeam, d: date) -> date | None:
    rows = db.scalars(
        select(Drill.conducted_at).where(
            Drill.team_id == t.id,
            Drill.drill_type == TEAM_DRILL[t.team_type],
            Drill.status == DrillStatus.evaluated,
            Drill.conducted_at.is_not(None),
        )
    )
    days = [ec.local_day(x) for x in rows if x is not None and ec.local_day(x) <= d]
    return max(days) if days else None


def equipment_ready(db: Session, t: RescueTeam, d: date) -> bool:
    from app.services.emergency import assets  # noqa: PLC0415

    items = [db.get(EquipmentItem, i) for i in t.equipment_item_ids or []]
    kits = [db.get(EmergencyAsset, i) for i in t.asset_ids or []]
    if not items and not kits:
        return False
    if any(x is None or x.service_status != ServiceStatus.in_service for x in items):
        return False
    return all(a is not None and assets.readiness(db, a, d).ready for a in kits)


def readiness(db: Session, t: RescueTeam, d: date, quals: ec.Quals | None = None) -> Readiness:
    """RT-2 at date d."""
    c = ec.cfg(db, t.project_id)
    quals = quals or ec.Quals(db, t.project_id)
    people = [t.lead_deployment_id, *(t.member_deployment_ids or [])]
    wmap = ec.dep_worker(db, people)
    quals.load(wmap.values())
    code = ref.TEAM_CODE[t.team_type]
    r = Readiness(current=True)
    for dep in people:
        w = wmap.get(dep)
        if w is None:
            continue
        if quals.ok(w, code, d):
            r.qualified.add(dep)
        if quals.ok(w, "FIRST-AID", d):
            r.first_aiders.add(dep)
    if len(r.qualified) < int(c["rescue_team_min_members"][t.team_type.value]):
        r.reasons.append(TeamReason.TEAM_UNDERSTRENGTH)
    if not r.first_aiders & set(people):
        r.reasons.append(TeamReason.NO_FIRST_AIDER)
    r.last_drill_on = last_team_drill(db, t, d)
    if r.last_drill_on is not None:
        r.current_until = add_months(r.last_drill_on, 12) - timedelta(days=1)
    if r.current_until is None or d > r.current_until:
        r.reasons.append(TeamReason.RESCUE_DRILL_OVERDUE)
    if not equipment_ready(db, t, d):
        r.reasons.append(TeamReason.RESCUE_EQUIPMENT_NOT_READY)
    r.current = not r.reasons
    return r


def team_read(db: Session, t: RescueTeam, d: date | None = None) -> TeamRead:
    d = d or ec.local_day()
    r = readiness(db, t, d)
    members = []
    for dep in [t.lead_deployment_id, *(t.member_deployment_ids or [])]:
        w = ec.worker_of(db, dep)
        members.append(
            TeamMember(
                deployment_id=dep,
                worker=acommon.worker_ref(w, True) if w else None,
                lead=dep == t.lead_deployment_id,
                qualified=dep in r.qualified,
                first_aider=dep in r.first_aiders,
            )
        )
    items = [db.get(EquipmentItem, i) for i in t.equipment_item_ids or []]
    kits = [db.get(EmergencyAsset, i) for i in t.asset_ids or []]
    return TeamRead(
        id=t.id,
        project_id=t.project_id,
        team_code=t.team_code,
        team_type=t.team_type,
        site_ids=list(t.site_ids or []),
        members=members,
        equipment_item_ids=list(t.equipment_item_ids or []),
        equipment_nos=[x.equipment_no for x in items if x is not None],
        asset_ids=list(t.asset_ids or []),
        asset_tags=[x.asset_tag for x in kits if x is not None],
        status=t.status,
        readiness=TeamReadiness(
            current=r.current,
            reasons=r.reasons,
            last_drill_on=r.last_drill_on,
            current_until=r.current_until,
        ),
    )


def list_teams(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    team_type: TeamType | None,
    as_of: date | None,
    page: int,
    size: int,
) -> TeamPage:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    q = select(RescueTeam).where(RescueTeam.project_id == project_id)
    if team_type is not None:
        q = q.where(RescueTeam.team_type == team_type)
    rows = list(db.scalars(q.order_by(RescueTeam.team_code)))
    items = [team_read(db, t, as_of) for t in rows[(page - 1) * size : page * size]]
    return TeamPage(items=items, total=len(rows), page=page, page_size=size)


def _team(db: Session, p: Principal, team_id: uuid.UUID) -> RescueTeam:
    t = db.get(RescueTeam, team_id)
    if t is None or not p.can_see_project(t.project_id):
        raise not_found("Rescue team")
    ec.need(p, t.project_id, C.emergency_view, write=False)
    return t


def read_team(db: Session, p: Principal, team_id: uuid.UUID, as_of: date | None) -> TeamRead:
    return team_read(db, _team(db, p, team_id), as_of)


def _check_team(
    db: Session,
    project_id: uuid.UUID,
    team_type: TeamType,
    lead: uuid.UUID,
    members: list[uuid.UUID],
    items: list[uuid.UUID],
    kits: list[uuid.UUID],
    sites: list[uuid.UUID],
    self_id: uuid.UUID | None,
) -> None:
    for s in sites:
        ec.site_or_422(db, project_id, s)
    if lead in members:
        raise validation_error("member_deployment_ids", "The lead is not also a member.")
    for i, dep in enumerate([lead, *members]):
        ec.mobilised(
            db, dep, project_id, "lead_deployment_id" if i == 0 else "member_deployment_ids"
        )
    people = {lead, *members}
    for t in db.scalars(
        select(RescueTeam).where(
            RescueTeam.project_id == project_id,
            RescueTeam.team_type == team_type,
            RescueTeam.status == ActiveStatus.active,
        )
    ):
        if t.id == self_id:
            continue
        clash = people & {t.lead_deployment_id, *(t.member_deployment_ids or [])}
        if clash:
            raise ec.err(
                422,
                ErrorCode.ALREADY_IN_TEAM,
                f"Already in the active {team_type.value} team {t.team_code} (RT-1).",
                f"العامل عضو في فريق الإنقاذ {t.team_code}.",
                field="member_deployment_ids",
                team_code=t.team_code,
            )
    for i in items:
        x = db.get(EquipmentItem, i)
        if x is None or x.category != EquipmentCertCategory.tripod_winch:
            raise validation_error("equipment_item_ids", "Choose Phase 4 tripod / winch items.")
    for k in kits:
        a = db.get(EmergencyAsset, k)
        if a is None or a.project_id != project_id or a.asset_type != AssetType.rescue_kit_height:
            raise validation_error("asset_ids", "Choose height rescue kits of the project.")


def create_team(db: Session, p: Principal, project_id: uuid.UUID, body: TeamCreate) -> TeamRead:
    ec.project(db, p, project_id)
    p.require(project_id, C.emergency_roster_manage)
    members = list(dict.fromkeys(body.member_deployment_ids))
    _check_team(
        db, project_id, body.team_type, body.lead_deployment_id, members,
        body.equipment_item_ids, body.asset_ids, body.site_ids, None,
    )  # fmt: skip
    if db.scalar(
        select(RescueTeam.id).where(
            RescueTeam.project_id == project_id, RescueTeam.team_code == body.team_code
        )
    ):
        from app.services.common import duplicate  # noqa: PLC0415

        raise duplicate("team_code", "This team code is already used on the project.")
    t = RescueTeam(
        id=uuid.uuid4(),
        project_id=project_id,
        team_code=body.team_code,
        team_type=body.team_type,
        site_ids=list(body.site_ids),
        lead_deployment_id=body.lead_deployment_id,
        member_deployment_ids=members,
        equipment_item_ids=list(body.equipment_item_ids),
        asset_ids=list(body.asset_ids),
        created_on=ec.local_day(),
        status=ActiveStatus.active,
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    db.add(t)
    db.flush()
    ec.record(db, p, AuditAction.create, EntityType.rescue_team, t, project_id)
    return team_read(db, t)


def update_team(db: Session, p: Principal, team_id: uuid.UUID, body: TeamUpdate) -> TeamRead:
    t = _team(db, p, team_id)
    p.require(t.project_id, C.emergency_roster_manage)
    from app.services.cert import common as cc  # noqa: PLC0415

    snap = cc.snap(t)
    ch = body.changes()
    lead = ch.get("lead_deployment_id") or t.lead_deployment_id
    members = list(dict.fromkeys(ch.get("member_deployment_ids") or t.member_deployment_ids))
    status = ch.get("status") or t.status
    if status == ActiveStatus.active:
        _check_team(
            db, t.project_id, t.team_type, lead, members,
            ch.get("equipment_item_ids") or list(t.equipment_item_ids or []),
            ch.get("asset_ids") or list(t.asset_ids or []),
            ch.get("site_ids") or list(t.site_ids or []), t.id,
        )  # fmt: skip
    for k, v in ch.items():
        if v is not None:
            setattr(t, k, list(v) if isinstance(v, list) else v)
    t.member_deployment_ids = members
    t.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, EntityType.rescue_team, t, t.project_id, before=snap)
    return team_read(db, t)


def team_for_lead(
    db: Session, project_id: uuid.UUID, dep_id: uuid.UUID, team_type: TeamType
) -> RescueTeam | None:
    """RT-3: the active team of the type in which the deployment is lead or member."""
    for t in db.scalars(
        select(RescueTeam).where(
            RescueTeam.project_id == project_id,
            RescueTeam.team_type == team_type,
            RescueTeam.status == ActiveStatus.active,
        )
    ):
        if dep_id == t.lead_deployment_id or dep_id in (t.member_deployment_ids or []):
            return t
    return None


# ---- coverage ------------------------------------------------------------------------------------


def coverage_row(db: Session, x: ec.SiteDay, zmap: dict[uuid.UUID, Any]) -> CoverageRow:
    r = x.result
    nos = []
    for dep in x.not_qualified:
        w = ec.worker_of(db, dep)
        if w is not None:
            nos.append(w.worker_no)
    return CoverageRow(
        site_id=x.site_id,
        site_code=ec.site_code(db, x.site_id) or "",
        day=x.day,
        shift=x.shift,
        headcount=x.hc,
        zones_with_work=[zmap[z].code for z in x.zones_work if z in zmap],
        state=r.state,
        first_aiders_required=r.rfa,
        first_aiders_counted=r.fa,
        wardens_required=r.rw,
        wardens_counted=r.wardens,
        zones_without_warden=[zmap[z].code for z in r.zones_without if z in zmap],
        coordinator_ok=r.coordinator_ok,
        reasons=r.reasons,
        rostered_not_qualified=sorted(set(nos)),
    )


def coverage(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    date_from: date,
    date_to: date | None,
    site_id: uuid.UUID | None,
    shift: DrillShift | None,
) -> CoverageList:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    d1 = date_to or date_from
    if d1 < date_from or (d1 - date_from).days > 62:
        raise validation_error("date_to", "A range of at most 62 days, not before date_from.")
    zmap = ec.zone_map(db, project_id)
    rows = ec.coverage_days(db, project_id, date_from, d1, site_id, shift)
    return CoverageList(
        project_id=project_id,
        date_from=date_from,
        date_to=d1,
        rows=[coverage_row(db, x, zmap) for x in rows],
    )
