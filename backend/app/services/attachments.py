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
PHOTO_MAX_BYTES = 2 * 1024 * 1024
PHOTO_MIN_PX = 400
UNKNOWN = UserRef(id=uuid.UUID(int=0), full_name_en="—")


PERSONAL = frozenset(
    {
        AttachmentOwner.worker_photo,
        AttachmentOwner.pass_application_id_copy,
        AttachmentOwner.induction_signature,
        AttachmentOwner.offence_evidence,
        AttachmentOwner.gas_test_signature,
        AttachmentOwner.personnel_cert_scan,  # P4-3
        AttachmentOwner.training_record_scan,  # P5-3
        AttachmentOwner.training_attendance_signature,  # P5-8
        AttachmentOwner.toolbox_signature,  # 6d P6d-4
    }
)
PTW_OWNERS = frozenset(
    {
        AttachmentOwner.permit_document,
        AttachmentOwner.permit_attachment,
        AttachmentOwner.ptw_audit_photo,
        AttachmentOwner.gas_test_signature,
    }
)
ENCRYPTED = frozenset({"medical", "personal"})


def _bucket(owner: AttachmentOwner) -> str:
    if owner == AttachmentOwner.injury_case_medical:
        return "medical"
    if owner == AttachmentOwner.fitness_scan:  # 6a P6-5: separate encrypted medical bucket
        return "medical"
    return "personal" if owner in PERSONAL else "general"


def store(
    db: Session,
    owner_type: AttachmentOwner,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    file_name: str,
    content: bytes,
    ctype: str,
    user_id: uuid.UUID,
) -> Attachment:
    """Writes the file (encrypted for the medical and personal buckets) and the row."""
    aid = uuid.uuid4()
    bucket = _bucket(owner_type)
    key = f"{bucket}/{project_id}/{aid}"
    path = Path(get_settings().storage_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(crypto.encrypt_bytes(content) if bucket in ENCRYPTED else content)
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
        uploaded_by_user_id=user_id,
    )
    db.add(a)
    db.flush()
    return a


def erase(db: Session, a: Attachment) -> None:
    (Path(get_settings().storage_dir) / a.storage_key).unlink(missing_ok=True)
    db.delete(a)


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
    if owner_type in PTW_OWNERS:
        return _ptw_owner(db, p, owner_type, owner_id, write)
    if owner_type == AttachmentOwner.fitness_scan:
        from app.services.med import assessments as med_assessments  # noqa: PLC0415

        return med_assessments.scan_owner(db, p, owner_id, write)
    from app.services.cert import files as cert_files  # noqa: PLC0415

    if owner_type in cert_files.CERT_OWNERS:
        return cert_files.owner(db, p, owner_type, owner_id, write)
    from app.services.train import files as train_files  # noqa: PLC0415

    if owner_type in train_files.TRAIN_OWNERS:
        return train_files.owner(db, p, owner_type, owner_id, write)
    from app.services.field import files as field_files  # noqa: PLC0415

    if owner_type in field_files.FIELD_OWNERS:
        return field_files.owner(db, p, owner_type, owner_id, write)
    from app.services.env import files as env_files  # noqa: PLC0415

    if owner_type in env_files.ENV_OWNERS:
        return env_files.owner(db, p, owner_type, owner_id, write)
    if owner_type in PERSONAL:
        return _access_owner(db, p, owner_type, owner_id, write)
    m = db.get(HseMeeting, owner_id)
    if m is None or p.grant(m.project_id, Capability.incident_view) is None:
        raise deny(db, p, EntityType.hse_meeting, owner_id, m.project_id if m else None, "Meeting")
    if write:
        p.require(m.project_id, Capability.inspection_plan_manage)
    return m.project_id, True


