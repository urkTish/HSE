"""Permits to work: register, form, crew, equipment, documents, lifecycle, shifts, handovers,
suspensions, field records, exemptions, board, print and closure pack (spec 3-ptw §3.5-§3.10,
§3.13, §3.14, §4.1-§4.3, §5.1-§5.4, §5.7-§5.10, §5.12, §5.13)."""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses, not_implemented
from app.core.ptw_enums import (
    PermitAction,
    PermitBlocker,
    PermitRegisterSort,
    PermitStatus,
    PermitType,
    StatusReason,
)
from app.schemas.permits import (
    ApproveInput,
    AreaReviewInput,
    BarrierSurveyInput,
    BarrierSurveyRead,
    CancelInput,
    ChecklistInput,
    ChecklistRead,
    CloseInput,
    ClosurePackRead,
    ClosureRequestInput,
    EndShiftInput,
    EntryLogInput,
    EntryLogRead,
    ExcavationInspectionInput,
    ExcavationInspectionRead,
    ExemptionCreate,
    ExemptionDecision,
    ExemptionRead,
    GasAlarmInput,
    HandoverAcceptInput,
    HandoverCreate,
    HandoverList,
    HandoverRead,
    HotWorkEndInput,
    HseReviewInput,
    IncidentPermitSuggestions,
    IssueInput,
    PauseEndInput,
    PauseStartInput,
    PermitCopyInput,
    PermitCreate,
    PermitCrewInput,
    PermitCrewRead,
    PermitCrewUpdate,
    PermitDocumentInput,
    PermitDocumentRead,
    PermitEquipmentInput,
    PermitEquipmentRead,
    PermitFodCheckInput,
    PermitFodCheckRead,
    PermitPage,
    PermitPrintRead,
    PermitRead,
    PermitReadiness,
    PermitUpdate,
    PostExpiryCheckInput,
    PtwBoardResponse,
    ReceiverAcceptanceInput,
    ReceiverAcceptanceRead,
    RequestInput,
    ResumeInput,
    ReturnInput,
    RevalidateInput,
    SectionsInput,
    ShiftList,
    SourceReturnInput,
    StartInput,
    SuspendInput,
    SuspensionList,
    SuspensionPage,
    WindReadingInput,
    WindReadingRead,
)
from app.schemas.ptw_common import BLOCKED_DOC, SIGNING_DOC

router = APIRouter(tags=["permits"])


