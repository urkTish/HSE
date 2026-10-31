"""Quality home and "Awaiting my sign-off" (spec 8-quality §A.12, Q-NAV, Q-RPM-10 / -11).

The home shows, profile-aware: the profile badge, NCR counts by class and status, overdue
containment, steps without a responsible person, the stop-use banner and the parts' extra counts
(`registry.HOME_TILES`; Q4 adds the §E.7 tiles). Before a profile is chosen it only says "Choose
the sector profile" to 239 holders (Q-PRF-01)."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability, CapabilityScope
from app.core.quality.common import NCR_LIVE, QNcrClass, QNcrStatus
from app.models.quality import QNcr
from app.services.permissions import Principal, forbidden_error
from app.services.quality import alerts, rpm
from app.services.quality import common as qc
from app.services.quality import registry as reg

C = Capability
S = CapabilityScope


def awaiting(db: Session, p: Principal, project_id: uuid.UUID) -> dict[str, Any]:
    """Q-RPM-11: every pending step where the user resolves, across all parts, oldest first."""
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    project = qc.get_project(db, p, project_id)
    items: list[reg.PendingStep] = []
    for fn in reg.PENDING_STEPS.values():
        items += fn(db, p, project.id)
    items.sort(key=lambda s: (s.waiting_since, s.ref))
    at = now()
    return {
        "count": len(items),
        "items": [
            {
                "record_type": s.record_type,
                "record_id": s.record_id,
                "project_id": s.project_id,
                "ref": s.ref,
                "title": s.title,
                "step": s.step,
                "waiting_since": s.waiting_since,
                "waiting_hours": int((at - s.waiting_since).total_seconds() // 3600),
                "link_path": s.link_path,
                "part": s.part,
            }
            for s in items
        ],
    }


def home(db: Session, p: Principal, project_id: uuid.UUID) -> dict[str, Any]:
    from app.services.quality import ensure_registered  # noqa: PLC0415
    from app.services.quality.ncr import core  # noqa: PLC0415

    ensure_registered()
    project = qc.get_project(db, p, project_id)
    g = p.grant(project.id, C.quality_view)
    if (
        g is None
        and p.grant(project.id, C.ncr_raise) is None
        and p.grant(project.id, C.quality_settings) is None
    ):
        raise forbidden_error()
    row = qc.settings_row(db, project.id)
    prof = row.sector_profile if row else None
    day = qc.project_day(project)
    base: dict[str, Any] = {
        "project_id": project.id,
        "sector_profile": prof,
        "needs_profile": prof is None,
        "can_configure": p.grant(project.id, C.quality_settings) is not None,
        "awaiting_count": 0,
        "ncr_by_class": {},
        "ncr_by_status": {},
        "ncr_open": 0,
        "ncr_overdue": 0,
        "containment_overdue": 0,
        "steps_without_rp": [],
        "stop_use_alerts": [],
        "my_open_ncrs": [],
        "tiles": [],
    }
    if prof is None:
        return base
    ncrs = list(db.scalars(core.scoped(db, p, project)))
    live = [n for n in ncrs if n.status in NCR_LIVE]
    at = now()
    base["awaiting_count"] = awaiting(db, p, project.id)["count"]
    base["ncr_by_class"] = dict(Counter(n.classification.value for n in live if n.classification))
    for c in QNcrClass:
        base["ncr_by_class"].setdefault(c.value, 0)
    base["ncr_by_status"] = dict(
        Counter(n.status.value for n in ncrs if n.status != QNcrStatus.draft)
    )
    base["ncr_open"] = len(live)
    base["ncr_overdue"] = sum(1 for n in live if n.target_close_date and n.target_close_date < day)
    base["containment_overdue"] = sum(
        1
        for n in live
        if n.containment_due_at and n.containment_due_at < at and not core.containment_ok(db, n)
    )
    if p.grant(project.id, C.quality_settings) is not None or p.is_manager:
        base["steps_without_rp"] = [
            {
                "record_type": o.step.record_type,
                "record_id": o.step.record_id,
                "ref": o.step.ref,
                "step": o.step.step,
                "link_path": o.step.link_path,
            }
            for o in rpm.without_rp(db, project)
        ]
    base["stop_use_alerts"] = alerts.banners(db, p, project, day)
    mine = [n for n in live if n.owner_id == p.user.id]
    base["my_open_ncrs"] = [
        {
            "id": n.id,
            "ncr_no": n.ncr_no,
            "title": n.title,
            "status": n.status,
            "classification": n.classification,
            "target_close_date": n.target_close_date,
        }
        for n in sorted(mine, key=lambda x: x.target_close_date or day)[:10]
    ]
    tiles = []
    for fn in reg.HOME_TILES.values():
        for t in fn(db, p, project):
            tiles.append(t.__dict__)
    base["tiles"] = tiles
    _ = select, QNcr, S
    return base
