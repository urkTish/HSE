"""Helpers shared by the Q1 services (spec 8-quality Part B): loading with scope (Q-ROL-02, -04,
rule 12), the construction-profile guard (Part B header, Q-PRF-04), photos, location keys
(§B.4.1) and the read-only Viewer / Client (P8-3, P8-4)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability, CapabilityScope, EntityType
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QRecordType
from app.models import Attachment, Project, User
from app.models.quality import QSignoff
from app.services.permissions import Principal, deny
from app.services.quality import common as qc

C = Capability
S = CapabilityScope


def location_key(zone_code: str | None, system_code: str | None, location_ref: str) -> str:
    """§B.4.1: zone code (or system code) + "|" + lower-cased, trimmed, single-spaced ref."""
    ref = re.sub(r"\s+", " ", (location_ref or "").strip()).lower()
    return f"{zone_code or system_code or '-'}|{ref}"[:160]


def project(db: Session, project_id: uuid.UUID) -> Project:
    pr = db.get(Project, project_id)
    assert pr is not None  # noqa: S101
    return pr


def writable_construction(db: Session, p: Principal, pr: Project, rt: QRecordType) -> None:
    """Creating a Part B record needs the construction profile (Q-PRF-04 → 409 PROFILE_INACTIVE)."""
    qc.writable(pr, p)
    qc.ensure_profile_for(db, pr, rt)


def progress_writable(pr: Project, p: Principal) -> None:
    """Progressing an open record works under either profile (Q-PRF-04 "finish only")."""
    qc.writable(pr, p)


def viewer(p: Principal, project_id: uuid.UUID) -> bool:
    """P8: the Viewer / Client sees aggregates — no names, no photos."""
    if p.is_manager:
        return False
    sc = p.projects.get(project_id)
    return bool(sc and sc.read_only)


def signed_by(db: Session, rt: QRecordType, rid: uuid.UUID, uid: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(QSignoff.id).where(
                QSignoff.record_type == rt.value,
                QSignoff.record_id == rid,
                QSignoff.signed_by_user_id == uid,
            )
        )
        is not None
    )


def denied(
    db: Session, p: Principal, et: EntityType, rid: uuid.UUID, pid: uuid.UUID | None, what: str
) -> Any:
    return deny(db, p, et, rid, pid, what)


def store_photos(
    db: Session,
    owner: AttachmentOwner,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    photos: Iterable[Any],
    user_id: uuid.UUID,
    fld: str,
) -> list[uuid.UUID]:
    """Inline base64 photos (6d `PhotoInput`): EXIF stripped, virus-scanned and shrunk by
    `attachments.store` (D-282, D-302)."""
    from types import SimpleNamespace  # noqa: PLC0415

    from app.services.field import common as fc  # noqa: PLC0415

    items = [SimpleNamespace(**x) if isinstance(x, dict) else x for x in photos]
    return fc.store_photos(db, owner, owner_id, project_id, items, user_id, fld)


def attachment_ids(db: Session, owner: AttachmentOwner, owner_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(Attachment.id)
            .where(Attachment.owner_type == owner, Attachment.owner_id == owner_id)
            .order_by(Attachment.created_at)
        )
    )


def user_ref(db: Session, uid: uuid.UUID | None, hide: bool = False) -> dict[str, Any] | None:
    if uid is None or hide:
        return None
    u = db.get(User, uid)
    if u is None:
        return None
    return {"id": u.id, "full_name_en": u.full_name_en, "full_name_ar": u.full_name_ar}


def day(pr: Project) -> date:
    return qc.project_day(pr)


def scope_grant(p: Principal, project_id: uuid.UUID) -> Any:
    return p.grant(project_id, C.quality_view)