@router.get(
    "/projects/{project_id}/permits",
    response_model=PermitPage,
    summary="Permit register (capability 82; scope per §5.14; crew names need capability 46)",
    responses=error_responses(401, 403, 404, 422),
)
def list_permits(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[PermitStatus] | None, Query(alias="status")] = None,
    work_type: Annotated[list[PermitType] | None, Query()] = None,
    site_id: uuid.UUID | None = None,
    zone_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    issuer_user_id: uuid.UUID | None = None,
    receiver_user_id: uuid.UUID | None = None,
    worker_id: Annotated[
        uuid.UUID | None, Query(description="Permits listing this worker.")
    ] = None,
    live_on: Annotated[date | None, Query(description="Validity covers this day.")] = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    status_reason: StatusReason | None = None,
    blocker: Annotated[
        PermitBlocker | None, Query(description="Action panel: permits blocked by this code.")
    ] = None,
    awaiting_me: Annotated[
        bool, Query(description="Permits waiting on the caller's signature.")
    ] = False,
    simops_open: bool | None = None,
    isolation_id: uuid.UUID | None = None,
    wap_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: PermitRegisterSort = PermitRegisterSort.newest,
) -> PermitPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/permits",
    response_model=PermitRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Draft permit (capability 83; receiver = caller unless prepared for them)",
    responses=error_responses(401, 403, 404, 422),
)
def create_permit(
    project_id: uuid.UUID,
    body: PermitCreate,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.get(
    "/permits/{permit_id}",
    response_model=PermitRead,
    summary="Get a permit (allowed_actions, blockers and warnings for the caller)",
    responses=error_responses(401, 403, 404),
)
def get_permit(permit_id: uuid.UUID, user: CurrentUser, db: DB) -> PermitRead:
    raise not_implemented()


@router.patch(
    "/permits/{permit_id}",
    response_model=PermitRead,
    summary="Edit a Draft / Returned permit (preparer or receiver; else PERMIT_READ_ONLY)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_permit(
    permit_id: uuid.UUID,
    body: PermitUpdate,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.delete(
    "/permits/{permit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Draft permit never requested (preparer; else 409 use cancel)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_permit(permit_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/crew",
    response_model=PermitCrewRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a crew line (eligibility evaluated; CREW_NOT_IN_TREE, KEY_ROLE_BUSY)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def add_permit_crew(
    permit_id: uuid.UUID,
    body: PermitCrewInput,
    user: CurrentUser,
    db: DB,
) -> PermitCrewRead:
    raise not_implemented()


@router.patch(
    "/permits/{permit_id}/crew/{line_id}",
    response_model=PermitCrewRead,
    summary="Edit a crew line (role, present/briefed, removal while live)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_permit_crew(
    permit_id: uuid.UUID,
    line_id: uuid.UUID,
    body: PermitCrewUpdate,
    user: CurrentUser,
    db: DB,
) -> PermitCrewRead:
    raise not_implemented()


@router.delete(
    "/permits/{permit_id}/crew/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a crew line before issue (after issue: PATCH status removed)",
    responses=error_responses(401, 403, 404, 409),
)
def delete_permit_crew(permit_id: uuid.UUID, line_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/equipment",
    response_model=PermitEquipmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add equipment (registered vehicle/plant or tag; hooks evaluated)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def add_permit_equipment(
    permit_id: uuid.UUID,
    body: PermitEquipmentInput,
    user: CurrentUser,
    db: DB,
) -> PermitEquipmentRead:
    raise not_implemented()


@router.delete(
    "/permits/{permit_id}/equipment/{equipment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove equipment from a permit",
    responses=error_responses(401, 403, 404, 409),
)
def delete_permit_equipment(
    permit_id: uuid.UUID,
    equipment_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> None:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/documents",
    response_model=PermitDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a supporting document (method statement, lift plan, drawing…)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def add_permit_document(
    permit_id: uuid.UUID,
    body: PermitDocumentInput,
    user: CurrentUser,
    db: DB,
) -> PermitDocumentRead:
    raise not_implemented()


@router.patch(
    "/permits/{permit_id}/documents/{document_id}",
    response_model=PermitDocumentRead,
    summary="Edit a supporting document's reference / revision / validity",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_permit_document(
    permit_id: uuid.UUID,
    document_id: uuid.UUID,
    body: PermitDocumentInput,
    user: CurrentUser,
    db: DB,
) -> PermitDocumentRead:
    raise not_implemented()


@router.delete(
    "/permits/{permit_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a supporting document",
    responses=error_responses(401, 403, 404, 409),
)
def delete_permit_document(
    permit_id: uuid.UUID,
    document_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> None:
    raise not_implemented()


@router.put(
    "/permits/{permit_id}/sections",
    response_model=PermitRead,
    summary="Replace the type-specific sections (one per work type, §3.6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def put_permit_sections(
    permit_id: uuid.UUID,
    body: SectionsInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.put(
    "/permits/{permit_id}/checklist",
    response_model=ChecklistRead,
    summary="Answer the pre-issue checklist (GW + type items; n.a. only where allowed)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def put_permit_checklist(
    permit_id: uuid.UUID,
    body: ChecklistInput,
    user: CurrentUser,
    db: DB,
) -> ChecklistRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/request",
    response_model=PermitRead,
    summary="Draft/Returned → Requested (receiver, capability 84; signed, PT-15)",
    description=SIGNING_DOC + " " + BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def request_permit(
    permit_id: uuid.UUID,
    body: RequestInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/return",
    response_model=PermitRead,
    summary="Return to the receiver with a reason (area authority / HSE / issuer)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def return_permit(permit_id: uuid.UUID, body: ReturnInput, user: CurrentUser, db: DB) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/review",
    response_model=PermitRead,
    summary="Area authority review (capability 85; signed; SoD)",
    description=SIGNING_DOC + " " + BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def area_review_permit(
    permit_id: uuid.UUID,
    body: AreaReviewInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/hse-review",
    response_model=PermitRead,
    summary="HSE review for high-risk types (capability 86; signed)",
    description=SIGNING_DOC + " " + BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def hse_review_permit(
    permit_id: uuid.UUID,
    body: HseReviewInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/approve",
    response_model=PermitRead,
    summary="Reviewed → Approved (issuer, capability 87; signed; blockers list B)",
    description=SIGNING_DOC + " " + BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def approve_permit(
    permit_id: uuid.UUID,
    body: ApproveInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/issue",
    response_model=PermitRead,
    summary="Approved → Issued (issuer at site; signed; receiver acceptance or co-sign)",
    description=SIGNING_DOC + " " + BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def issue_permit(permit_id: uuid.UUID, body: IssueInput, user: CurrentUser, db: DB) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/start",
    response_model=PermitRead,
    summary="Issued → Active: first shift starts (receiver; crew present and briefed)",
    description=BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def start_permit(permit_id: uuid.UUID, body: StartInput, user: CurrentUser, db: DB) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/end-shift",
    response_model=PermitRead,
    summary="End the current shift (Active → Issued for next shift, or → closure)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def end_shift_permit(
    permit_id: uuid.UUID,
    body: EndShiftInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/suspend",
    response_model=PermitRead,
    summary="Suspend a live permit (capability 88; reason from the manual list)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def suspend_permit(
    permit_id: uuid.UUID,
    body: SuspendInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/gas-alarm",
    response_model=PermitRead,
    summary="Record a gas alarm: immediate suspension gas_alarm (anyone on the crew)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def gas_alarm_permit(
    permit_id: uuid.UUID,
    body: GasAlarmInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/revalidate",
    response_model=PermitRead,
    summary="Revalidate for the next day/shift (issuer; signed; per type rule)",
    description=SIGNING_DOC + " " + BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def revalidate_permit(
    permit_id: uuid.UUID,
    body: RevalidateInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/resume",
    response_model=PermitRead,
    summary="Suspended → Active/Issued once the cause is cleared (issuer; signed)",
    description=SIGNING_DOC + " " + BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def resume_permit(permit_id: uuid.UUID, body: ResumeInput, user: CurrentUser, db: DB) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/receiver-acceptance",
    response_model=ReceiverAcceptanceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Receiver records acceptance on their own device (valid step_up_reauth_minutes)",
    description=SIGNING_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_receiver_acceptance(
    permit_id: uuid.UUID,
    body: ReceiverAcceptanceInput,
    user: CurrentUser,
    db: DB,
) -> ReceiverAcceptanceRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/request-closure",
    response_model=PermitRead,
    summary="Receiver requests closure (closure checklist X-items, work status)",
    description=BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def request_permit_closure(
    permit_id: uuid.UUID,
    body: ClosureRequestInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/close",
    response_model=PermitRead,
    summary="Issuer closes after site inspection (signed; CLOSURE_INCOMPLETE)",
    description=SIGNING_DOC + " " + BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def close_permit(permit_id: uuid.UUID, body: CloseInput, user: CurrentUser, db: DB) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/cancel",
    response_model=PermitRead,
    summary="Cancel a permit not yet started or never used (capability 89; reason)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def cancel_permit(permit_id: uuid.UUID, body: CancelInput, user: CurrentUser, db: DB) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/post-expiry-check",
    response_model=PermitRead,
    summary="Record the post-expiry site check of an Expired permit (issuer)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def post_expiry_check_permit(
    permit_id: uuid.UUID,
    body: PostExpiryCheckInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/pause",
    response_model=PermitRead,
    summary="Start a pause (break, prayer, heat, weather) within an Active shift",
    responses=error_responses(401, 403, 404, 409, 422),
)
def start_permit_pause(
    permit_id: uuid.UUID,
    body: PauseStartInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/pause/end",
    response_model=PermitRead,
    summary="End the current pause (gas re-test if the pause exceeded the limit)",
    description=BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def end_permit_pause(
    permit_id: uuid.UUID,
    body: PauseEndInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/hot-work-end",
    response_model=PermitRead,
    summary="Hot work finished: fire watch timer starts (fire_watch_minutes)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_hot_work_end(
    permit_id: uuid.UUID,
    body: HotWorkEndInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/entry-log",
    response_model=EntryLogRead,
    status_code=status.HTTP_201_CREATED,
    summary="Confined-space entry / exit by the attendant",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_entry_log(
    permit_id: uuid.UUID,
    body: EntryLogInput,
    user: CurrentUser,
    db: DB,
) -> EntryLogRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/wind-readings",
    response_model=WindReadingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Wind reading for a lift (over limit → suspension weather)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_wind_reading(
    permit_id: uuid.UUID,
    body: WindReadingInput,
    user: CurrentUser,
    db: DB,
) -> WindReadingRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/excavation-inspections",
    response_model=ExcavationInspectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Competent-person excavation inspection (start of shift, after rain)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_excavation_inspection(
    permit_id: uuid.UUID,
    body: ExcavationInspectionInput,
    user: CurrentUser,
    db: DB,
) -> ExcavationInspectionRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/barrier-surveys",
    response_model=BarrierSurveyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Radiography barrier dose-rate survey (BARRIER_TOO_SMALL)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_barrier_survey(
    permit_id: uuid.UUID,
    body: BarrierSurveyInput,
    user: CurrentUser,
    db: DB,
) -> BarrierSurveyRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/source-return",
    response_model=PermitRead,
    summary="Radiography source returned and stored (needed before closure)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_source_return(
    permit_id: uuid.UUID,
    body: SourceReturnInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/fod-check",
    response_model=PermitFodCheckRead,
    status_code=status.HTTP_201_CREATED,
    summary="Airside FOD check at shift end / closure",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_permit_fod_check(
    permit_id: uuid.UUID,
    body: PermitFodCheckInput,
    user: CurrentUser,
    db: DB,
) -> PermitFodCheckRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/exemptions",
    response_model=ExemptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request an exemption (midday ban, energized work…)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def request_permit_exemption(
    permit_id: uuid.UUID,
    body: ExemptionCreate,
    user: CurrentUser,
    db: DB,
) -> ExemptionRead:
    raise not_implemented()


@router.post(
    "/permit-exemptions/{exemption_id}/decision",
    response_model=ExemptionRead,
    summary="Grant or refuse an exemption (capability 102; signed)",
    description=SIGNING_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def decide_permit_exemption(
    exemption_id: uuid.UUID,
    body: ExemptionDecision,
    user: CurrentUser,
    db: DB,
) -> ExemptionRead:
    raise not_implemented()


@router.get(
    "/permits/{permit_id}/handovers",
    response_model=HandoverList,
    summary="Shift handovers of a permit",
    responses=error_responses(401, 403, 404),
)
def list_permit_handovers(permit_id: uuid.UUID, user: CurrentUser, db: DB) -> HandoverList:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/handovers",
    response_model=HandoverRead,
    status_code=status.HTTP_201_CREATED,
    summary="Outgoing receiver offers a handover (HANDOVER_LIMIT, HANDOVER_TOO_EARLY)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_permit_handover(
    permit_id: uuid.UUID,
    body: HandoverCreate,
    user: CurrentUser,
    db: DB,
) -> HandoverRead:
    raise not_implemented()


@router.post(
    "/permit-handovers/{handover_id}/accept",
    response_model=PermitRead,
    summary="Incoming receiver accepts (signed; issuer co-sign if required)",
    description=SIGNING_DOC + " " + BLOCKED_DOC,
    responses=error_responses(401, 403, 404, 409, 422),
)
def accept_permit_handover(
    handover_id: uuid.UUID,
    body: HandoverAcceptInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.get(
    "/permits/{permit_id}/shifts",
    response_model=ShiftList,
    summary="Shifts of a permit with pauses",
    responses=error_responses(401, 403, 404),
)
def list_permit_shifts(permit_id: uuid.UUID, user: CurrentUser, db: DB) -> ShiftList:
    raise not_implemented()


@router.get(
    "/permits/{permit_id}/suspensions",
    response_model=SuspensionList,
    summary="Suspensions of a permit",
    responses=error_responses(401, 403, 404),
)
def list_permit_suspensions(permit_id: uuid.UUID, user: CurrentUser, db: DB) -> SuspensionList:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/permit-suspensions",
    response_model=SuspensionPage,
    summary="Suspension log of a project (K-65 drill-down)",
    responses=error_responses(401, 403, 404, 422),
)
def list_project_permit_suspensions(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    reason: Annotated[list[StatusReason] | None, Query()] = None,
    work_type: Annotated[list[PermitType] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    zone_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    open_only: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
) -> SuspensionPage:
    raise not_implemented()


@router.get(
    "/permits/{permit_id}/readiness",
    response_model=PermitReadiness,
    summary="What would block an action now (blockers in list B order, warnings)",
    responses=error_responses(401, 403, 404, 422),
)
def get_permit_readiness(
    permit_id: uuid.UUID,
    action: PermitAction,
    user: CurrentUser,
    db: DB,
) -> PermitReadiness:
    raise not_implemented()


@router.get(
    "/permits/{permit_id}/print",
    response_model=PermitPrintRead,
    summary="Print data (A4 EN/AR, QR HSE2:PT:…); Issued or later",
    responses=error_responses(401, 403, 404, 409),
)
def get_permit_print(permit_id: uuid.UUID, user: CurrentUser, db: DB) -> PermitPrintRead:
    raise not_implemented()


@router.get(
    "/permits/{permit_id}/closure-pack",
    response_model=ClosurePackRead,
    summary="Closure pack of a Closed / Expired / Cancelled permit",
    responses=error_responses(401, 403, 404, 409),
)
def get_permit_closure_pack(permit_id: uuid.UUID, user: CurrentUser, db: DB) -> ClosurePackRead:
    raise not_implemented()


@router.post(
    "/permits/{permit_id}/copy",
    response_model=PermitRead,
    status_code=status.HTTP_201_CREATED,
    summary="Copy as a new Draft (no signatures, gas tests, isolations)",
    responses=error_responses(401, 403, 404, 422),
)
def copy_permit(
    permit_id: uuid.UUID,
    body: PermitCopyInput,
    user: CurrentUser,
    db: DB,
) -> PermitRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/ptw-board",
    response_model=PtwBoardResponse,
    summary="Live permit board by zone (capability 82)",
    responses=error_responses(401, 403, 404, 422),
)
def get_ptw_board(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    site_id: uuid.UUID | None = None,
    zone_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    work_type: Annotated[list[PermitType] | None, Query()] = None,
    include_planned_hours: Annotated[int, Query(ge=0, le=72)] = 12,
) -> PtwBoardResponse:
    raise not_implemented()


@router.get(
    "/incidents/{incident_id}/permit-suggestions",
    response_model=IncidentPermitSuggestions,
    summary="Permits live at the incident's place and time (link via investigation ptw_ids)",
    responses=error_responses(401, 403, 404),
)
def get_incident_permit_suggestions(
    incident_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
) -> IncidentPermitSuggestions:
    raise not_implemented()
