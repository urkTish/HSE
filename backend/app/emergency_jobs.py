"""Phase 6c scheduled jobs (6c-emergency-drills §4, §7, P6c-4).

`emergency_minute` (every 60 s): exits after a muster opened (MU-2), reconciliation, the
headcount-target alert (MU-8) and the live coverage check at shift start + offset (EO-7).
`emergency_daily` (00:08): muster retention purge (P6c-4) and the cache reset.
`emergency_alerts` (07:05): drill due (DP-4), drill evaluation and event review overdue (DR-6,
EV-5), asset check overdue, service / hydrotest / consumable 30 / 7 / 0, rescue team currency
30 / 7 / 0 and at the change, ERP review 30 / 7 / 0 and overdue (ER-7).

Every step is de-duplicated per (subject, step) through JobMark."""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.emergency_enums import (
    ActiveStatus,
    AssetStatus,
    CoverageState,
    DrillShift,
    DrillStatus,
    EventStatus,
    MusterStatus,
    NotReadyReason,
)
from app.core.enums import AuditAction, EntityType, NotificationKind, SiteStatus
from app.core.hse_enums import Shift, WorkforceStatus
from app.models import (
    Drill,
    EmergencyAsset,
    EmergencyEvent,
    EmergencySettings,
    Muster,
    MusterEntry,
    RescueTeam,
    Site,
    WorkforceReturn,
)
from app.services import audit
from app.services.cert.alerts import long_step

NK = NotificationKind
SHORT = (30, 7, 0)


def _projects(db: Session) -> list[Any]:
    return list(
        db.scalars(
            select(EmergencySettings.project_id).where(
                EmergencySettings.emergency_register_from.is_not(None)
            )
        )
    )


# ---- EO-7 live coverage --------------------------------------------------------------------------


def live_headcount(
    db: Session, pid: uuid.UUID, site_id: uuid.UUID, d: date, sh: DrillShift, at: datetime
) -> tuple[int, list[uuid.UUID]]:
    """The live on-site roll (MU-2) on a gated site, else the mean headcount of the same shift
    over the last 7 days with returns."""
    from app.services.emergency import common as ec  # noqa: PLC0415
    from app.services.emergency import muster as mu  # noqa: PLC0415

    if ec.has_gates(db, pid, site_id):
        rows = mu.roll(db, pid, site_id, at, None)
        zones = list(dict.fromkeys(r.zone_id for r in rows if r.zone_id is not None))
        return len(rows), zones
    shifts = (
        (Shift.night,) if sh == DrillShift.night else tuple(s for s in Shift if s != Shift.night)
    )
    per_day: dict[date, int] = defaultdict(int)
    zones = []
    for wd, z, n in db.execute(
        select(WorkforceReturn.work_date, WorkforceReturn.zone_id, WorkforceReturn.headcount).where(
            WorkforceReturn.project_id == pid,
            WorkforceReturn.site_id == site_id,
            WorkforceReturn.work_date >= d - timedelta(days=7),
            WorkforceReturn.work_date < d,
            WorkforceReturn.shift.in_(shifts),
            WorkforceReturn.status != WorkforceStatus.draft,
            WorkforceReturn.no_work.is_(False),
        )
    ):
        per_day[wd] += int(n or 0)
        if z is not None and (n or 0) > 0 and z not in zones:
            zones.append(z)
    days = [v for v in per_day.values() if v > 0]
    return (math.ceil(sum(days) / len(days)) if days else 0), zones


def live_coverage(db: Session, pid: uuid.UUID, at: datetime) -> int:
    from app.services.emergency import common as ec  # noqa: PLC0415

    c = ec.cfg(db, pid)
    d, sh = c.shift_of(at)
    check_at = c.shift_begin(d, sh) + timedelta(minutes=int(c["coverage_check_offset_minutes"]))
    if at < check_at or not c.active_on(d):
        return 0
    n = 0
    for s in db.scalars(
        select(Site).where(Site.project_id == pid, Site.status == SiteStatus.active)
    ):
        if not ec.once(db, f"eo7:{s.id}:{d}:{sh.value}"):
            continue
        hc, zones = live_headcount(db, pid, s.id, d, sh, at)
        rows = ec.coverage_days(db, pid, d, d, s.id, sh, {(s.id, d, sh): (hc, zones)})
        bad = [x for x in rows if x.result.state == CoverageState.short]
        if not bad:
            continue
        r = bad[0].result
        users = (
            ec.site_engineers(db, pid, s.id) | ec.site_reps(db, pid, s.id) | ec.officers(db, pid)
        )
        n += ec.send(
            db, users, NK.emergency_coverage_short,
            f"Emergency team shortfall on {s.code} ({sh.value} shift): first aiders {r.fa}/{r.rfa},"
            f" wardens {r.wardens}/{r.rw}" + (f"; {', '.join(r.reasons)}" if r.reasons else ""),
            f"نقص في فريق الطوارئ في {s.code}: المسعفون {r.fa}/{r.rfa}، مسؤولو الإخلاء "
            f"{r.wardens}/{r.rw}",
            pid, EntityType.emergency_roster, None,
        )  # fmt: skip
    return n


