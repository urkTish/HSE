"""Attachment owners of Phase 5 (spec 5-training P5-1, P5-3): upload / read rights and the
project an attachment is stored under. Certificate scans and attendance signatures live in the
personal bucket; a scan is read through the scan-url endpoint (capability 139, reason)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability
from app.core.errors import not_found
from app.core.hse_enums import AttachmentOwner
from app.core.train_enums import NominationStatus, SessionStatus, TrainingRecordStatus
from app.models import (
    Deployment,
    Project,
    TrainerAuthorisation,
    TrainingNomination,
    TrainingProvider,
    TrainingProviderAccreditation,
    TrainingRecord,
    TrainingSession,
)
from app.services.permissions import Principal, forbidden_error
from app.services.train import common

C = Capability
A = AttachmentOwner
TRAIN_OWNERS = frozenset(
    {
        A.training_record_scan,
        A.training_accreditation_certificate,
        A.trainer_authorisation_evidence,
        A.training_attendance_sheet,
        A.training_verification_evidence,
        A.training_attendance_signature,
    }
)
PERSONAL = frozenset({A.training_record_scan, A.training_attendance_signature})
OPEN_SESSION = (
    SessionStatus.draft,
    SessionStatus.scheduled,
    SessionStatus.in_progress,
    SessionStatus.delivered,
)


def _any_project(db: Session, p: Principal, cap: Capability) -> uuid.UUID:
    grants = p.project_grants(cap)
    if grants:
        return sorted(grants, key=str)[0]
    if grants is None:
        pid = db.scalar(select(Project.id).order_by(Project.code).limit(1))
        if pid is not None:
            return pid
    raise forbidden_error()


def _record_dep(db: Session, r: TrainingRecord) -> Deployment | None:
    return common.deployment(db, r.worker_id, r.project_id) if r.project_id else None


def _session_writer(db: Session, p: Principal, s: TrainingSession) -> None:
    from app.services.train import sessions  # noqa: PLC0415

    p.ensure_writer()
    if p.grant(s.project_id, C.training_attendance_record) is not None:
        return
    if p.user.id in sessions.trainer_user_ids(db, s):
        return
    raise forbidden_error()


def owner(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    """→ (project_id, editable) or 403 / 404."""
    if owner_type in (A.training_record_scan, A.training_verification_evidence):
        r = db.get(TrainingRecord, owner_id)
        if r is None or r.project_id is None:
            raise not_found("Training record")
        dep = _record_dep(db, r)
        if owner_type == A.training_record_scan:
            cap = C.training_record_submit if write else C.training_scan_view
            editable = r.status in (TrainingRecordStatus.draft, TrainingRecordStatus.submitted)
        else:
            cap = C.training_record_review
            editable = True
        if write:
            p.ensure_writer()
        if not common.covers_dep(p.grant(r.project_id, cap), dep):
            raise forbidden_error()
        return r.project_id, editable
    if owner_type == A.training_accreditation_certificate:
        if (
            db.get(TrainingProviderAccreditation, owner_id) is None
            and db.get(TrainingProvider, owner_id) is None
        ):
            raise not_found("Accreditation")
        if write:
            p.require_any(C.training_provider_edit)
            return _any_project(db, p, C.training_provider_edit), True
        if not p.has_any(C.training_catalogue_view):
            raise forbidden_error()
        return _any_project(db, p, C.training_catalogue_view), True
    if owner_type == A.trainer_authorisation_evidence:
        # uploaded before the authorisation exists: the owner is the project or an authorisation
        ta = db.get(TrainerAuthorisation, owner_id)
        pid = ta.project_id if ta is not None else owner_id
        if ta is None and db.get(Project, owner_id) is None:
            raise not_found("Trainer authorisation")
        if write:
            p.require(pid, C.trainer_authorise)
        elif p.grant(pid, C.training_catalogue_view) is None:
            raise forbidden_error()
        return pid, True
    if owner_type == A.training_attendance_sheet:
        s = db.get(TrainingSession, owner_id)
        if s is None:
            raise not_found("Training session")
        if write:
            _session_writer(db, p, s)
        elif p.grant(s.project_id, C.training_record_view) is None:
            raise forbidden_error()
        return s.project_id, s.status in OPEN_SESSION
    if owner_type == A.training_attendance_signature:
        n = db.get(TrainingNomination, owner_id)
        s = db.get(TrainingSession, n.session_id) if n is not None else None
        if n is None or s is None:
            raise not_found("Nomination")
        if write:
            _session_writer(db, p, s)
        elif (
            p.grant(s.project_id, C.training_record_view) is None
            or p.grant(s.project_id, C.worker_view) is None
        ):
            raise forbidden_error("Worker signatures need capability 46.")
        return s.project_id, s.status in OPEN_SESSION and n.status != NominationStatus.withdrawn
    raise not_found("Attachment owner")
