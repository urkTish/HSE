"""Attachment owners of Phase 6e (spec 6e-environmental §3.3, CON-6, P6e-1, P6e-5): permit and
licence documents (owner = permit; upload 204), weighbridge tickets (owner = consignment; upload
206 / 207 in scope, before the receipt is recorded) and photos (owner = reading or spill; written
by the 6e services only). Viewer / Client never reads photos (P6e-3)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.env_enums import ConsignmentStatus
from app.core.errors import not_found
from app.core.hse_enums import AttachmentOwner
from app.models import EnvPermit, EnvReading, Spill, WasteConsignment
from app.services.env import common as ec
from app.services.permissions import Principal, forbidden_error

A = AttachmentOwner
C = Capability
ENV_OWNERS = frozenset({A.env_permit_document, A.consignment_ticket, A.env_photo})


def owner(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    if owner_type == A.env_permit_document:
        pm = db.get(EnvPermit, owner_id)
        if pm is None:
            raise not_found("Attachment owner")
        if pm.project_id is None:
            if write and not p.has_any(C.env_permit_manage):
                raise forbidden_error()
            if not p.has_any(C.env_view):
                raise forbidden_error()
            pid = next(iter(p.projects), None)
            if pid is None:
                raise forbidden_error()
            return pid, True
        if not p.can_see_project(pm.project_id) or p.grant(pm.project_id, C.env_view) is None:
            raise not_found("Attachment owner")
        if write:
            p.require(pm.project_id, C.env_permit_manage)
        return pm.project_id, True
    if owner_type == A.consignment_ticket:
        c = db.get(WasteConsignment, owner_id)
        if c is None or not p.can_see_project(c.project_id):
            raise not_found("Attachment owner")
        g = p.grant(c.project_id, C.env_view)
        if g is None or not ec.scope_ok(g, c.site_id, c.generator_engagement_id):
            raise not_found("Attachment owner")
        if write:
            w = p.grant(c.project_id, C.consignment_record) or p.grant(
                c.project_id, C.consignment_close
            )
            if w is None or not ec.scope_ok(w, c.site_id, c.generator_engagement_id):
                raise forbidden_error()
        return c.project_id, c.status == ConsignmentStatus.dispatched
    if write:
        raise forbidden_error("6e photos are attached through their own records.")
    r = db.get(EnvReading, owner_id)
    s = db.get(Spill, owner_id) if r is None else None
    if r is None and s is None:
        raise not_found("Attachment owner")
    pid = r.project_id if r is not None else s.project_id  # type: ignore[union-attr]
    if not p.can_see_project(pid) or ec.is_viewer(p, pid):
        raise forbidden_error("Photos are not shown to Viewer / Client (P6e-3).")
    if p.grant(pid, C.env_view) is None:
        raise forbidden_error()
    return pid, False
