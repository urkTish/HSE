"""Q4 HTTP routes: document control, read-and-acknowledge, citations and transmittals (spec
8-quality §E.1)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.quality.common import QRecordType
from app.core.quality.q4 import QDocType, QRevStatus, QTransmittalStatus
from app.schemas.quality.q4 import (
    Q4AckResult,
    Q4Citation,
    Q4CiteInput,
    Q4Decision,
    Q4Distribution,
    Q4DocumentCreate,
    Q4DocumentPage,
    Q4DocumentRead,
    Q4DocumentUpdate,
    Q4MyAck,
    Q4Reason,
    Q4RevisionUpdate,
    Q4TransmittalCreate,
    Q4TransmittalPage,
    Q4TransmittalRead,
    Q4TransmittalRespond,
)
from app.services.quality.q4 import documents as docs

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)
P = "/projects/{project_id}/quality"


@router.get(
    P + "/documents", response_model=Q4DocumentPage, summary="Document register (§E.1)", responses=E
)
def q4_list_documents(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    pg: PageParams,
    doc_type: QDocType | None = None,
    status_: Annotated[QRevStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    return docs.list_documents(db, user, project_id, doc_type, status_, q, pg.page, pg.page_size)


@router.post(
    P + "/documents",
    response_model=Q4DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="New controlled document with its first Draft revision (273)",
    responses=E,
)
def q4_create_document(
    project_id: uuid.UUID, body: Q4DocumentCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return docs.create(db, user, project_id, body.model_dump())


@router.get(
    "/quality/documents/{doc_id}",
    response_model=Q4DocumentRead,
    summary="One document",
    responses=E,
)
def q4_get_document(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return docs.read(db, user, doc_id)


@router.patch(
    "/quality/documents/{doc_id}",
    response_model=Q4DocumentRead,
    summary="Edit document data (273)",
    responses=E,
)
def q4_update_document(
    doc_id: uuid.UUID, body: Q4DocumentUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return docs.update(db, user, doc_id, body.model_dump(exclude_unset=True))


@router.post(
    "/quality/documents/{doc_id}/revisions",
    response_model=Q4DocumentRead,
    summary="Start a new revision from the current one (Q-DOC-03)",
    responses=E,
)
def q4_new_revision(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return docs.new_revision(db, user, doc_id)


@router.put(
    "/quality/documents/{doc_id}/distribution",
    response_model=Q4DocumentRead,
    summary="Distribution and read-and-acknowledge (Q-DOC-05)",
    responses=E,
)
def q4_distribution(
    doc_id: uuid.UUID, body: Q4Distribution, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return docs.set_distribution(db, user, doc_id, body.model_dump())


@router.post(
    "/quality/documents/{doc_id}/obsolete",
    response_model=Q4DocumentRead,
    summary="Withdraw an approved document (239)",
    responses=E,
)
def q4_obsolete(doc_id: uuid.UUID, body: Q4Reason, user: CurrentUser, db: DB) -> dict[str, Any]:
    return docs.obsolete(db, user, doc_id, body.reason)


@router.patch(
    "/quality/document-revisions/{rev_id}",
    response_model=Q4DocumentRead,
    summary="Edit a Draft revision (409 DOCUMENT_IMMUTABLE once approved)",
    responses=E,
)
def q4_update_revision(
    rev_id: uuid.UUID, body: Q4RevisionUpdate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return docs.update_revision(db, user, rev_id, body.model_dump(exclude_unset=True))


@router.post(
    "/quality/document-revisions/{rev_id}/submit",
    response_model=Q4DocumentRead,
    summary="Draft → For Review (PDF required)",
    responses=E,
)
def q4_submit_revision(rev_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return docs.submit(db, user, rev_id)


@router.post(
    "/quality/document-revisions/{rev_id}/review",
    response_model=Q4DocumentRead,
    summary="Review sign-off `document.review` (returned → Draft)",
    responses=E,
)
def q4_review_revision(
    rev_id: uuid.UUID, body: Q4Decision, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return docs.review(db, user, rev_id, body.model_dump())


@router.post(
    "/quality/document-revisions/{rev_id}/approve",
    response_model=Q4DocumentRead,
    summary="Approval `document.approve` (Q-DOC-02…05)",
    responses=E,
)
def q4_approve_revision(
    rev_id: uuid.UUID, body: Q4Decision, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return docs.approve(db, user, rev_id, body.model_dump())


@router.post(
    "/quality/document-revisions/{rev_id}/ack",
    response_model=Q4AckResult,
    summary="Acknowledge a revision (275; idempotent)",
    responses=E,
)
def q4_ack(rev_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return docs.acknowledge(db, user, rev_id)


@router.get(
    "/quality/document-revisions/{rev_id}/download",
    summary="The revision PDF (superseded files carry the -SUPERSEDED suffix)",
    responses=E,
    response_class=Response,
)
def q4_download_revision(rev_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    content, name = docs.download(db, user, rev_id)
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post(
    "/quality/document-revisions/{rev_id}/citations",
    response_model=list[Q4Citation],
    summary="Cite a revision from a Quality record (Q-DOC-06)",
    responses=E,
)
def q4_cite(
    rev_id: uuid.UUID, body: Q4CiteInput, user: CurrentUser, db: DB
) -> list[dict[str, Any]]:
    return docs.cite(db, user, rev_id, QRecordType(body.record_type), body.record_id)


@router.get(
    "/quality/citations",
    response_model=list[Q4Citation],
    summary="Documents a record cites, with 'newer revision available'",
    responses=E,
)
def q4_citations(
    record_type: QRecordType, record_id: uuid.UUID, user: CurrentUser, db: DB
) -> list[dict[str, Any]]:
    return docs.citations_of(db, user, record_type, record_id)


@router.get(
    P + "/my-acknowledgements",
    response_model=list[Q4MyAck],
    summary="My read-and-acknowledge tasks",
    responses=E,
)
def q4_my_acks(
    project_id: uuid.UUID, user: CurrentUser, db: DB, pending: bool = True
) -> list[dict[str, Any]]:
    return docs.my_acks(db, user, project_id, pending)


@router.get(
    P + "/transmittals",
    response_model=Q4TransmittalPage,
    summary="Transmittals (Q-DOC-07)",
    responses=E,
)
def q4_list_transmittals(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    pg: PageParams,
    status_: Annotated[QTransmittalStatus | None, Query(alias="status")] = None,
) -> dict[str, Any]:
    return docs.list_transmittals(db, user, project_id, status_, pg.page, pg.page_size)


@router.post(
    P + "/transmittals",
    response_model=Q4TransmittalRead,
    status_code=status.HTTP_201_CREATED,
    summary="New transmittal (273)",
    responses=E,
)
def q4_create_transmittal(
    project_id: uuid.UUID, body: Q4TransmittalCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return docs.create_transmittal(db, user, project_id, body.model_dump())


@router.get(
    "/quality/transmittals/{tid}",
    response_model=Q4TransmittalRead,
    summary="One transmittal",
    responses=E,
)
def q4_get_transmittal(tid: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return docs.read_transmittal(db, user, tid)


@router.post(
    "/quality/transmittals/{tid}/send",
    response_model=Q4TransmittalRead,
    summary="Send: number, cover sheet EN / AR (Hijri) and email outbox",
    responses=E,
)
def q4_send_transmittal(tid: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return docs.send_transmittal(db, user, tid)


@router.post(
    "/quality/transmittals/{tid}/response",
    response_model=Q4TransmittalRead,
    summary="Record the response with per-item codes A–D",
    responses=E,
)
def q4_respond_transmittal(
    tid: uuid.UUID, body: Q4TransmittalRespond, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return docs.respond_transmittal(db, user, tid, body.model_dump())


@router.post(
    "/quality/transmittals/{tid}/cancel",
    response_model=Q4TransmittalRead,
    summary="Cancel a Draft transmittal",
    responses=E,
)
def q4_cancel_transmittal(
    tid: uuid.UUID, body: Q4Reason, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return docs.cancel_transmittal(db, user, tid, body.reason)
