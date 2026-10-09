"""Heat alerts (spec 6b-heat-stress §5.4, §7): regime raised / stop / may resume (HA-1…HA-3),
reading overdue (HA-4) and the non-permit midday-ban pre-warning (HA-6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import EntityType, NotificationKind
from app.core.heat_enums import AcclimatisationBasis, Regime
from app.core.ptw_enums import Exposure, PermitStatus
from app.models import JobMark, MonitoringPoint, Permit, Zone
from app.services.heat import common as hc
from app.services.heat import state

K = NotificationKind
AB = AcclimatisationBasis
WL_EN = {"light": "light", "moderate": "moderate", "heavy": "heavy", "very_heavy": "very heavy"}
WL_AR = {"light": "الخفيف", "moderate": "المتوسط", "heavy": "الشاق", "very_heavy": "الشاق جداً"}


def window_once(db: Session, key: str, minutes: int = 60, at: datetime | None = None) -> bool:
    """HA-3: True when `key` was not alerted in the last `minutes`."""
    at = at or now()
    key = key[:200]
    m = db.get(JobMark, key)
    if m is not None and m.created_at > at - timedelta(minutes=minutes):
        return False
    if m is None:
        db.add(JobMark(key=key, created_at=at))
    else:
        m.created_at = at
    db.flush()
    return True


def zone_people(db: Session, project_id: uuid.UUID, zone: Zone) -> set[uuid.UUID]:
    """HA-1 recipients: site engineers, receivers / issuers of Issued/Active outdoor permits in
    the zone, Contractor HSE Reps of engagements Mobilised on the site, HSE Officers."""
    out = hc.site_engineers(db, project_id, zone.site_id) | hc.officers(db, project_id)
    out |= hc.site_reps(db, project_id, zone.site_id)
    for pm in db.scalars(
        select(Permit).where(
            Permit.project_id == project_id,
            Permit.status.in_([PermitStatus.issued, PermitStatus.active]),
            Permit.exposure.in_([Exposure.outdoor_direct_sun, Exposure.outdoor_shaded]),
            Permit.zone_ids.any(zone.id),  # type: ignore[arg-type]
        )
    ):
        out.add(pm.receiver_user_id)
        if pm.issuer_user_id:
            out.add(pm.issuer_user_id)
    return out


def _cells_text(z: state.ZState, t: hc.Table, cfg: hc.Cfg) -> str:
    parts = []
    for b in AB:
        row = "/".join(z.regime(t, cfg.offset, b, w).value for w in hc.WORKLOADS)
        parts.append(f"{'acc' if b == AB.acclimatised else 'unacc'} {row}")
    return "; ".join(parts)


def _hhmm(at: datetime) -> str:
    from app.services.access import common as acommon  # noqa: PLC0415

    return at.astimezone(acommon.RIYADH).strftime("%H:%M")


def on_reading(db: Session, pt: MonitoringPoint, before: state.ZState, at: datetime) -> None:
    """HA-1 / HA-2 after a live (not late) reading."""
    cfg = hc.cfg(db, pt.project_id)
    if not cfg.active_on(hc.local_day(at)):
        return
    after = state.point_state(db, pt, at, cfg)
    t = hc.table(db)
    h0, h1 = state.headline(before, cfg), state.headline(after, cfg)
    new_r4 = [w for w in after.acc_r4() if w not in before.acc_r4()]
    if not new_r4 and hc.ORDER[h1] <= hc.ORDER[h0]:
        return
    zones = hc.zone_map(db, pt.project_id)
    w = after.latest.wbgt if after.latest else None
    rest = hc.REST_MIN.get(h1)
    for zid in pt.zone_ids or []:
        z = zones.get(zid)
        if z is None:
            continue
        regime = Regime.R4 if new_r4 else h1
        if not window_once(db, f"heat:ha1:{zid}:{regime.value}:up", at=now()):
            continue
        cells = _cells_text(after, t, cfg)
        if new_r4:
            wl = new_r4[0]
            en = f"Stop outdoor {WL_EN[wl.value]} work in {z.code} — WBGT {w} at {_hhmm(at)}"
            ar = f"أوقف العمل الخارجي {WL_AR[wl.value]} في {z.code} — المؤشر {w}"
        else:
            en = (
                f"Heat regime raised to {h1.value} in {z.code}: WBGT {w} at {_hhmm(at)}, "
                f"rest {rest} min per hour"
            )
            ar = f"ارتفع نظام العمل إلى {h1.value} في {z.code}: المؤشر {w}، راحة {rest} دقيقة"
        hc.send(
            db,
            zone_people(db, pt.project_id, z),
            K.heat_regime_raised,
            f"{en} ({cells}). {hc.WATER[0]}",
            f"{ar}. {hc.WATER[1]}",
            pt.project_id,
            EntityType.monitoring_point,
            pt.id,
            email=bool(new_r4),
        )


def resume_check(db: Session, project_id: uuid.UUID, at: datetime, step: timedelta) -> int:
    """HA-2: a zone whose acclimatised R4 ended (after WR-8) gets "Work may resume"."""
    cfg = hc.cfg(db, project_id)
    zones = hc.zone_map(db, project_id)
    n = 0
    for pt in hc.points(db, project_id):
        if not pt.active:
            continue
        prev = state.point_state(db, pt, at - step, cfg)
        cur = state.point_state(db, pt, at, cfg)
        if not prev.acc_r4() or cur.acc_r4() or cur.latest is None:
            continue
        h = state.headline(cur, cfg)
        for zid in pt.zone_ids or []:
            z = zones.get(zid)
            if z is None or not window_once(db, f"heat:ha2:{zid}:{h.value}:down", at=at):
                continue
            n += hc.send(
                db,
                zone_people(db, project_id, z),
                K.heat_regime_raised,
                f"Work may resume in {z.code} under regime {h.value}",
                f"يمكن استئناف العمل في {z.code} وفق النظام {h.value}",
                project_id,
                EntityType.monitoring_point,
                pt.id,
            )
    return n


def overdue(db: Session, project_id: uuid.UUID, at: datetime) -> int:
    """HA-4: in the controls period, monitoring hours and a day with work, a required zone that
    is stale or unknown 15 min into an hour slot alerts the HSE Officers and site engineers."""
    cfg = hc.cfg(db, project_id)
    d = hc.local_day(at)
    if not (cfg.active_on(d) and cfg.in_controls(d) and cfg.in_monitoring(at)):
        return 0
    ws, _we = cfg.monitoring(d)
    slot = ws + timedelta(hours=int((at - ws).total_seconds() // 3600))
    if at < slot + timedelta(minutes=15):
        return 0
    work = hc.days_with_work(db, project_id, d, d)
    zones = hc.zone_map(db, project_id)
    n = 0
    for zid in hc.required_zone_ids(db, project_id):
        z = zones.get(zid)
        if z is None or d not in work.get(z.site_id, set()):
            continue
        zs = state.zone_state(db, project_id, zid, at)
        if zs.state == state.S.current:
            continue
        if not hc.once(db, f"heat:ha4:{zid}:{slot.isoformat()}"):
            continue
        n += hc.send(
            db,
            hc.officers(db, project_id) | hc.site_engineers(db, project_id, z.site_id),
            K.heat_reading_overdue,
            f"WBGT reading overdue in {z.code} ({zs.state.value}) for the {_hhmm(slot)} slot",
            f"قراءة المؤشر الحراري متأخرة في {z.code} لفترة {_hhmm(slot)}",
            project_id,
            EntityType.monitoring_point,
            None,
        )
    return n


def prewarn(db: Session, project_id: uuid.UUID, at: datetime) -> int:
    """HA-6: on ban dates at ban start − prewarn, the site engineers and Contractor HSE Reps of
    engagements Mobilised on sites with required zones."""
    cfg = hc.cfg(db, project_id)
    d = hc.local_day(at)
    w = cfg.ban_window(d)
    if w is None or not cfg.active_on(d):
        return 0
    start = w[0] - timedelta(minutes=cfg.ban_prewarn)
    if not start <= at < w[0]:
        return 0
    if not hc.once(db, f"heat:ha6:{project_id}:{d.isoformat()}"):
        return 0
    zones = hc.zone_map(db, project_id)
    sites = {zones[z].site_id for z in hc.required_zone_ids(db, project_id) if z in zones}
    users: set[uuid.UUID] = set()
    for s in sites:
        users |= hc.site_engineers(db, project_id, s) | hc.site_reps(db, project_id, s)
    hh = _hhmm(w[0])
    return hc.send(
        db,
        users,
        K.heat_ban_prewarn,
        f"Midday ban from {hh} — stop work in direct sun",
        f"حظر العمل وقت الظهيرة يبدأ {hh}",
        project_id,
    )
