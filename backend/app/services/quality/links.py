"""Links between Quality records (spec 8-quality §A.8.5, Q-SHR-05, §3.4). A link is created only
when both ends resolve through `registry.RECORD_TYPES` on the same project and the user can see
both; links have no foreign keys and are never cascaded; a voided end shows "voided"."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, EntityType
from app.core.errors import ErrorCode
from app.core.quality.common import QLinkKind, QRecordType
from app.models.quality import QLink
from app.services import audit
from app.services.permissions import Principal
from app.services.quality import common as qc
from app.services.quality import registry as reg


def not_allowed(
    en: str = "Both records must exist on the same project and be visible to you.",
) -> Any:
    return qc.err(
        422,
        ErrorCode.LINK_NOT_ALLOWED,
        en,
        "يجب أن يكون السجلان في المشروع نفسه وأن تتمكن من رؤيتهما.",
    )


def _end(db: Session, rt: QRecordType | str, rid: uuid.UUID) -> tuple[reg.RecordTypeAdapter, Any]:
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    try:
        ad = reg.RECORD_TYPES.get(QRecordType(rt))
    except ValueError:
        ad = None
    row = ad.get(db, rid) if ad else None
    if ad is None or row is None:
        raise not_allowed("The linked record does not exist.")
    return ad, row


def add(
    db: Session,
    project_id: uuid.UUID,
    from_type: QRecordType,
    from_id: uuid.UUID,
    to_type: QRecordType,
    to_id: uuid.UUID,
    kind: QLinkKind,
    user_id: uuid.UUID | None,
) -> QLink:
    """System link (no visibility check; callers made both records)."""
    existing = db.scalar(
        select(QLink).where(
            QLink.from_type == from_type.value,
            QLink.from_id == from_id,
            QLink.to_type == to_type.value,
            QLink.to_id == to_id,
            QLink.kind == kind,
        )
    )
    if existing is not None:
        return existing
    link = QLink(
        project_id=project_id,
        from_type=from_type.value,
        from_id=from_id,
        to_type=to_type.value,
        to_id=to_id,
        kind=kind,
        created_by_user_id=user_id,
        created_at=now(),
    )
    db.add(link)
    db.flush()
    return link


def create(
    db: Session,
    p: Principal,
    from_type: QRecordType,
    from_id: uuid.UUID,
    to_type: QRecordType,
    to_id: uuid.UUID,
    kind: QLinkKind,
) -> dict[str, Any]:
    fa, frow = _end(db, from_type, from_id)
    ta, trow = _end(db, to_type, to_id)
    pid = fa.project_id(frow)
    if pid != ta.project_id(trow):
        raise not_allowed()
    if not fa.scope(db, p, frow) or not ta.scope(db, p, trow):
        raise not_allowed()
    project = qc.get_project(db, p, pid)
    qc.writable(project, p)
    link = add(db, pid, from_type, from_id, to_type, to_id, kind, p.user.id)
    audit.record(
        db,
        AuditAction.create,
        p.actor(pid),
        entity_type=EntityType.q_link,
        entity_id=link.id,
        project_id=pid,
        after={
            "from": f"{from_type.value}:{from_id}",
            "to": f"{to_type.value}:{to_id}",
            "kind": kind.value,
        },
    )
    return read_many(db, p, [link], from_type, from_id)[0]


def read_many(
    db: Session, p: Principal | None, rows: list[QLink], rt: QRecordType, rid: uuid.UUID
) -> list[dict[str, Any]]:
    out = []
    for link in rows:
        outgoing = link.from_type == rt.value and link.from_id == rid
        other_t = link.to_type if outgoing else link.from_type
        other_id = link.to_id if outgoing else link.from_id
        try:
            ad = reg.RECORD_TYPES.get(QRecordType(other_t))
        except ValueError:
            ad = None
        row = ad.get(db, other_id) if ad else None
        visible = row is not None and ad is not None and (p is None or ad.scope(db, p, row))
        out.append(
            {
                "id": link.id,
                "kind": link.kind,
                "direction": "outgoing" if outgoing else "incoming",
                "record_type": other_t,
                "record_id": other_id,
                "ref": ad.ref(row) if visible and ad and row is not None else None,
                "title": ad.title(row) if visible and ad and row is not None else None,
                "link_path": ad.link_path(row) if visible and ad and row is not None else None,
                "voided": bool(ad.voided(row)) if ad and row is not None else False,
                "visible": visible,
                "created_at": link.created_at,
            }
        )
    return out


def links_for(
    db: Session, p: Principal | None, rt: QRecordType, rid: uuid.UUID
) -> list[dict[str, Any]]:
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    rows = list(
        db.scalars(
            select(QLink)
            .where(
                or_(
                    (QLink.from_type == rt.value) & (QLink.from_id == rid),
                    (QLink.to_type == rt.value) & (QLink.to_id == rid),
                )
            )
            .order_by(QLink.created_at)
        )
    )
    return read_many(db, p, rows, rt, rid)


def list_api(db: Session, p: Principal, rt: QRecordType, rid: uuid.UUID) -> list[dict[str, Any]]:
    ad, row = _end(db, rt, rid)
    if not ad.scope(db, p, row):
        from app.services.permissions import deny  # noqa: PLC0415

        raise deny(db, p, EntityType.q_link, rid, ad.project_id(row), "Record")
    return links_for(db, p, rt, rid)
