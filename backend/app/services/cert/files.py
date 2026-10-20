"""Attachment owners of Phase 4 (spec 4-third-party-cert P4-3): upload / read rights and the
project an attachment is stored under. Personnel card scans live in the personal bucket with
≤ 5-minute links; their read goes through the scan-url endpoint (capability 119, reason)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cert_enums import CertificateStatus, DefectStatus, ScaffoldStatus
from app.core.enums import Capability
from app.core.errors import not_found
from app.core.hse_enums import AttachmentOwner
from app.models import (
    EquipmentCertificate,
    EquipmentDefect,
    PersonnelCertificate,
    Project,
    Tpi,
    TpiAccreditation,
)
from app.services.permissions import Principal, forbidden_error

C = Capability
A = AttachmentOwner
CERT_OWNERS = frozenset(
    {
        A.tpi_accreditation_certificate,
        A.equipment_document,
        A.equipment_certificate_scan,
        A.personnel_cert_scan,
        A.verification_evidence,
        A.defect_photo,
        A.defect_evidence,
        A.scaffold_inspection_photo,
    }
)
EDITABLE = (CertificateStatus.draft, CertificateStatus.submitted)


def _any_project(db: Session, p: Principal, cap: Capability) -> uuid.UUID:
    grants = p.project_grants(cap)
    if grants:
        return sorted(grants, key=str)[0]
    if grants is None:
        pid = db.scalar(select(Project.id).order_by(Project.code).limit(1))
        if pid is not None:
            return pid
    raise forbidden_error()


def _need(p: Principal, project_id: uuid.UUID, cap: Capability, write: bool) -> None:
    if write:
        p.require(project_id, cap)
    elif p.grant(project_id, cap) is None:
        raise forbidden_error()


def owner(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    """→ (project_id, editable) or 403 / 404."""
    if owner_type == A.tpi_accreditation_certificate:
        # The certificate is uploaded before the accreditation exists, so the owner may be the
        # TPI organisation (the UI's choice) or an existing accreditation.
        if db.get(TpiAccreditation, owner_id) is None and db.get(Tpi, owner_id) is None:
            raise not_found("Accreditation")
        if write:
            p.require_any(C.tpi_edit)
            return _any_project(db, p, C.tpi_edit), True
        if not p.has_any(C.cert_register_view):
            raise forbidden_error()
        return _any_project(db, p, C.cert_register_view), True
    if owner_type == A.equipment_document:
        from app.services.cert import common as cc  # noqa: PLC0415
        from app.services.cert import equipment as esvc  # noqa: PLC0415

        item = esvc.get_row(db, owner_id)
        if write and not esvc.can_edit(db, p, item):
            raise forbidden_error()
        if not write and not esvc.can_see(db, p, item):
            raise not_found("Equipment")
        dep = cc.live_deployment(db, item.id)
        pid = (
            dep.project_id
            if dep
            else _any_project(db, p, C.equipment_edit if write else C.cert_register_view)
        )
        return pid, True
    if owner_type == A.equipment_certificate_scan:
        from app.services.cert import equipment_certs  # noqa: PLC0415

        if write:
            c = equipment_certs.get_row(db, owner_id)
            _need(p, c.project_id, C.equipment_edit, True)
        else:
            c = equipment_certs.get_visible(db, p, owner_id)  # grant scope: 404 outside it
        return c.project_id, c.status in EDITABLE
    if owner_type == A.personnel_cert_scan:
        from app.services.cert import personnel  # noqa: PLC0415

        if write:
            pc = personnel.get_row(db, owner_id)
            _need(p, pc.project_id, C.personnel_cert_submit, True)
        else:
            # PC-1 / P4-3: the reader's grant must cover the holder's deployment (a Contractor
            # HSE Rep sees only their tree); 119 is needed on top of the register view.
            pc = personnel.get_visible(db, p, owner_id)
            _need(p, pc.project_id, C.personnel_cert_scan_view, False)
        return pc.project_id, pc.status in EDITABLE
    if owner_type == A.verification_evidence:
        ec = db.get(EquipmentCertificate, owner_id)
        pcx = db.get(PersonnelCertificate, owner_id) if ec is None else None
        cert = ec or pcx
        if cert is None:
            raise not_found("Certificate")
        _need(p, cert.project_id, C.cert_verify, write)
        return cert.project_id, True
    if owner_type in (A.defect_photo, A.defect_evidence):
        from app.services.cert import defects  # noqa: PLC0415

        if write:
            d = db.get(EquipmentDefect, owner_id)
            if d is None:
                raise not_found("Defect")
            _need(p, d.project_id, C.defect_raise if owner_type == A.defect_photo
                  else C.defect_rectify, True)  # fmt: skip
        else:
            d = defects.get_visible(db, p, owner_id)
        return d.project_id, d.status in (DefectStatus.open, DefectStatus.rectified)
    if owner_type == A.scaffold_inspection_photo:
        from app.services.cert import scaffolds  # noqa: PLC0415

        if write:
            sc = scaffolds.get_row(db, owner_id)
            _need(p, sc.project_id, C.scaffold_inspect, True)
        else:
            sc = scaffolds.get_visible(db, p, owner_id)
        return sc.project_id, sc.status != ScaffoldStatus.dismantled
    raise not_found("Attachment owner")
