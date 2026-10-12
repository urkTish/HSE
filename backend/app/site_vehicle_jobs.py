"""Option 7b scheduled job (spec 7b-fleet-driver §4, §7, DA-3): `site_vehicle_daily` at 00:30.

For every project with `site_vehicles_from` set: DA-3 hook re-evaluation of Active authorisations
(a hook not met under policy block → Expired with the reason), expiry of authorisations past
effective_valid_until, the stored readiness of every site vehicle, document expiry alerts
(30 / 14 / 7 / 0 days: engagement reps; HSE Officers at 7 / 0; in-app + email) and authorisation
expiry alerts (30 / 7 / 0 days: reps; in-app). Each alert threshold is sent once (JobMark); on a
first run only the tightest threshold reached is sent. No journey alerts (prototype)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import VehicleStatus
from app.core.clock import now
from app.core.enums import AuditAction, EntityType, NotificationKind
from app.core.site_vehicle_enums import SiteVehAuthStatus, SiteVehPolicy
from app.models import DriverAuthorisation, Worker

DOC_THRESHOLDS = (30, 14, 7, 0)
AUTH_THRESHOLDS = (30, 7, 0)
OFFICER_THRESHOLDS = frozenset({7, 0})


def _threshold(days_left: int, steps: tuple[int, ...]) -> int | None:
    """The tightest threshold reached (days_left ≤ t), None when none is reached; past expiry
    counts as 0."""
    hit = [t for t in steps if days_left <= t]
    return min(hit) if hit else None


def site_vehicle_daily(db: Session, day: date | None = None) -> dict[str, Any]:
    from app.services.site_vehicle import authorisations as auths  # noqa: PLC0415
    from app.services.site_vehicle import common as c  # noqa: PLC0415
    from app.services.site_vehicle.reference import DOC_LABEL  # noqa: PLC0415

    c.clear_cache(db)
    d = day or c.local_day()
    out = {"projects": 0, "vehicles": 0, "doc_alerts": 0, "auth_alerts": 0, "expired": 0}
    for pid in c.live_project_ids(db):
        cf = c.cfg(db, pid)
        if cf.live_from is None or cf.live_from > d:
            continue
        out["projects"] += 1
        # DA-3 and expiry
        for a in db.scalars(
            select(DriverAuthorisation).where(
                DriverAuthorisation.project_id == pid,
                DriverAuthorisation.status == SiteVehAuthStatus.active,
            )
        ):
            _, bad = auths.evaluate(db, a)
            reason = None
            if bad and cf.hook_policy == SiteVehPolicy.block:
                failed = [h["code"] for h in a.hook_results if h["result"] != "met"]
                reason = f"Requirement no longer met: {', '.join(failed)} (DA-3)."
            elif a.effective_valid_until is not None and a.effective_valid_until < d:
                reason = f"Effective validity ended ({a.limiting_factor})."
            if reason:
                before = {"status": a.status.value}
                a.status = SiteVehAuthStatus.expired
                a.status_reason = reason
                a.status_changed_at = now()
                c.record(
                    db, None, AuditAction.status_change, EntityType.driver_authorisation, a,
                    pid, before, {"reason": reason},
                )  # fmt: skip
                out["expired"] += 1
        db.flush()
        # readiness and document alerts
        officers = c.officer_users(db, pid)
        for v in db.scalars(c.site_vehicle_query(pid)):
            out["vehicles"] += 1
            c.refresh(db, v)
            if v.status == VehicleStatus.withdrawn:
                continue
            for kind, doc_exp in c.documents(v):
                exp = doc_exp
                t = _threshold((exp - d).days, DOC_THRESHOLDS)
                if t is None or not c.once(db, f"sv-doc:{v.id}:{kind}:{exp}:{t}"):
                    continue
                users = c.rep_users(db, pid, v.engagement_id)
                if t in OFFICER_THRESHOLDS:
                    users |= officers
                en, ar = DOC_LABEL[kind]
                left = (exp - d).days
                when = f"expires in {left} days ({exp})" if left > 0 else "expires today"
                if exp < d:
                    when = f"expired on {exp}"
                out["doc_alerts"] += (
                    c.send(
                        db,
                        users,
                        NotificationKind.site_vehicle_doc_expiry,
                        f"{v.vehicle_no} ({v.fleet_no}): {en} {when}.",
                        f"{v.vehicle_no}: تنتهي {ar} في {exp}"
                        + (f" (بعد {left} يوم)." if left > 0 else "."),
                        pid,
                        EntityType.vehicle,
                        v.id,
                        email=True,
                    )
                    and 1
                )
        # authorisation expiry alerts
        for a, wno in db.execute(
            select(DriverAuthorisation, Worker.worker_no)
            .join(Worker, Worker.id == DriverAuthorisation.worker_id)
            .where(
                DriverAuthorisation.project_id == pid,
                DriverAuthorisation.status == SiteVehAuthStatus.active,
                DriverAuthorisation.effective_valid_until.is_not(None),
            )
        ).all():
            until = a.effective_valid_until
            assert until is not None  # noqa: S101
            t = _threshold((until - d).days, AUTH_THRESHOLDS)
            if t is None or not c.once(db, f"sv-auth:{a.id}:{until}:{t}"):
                continue
            out["auth_alerts"] += (
                c.send(
                    db,
                    c.rep_users(db, pid, a.engagement_id),
                    NotificationKind.driver_auth_expiry,
                    f"{wno}: driver authorisation {a.auth_no} valid until {until}.",
                    f"{wno}: تفويض القيادة {a.auth_no} ساري حتى {until}.",
                    pid,
                    EntityType.driver_authorisation,
                    a.id,
                )
                and 1
            )
        db.flush()
    return out


PHASE7B_JOBS = {"site_vehicle_daily": site_vehicle_daily}
