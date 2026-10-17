"""Automatic daily returns (D-268).

Headcount per engagement × site × day comes from the platform itself:

* gate entries when the project logs them that day (workers who checked in), else
* the deployment roster (mobilised workers whose deployment covers the day).

A worker counts once per day, at the gate's site or at the first of their deployment sites that
the engagement works on (the engagement's first site when the deployment names none).
``man_hours = (headcount − absent_count) × standard_hours_per_person_day + overtime_hours``;
absence and overtime are the only figures typed by hand. Rest days get no automatic row unless
someone came through a gate. Manual and imported rows always win: a key that already has one
is skipped, as are verified / locked rows and locked months.
"""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, GateDirection, GateResult, GateSubjectKind
from app.core.enums import AuditAction, EntityType
from app.core.hse_enums import Shift, WorkforceSource, WorkforceStatus
from app.models import Deployment, GateCheck, HseSettings, Project, ProjectEngagement
from app.models import WorkforceReturn as W
from app.services import audit, hse_settings
from app.services.hse_common import is_locked, mark_restated, project_today
from app.services.permissions import Principal

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
GRANTED = (GateResult.GRANTED, GateResult.GRANTED_WITH_WARNING)
EDITABLE = (WorkforceStatus.draft, WorkforceStatus.submitted)


def man_hours(headcount: int, absent: int, overtime: Decimal, s: HseSettings) -> Decimal:
    present = max(headcount - absent, 0)
    return (Decimal(present * s.standard_hours_per_person_day) + overtime).quantize(Decimal("0.01"))


def _engagements(db: Session, project: Project, day: date) -> dict[uuid.UUID, ProjectEngagement]:
    rows = db.scalars(
        select(ProjectEngagement).where(
            ProjectEngagement.project_id == project.id,
            ProjectEngagement.mobilisation_date <= day,
            or_(
                ProjectEngagement.demobilisation_date.is_(None),
                ProjectEngagement.demobilisation_date >= day,
            ),
        )
    )
    return {e.id: e for e in rows if e.site_ids}


def _home_site(dep: Deployment, eng: ProjectEngagement) -> uuid.UUID:
    for s in dep.site_ids or []:
        if s in eng.site_ids:
            return s
    return eng.site_ids[0]


def headcounts(db: Session, project: Project, day: date) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    """(engagement_id, site_id) → people at work on ``day``; empty on a rest day without entries."""
    engs = _engagements(db, project, day)
    if not engs:
        return {}
    gate = db.execute(
        select(GateCheck.deployment_id, GateCheck.site_id).where(
            GateCheck.project_id == project.id,
            GateCheck.local_date == day,
            GateCheck.subject_kind == GateSubjectKind.person,
            GateCheck.direction == GateDirection.in_,
            GateCheck.result.in_(GRANTED),
            GateCheck.final.is_(True),
            GateCheck.deployment_id.is_not(None),
        )
    ).all()
    s = hse_settings.get(db, project.id)
    if not gate and WEEKDAYS[day.weekday()] in (s.rest_days or []):
        return {}
    deps = db.scalars(
        select(Deployment).where(
            Deployment.project_id == project.id,
            Deployment.engagement_id.in_(list(engs)),
            Deployment.status != DeploymentStatus.pending_induction,
            Deployment.mobilised_on <= day,
            or_(Deployment.demobilised_on.is_(None), Deployment.demobilised_on >= day),
        )
    ).all()
    by_id = {d.id: d for d in deps}
    people: dict[uuid.UUID, uuid.UUID] = {}  # deployment → site
    if gate:
        for dep_id, site_id in gate:
            dep = by_id.get(dep_id) if dep_id else None
            if dep is None or dep.id in people or dep.engagement_id is None:
                continue
            eng = engs[dep.engagement_id]
            people[dep.id] = site_id if site_id in eng.site_ids else _home_site(dep, eng)
    else:
        for dep in deps:
            if dep.engagement_id is None or (dep.inducted_on and dep.inducted_on > day):
                continue
            people[dep.id] = _home_site(dep, engs[dep.engagement_id])
    counts: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for dep_id, site_id in people.items():
        eng_id = by_id[dep_id].engagement_id
        assert eng_id is not None  # noqa: S101
        counts[(eng_id, site_id)] += 1
    return dict(counts)


def fill_day(db: Session, p: Principal | None, project: Project, day: date) -> dict[str, int]:
    """Create or refresh the automatic rows of one day. Returns counts by outcome."""
    out = {"created": 0, "updated": 0, "skipped": 0}
    s = hse_settings.get(db, project.id)
    if not s.auto_man_hours or day > project_today(project) or day < project.start_date:
        return out
    if is_locked(db, project.id, day):
        return out
    counts = headcounts(db, project, day)
    existing = {
        (r.engagement_id, r.site_id): r
        for r in db.scalars(
            select(W).where(
                W.project_id == project.id,
                W.work_date == day,
                W.zone_id.is_(None),
                W.shift == Shift.day,
            )
        )
    }
    actor = p.actor(project.id) if p else audit.SYSTEM
    for (eng_id, site_id), n in sorted(counts.items(), key=lambda kv: str(kv[0])):
        r = existing.get((eng_id, site_id))
        if r is not None and (r.source != WorkforceSource.auto or r.status not in EDITABLE):
            out["skipped"] += 1
            continue
        if r is None:
            r = W(
                project_id=project.id,
                site_id=site_id,
                zone_id=None,
                engagement_id=eng_id,
                work_date=day,
                shift=Shift.day,
                no_work=False,
                headcount=n,
                absent_count=0,
                overtime_hours=Decimal(0),
                man_hours=man_hours(n, 0, Decimal(0), s),
                source=WorkforceSource.auto,
                status=WorkforceStatus.submitted,
                warnings=[],
                created_by_user_id=p.user.id if p else None,
            )
            db.add(r)
            db.flush()
            audit.record(
                db,
                AuditAction.create,
                actor,
                entity_type=EntityType.workforce_return,
                entity_id=r.id,
                project_id=project.id,
                after={"headcount": n, "man_hours": r.man_hours, "source": "auto"},
            )
            out["created"] += 1
            continue
        new_hours = man_hours(n, r.absent_count, r.overtime_hours, s)
        if r.headcount == n and r.man_hours == new_hours:
            continue
        before = {"headcount": r.headcount, "man_hours": r.man_hours}
        r.headcount, r.man_hours = n, new_hours
        audit.record(
            db,
            AuditAction.update,
            actor,
            entity_type=EntityType.workforce_return,
            entity_id=r.id,
            project_id=project.id,
            before=before,
            after={"headcount": n, "man_hours": new_hours},
        )
        out["updated"] += 1
    if out["created"] or out["updated"]:
        mark_restated(db, p, project.id, day, "automatic workforce returns refreshed")
    return out


def fill_range(
    db: Session, p: Principal | None, project: Project, start: date, end: date
) -> dict[str, int]:
    total = {"created": 0, "updated": 0, "skipped": 0, "days": 0}
    d = start
    while d <= end:
        for k, v in fill_day(db, p, project, d).items():
            total[k] += v
        total["days"] += 1
        d += timedelta(days=1)
    return total
