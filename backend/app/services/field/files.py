"""Attachment owners of Phase 6d (spec 6d-field-assurance P6d-3, P6d-4): answer photos (owner =
response), stop-work release photos (owner = order), talk signatures (personal bucket; capability
199) and attendance sheets (owner = talk), audit reports (owner = audit). Files are written only by
the 6d services (submissions, releases, talks, issue), never through the generic upload; Viewer /
Client never reads photos or signatures."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.errors import not_found
from app.core.hse_enums import AttachmentOwner
from app.models import ChecklistResponse, FieldAudit, StopWorkOrder, ToolboxTalk
from app.services.field import common as fc
from app.services.permissions import Principal, forbidden_error

A = AttachmentOwner
C = Capability
FIELD_OWNERS = frozenset(
    {A.field_photo, A.stop_work_photo, A.toolbox_signature, A.toolbox_sheet, A.field_audit_report}
)


def owner(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    if write:
        raise forbidden_error("6d files are attached through their own records.")
    site: uuid.UUID | None = None
    eng: uuid.UUID | None = None
    if owner_type == A.field_photo:
        r = db.get(ChecklistResponse, owner_id)
        if r is None:
            raise not_found("Attachment owner")
        pid, site, eng = r.project_id, r.site_id, r.engagement_id
        if r.inspector_id == p.user.id:
            return pid, False
    elif owner_type == A.stop_work_photo:
        o = db.get(StopWorkOrder, owner_id)
        if o is None:
            raise not_found("Attachment owner")
        pid, site, eng = o.project_id, o.site_id, o.engagement_id
    elif owner_type in (A.toolbox_signature, A.toolbox_sheet):
        t = db.get(ToolboxTalk, owner_id)
        if t is None:
            raise not_found("Attachment owner")
        pid, site, eng = t.project_id, t.site_id, t.host_engagement_id
        if owner_type == A.toolbox_signature:
            g = p.grant(pid, C.toolbox_names_view)
            if not fc.in_scope(g, site, None):
                raise forbidden_error("Signatures need capability 199.")
            return pid, False
    else:
        au = db.get(FieldAudit, owner_id)
        if au is None:
            raise not_found("Attachment owner")
        pid, eng = au.project_id, au.auditee_engagement_id
    if not p.can_see_project(pid) or fc.is_viewer(p, pid):
        raise forbidden_error("Photos and files are not shown to Viewer / Client (P6d-3).")
    g = p.grant(pid, C.field_view)
    if g is None or not (g.engagement_ids is None or g.covers_engagement(eng)):
        raise forbidden_error()
    if site is not None and not g.covers_site(site):
        raise forbidden_error()
    return pid, False
