"""Q1 HTTP routes: inspection requests — draft, submit, return, schedule, attend, decide (also
offline), witness waiver, re-inspection, cancel, void, comments, PDF (spec 8-quality §B.4)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.quality.q1 import QIrStatus, QPointType
from app.schemas.quality.q1 import (
    QCommentText,
    QIrCommentClose,
    QIrCommentRespond,
    QIrConfirm,
    QIrCreate,
    QIrDecide,
    QIrPage,
    QIrRead,
    QIrReinspect,
    QIrSchedule,
    QIrSelfCheck,
    QIrSubmit,
    QIrUpdate,
    QIrWaive,
    QLocationSuggestion,
    QReason,
)
from app.services.quality.q1 import decide, ir, pdf

router = APIRouter(tags=["quality"])
E = error_responses(401, 403, 404, 409, 422)


def _r(
    db: Any,
    user: Any,
    r: Any,
    warnings: list[Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = ir.read(db, user, r, warnings, **(extra or {}))
    if extra and extra.get("ncr_id"):
        out["ncr_id"] = extra["ncr_id"]
    return out


@router.get(
    "/projects/{project_id}/quality/inspection-requests",
    response_model=QIrPage,
    summary="IR board / register (scoped P / S / C; N = steps of the responsible person)",
    responses=E,
)
def q1_list_irs(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[QIrStatus] | None, Query(alias="status")] = None,
    itp_family_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    governing_type: QPointType | None = None,
    mine: bool = False,
    inspector_me: bool = Query(
        default=False, description="My inspections (current round inspector)."
    ),
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    return ir.list_page(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        statuses=status_,
        itp_family_id=itp_family_id,
        engagement_id=engagement_id,
        zone_id=zone_id,
        governing_type=governing_type,
        mine=mine,
        inspector_me=inspector_me,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
        q=q,
    )


@router.get(
    "/projects/{project_id}/quality/inspection-requests/locations",
    response_model=list[QLocationSuggestion],
    summary="Location autocomplete from earlier IR location keys",
    responses=E,
)
def q1_ir_locations(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    itp_family_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[dict[str, Any]]:
    return ir.location_suggestions(db, user, project_id, itp_family_id, zone_id, q)


@router.post(
    "/projects/{project_id}/quality/inspection-requests",
    response_model=QIrRead,
    status_code=status.HTTP_201_CREATED,
    summary="Raise an IR (249): Draft, or Submitted with `submit = true` (Q-IR-02 … -04, -08)",
    responses=E,
)
def q1_create_ir(
    project_id: uuid.UUID, body: QIrCreate, user: CurrentUser, db: DB
) -> dict[str, Any]:
    r, warnings = ir.create(db, user, project_id, body.model_dump(mode="python"))
    return _r(db, user, r, warnings)


@router.get(
    "/quality/inspection-requests/{ir_id}", response_model=QIrRead, summary="One IR", responses=E
)
def q1_get_ir(ir_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, ir.get_ir(db, user, ir_id))


@router.patch(
    "/quality/inspection-requests/{ir_id}",
    response_model=QIrRead,
    summary="Edit a draft IR",
    responses=E,
)
def q1_update_ir(ir_id: uuid.UUID, body: QIrUpdate, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(
        db, user, ir.update(db, user, ir_id, body.model_dump(exclude_unset=True, mode="python"))
    )


@router.delete(
    "/quality/inspection-requests/{ir_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a never-submitted draft",
    responses=E,
)
def q1_delete_ir(ir_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    ir.delete_draft(db, user, ir_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/quality/inspection-requests/{ir_id}/submit",
    response_model=QIrRead,
    summary="Submit (notice, self-check, hold points)",
    responses=E,
)
def q1_submit_ir(ir_id: uuid.UUID, body: QIrSubmit, user: CurrentUser, db: DB) -> dict[str, Any]:
    r, warnings = ir.submit(db, user, ir_id, body.short_notice_reason)
    return _r(db, user, r, warnings)


@router.post(
    "/quality/inspection-requests/{ir_id}/self-check",
    response_model=QIrRead,
    summary="Contractor self-check on the points' checklists, kept as round 0 (Q-IR-04)",
    responses=E,
)
def q1_self_check_ir(
    ir_id: uuid.UUID, body: QIrSelfCheck, user: CurrentUser, db: DB
) -> dict[str, Any]:
    data = body.model_dump(mode="python")
    return _r(db, user, ir.self_check(db, user, ir_id, data["answers"], data["note"]))


@router.post(
    "/quality/inspection-requests/{ir_id}/return",
    response_model=QIrRead,
    summary="Return to Draft (250 + RPM, comment ≥ 20)",
    responses=E,
)
def q1_return_ir(ir_id: uuid.UUID, body: QCommentText, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, ir.return_to_draft(db, user, ir_id, body.comment))


@router.post(
    "/quality/inspection-requests/{ir_id}/schedule",
    response_model=QIrRead,
    summary="Schedule or re-schedule (250 + RPM; Q-IR-07 competence)",
    responses=E,
)
def q1_schedule_ir(
    ir_id: uuid.UUID, body: QIrSchedule, user: CurrentUser, db: DB
) -> dict[str, Any]:
    r, warnings = ir.schedule(db, user, ir_id, body.scheduled_at, body.inspector_id, body.reason)
    return _r(db, user, r, warnings)


@router.post(
    "/quality/inspection-requests/{ir_id}/attend",
    response_model=QIrRead,
    summary="Record the inspector's attendance",
    responses=E,
)
def q1_attend_ir(ir_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, ir.attend(db, user, ir_id))


@router.post(
    "/quality/inspection-requests/{ir_id}/decide",
    response_model=QIrRead,
    summary="Record the round result (250 + RPM) or review a waived witness point",
    description="Offline rounds carry `recorded_at` (Q-IR-14).",
    responses=E,
)
def q1_decide_ir(ir_id: uuid.UUID, body: QIrDecide, user: CurrentUser, db: DB) -> dict[str, Any]:
    r, warnings, extra = decide.decide(
        db, user, ir_id, body.model_dump(mode="python", exclude_none=False)
    )
    return _r(db, user, r, warnings, extra)


@router.post(
    "/quality/inspection-requests/{ir_id}/confirm-offline",
    response_model=QIrRead,
    summary="Confirm or discard a round kept as needs confirmation",
    responses=E,
)
def q1_confirm_ir(ir_id: uuid.UUID, body: QIrConfirm, user: CurrentUser, db: DB) -> dict[str, Any]:
    r, warnings, extra = decide.confirm_offline(db, user, ir_id, body.discard)
    return _r(db, user, r, warnings, extra)


@router.post(
    "/quality/inspection-requests/{ir_id}/waive",
    response_model=QIrRead,
    summary="Witness waived (249; W only, after the wait; H → HOLD_NOT_WAIVABLE)",
    responses=E,
)
def q1_waive_ir(ir_id: uuid.UUID, body: QIrWaive, user: CurrentUser, db: DB) -> dict[str, Any]:
    r, warnings = decide.waive(db, user, ir_id, body.model_dump(mode="python"))
    return _r(db, user, r, warnings)


@router.post(
    "/quality/inspection-requests/{ir_id}/reinspection",
    response_model=QIrRead,
    summary="Request re-inspection after a rejection (note ≥ 20, photo)",
    responses=E,
)
def q1_reinspect_ir(
    ir_id: uuid.UUID, body: QIrReinspect, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, ir.request_reinspection(db, user, ir_id, body.note, body.photos))


@router.post(
    "/quality/inspection-requests/{ir_id}/cancel",
    response_model=QIrRead,
    summary="Cancel (requester or 250; reason ≥ 20)",
    responses=E,
)
def q1_cancel_ir(ir_id: uuid.UUID, body: QReason, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, ir.cancel(db, user, ir_id, body.reason))


@router.post(
    "/quality/inspection-requests/{ir_id}/void",
    response_model=QIrRead,
    summary="Void an approved IR (244); later undecided IRs are re-blocked",
    responses=E,
)
def q1_void_ir(ir_id: uuid.UUID, body: QReason, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _r(db, user, ir.void(db, user, ir_id, body.reason))


@router.post(
    "/quality/ir-comments/{comment_id}/respond",
    response_model=QIrRead,
    summary="Respond to an approval comment (249)",
    responses=E,
)
def q1_respond_comment(
    comment_id: uuid.UUID, body: QIrCommentRespond, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, ir.respond_comment(db, user, comment_id, body.response_text, body.photos))


@router.post(
    "/quality/ir-comments/{comment_id}/close",
    response_model=QIrRead,
    summary="Close (or re-open) an approval comment (250 + RPM)",
    responses=E,
)
def q1_close_comment(
    comment_id: uuid.UUID, body: QIrCommentClose, user: CurrentUser, db: DB
) -> dict[str, Any]:
    return _r(db, user, ir.close_comment(db, user, comment_id, body.accept, body.note))


@router.get(
    "/quality/inspection-requests/{ir_id}/pdf",
    summary="IR form in EN or AR with the Hijri issue date (Q-IR-13)",
    responses={
        **E,
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}},
    },
    response_class=Response,
)
def q1_ir_pdf(
    ir_id: uuid.UUID, user: CurrentUser, db: DB, lang: Literal["en", "ar"] = "en"
) -> Response:
    content, name = pdf.pdf(db, user, ir_id, lang)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
