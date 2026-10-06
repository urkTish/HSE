"""Attachments with local storage and HMAC-signed download links (spec 1-dashboard P1-3).
Medical files go to a separate bucket, links live ≤ 5 min and every link is audited."""

import hashlib
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import API_PREFIX, get_settings
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ApiError, ErrorCode, not_found
from app.core.hse_enums import (
    AttachmentOwner,
    CaStatus,
    IncidentStatus,
    ObservationStatus,
    ScanStatus,
)
from app.models import Attachment, HseMeeting, InjuryCase
from app.schemas.attachments import AttachmentList, AttachmentRead, SignedUrlRead
from app.schemas.hse_common import UserRef
from app.services import audit
from app.services import corrective_actions as ca_svc
from app.services import incidents as inc_svc
from app.services import observations as obs_svc
from app.services.hse_common import Refs, covers
from app.services.permissions import Principal, deny, forbidden_error

TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
    ".pdf": "application/pdf",
}
MAGIC = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG",),
    "application/pdf": (b"%PDF",),
    "image/heic": (b"",),  # ftyp box at offset 4, checked below
}
MEDICAL_TTL = 300
DEFAULT_TTL = 900
MAX_OBS_PHOTOS = 3
UNKNOWN = UserRef(id=uuid.UUID(int=0), full_name_en="—")


def _bucket(owner: AttachmentOwner) -> str:
    return "medical" if owner == AttachmentOwner.injury_case_medical else "general"


# ---- owner resolution and permissions ------------------------------------------------------------


def _owner(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    """Returns (project_id, editable) or raises 404/403. `write` checks upload rights."""
    if owner_type == AttachmentOwner.incident:
        inc = inc_svc.get_incident(db, p, owner_id)
        b = inc_svc.bundle(db, inc)
        editable = inc.status not in (IncidentStatus.voided, IncidentStatus.closed)
        if write and not (inc_svc.can_edit(p, b) or inc.reported_by_user_id == p.user.id):
            raise forbidden_error()
        return inc.project_id, editable
    if owner_type == AttachmentOwner.injury_case_medical:
        c = db.get(InjuryCase, owner_id)
        if c is None:
            raise deny(db, p, EntityType.injury_case, owner_id, None, "Injury case")
        inc = inc_svc.get_incident(db, p, c.incident_id)
        g = p.grant(inc.project_id, Capability.injury_medical_view)
        if not covers(g, inc.site_id, c.employer_engagement_id or inc.responsible_engagement_id):
            raise forbidden_error("Medical attachments need capability 30.")
        return inc.project_id, inc.status != IncidentStatus.voided
    if owner_type == AttachmentOwner.observation:
        o = obs_svc.get_obs(db, p, owner_id)
        if write and o.observer_id != p.user.id and not obs_svc._can_close(p, o):
            raise forbidden_error()
        return o.project_id, o.status != ObservationStatus.closed or o.observer_id == p.user.id
    if owner_type == AttachmentOwner.corrective_action_evidence:
        ca = ca_svc.get_ca(db, p, owner_id)
        if write and p.user.id != ca.owner_id and not ca_svc._staff(p, ca):
            raise forbidden_error()
        return ca.project_id, ca.status in (CaStatus.open, CaStatus.in_progress)
    m = db.get(HseMeeting, owner_id)
    if m is None or p.grant(m.project_id, Capability.incident_view) is None:
        raise deny(db, p, EntityType.hse_meeting, owner_id, m.project_id if m else None, "Meeting")
    if write:
        p.require(m.project_id, Capability.inspection_plan_manage)
    return m.project_id, True


# ---- operations ----------------------------------------------------------------------------------


def _read(a: Attachment, refs: Refs) -> AttachmentRead:
    return AttachmentRead(
        id=a.id,
        owner_type=a.owner_type,
        owner_id=a.owner_id,
        file_name=a.file_name,
        content_type=a.content_type,
        size_bytes=a.size_bytes,
        sha256=a.sha256,
        scan_status=a.scan_status,
        uploaded_by=refs.user(a.uploaded_by_user_id) or UNKNOWN,
        created_at=a.created_at,
    )


def _content_type(name: str, content: bytes) -> str:
    ext = Path(name).suffix.lower()
    ctype = TYPES.get(ext)
    ok = ctype is not None and (
        content[4:8] == b"ftyp" if ctype == "image/heic" else content.startswith(MAGIC[ctype])
    )
    if not ok or ctype is None:
        raise ApiError(
            422,
            ErrorCode.FILE_TYPE_NOT_ALLOWED,
            "Only JPEG, PNG, HEIC images or PDF files are allowed.",
            "يُسمح فقط بصور JPEG وPNG وHEIC أو ملفات PDF.",
        )
    return ctype


def upload(
    db: Session,
    p: Principal,
    owner_type: AttachmentOwner,
    owner_id: uuid.UUID,
    file_name: str,
    content: bytes,
) -> AttachmentRead:
    p.ensure_writer()
    settings = get_settings()
    project_id, editable = _owner(db, p, owner_type, owner_id, write=True)
    if not editable:
        raise ApiError(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The record is closed; attachments cannot be added.",
            "السجل مغلق؛ لا يمكن إضافة مرفقات.",
        )
    if len(content) > settings.attachment_max_bytes:
        raise ApiError(
            422,
            ErrorCode.FILE_TOO_LARGE,
            "Files must be 20 MB or smaller.",
            "الحد الأقصى 20 ميغابايت.",
        )
    ctype = _content_type(file_name, content)
    if owner_type == AttachmentOwner.observation:
        n = db.scalar(
            select(func.count())
            .select_from(Attachment)
            .where(Attachment.owner_type == owner_type, Attachment.owner_id == owner_id)
        )
        if (n or 0) >= MAX_OBS_PHOTOS:
            raise ApiError(
                409,
                ErrorCode.TRANSITION_CONDITION_NOT_MET,
                "An observation can have at most 3 photos.",
                "الحد الأقصى 3 صور للملاحظة.",
            )
    aid = uuid.uuid4()
    bucket = _bucket(owner_type)
    key = f"{bucket}/{project_id}/{aid}"
    path = Path(settings.storage_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    data = crypto.encrypt_bytes(content) if bucket == "medical" else content
    path.write_bytes(data)
    a = Attachment(
        id=aid,
        owner_type=owner_type,
        owner_id=owner_id,
        project_id=project_id,
        file_name=Path(file_name).name[:255],
        content_type=ctype,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_bucket=bucket,
        storage_key=key,
        scan_status=ScanStatus.skipped,
        uploaded_by_user_id=p.user.id,
    )
    db.add(a)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project_id),
        entity_type=EntityType.attachment,
        entity_id=a.id,
        project_id=project_id,
        details={"owner_type": owner_type.value, "owner_id": str(owner_id), "size": len(content)},
    )
    return _read(a, Refs(db))


