"""Phase 6f scheduled jobs (6f-incident-followup §7, NR-5, P6f-4).

`followup_minute` (every 60 s): requirements derived for incidents under the profile (NR-1…NR-7),
pre-due and overdue alerts (§6.1), packs awaiting approval > 4 h.
`followup_daily` (00:13): lesson publication reminders (LL-1), acknowledgement reminders (DS-4),
effectiveness checks due (EF-1), identity pack purge after anonymisation (P6f-4), settings cache
reset.
`followup_alerts` (07:10): daily overdue repeats for requirements (§7).

Every step is de-duplicated per (subject, step) through JobMark."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import ProjectStatus
from app.models import Project


def _projects(db: Session) -> list[uuid.UUID]:
    return list(db.scalars(select(Project.id).where(Project.status != ProjectStatus.closed)))


def followup_minute(db: Session) -> dict[str, Any]:
    from app.services.followup import common as fc  # noqa: PLC0415
    from app.services.followup import packs, requirements  # noqa: PLC0415

    t = now()
    created = alerts = 0
    for pid in _projects(db):
        if fc.cfg(db, pid).rules_from is None:
            continue
        created += requirements.derive_project(db, pid, t)
        alerts += requirements.run_alerts(db, pid, t)
        alerts += packs.approval_alerts(db, pid, t)
    db.flush()
    return {"created": created, "alerts": alerts}


def followup_daily(db: Session) -> dict[str, Any]:
    from app.services.followup import common as fc  # noqa: PLC0415
    from app.services.followup import effectiveness, lessons, packs  # noqa: PLC0415

    fc.clear_cache(db)
    today = fc.local_day()
    lessons.daily(db, today)
    effectiveness.daily(db, today)
    purged = packs.purge_identity(db)
    db.flush()
    return {"purged": purged}


def followup_alerts(db: Session) -> dict[str, Any]:
    from app.services.followup import common as fc  # noqa: PLC0415
    from app.services.followup import requirements  # noqa: PLC0415

    t = now()
    n = 0
    for pid in _projects(db):
        if fc.cfg(db, pid).rules_from is not None:
            n += requirements.daily_overdue(db, pid, t)
    db.flush()
    return {"alerts": n}


PHASE6F_JOBS = {
    "followup_minute": followup_minute,
    "followup_daily": followup_daily,
    "followup_alerts": followup_alerts,
}
