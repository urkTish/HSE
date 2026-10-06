"""File attachments (incident photos, medical files, CA evidence, observation photos, meeting
minutes). Spec 1-dashboard §3.3, §3.4, §3.6, §3.8, P1-3."""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.hse_enums import AttachmentOwner, ScanStatus
from app.schemas.common import ApiModel
from app.schemas.hse_common import UserRef


class AttachmentRead(ApiModel):
    id: uuid.UUID
    owner_type: AttachmentOwner
    owner_id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    scan_status: ScanStatus
    uploaded_by: UserRef
    created_at: datetime


class AttachmentList(ApiModel):
    items: list[AttachmentRead]


class SignedUrlRead(ApiModel):
    """Short-lived download link. Medical attachments: ≤ 5 min (P1-3); others 15 min."""

    url: str = Field(description="Relative URL under /api/v1; no auth header needed.")
    expires_at: datetime
