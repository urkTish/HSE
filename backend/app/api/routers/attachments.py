"""File attachments with signed download URLs (spec 1-dashboard §3.3, §3.4, P1-3)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import DB, CurrentUser
from app.core.errors import error_responses, not_implemented
from app.core.hse_enums import AttachmentOwner
from app.schemas.attachments import AttachmentList, AttachmentRead, SignedUrlRead

router = APIRouter(tags=["attachments"])

UPLOAD_DESC = (
    "Images (JPEG/PNG/HEIC) or PDF, ≤ 20 MB each. Limits: observation ≤ 3 photos. "
    "`injury_case_medical` needs capability 30 and is stored in the separate encrypted bucket; "
    "it is never included in bulk exports (P1-3). Files are virus-scanned (scan_status); "
    "422 FILE_TOO_LARGE / FILE_TYPE_NOT_ALLOWED."
)


@router.post(
    "/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an attachment to a record",
    description=UPLOAD_DESC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def upload_attachment(
    user: CurrentUser,
    db: DB,
    owner_type: Annotated[AttachmentOwner, Form()],
    owner_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
) -> AttachmentRead:
    raise not_implemented()


@router.get(
    "/attachments",
    response_model=AttachmentList,
    summary="List attachments of a record the caller can see",
    responses=error_responses(401, 403, 404, 422),
)
def list_attachments(
    user: CurrentUser,
    db: DB,
    owner_type: AttachmentOwner,
    owner_id: uuid.UUID,
) -> AttachmentList:
    raise not_implemented()


@router.post(
    "/attachments/{attachment_id}/signed-url",
    response_model=SignedUrlRead,
    summary="Get a short-lived download link (medical ≤ 5 min; read audited for medical)",
    responses=error_responses(401, 403, 404, 409),
)
def sign_attachment_url(attachment_id: uuid.UUID, user: CurrentUser, db: DB) -> SignedUrlRead:
    raise not_implemented()


@router.get(
    "/attachments/{attachment_id}/content",
    summary="Download through a signed link (no session needed)",
    description="410 SIGNED_URL_INVALID when expired or tampered.",
    response_class=Response,
    responses={
        200: {
            "description": "File content.",
            "content": {"application/octet-stream": {"schema": {"type": "string"}}},
        },
        **error_responses(404, 410),
    },
)
def download_attachment(
    attachment_id: uuid.UUID,
    db: DB,
    expires: Annotated[int, Query(description="Unix seconds.")],
    signature: Annotated[str, Query(max_length=128)],
) -> Response:
    raise not_implemented()


@router.delete(
    "/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an attachment (uploader while the record is editable)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_attachment(attachment_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    raise not_implemented()
