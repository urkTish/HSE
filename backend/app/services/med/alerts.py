"""Phase 6a alerts (spec 6a-occupational-health §7). Texts follow P6-7: worker_no, code (only for
tier 2+ recipients), date and reference; never an outcome for tier-1 recipients, never a reason,
never a clinic. SMS has no channel in the platform yet (no provider), so "SMS" alerts go in-app and
by email (DECISIONS)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.core.enums import EntityType, NotificationKind
from app.models import Worker
from app.services.cert import alerts as calerts
from app.services.med import common
from app.services.med import reference as ref

K = NotificationKind


def oh(db: Session, project_id: uuid.UUID) -> set[uuid.UUID]:
    return set(common.oh_users(db, project_id))


def send(
    db: Session,
    users: Iterable[uuid.UUID],
    kind: NotificationKind,
    en: str,
    ar: str,
    project_id: uuid.UUID | None = None,
    entity_type: EntityType | None = None,
    entity_id: uuid.UUID | None = None,
    email: bool = True,
) -> int:
    return calerts.send(db, users, kind, en, ar, entity_type, entity_id, project_id, email=email)


def managers(db: Session) -> set[uuid.UUID]:
    return calerts.managers(db)


def officers(db: Session, project_id: uuid.UUID) -> set[uuid.UUID]:
    return calerts.officers(db, project_id)


def reps(db: Session, project_id: uuid.UUID, engagement_id: uuid.UUID | None) -> set[uuid.UUID]:
    return calerts.reps(db, project_id, engagement_id)


def wno(db: Session, worker_id: uuid.UUID) -> str:
    w = db.get(Worker, worker_id)
    return w.worker_no if w else "—"


def catalogue_shortened(
    db: Session, project_id: uuid.UUID, worker_id: uuid.UUID, code: str
) -> None:
    from app.services.cert.alerts import reps  # noqa: PLC0415

    dep = common.deployment(db, worker_id, project_id)
    users = oh(db, project_id) | reps(db, project_id, dep.engagement_id if dep else None)
    n = wno(db, worker_id)
    send(
        db, users, K.fitness_catalogue_shortened,
        f"{ref.CERT_DUE[0]}: {n} ({code})", f"{ref.CERT_DUE[1]}: {n} ({code})", project_id,
    )  # fmt: skip
