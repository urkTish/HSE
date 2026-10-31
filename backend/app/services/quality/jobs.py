"""Quality job slots (spec 8-quality §4): `quality_daily` 00:21, `quality_alerts` 07:12,
`quality_weekly` Sunday 07:12 and `quality_monthly` day 2 07:24 (Asia/Riyadh), wired once into
`app/jobs.py` and `app/scheduler.py`. Each slot runs Q0's own work and then every job a part
registered in `registry.JOBS` for that slot. Every function is idempotent: each record, step and
recipient is alerted once per period (`common.send(key=…)`)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability, EntityType, ProjectStatus
from app.core.quality.common import NCR_LIVE, QNcrStatus
from app.models import Project
from app.models.quality import QNcr, QSettings
from app.services.quality import alerts, complaints, rpm
from app.services.quality import common as qc
from app.services.quality import registry as reg

C = Capability
ST = QNcrStatus


def _projects(db: Session) -> list[Project]:
    """Projects that use Quality (a profile is set)."""
    ids = [r.project_id for r in db.scalars(select(QSettings)) if r.sector_profile is not None]
    if not ids:
        return []
    return list(
        db.scalars(
            select(Project).where(Project.id.in_(ids), Project.status != ProjectStatus.closed)
        )
    )


# ---- Q0 daily ---------------------------------------------------------------------------------


def effectiveness_proposals(db: Session, at: datetime) -> int:
    """Q-NCR-17: on the due date propose effective / not effective and tell the owner."""
    from app.services.quality.ncr import core  # noqa: PLC0415

    n = 0
    for project in _projects(db):
        day = qc.project_day(project, at)
        for ncr in db.scalars(
            select(QNcr).where(QNcr.project_id == project.id, QNcr.status == ST.closed)
        ):
            eff = dict(ncr.effectiveness or {})
            due = eff.get("due_on")
            if not due or eff.get("proposed") or eff.get("result") or date.fromisoformat(due) > day:
                continue
            eff["proposed"] = core.propose_effectiveness(db, ncr)
            eff["proposed_at"] = at.isoformat()
            ncr.effectiveness = eff
            if ncr.owner_id:
                qc.send(
                    db,
                    [ncr.owner_id],
                    f"{ncr.ncr_no}: effectiveness check due",
                    f"{ncr.ncr_no}: موعد فحص الفعالية",
                    entity_type=EntityType.q_ncr,
                    entity_id=ncr.id,
                    project_id=ncr.project_id,
                    email=False,
                    key=f"ncr_eff:{ncr.id}",
                )
            n += 1
    db.flush()
    return n


def q0_daily(db: Session, at: datetime) -> dict[str, Any]:
    return {
        "effectiveness_proposed": effectiveness_proposals(db, at),
        "alerts_expired": alerts.expire(db, at),
    }


# ---- Q0 alerts (07:12) -----------------------------------------------------------------------


def ncr_alerts(db: Session, at: datetime) -> int:
    """Containment overdue (at containment_due_at, then daily; owner + 239 holders) and target
    close date passed (the day after, then weekly; owner, 239 holders, engagement quality
    contacts)."""
    from app.services.quality.ncr import core  # noqa: PLC0415

    sent = 0
    for project in _projects(db):
        day = qc.project_day(project, at)
        managers = set(qc.holders_of(db, project, C.quality_settings, include_manager=False))
        for n in db.scalars(
            select(QNcr).where(QNcr.project_id == project.id, QNcr.status.in_(list(NCR_LIVE)))
        ):
            owner = {n.owner_id} if n.owner_id else set()
            if (
                n.containment_due_at is not None
                and n.containment_done_at is None
                and not core.containment_ok(db, n)
                and at >= n.containment_due_at
            ):
                sent += qc.send(
                    db,
                    owner | managers,
                    f"{n.ncr_no}: containment overdue",
                    f"{n.ncr_no}: تأخر الاحتواء",
                    entity_type=EntityType.q_ncr,
                    entity_id=n.id,
                    project_id=n.project_id,
                    key=f"ncr_containment:{n.id}:{day}",
                    path=f"/quality/ncrs/{n.id}",
                )
            if n.target_close_date is not None and day > n.target_close_date:
                late = (day - n.target_close_date).days
                if late == 1 or late % 7 == 1:
                    who = (
                        owner
                        | managers
                        | core.engagement_contacts(db, project, n.responsible_engagement_id)
                    )
                    sent += qc.send(
                        db,
                        who,
                        f"{n.ncr_no}: target close date passed",
                        f"{n.ncr_no}: تجاوز تاريخ الإغلاق المستهدف",
                        entity_type=EntityType.q_ncr,
                        entity_id=n.id,
                        project_id=n.project_id,
                        key=f"ncr_target:{n.id}:{day}",
                        path=f"/quality/ncrs/{n.id}",
                    )
            sr = n.supplier_response or {}
            scar_late = (
                bool(sr.get("requested_at") and not sr.get("received_at") and sr.get("due_on"))
                and day > date.fromisoformat(str(sr["due_on"]))
                and n.owner_id is not None
            )
            if scar_late and n.owner_id is not None:
                sent += qc.send(
                    db,
                    [n.owner_id],
                    f"{n.ncr_no}: supplier response overdue",
                    f"{n.ncr_no}: تأخر رد المورد",
                    entity_type=EntityType.q_ncr,
                    entity_id=n.id,
                    project_id=n.project_id,
                    email=False,
                    key=f"ncr_scar:{n.id}",
                )
    return sent


def step_reminders(db: Session, at: datetime) -> int:
    """Step pending for me: reminder daily while pending > 24 h; and the daily digest of steps
    without a responsible person to 239 holders."""
    from app.services.permissions import build_principal  # noqa: PLC0415
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    sent = 0
    for project in _projects(db):
        day = qc.project_day(project, at)
        steps = [o for fn in reg.OPEN_STEPS.values() for o in fn(db, project)]
        by_user: dict[Any, list[reg.OpenStep]] = {}
        grants = rpm._Grants(db)
        for o in steps:
            if at - o.step.waiting_since < timedelta(hours=24):
                continue
            res = rpm.resolve(
                db,
                project,
                o.step.record_type,
                o.step.step,
                rpm.Ctx(o.site_id, o.engagement_id, o.requesters),
                qualifier=o.qualifier,
                record_id=o.step.record_id,
                grants=grants,
            )
            for uid in res.users:
                if uid not in o.requesters:
                    by_user.setdefault(uid, []).append(o)
        for uid, items in by_user.items():
            u = qc.active_user(db, uid)
            if u is None:
                continue
            p = build_principal(db, u, None)
            if not rpm.pending_from_open(db, p, project, items):
                continue
            refs = ", ".join(sorted({o.step.ref for o in items}))
            sent += qc.send(
                db,
                [uid],
                f"{project.code}: {len(items)} Quality sign-off(s) waiting",
                f"{project.code}: {len(items)} توقيعات جودة بانتظارك",
                body_en=refs,
                body_ar=refs,
                project_id=project.id,
                key=f"step_reminder:{project.id}:{day}",
                path="/quality/awaiting",
            )
        missing = rpm.without_rp(db, project)
        if missing:
            who = qc.holders_of(db, project, C.quality_settings, include_manager=False)
            refs = ", ".join(sorted({f"{o.step.ref} ({o.step.step})" for o in missing}))
            sent += qc.send(
                db,
                who,
                f"{project.code}: {len(missing)} step(s) without a responsible person",
                f"{project.code}: خطوات بلا شخص مسؤول",
                body_en=refs,
                body_ar=refs,
                project_id=project.id,
                email=False,
                key=f"no_rp_digest:{project.id}:{day}",
            )
    return sent


def q0_alerts(db: Session, at: datetime) -> dict[str, Any]:
    return {
        "ncr": ncr_alerts(db, at),
        "steps": step_reminders(db, at),
        "complaints": complaints.overdue_alerts(db, at),
        "alert_reminders": alerts.remind(db, at),
    }


Q0_SLOTS: dict[str, Callable[[Session, datetime], dict[str, Any]]] = {
    "quality_daily": q0_daily,
    "quality_alerts": q0_alerts,
}


def run_slot(db: Session, slot: str, at: datetime | None = None) -> dict[str, Any]:
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    t = at or now()
    out: dict[str, Any] = {}
    if slot in Q0_SLOTS:
        out["Q0"] = Q0_SLOTS[slot](db, t)
    for code, job in sorted(reg.JOBS.items()):
        if job.slot == slot:
            out[code] = job.run(db, t)
    return out


def _slot(name: str) -> Callable[[Session], dict[str, Any]]:
    def run(db: Session) -> dict[str, Any]:
        return run_slot(db, name)

    run.__name__ = name
    return run


QUALITY_JOBS: dict[str, Callable[[Session], dict[str, Any]]] = {
    name: _slot(name) for name in reg.JOB_SLOTS
}
