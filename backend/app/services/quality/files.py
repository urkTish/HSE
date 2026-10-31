"""Attachment owners of the Quality module (spec 8-quality §A.8.7, list QAO): one dispatch
branch in `attachments._owner` calls `owner()`, which looks the owner type up in
`registry.ATTACHMENT_OWNERS` (each part registers its own). All files go through
`attachments.store` (virus scan D-302, photo shrinking D-282, storage cap D-293).

P8-3: the Viewer / Client never opens photos; P8-6: paper sign-off scans only for 238 holders of
the record's scope (never the Viewer / Client)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.errors import not_found
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import NCR_LIVE, QNcrStatus, QObservationStatus, QRecordType
from app.models.quality import QAlert, QComplaint, QMteItem, QObservation, QSignoff, QSupplier
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg

A = AttachmentOwner
C = Capability


def owner(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality import ensure_registered  # noqa: PLC0415

    ensure_registered()
    fn = reg.ATTACHMENT_OWNERS.get(owner_type)
    if fn is None:
        raise not_found("Attachment owner")
    return fn(db, p, owner_id, write)


def _viewer(p: Principal, project_id: uuid.UUID) -> bool:
    from app.services.quality.ncr.core import read_only_viewer  # noqa: PLC0415

    return read_only_viewer(p, project_id)


def ncr_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality.ncr import core  # noqa: PLC0415

    n = core.get_ncr(db, p, owner_id)
    if _viewer(p, n.project_id):
        raise forbidden_error("Photos and evidence are not shown to the Viewer / Client (P8-3).")
    editable = n.status in NCR_LIVE or n.status == QNcrStatus.draft
    if write:
        p.ensure_writer()
        mine = p.user.id in (n.raised_by_user_id, n.owner_id)
        g = p.grant(n.project_id, C.ncr_manage)
        if not mine and not qc.covers(g, n.site_id, n.responsible_engagement_id):
            raise forbidden_error()
    return n.project_id, editable


def observation_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality import observations  # noqa: PLC0415

    o = observations.get_obs(db, p, owner_id)
    if _viewer(p, o.project_id):
        raise forbidden_error("Photos are not shown to the Viewer / Client (P8-3).")
    if write and p.user.id != o.raised_by_user_id:
        qc.require_cover(p, o.project_id, C.ncr_manage, o.site_id, o.engagement_id)
    return o.project_id, o.status != QObservationStatus.closed


def alert_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality import alerts  # noqa: PLC0415

    a: QAlert = alerts.get_alert(db, p, owner_id)
    if write:
        p.require(a.project_id, C.ncr_manage)
    return a.project_id, a.status.value == "draft"


def complaint_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality import complaints  # noqa: PLC0415

    c: QComplaint = complaints.get_complaint(db, p, owner_id)
    if write:
        p.require(c.project_id, C.complaint_manage)
    return c.project_id, c.status.value not in ("closed", "withdrawn")


def signoff_scan_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    s = db.get(QSignoff, owner_id)
    if s is None:
        raise not_found("Attachment owner")
    if write:
        raise forbidden_error("Sign-off scans are attached with the paper sign-off.")
    if _viewer(p, s.project_id) or p.grant(s.project_id, C.quality_view) is None:
        raise forbidden_error("Paper sign-off scans need capability 238 (P8-6).")
    ad = reg.RECORD_TYPES.get(QRecordType(s.record_type))
    row = ad.get(db, s.record_id) if ad else None
    if ad is None or row is None or not ad.scope(db, p, row):
        raise forbidden_error()
    return s.project_id, False


def supplier_doc_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    s = db.get(QSupplier, owner_id)
    if s is None:
        raise not_found("Attachment owner")
    if write:
        p.require_any(C.supplier_manage)
    elif not (p.has_any(C.quality_view) or p.has_any(C.supplier_manage)):
        raise forbidden_error()
    # org-wide record: files are stored under the uploader's first visible project
    pid = next(iter(p.projects), None) if not p.is_manager else None
    if pid is None:
        from sqlalchemy import select  # noqa: PLC0415

        from app.models import Project  # noqa: PLC0415

        pid = db.scalar(select(Project.id).order_by(Project.created_at).limit(1))
    assert pid is not None  # noqa: S101
    return pid, True


def mte_doc_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    from app.services.quality import mte  # noqa: PLC0415

    m: QMteItem = mte.get_item(db, p, owner_id)
    if write:
        qc.require_cover(p, m.project_id, C.mte_manage, m.site_id, m.owner_engagement_id)
    return m.project_id, True


def register() -> None:
    reg.ATTACHMENT_OWNERS.update(
        {
            A.q_ncr: ncr_owner,
            A.q_ncr_evidence: ncr_owner,
            A.q_observation: observation_owner,
            A.q_alert: alert_owner,
            A.q_complaint: complaint_owner,
            A.q_signoff_scan: signoff_scan_owner,
            A.q_supplier_doc: supplier_doc_owner,
            A.q_mte_doc: mte_doc_owner,
        }
    )


_ = (QObservation,)
