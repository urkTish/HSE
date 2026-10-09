"""Emergency band, action panel and the permit emergency_info pre-fill (spec 6c-emergency-drills
§8.1 item 2, §8.2, PE-6)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.emergency_enums import (
    ActiveStatus,
    ApKind,
    AssetStatus,
    DrillShift,
    DrillStatus,
    EmergencyActionKind,
    EventStatus,
    LineStatus,
    MusterStatus,
    NotReadyReason,
    TeamType,
)
from app.core.enums import Capability, SiteSide, SiteStatus
from app.core.ptw_enums import PermitStatus, PtwCrewRole, StatusReason
from app.core.ptw_enums import PermitType as T
from app.models import (
    AssemblyPoint,
    Drill,
    EmergencyAsset,
    EmergencyContact,
    EmergencyEvent,
    Muster,
    Permit,
    PermitCrew,
    PermitSuspension,
    RescueTeam,
    Site,
    Zone,
)
from app.schemas.emergency import (
    BoardSite,
    EmergencyActionItem,
    EmergencyActionPanel,
    EmergencyBoard,
    EmergencyInfo,
)
from app.services.emergency import assets as em_assets
from app.services.emergency import common as ec
from app.services.emergency import drills as em_drills
from app.services.emergency import erp as em_erp
from app.services.emergency import events as em_events
from app.services.emergency import muster as mu
from app.services.emergency import org, programme
from app.services.permissions import Principal

C = Capability
K = EmergencyActionKind
LIVE_MUSTER = (MusterStatus.open, MusterStatus.reconciled)

LABELS: dict[EmergencyActionKind, tuple[str, str]] = {
    K.erp_overdue: ("ERP review overdue", "مراجعة خطة الطوارئ متأخرة"),
    K.erp_review_required: ("ERP review required", "مطلوب مراجعة خطة الطوارئ"),
    K.zone_without_assembly_point: ("Zones without an assembly point", "مناطق بلا نقطة تجمع"),
    K.active_events: ("Active emergency events", "أحداث طارئة نشطة"),
    K.open_musters_unaccounted: (
        "Open musters with unaccounted persons",
        "تجميع مفتوح بأشخاص غير محصورين",
    ),
    K.coverage_shortfall: (
        "Current-shift coverage shortfalls",
        "نقص تغطية فريق الطوارئ في الوردية الحالية",
    ),
    K.programme_overdue: ("Overdue drill programme lines", "بنود برنامج تمارين متأخرة"),
    K.drill_evaluation_overdue: ("Drills not evaluated in time", "تمارين لم تُقيَّم في الوقت"),
    K.event_review_overdue: ("Events not reviewed in time", "أحداث لم تُراجع في الوقت"),
    K.assets_out_of_service: ("Assets Out of Service or Missing", "معدات خارج الخدمة أو مفقودة"),
    K.asset_checks_overdue: ("Asset checks overdue", "فحوص معدات متأخرة"),
    K.provision_gaps: ("Emergency provision gaps", "نقص في معدات الطوارئ"),
    K.rescue_teams_not_current: ("Rescue teams not current", "فرق إنقاذ غير جاهزة"),
    K.cse_permits_team_not_current: (
        "Active CSE permits whose rescue team is not current",
        "تصاريح أماكن محصورة نشطة وفريق الإنقاذ غير جاهز",
    ),
    K.permits_still_drill_suspended: (
        "Permits still suspended 2 h after a drill",
        "تصاريح ما زالت موقوفة بعد التمرين بساعتين",
    ),
}


def _sites(db: Session, project_id: uuid.UUID) -> list[Site]:
    return list(
        db.scalars(
            select(Site)
            .where(Site.project_id == project_id, Site.status == SiteStatus.active)
            .order_by(Site.code)
        )
    )


def _today_zones(db: Session, project_id: uuid.UUID, d: date) -> dict[uuid.UUID, list[uuid.UUID]]:
    out: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for (s, _d, _sh), (_hc, zw) in ec.returns_by_site_day(db, project_id, d, d).items():
        for z in zw:
            if z not in out[s]:
                out[s].append(z)
    return out


def _live_musters(db: Session, project_id: uuid.UUID) -> list[Muster]:
    return list(
        db.scalars(
            select(Muster)
            .where(Muster.project_id == project_id, Muster.status.in_(LIVE_MUSTER))
            .order_by(Muster.opened_at)
        )
    )


def _active_events(db: Session, project_id: uuid.UUID) -> list[EmergencyEvent]:
    return list(
        db.scalars(
            select(EmergencyEvent)
            .where(
                EmergencyEvent.project_id == project_id, EmergencyEvent.status == EventStatus.active
            )
            .order_by(EmergencyEvent.raised_at)
        )
    )


def _current_coverage(
    db: Session, project_id: uuid.UUID, at: datetime
) -> tuple[date, DrillShift, dict[uuid.UUID, ec.SiteDay]]:
    d, sh = ec.cfg(db, project_id).shift_of(at)
    rows = ec.coverage_days(db, project_id, d, d, None, sh)
    return d, sh, {x.site_id: x for x in rows}


def board(db: Session, p: Principal, project_id: uuid.UUID) -> EmergencyBoard:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    at = now()
    today = ec.local_day(at)
    e = ec.erp_in_force(db, project_id)
    _d, sh, cov = _current_coverage(db, project_id, at)
    zmap = ec.zone_map(db, project_id)
    gaps = em_assets.provision_gaps(db, project_id, today, _today_zones(db, project_id, today))
    lines = [
        ln for ln in programme.views(db, project_id, today) if ln.status != LineStatus.satisfied
    ]
    sites = []
    for s in _sites(db, project_id):
        due = sorted(
            (ln for ln in lines if ln.site_id == s.id and ln.due_by is not None),
            key=lambda ln: ln.due_by or today,
        )[:3]
        x = cov.get(s.id)
        sites.append(
            BoardSite(
                site_id=s.id,
                site_code=s.code,
                shift=sh,
                coverage=org.coverage_row(db, x, zmap) if x else None,
                provision_gaps=gaps.get(s.id, []),
                next_drills_due=due,
            )
        )
    return EmergencyBoard(
        project_id=project_id,
        at=at,
        erp=em_erp.erp_read(db, e) if e else None,
        active_events=[em_events.event_read(db, x) for x in _active_events(db, project_id)],
        open_musters=[mu.muster_read(db, m, p) for m in _live_musters(db, project_id)],
        sites=sites,
    )


# ---- action panel (§8.2) -------------------------------------------------------------------------


def _unaccounted(db: Session, m: Muster) -> bool:
    if m.status != MusterStatus.open:
        return False
    if m.counts:
        return any(mu._row_outstanding(r) > 0 for r in m.counts)
    return any(x.state in mu.OPEN_STATES for x in mu.entries(db, m))


def cse_permits_not_current(db: Session, project_id: uuid.UUID, d: date) -> list[str]:
    from app.services.med import common as mcommon  # noqa: PLC0415

    out = []
    for pm in db.scalars(
        select(Permit).where(
            Permit.project_id == project_id,
            Permit.status == PermitStatus.active,
            Permit.work_types.contains([T.confined_space.value]),
        )
    ):
        for line in db.scalars(
            select(PermitCrew).where(
                PermitCrew.permit_id == pm.id,
                PermitCrew.crew_role == PtwCrewRole.rescue_lead,
                PermitCrew.removed_at.is_(None),
            )
        ):
            dep = mcommon.deployment(db, line.worker_id, project_id)
            t = org.team_for_lead(db, project_id, dep.id, TeamType.confined_space) if dep else None
            if t is None or not org.readiness(db, t, d).current:
                out.append(pm.permit_no)
                break
    return out


def action_items(db: Session, project_id: uuid.UUID, at: datetime) -> list[EmergencyActionItem]:
    c = ec.cfg(db, project_id)
    today = ec.local_day(at)
    found: dict[EmergencyActionKind, list[str]] = defaultdict(list)
    e = ec.erp_in_force(db, project_id)
    if e is not None and ec.erp_overdue(e, today):
        found[K.erp_overdue].append(e.erp_no)
    if e is not None and e.review_required:
        found[K.erp_review_required].append(e.erp_no)
    served: set[uuid.UUID] = set()
    for a in ec.active_aps(db, project_id):
        served |= set(a.zones_served or [])
        if a.zone_id:
            served.add(a.zone_id)
    plan_sites = {str(x) for x in (e.site_ids if e else [])}
    for z in ec.zone_map(db, project_id).values():
        if str(z.site_id) in plan_sites and z.id not in served:
            found[K.zone_without_assembly_point].append(z.code)
    for ev in _active_events(db, project_id):
        found[K.active_events].append(ev.event_no)
    for m in _live_musters(db, project_id):
        if _unaccounted(db, m):
            found[K.open_musters_unaccounted].append(m.muster_no)
    _d, _sh, cov = _current_coverage(db, project_id, at)
    for x in cov.values():
        if x.result.state.value == "short":
            found[K.coverage_shortfall].append(ec.site_code(db, x.site_id) or "")
    for ln in programme.views(db, project_id, today):
        if ln.status == LineStatus.overdue:
            found[K.programme_overdue].append(ln.line_no)
    for d in db.scalars(
        select(Drill).where(Drill.project_id == project_id, Drill.status == DrillStatus.conducted)
    ):
        due = em_drills.evaluation_due(db, d)
        if due is not None and today > due:
            found[K.drill_evaluation_overdue].append(d.drill_no)
    rdays = int(c["event_review_days"])
    for ev in db.scalars(
        select(EmergencyEvent).where(
            EmergencyEvent.project_id == project_id,
            EmergencyEvent.status == EventStatus.all_clear,
        )
    ):
        if ev.all_clear_at and today > ec.local_day(ev.all_clear_at) + timedelta(days=rdays):
            found[K.event_review_overdue].append(ev.event_no)
    assets = [
        a
        for a in db.scalars(select(EmergencyAsset).where(EmergencyAsset.project_id == project_id))
        if a.asset_type.value != "spill_kit"  # 6c v1.2: shown on the 6e pages (K-125)
    ]
    by_id = {a.id: a for a in assets}
    for a in assets:
        if a.status in (AssetStatus.out_of_service, AssetStatus.missing):
            found[K.assets_out_of_service].append(a.asset_tag)
    checks_by_site: dict[str, int] = defaultdict(int)
    for aid, r in em_assets.ready_map(db, project_id, today, assets).items():
        if NotReadyReason.CHECK_OVERDUE in r.reasons:
            checks_by_site[ec.site_code(db, by_id[aid].site_id) or ""] += 1
    n_checks = sum(checks_by_site.values())
    gaps = em_assets.provision_gaps(db, project_id, today, _today_zones(db, project_id, today))
    for s, g in gaps.items():
        found[K.provision_gaps].extend(f"{ec.site_code(db, s)}: {x}" for x in g)
    for t in db.scalars(
        select(RescueTeam).where(
            RescueTeam.project_id == project_id, RescueTeam.status == ActiveStatus.active
        )
    ):
        if not org.readiness(db, t, today).current:
            found[K.rescue_teams_not_current].append(t.team_code)
    if c.enforced_on(today):
        found[K.cse_permits_team_not_current] = cse_permits_not_current(db, project_id, today)
    for pm, sp in db.execute(
        select(Permit, PermitSuspension)
        .join(PermitSuspension, PermitSuspension.permit_id == Permit.id)
        .where(
            Permit.project_id == project_id,
            Permit.status == PermitStatus.suspended,
            Permit.status_reason == StatusReason.emergency_drill,
            PermitSuspension.resumed_at.is_(None),
        )
    ):
        dr = db.scalar(select(Drill).where(Drill.drill_no == sp.auto_source_ref))
        if dr is not None and dr.conducted_at is not None:
            tl_end = ec.dt((dr.timeline or {}).get("all_clear_at")) or dr.conducted_at
            if at - tl_end > timedelta(hours=2):
                found[K.permits_still_drill_suspended].append(pm.permit_no)
    out = []
    for k in K:
        refs = found.get(k) or []
        n = n_checks if k == K.asset_checks_overdue else len(refs)
        if k == K.asset_checks_overdue:
            refs = [f"{s}: {v}" for s, v in sorted(checks_by_site.items())]
        if n:
            out.append(
                EmergencyActionItem(
                    kind=k, count=n, refs=refs[:50], label_en=LABELS[k][0], label_ar=LABELS[k][1]
                )
            )
    return out


def action_panel(db: Session, p: Principal, project_id: uuid.UUID) -> EmergencyActionPanel:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_kpi_view, write=False)
    at = now()
    return EmergencyActionPanel(
        project_id=project_id, at=at, items=action_items(db, project_id, at)
    )


# ---- PE-6 ----------------------------------------------------------------------------------------


def emergency_info(
    db: Session, p: Principal, project_id: uuid.UUID, zone_ids: list[uuid.UUID]
) -> EmergencyInfo:
    ec.project(db, p, project_id)
    zmap = ec.zone_map(db, project_id)
    zones = [zmap[z] for z in zone_ids if z in zmap]
    first: Zone | None = zones[0] if zones else None
    ap: AssemblyPoint | None = None
    if first is not None:
        aps = [
            a
            for a in ec.active_aps(db, project_id, first.site_id)
            if first.id in (a.zones_served or []) or a.zone_id == first.id
        ]
        aps.sort(key=lambda a: (a.kind != ApKind.primary, a.ap_code))
        ap = aps[0] if aps else None
    site = db.get(Site, first.site_id) if first else None
    airside = any(z.airside_area is not None or z.in_movement_area for z in zones) or (
        site is not None and site.site_side == SiteSide.airside
    )
    wanted = ["site_clinic", "client_emergency", "civil_defense", "red_crescent"]
    if airside:
        wanted.append("airport_arff")
    contacts = [
        c
        for c in db.scalars(
            select(EmergencyContact).where(
                EmergencyContact.project_id == project_id,
                EmergencyContact.active.is_(True),
                EmergencyContact.agency.in_(wanted),
            )
        )
        if not c.site_ids or site is None or site.id in c.site_ids
    ]
    best: dict[str, EmergencyContact] = {}
    for c in sorted(contacts, key=lambda c: c.priority):
        best.setdefault(c.agency, c)
    internal = best.get("site_clinic") or best.get("client_emergency")
    numbers: list[str] = []
    parts: list[str] = []
    if ap is not None:
        parts.append(f"Assembly point {ap.ap_code} ({ap.location_en})")
    if internal is not None:
        numbers.append(internal.phone)
        parts.append(f"Internal emergency {internal.phone}")
    for ag, label in (
        ("civil_defense", "Civil Defense"),
        ("red_crescent", "Red Crescent"),
        ("airport_arff", "Airport ARFF"),
    ):
        x = best.get(ag)
        if x is not None:
            numbers.append(x.phone)
            parts.append(f"{label} {x.phone}")
    return EmergencyInfo(
        text="; ".join(parts)[:300],
        assembly_point_code=ap.ap_code if ap else None,
        numbers=numbers,
    )
