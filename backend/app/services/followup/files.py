"""Attachment owners of Phase 6f (spec 6f §3.4, §3.5, P6f-1, P6f-4, P6f-5): pack files (owner =
pack; identity packs in the encrypted bucket with signed URLs ≤ 5 min), submission and waiver
evidence (owner = submission or requirement; personal) and lesson photos (owner = lesson). All are
written by the 6f services only; Viewer / Client never reads packs or evidence files."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.core.followup_enums import FuForm
from app.core.hse_enums import AttachmentOwner
from app.models import FuRequirement, FuSubmission
from app.services.followup import common as fc
from app.services.permissions import Principal, forbidden_error

A = AttachmentOwner
FU_OWNERS = frozenset({A.fu_pack_file, A.fu_pack_identity_file, A.fu_evidence, A.fu_lesson_photo})


def owner(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    if write:
        raise forbidden_error("6f files are written through the follow-up endpoints.")
    if owner_type in (A.fu_pack_file, A.fu_pack_identity_file):
        from app.services.followup import packs  # noqa: PLC0415

        pk, req, inc = packs._get(db, p, owner_id)
        if not packs._identity_ok(p, req, inc, pk.field_set, FuForm(pk.form_code)):
            raise forbidden_error("Identity packs need capability 29 (P6f-1).")
        return pk.project_id, False
    if owner_type == A.fu_evidence:
        from app.services.followup import requirements as rq  # noqa: PLC0415

        s = db.get(FuSubmission, owner_id)
        req_id = s.requirement_id if s is not None else owner_id
        r = db.get(FuRequirement, req_id)
        if r is None:
            raise not_found("Attachment owner")
        if fc.is_viewer(p, r.project_id):
            raise forbidden_error("Viewer / Client never sees evidence files (P6f-5).")
        rq.get_req(db, p, r.id)
        return r.project_id, False
    from app.services.followup import lessons  # noqa: PLC0415

    ls = lessons._get(db, p, owner_id)
    pid = ls.source_project_id or next(iter(ls.distribution_project_ids or []), None)
    if pid is None:
        raise not_found("Attachment owner")
    return pid, False