def emergency_minute(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.emergency import common as ec  # noqa: PLC0415
    from app.services.emergency import muster as mu  # noqa: PLC0415

    at = at or now()
    out = {"exits": 0, "mu8": 0, "coverage": 0}
    for pid in _projects(db):
        if not ec.cfg(db, pid).active_on(ec.local_day(at)):
            continue
        for m in db.scalars(
            select(Muster).where(Muster.project_id == pid, Muster.status == MusterStatus.open)
        ):
            out["exits"] += mu.sync_exits(db, m, at)
            mu.reconcile(db, m)
            out["mu8"] += mu.headcount_timer(db, m, at)
        out["coverage"] += live_coverage(db, pid, at)
    db.flush()
    return out


# ---- P6c-4 retention -----------------------------------------------------------------------------


def purge_musters(db: Session, pid: uuid.UUID, at: datetime) -> int:
    """Named entries of Closed musters older than `muster_detail_retention_months` are reduced
    to counts by state, reason and engagement (`summary`, `purged_at`); timings stay."""
    from app.services.emergency import common as ec  # noqa: PLC0415
    from app.services.train.validity import add_months  # noqa: PLC0415

    months = int(ec.cfg(db, pid)["muster_detail_retention_months"])
    cutoff = ec.day_start(add_months(ec.local_day(at), -months))
    n = 0
    for m in db.scalars(
        select(Muster).where(
            Muster.project_id == pid,
            Muster.status.in_((MusterStatus.closed, MusterStatus.voided)),
            Muster.closed_at < cutoff,
        )
    ):
        if m.purged_at is not None:
            continue
        es = list(db.scalars(select(MusterEntry).where(MusterEntry.muster_id == m.id)))
        if not es:
            continue
        by_state: dict[str, int] = defaultdict(int)
        by_reason: dict[str, int] = defaultdict(int)
        by_eng: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for e in es:
            by_state[e.state.value] += 1
            by_eng[str(e.engagement_id)][e.state.value] += 1
            if e.resolution_reason is not None:
                by_reason[e.resolution_reason.value] += 1
        m.summary = {
            "by_state": dict(by_state),
            "by_reason": dict(by_reason),
            "by_engagement": {k: dict(v) for k, v in by_eng.items()},
        }
        m.purged_at = at
        db.execute(delete(MusterEntry).where(MusterEntry.muster_id == m.id))
        audit.record(
            db, AuditAction.retention_purge, audit.SYSTEM, entity_type=EntityType.emergency_muster,
            entity_id=m.id, project_id=pid, after={"entries_reduced": len(es)},
        )  # fmt: skip
        n += 1
    return n


def emergency_daily(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.emergency import common as ec  # noqa: PLC0415

    at = at or now()
    ec.clear_cache(db)
    out = {"purged": 0}
    for pid in _projects(db):
        out["purged"] += purge_musters(db, pid, at)
    db.flush()
    return out


# ---- §7 alerts (07:05) ---------------------------------------------------------------------------


def _overdue_two_step(
    db: Session, pid: uuid.UUID, key: str, deadline: date, d: date, en: str, ar: str,
    et: EntityType, eid: uuid.UUID,
) -> int:  # fmt: skip
    """At the deadline and daily: the HSE Officers; the HSE Manager after 2 more days."""
    from app.services.emergency import common as ec  # noqa: PLC0415

    if d < deadline:
        return 0
    users = set(ec.officers(db, pid))
    if d >= deadline + timedelta(days=2):
        users |= ec.managers(db)
    if not ec.once(db, f"{key}:{d}"):
        return 0
    return ec.send(db, users, NK.emergency_evaluation_overdue, en, ar, pid, et, eid, email=True)


def emergency_alerts(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.emergency import assets as em_assets  # noqa: PLC0415
    from app.services.emergency import common as ec  # noqa: PLC0415
    from app.services.emergency import drills as em_drills  # noqa: PLC0415
    from app.services.emergency import org, programme  # noqa: PLC0415

    at = at or now()
    d = ec.local_day(at)
    out = dict.fromkeys(("due", "evaluation", "review", "assets", "teams", "erp"), 0)
    for pid in _projects(db):
        c = ec.cfg(db, pid)
        if not c.active_on(d):
            continue
        out["due"] += programme.due_alerts(db, pid, d)
        for x in db.scalars(
            select(Drill).where(Drill.project_id == pid, Drill.status == DrillStatus.conducted)
        ):
            due = em_drills.evaluation_due(db, x)
            if due is not None:
                out["evaluation"] += _overdue_two_step(
                    db, pid, f"eval:{x.id}", due, d,
                    f"{x.drill_no}: evaluation overdue (due {due})",
                    f"{x.drill_no}: تأخر تقييم التمرين", EntityType.emergency_drill, x.id,
                )  # fmt: skip
        rdays = int(c["event_review_days"])
        for ev in db.scalars(
            select(EmergencyEvent).where(
                EmergencyEvent.project_id == pid, EmergencyEvent.status == EventStatus.all_clear
            )
        ):
            if ev.all_clear_at is None:
                continue
            due = ec.local_day(ev.all_clear_at) + timedelta(days=rdays)
            out["review"] += _overdue_two_step(
                db, pid, f"review:{ev.id}", due, d, f"{ev.event_no}: review overdue (due {due})",
                f"{ev.event_no}: تأخرت مراجعة الحدث", EntityType.emergency_event, ev.id,
            )  # fmt: skip
        assets = [
            a
            for a in db.scalars(select(EmergencyAsset).where(EmergencyAsset.project_id == pid))
            if a.status != AssetStatus.retired
        ]
        rm = em_assets.ready_map(db, pid, d, assets)
        for a in assets:
            r = rm.get(a.id)
            if r is None:
                continue
            owners = ec.reps(db, pid, a.owner_engagement_id)
            if (
                NotReadyReason.CHECK_OVERDUE in r.reasons
                and r.check_due is not None
                and d == r.check_due + timedelta(days=1)
                and ec.once(db, f"chk_over:{a.id}:{r.check_due}")
            ):
                out["assets"] += ec.send(
                    db, owners | ec.site_engineers(db, pid, a.site_id), NK.emergency_asset_due,
                    f"{a.asset_tag}: check overdue (due {r.check_due})",
                    f"{a.asset_tag}: فحص متأخر", pid, EntityType.emergency_asset, a.id,
                )  # fmt: skip
            dues = [("service", r.service_due), ("hydrotest", r.hydro_due)] + [
                (str(x["item"]), date.fromisoformat(str(x["expires_on"]))) for x in a.expiries or []
            ]
            for what, until in dues:
                step = long_step(db, f"em:asset:{a.id}:{what}", until, d, SHORT)
                if step is None:
                    continue
                out["assets"] += ec.send(
                    db, owners | ec.officers(db, pid), NK.emergency_asset_due,
                    f"{a.asset_tag}: {what} due {until} ({step} days)",
                    f"{a.asset_tag}: موعد {what} في {until}", pid, EntityType.emergency_asset,
                    a.id, email=True,
                )  # fmt: skip
        for t in db.scalars(
            select(RescueTeam).where(
                RescueTeam.project_id == pid, RescueTeam.status == ActiveStatus.active
            )
        ):
            rd = org.readiness(db, t, d)
            users = ec.reps(db, pid, _team_eng(db, t)) | ec.officers(db, pid)
            if not rd.current and ec.once(db, f"team_nc:{t.id}:{','.join(sorted(rd.reasons))}"):
                out["teams"] += ec.send(
                    db, users, NK.emergency_team_not_current,
                    f"{t.team_code} is not current: {', '.join(rd.reasons)}",
                    f"فريق الإنقاذ {t.team_code} غير جاهز", pid, EntityType.rescue_team, t.id,
                    email=True,
                )  # fmt: skip
            elif rd.current:
                step = long_step(db, f"em:team:{t.id}", rd.current_until, d, SHORT)
                if step is not None:
                    out["teams"] += ec.send(
                        db, users, NK.emergency_team_not_current,
                        f"{t.team_code}: rescue drill currency ends {rd.current_until} "
                        f"({step} days)",
                        f"فريق الإنقاذ {t.team_code}: تنتهي الجاهزية في {rd.current_until}",
                        pid, EntityType.rescue_team, t.id, email=True,
                    )  # fmt: skip
        e = ec.erp_in_force(db, pid)
        if e is not None and e.review_due_on is not None:
            users = ec.managers(db) | ec.officers(db, pid)
            step = long_step(db, f"em:erp:{e.id}", e.review_due_on, d, SHORT)
            if step is not None:
                out["erp"] += ec.send(
                    db, users, NK.emergency_erp_review,
                    f"{e.erp_no}: review due {e.review_due_on} ({step} days)",
                    f"{e.erp_no}: موعد مراجعة الخطة {e.review_due_on}", pid, EntityType.erp, e.id,
                    email=True,
                )  # fmt: skip
            elif ec.erp_overdue(e, d) and ec.once(db, f"erp_over:{e.id}:{e.review_due_on}"):
                out["erp"] += ec.send(
                    db, users, NK.emergency_erp_review,
                    f"{e.erp_no}: review overdue since {e.review_due_on}",
                    f"{e.erp_no}: مراجعة الخطة متأخرة", pid, EntityType.erp, e.id, email=True,
                )  # fmt: skip
    db.flush()
    return out


def _team_eng(db: Session, t: RescueTeam) -> uuid.UUID | None:
    from app.models import Deployment  # noqa: PLC0415

    dep = db.get(Deployment, t.lead_deployment_id)
    return dep.engagement_id if dep else None


PHASE6C_JOBS = {
    "emergency_minute": emergency_minute,
    "emergency_daily": emergency_daily,
    "emergency_alerts": emergency_alerts,
}
