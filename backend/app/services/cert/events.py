"""Phase 4 events (spec 4-third-party-cert HK4-10): `cert.status_changed`,
`equipment.status_changed`, `scaffold.tag_changed`, `holder.ban_changed`,
`tpi.status_changed`, `hook_policy.changed`; Phase 5 (5-training HK5-8) adds
`training.record_changed`, `training.session_voided` and `training.provider_changed`.

Delivery is in the publishing transaction (at least once, before commit): the provider cache is
cleared, Phase 3 permits naming the subject are marked for re-evaluation (`ptw.hooks.process`
runs before the request commits; the PTW minute job is the ≤ 60 s backstop) and Phase 2 AVPs of
linked vehicles are re-evaluated (HK4-11)."""

import logging
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.ptw_enums import PERMIT_LIVE, PermitStatus
from app.models import EquipmentDeployment, EquipmentItem, Permit, PermitEquipment, Scaffold
from app.services.ptw import hooks as ptw_hooks

log = logging.getLogger(__name__)
EVENTS = frozenset(
    {
        "cert.status_changed",
        "equipment.status_changed",
        "scaffold.tag_changed",
        "holder.ban_changed",
        "tpi.status_changed",
        "hook_policy.changed",
        # Phase 5 (5-training HK5-8)
        "training.record_changed",
        "training.session_voided",
        "training.provider_changed",
        # Phase 6a (6a-occupational-health HK6-8)
        "medical.fitness_changed",
        "medical.hold_changed",
        "medical.provider_changed",
    }
)
LOG_KEY = "cert_events"
_STATUSES = [*PERMIT_LIVE, PermitStatus.approved]


def _ids(xs: Iterable[uuid.UUID | None]) -> set[uuid.UUID]:
    return {x for x in xs if x is not None}


def permits_for_items(db: Session, item_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """Approved / live permits naming the items (by item id or by deployment tag)."""
    if not item_ids:
        return set()
    out = set(
        db.scalars(
            select(PermitEquipment.permit_id)
            .join(Permit, Permit.id == PermitEquipment.permit_id)
            .where(PermitEquipment.equipment_item_id.in_(item_ids), Permit.status.in_(_STATUSES))
        )
    )
    deps = list(
        db.execute(
            select(EquipmentDeployment.project_id, EquipmentDeployment.tag).where(
                EquipmentDeployment.equipment_id.in_(item_ids)
            )
        )
    )
    vehicles = _ids(
        db.scalars(select(EquipmentItem.vehicle_id).where(EquipmentItem.id.in_(item_ids)))
    )
    conds: list[Any] = []
    for pid, tag in deps:
        conds.append((Permit.project_id == pid) & (PermitEquipment.tag.ilike(tag)))
    if vehicles:
        conds.append(PermitEquipment.vehicle_id.in_(vehicles))
    if conds:
        out |= set(
            db.scalars(
                select(PermitEquipment.permit_id)
                .join(Permit, Permit.id == PermitEquipment.permit_id)
                .where(or_(*conds), Permit.status.in_(_STATUSES))
            )
        )
    return out


def permits_for_scaffolds(db: Session, scaffold_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for sc in db.scalars(select(Scaffold).where(Scaffold.id.in_(scaffold_ids))):
        for pm in db.scalars(
            select(Permit).where(Permit.project_id == sc.project_id, Permit.status.in_(_STATUSES))
        ):
            for sec in (pm.sections or {}).values():
                if (
                    isinstance(sec, dict)
                    and str(sec.get("scaffold_tag_ref") or "").strip().upper() == sc.tag.upper()
                ):
                    out.add(pm.id)
    return out


def publish(
    db: Session,
    event: str,
    *,
    project_id: uuid.UUID | None = None,
    worker_ids: Iterable[uuid.UUID | None] = (),
    item_ids: Iterable[uuid.UUID | None] = (),
    scaffold_ids: Iterable[uuid.UUID | None] = (),
    project_wide: bool = False,
) -> None:
    assert event in EVENTS, event  # noqa: S101
    from app.services.cert import policy  # noqa: PLC0415

    policy.clear_cache(db)
    if event.startswith("training.") or event == "hook_policy.changed":
        from app.services.train import hook as thook  # noqa: PLC0415

        thook.clear_cache(db)
    if event.startswith("medical.") or event == "hook_policy.changed":
        from app.services.med import common as mcommon  # noqa: PLC0415

        mcommon.clear_cache(db)
    db.info.setdefault(LOG_KEY, []).append(event)
    workers = _ids(worker_ids)
    items = _ids(item_ids)
    scaffolds = _ids(scaffold_ids)
    db.flush()
    if event == "hook_policy.changed" or project_wide:  # noqa: SIM102
        if project_id is not None:
            ptw_hooks.mark_projects(db, [project_id])
    if workers:
        ptw_hooks.mark_workers(db, workers)
    if items:
        ptw_hooks.mark_permits(db, permits_for_items(db, items))
        _refresh_avps(db, items)
    if scaffolds:
        ptw_hooks.mark_permits(db, permits_for_scaffolds(db, scaffolds))
    if event == "hook_policy.changed" and project_id is not None:
        _refresh_project_avps(db, project_id)


def _refresh_avps(db: Session, item_ids: set[uuid.UUID]) -> None:
    from app.services.access import lifecycle  # noqa: PLC0415

    for vid in _ids(
        db.scalars(select(EquipmentItem.vehicle_id).where(EquipmentItem.id.in_(item_ids)))
    ):
        lifecycle.refresh_vehicle(db, vid)


def _refresh_project_avps(db: Session, project_id: uuid.UUID) -> None:
    from app.models import Avp  # noqa: PLC0415
    from app.services.access import lifecycle  # noqa: PLC0415

    vids = set(db.scalars(select(Avp.vehicle_id).where(Avp.project_id == project_id)))
    linked = _ids(
        db.scalars(select(EquipmentItem.vehicle_id).where(EquipmentItem.vehicle_id.in_(vids)))
    )
    for vid in linked:
        lifecycle.refresh_vehicle(db, vid)


def published(db: Session) -> list[str]:
    """Events published in this session (tests)."""
    return list(db.info.get(LOG_KEY, []))
