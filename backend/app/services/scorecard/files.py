"""Attachment owners of Phase 6g (spec 6g RP-5, EX-8, P6g-1): pack files (owner = pack), export
files (owner = export job; encrypted bucket; requester only) and dispute files (owner = remark).
All are written by the 6g services only."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.hse_enums import AttachmentOwner
from app.models import ScRemark, XpJob
from app.services.permissions import Principal, forbidden_error

A = AttachmentOwner
SC_OWNERS = frozenset({A.rp_pack_file, A.xp_export_file, A.sc_remark_file})


def owner(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    if write:
        raise forbidden_error("6g files are written through the scorecard and export endpoints.")
    if owner_type == A.rp_pack_file:
        from app.services.scorecard import packs  # noqa: PLC0415

        pk = packs.get_pack(db, p, owner_id)
        return packs._owner_project(db, pk), False
    if owner_type == A.sc_remark_file:
        from app.services.scorecard import remarks  # noqa: PLC0415

        r: ScRemark = remarks._get(db, p, owner_id)
        return r.project_id, False
    j = db.get(XpJob, owner_id)
    if j is None or j.requested_by_user_id != p.user.id:
        raise forbidden_error("Export files are for their requester only (EX-8).")
    return j.project_id or uuid.UUID(int=0), False