def list_for(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID
) -> AttachmentList:
    _owner(db, p, owner_type, owner_id, write=False)
    rows = list(
        db.scalars(
            select(Attachment)
            .where(Attachment.owner_type == owner_type, Attachment.owner_id == owner_id)
            .order_by(Attachment.created_at)
        )
    )
    refs = Refs(db).load(users=[a.uploaded_by_user_id for a in rows])
    return AttachmentList(items=[_read(a, refs) for a in rows])


def _get(db: Session, p: Principal, attachment_id: uuid.UUID) -> Attachment:
    a = db.get(Attachment, attachment_id)
    if a is None:
        raise deny(db, p, EntityType.attachment, attachment_id, None, "Attachment")
    _owner(db, p, a.owner_type, a.owner_id, write=False)
    return a


def signed_url(db: Session, p: Principal, attachment_id: uuid.UUID) -> SignedUrlRead:
    a = _get(db, p, attachment_id)
    medical = a.owner_type == AttachmentOwner.injury_case_medical
    expires = int(time.time()) + (MEDICAL_TTL if medical else DEFAULT_TTL)
    sig = crypto.sign(f"{a.id}:{expires}", get_settings().attachment_url_secret)
    audit.record(
        db,
        AuditAction.sensitive_field_read if medical else AuditAction.export,
        p.actor(a.project_id),
        entity_type=EntityType.attachment,
        entity_id=a.id,
        project_id=a.project_id,
        fields_read=["medical_attachment"] if medical else None,
        details={"signed_url_expires": expires},
    )
    return SignedUrlRead(
        url=f"{API_PREFIX}/attachments/{a.id}/content?expires={expires}&signature={sig}",
        expires_at=datetime.fromtimestamp(expires, UTC),
    )


def download(
    db: Session, attachment_id: uuid.UUID, expires: int, signature: str
) -> tuple[bytes, str, str]:
    a = db.get(Attachment, attachment_id)
    if a is None:
        raise not_found("Attachment")
    good = crypto.verify(f"{a.id}:{expires}", signature, get_settings().attachment_url_secret)
    if not good or expires < int(time.time()):
        raise ApiError(
            410,
            ErrorCode.SIGNED_URL_INVALID,
            "This download link has expired or is invalid.",
            "انتهت صلاحية رابط التنزيل أو أنه غير صالح.",
        )
    data = (Path(get_settings().storage_dir) / a.storage_key).read_bytes()
    if a.storage_bucket == "medical":
        data = crypto.decrypt_bytes(data)
    return data, a.content_type, a.file_name


def delete(db: Session, p: Principal, attachment_id: uuid.UUID) -> None:
    a = _get(db, p, attachment_id)
    p.ensure_writer()
    _, editable = _owner(db, p, a.owner_type, a.owner_id, write=False)
    if a.uploaded_by_user_id != p.user.id and not p.is_manager:
        raise forbidden_error("Only the uploader may delete an attachment.")
    if not editable:
        raise ApiError(409, ErrorCode.INVALID_TRANSITION, "The record is closed.", "السجل مغلق.")
    path = Path(get_settings().storage_dir) / a.storage_key
    path.unlink(missing_ok=True)
    details: dict[str, Any] = {"owner_type": a.owner_type.value, "file_name": a.file_name}
    audit.record(
        db,
        AuditAction.archive,
        p.actor(a.project_id),
        entity_type=EntityType.attachment,
        entity_id=a.id,
        project_id=a.project_id,
        details=details,
    )
    db.delete(a)
    db.flush()


def count_for(db: Session, owner_type: AttachmentOwner, owner_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Attachment)
            .where(Attachment.owner_type == owner_type, Attachment.owner_id == owner_id)
        )
        or 0
    )