def _ptw_owner(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    """Phase 3 files: permit documents and attachments (owner = permit), PTW audit photos
    (owner = audit; "avoid faces", AU-8), gas-tester signatures (owner = gas test; capability
    46 to read, written only with the test)."""
    from app.core.ptw_enums import PERMIT_TERMINAL, PtwAuditStatus  # noqa: PLC0415
    from app.models import GasTest  # noqa: PLC0415
    from app.services.access import common as acc  # noqa: PLC0415
    from app.services.ptw import audits as ptw_audits  # noqa: PLC0415
    from app.services.ptw import common as ptw_common  # noqa: PLC0415

    c = Capability
    if owner_type == AttachmentOwner.ptw_audit_photo:
        a = ptw_audits.get_row(db, p, owner_id)
        if write and a.auditor_user_id != p.user.id and not p.is_manager:
            raise forbidden_error("Only the auditor adds photos to the audit.")
        return a.project_id, a.status != PtwAuditStatus.locked
    if owner_type == AttachmentOwner.gas_test_signature:
        t = db.get(GasTest, owner_id)
        if t is None:
            raise not_found("Gas test")
        permit = ptw_common.get_permit(db, p, t.permit_id)
        if write:
            raise forbidden_error("The signature is captured with the gas test.")
        if p.grant(permit.project_id, c.worker_view) is None:
            raise forbidden_error("Worker signatures need capability 46.")
        return permit.project_id, False
    permit = ptw_common.get_permit(db, p, owner_id)
    if write:
        pid = permit.project_id
        if p.grant(pid, c.permit_prepare) is not None:
            acc.require_cap(p, pid, c.permit_prepare, [permit.site_id], permit.engagement_id)
        elif p.grant(pid, c.permit_receive) is not None:
            acc.require_cap(p, pid, c.permit_receive, [permit.site_id], permit.engagement_id)
        else:
            acc.require_cap(p, pid, c.permit_issue, [permit.site_id], None)
    editable = owner_type == AttachmentOwner.permit_attachment or (
        permit.status not in PERMIT_TERMINAL
    )
    return permit.project_id, editable


def _access_owner(
    db: Session, p: Principal, owner_type: AttachmentOwner, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    """Phase 2 personal files (spec 2-access-permits §3.1 photo, §3.8 ID copy, §3.4 signature,
    §3.11 evidence; P2-2): encrypted bucket, signed URLs ≤ 5 min."""
    from app.core.access_enums import (  # noqa: PLC0415 (access services import this module)
        PassApplicationStatus,
        WorkerStatus,
    )
    from app.models import Deployment  # noqa: PLC0415
    from app.services.access import common as acc  # noqa: PLC0415
    from app.services.access import driving, inductions, passes, workers  # noqa: PLC0415

    c = Capability
    if owner_type == AttachmentOwner.worker_photo:
        w = workers.get_worker(db, p, owner_id)
        if write:
            workers._can_edit(db, p, w)
        dep = db.scalars(
            select(Deployment)
            .where(Deployment.worker_id == w.id)
            .order_by(Deployment.mobilised_on.desc())
            .limit(1)
        ).first()
        if dep is None:
            raise ApiError(
                422,
                ErrorCode.VALIDATION_ERROR,
                "Deploy the worker on a project before adding a photo.",
                "يجب تعيين العامل في مشروع قبل إضافة الصورة.",
            )
        return dep.project_id, w.status != WorkerStatus.anonymised
    if owner_type == AttachmentOwner.pass_application_id_copy:
        a, d = passes.get_application(db, p, owner_id)
        cap = c.pass_application_create if write else c.worker_unmask_id
        acc.require_cap(p, a.project_id, cap, d.site_ids, d.engagement_id)
        editable = a.status in (PassApplicationStatus.draft, PassApplicationStatus.submitted)
        return a.project_id, editable
    if owner_type == AttachmentOwner.induction_signature:
        r = inductions.get_record(db, p, owner_id)
        if write:
            raise forbidden_error("The signature is captured with the induction record.")
        return r.project_id, False
    o = driving.get_offence_row(db, p, owner_id)
    if write:
        acc.require_cap(p, o.project_id, c.offence_record, None, o.engagement_id)
    return o.project_id, True


def _image_size(content: bytes, ctype: str) -> tuple[int, int] | None:
    """(width, height) from the PNG IHDR or the first JPEG SOF marker."""
    if ctype == "image/png" and len(content) >= 24:
        return int.from_bytes(content[16:20], "big"), int.from_bytes(content[20:24], "big")
    if ctype == "image/jpeg":
        i = 2
        while i + 9 < len(content):
            if content[i] != 0xFF:
                i += 1
                continue
            marker = content[i + 1]
            seg = int.from_bytes(content[i + 2 : i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD):
                h = int.from_bytes(content[i + 5 : i + 7], "big")
                return int.from_bytes(content[i + 7 : i + 9], "big"), h
            i += 2 + seg
    return None


def _check_photo(content: bytes, ctype: str) -> None:
    """§3.1: JPEG/PNG ≤ 2 MB, ≥ 400×400."""
    size = _image_size(content, ctype) if ctype in ("image/jpeg", "image/png") else None
    if len(content) > PHOTO_MAX_BYTES or size is None or min(size) < PHOTO_MIN_PX:
        raise ApiError(
            422,
            ErrorCode.FILE_TYPE_NOT_ALLOWED,
            "Worker photos must be JPEG or PNG, at most 2 MB and at least 400×400 pixels.",
            "يجب أن تكون صورة العامل JPEG أو PNG بحجم لا يتجاوز 2 ميغابايت "
            "و400×400 بكسل على الأقل.",
        )


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
    if owner_type == AttachmentOwner.worker_photo:
        _check_photo(content, ctype)
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
    a = store(db, owner_type, owner_id, project_id, file_name, content, ctype, p.user.id)
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
    if a.owner_type == AttachmentOwner.fitness_scan:
        raise forbidden_error("Open fitness scans through scan-url with a reason (P6-5).")
    medical = a.owner_type == AttachmentOwner.injury_case_medical
    short = medical or a.owner_type in PERSONAL  # P1-3 / P2-2: ≤ 5 min
    expires = int(time.time()) + (MEDICAL_TTL if short else DEFAULT_TTL)
    if a.owner_type == AttachmentOwner.pass_application_id_copy:
        audit.record(
            db,
            AuditAction.sensitive_field_read,
            p.actor(a.project_id),
            entity_type=EntityType.pass_application,
            entity_id=a.owner_id,
            project_id=a.project_id,
            fields_read=["id_copy"],
        )
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


def raw_signed_url(attachment_id: uuid.UUID, ttl: int) -> str:
    """Short-lived signed URL without a principal (gate result screen photo, GC-7)."""
    expires = int(time.time()) + ttl
    sig = crypto.sign(f"{attachment_id}:{expires}", get_settings().attachment_url_secret)
    return f"{API_PREFIX}/attachments/{attachment_id}/content?expires={expires}&signature={sig}"


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
    if a.storage_bucket in ENCRYPTED:
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
