"""Incident follow-up: rule profile, settings, notification requirements, packs, submissions, band
and action panel (spec 6f-incident-followup §3.1-§3.5, §3.10, §4.1-§4.3, NR, PK, SB, §8)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.followup_enums import FuPackStatus, FuRequirementStatus, FuStage
from app.core.hse_enums import ExternalBody
from app.schemas.attachments import SignedUrlRead
from app.schemas.followup import (
    FuActionPanel,
    FuBand,
    FuPackCreate,
    FuPackPage,
    FuPackRead,
    FuPackTransition,
    FuPackUpdate,
    FuReference,
    FuRequirementPage,
    FuRequirementRead,
    FuRuleCreate,
    FuRuleList,
    FuRuleRead,
    FuRuleUpdate,
    FuSettingsRead,
    FuSettingsUpdate,
    FuSubmissionAck,
    FuSubmissionCreate,
    FuSubmissionPage,
    FuSubmissionRead,
    FuSubmissionUpdate,
    FuSubmissionVoid,
    FuWaiverRequest,
)
from app.services.followup import board, config, packs, requirements, submissions

router = APIRouter(tags=["incident-followup"])


@router.get(
    "/followup-reference",
    response_model=FuReference,
    summary="6f reference lists with EN/AR labels (§3.11)",
    responses=error_responses(401),
)
def get_followup_reference(user: CurrentUser, db: DB) -> FuReference:
    return config.reference(db, user)


@router.get(
    "/projects/{project_id}/followup-settings",
    response_model=FuSettingsRead,
    summary="6f project settings, client recipients and body directory (§3.2, §3.10; 215)",
    responses=error_responses(401, 403, 404),
)
def get_followup_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> FuSettingsRead:
    return config.get_settings(db, user, project_id)


@router.patch(
    "/projects/{project_id}/followup-settings",
    response_model=FuSettingsRead,
    summary="Edit 6f settings (218, HSE Manager; tighten only → 422 SETTING_LOOSENING)",
    responses=error_responses(401, 403, 404, 422),
)
def update_followup_settings(
    project_id: uuid.UUID, body: FuSettingsUpdate, user: CurrentUser, db: DB
) -> FuSettingsRead:
    return config.update_settings(db, user, project_id, body)


@router.get(
    "/projects/{project_id}/notification-rules",
    response_model=FuRuleList,
    summary="The project's notification rule profile (§3.1; 215)",
    responses=error_responses(401, 403, 404),
)
def list_notification_rules(project_id: uuid.UUID, user: CurrentUser, db: DB) -> FuRuleList:
    return config.list_rules(db, user, project_id)


@router.post(
    "/projects/{project_id}/notification-rules",
    response_model=FuRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a client / PMC rule row (218; 422 CLIENT_RECIPIENT_REQUIRED, NR-9)",
    responses=error_responses(401, 403, 404, 422),
)
def create_notification_rule(
    project_id: uuid.UUID, body: FuRuleCreate, user: CurrentUser, db: DB
) -> FuRuleRead:
    return config.create_rule(db, user, project_id, body)


@router.patch(
    "/notification-rules/{rule_id}",
    response_model=FuRuleRead,
    summary="Edit a rule row (218; statutory rows only tighten → 422 RULE_LOOSENING, NR-3)",
    responses=error_responses(401, 403, 404, 422),
)
def update_notification_rule(
    rule_id: uuid.UUID, body: FuRuleUpdate, user: CurrentUser, db: DB
) -> FuRuleRead:
    return config.update_rule(db, user, rule_id, body)


@router.get(
    "/projects/{project_id}/notification-requirements",
    response_model=FuRequirementPage,
    summary="Notification register (§8.3; 215). Ordered by due time.",
    responses=error_responses(401, 403, 404),
)
def list_notification_requirements(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    body: Annotated[list[ExternalBody] | None, Query()] = None,
    stage: Annotated[list[FuStage] | None, Query()] = None,
    status_: Annotated[list[FuRequirementStatus] | None, Query(alias="status")] = None,
    engagement_id: uuid.UUID | None = None,
    incident_id: uuid.UUID | None = None,
) -> FuRequirementPage:
    return requirements.list_requirements(
        db, user, project_id, body, stage, status_, engagement_id, incident_id, pg.page,
        pg.page_size,
    )  # fmt: skip


@router.get(
    "/notification-requirements/{requirement_id}",
    response_model=FuRequirementRead,
    summary="One requirement (215)",
    responses=error_responses(401, 403, 404),
)
def get_notification_requirement(
    requirement_id: uuid.UUID, user: CurrentUser, db: DB
) -> FuRequirementRead:
    return requirements.read_requirement(db, user, requirement_id)


@router.post(
    "/notification-requirements/{requirement_id}/waive",
    response_model=FuRequirementRead,
    summary="Waive a requirement (218; NR-8, 422 WAIVER_EVIDENCE_REQUIRED)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def waive_notification_requirement(
    requirement_id: uuid.UUID, body: FuWaiverRequest, user: CurrentUser, db: DB
) -> FuRequirementRead:
    return requirements.waive(db, user, requirement_id, body)


@router.post(
    "/notification-requirements/{requirement_id}/packs",
    response_model=FuPackRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate (or regenerate) the pack of a requirement (216; PK-1…PK-5)",
    description="Identity field sets need 29 (+30 for medical) → else 403; CLIENT-FINAL needs the "
    "investigation approved (422 INVESTIGATION_NOT_APPROVED); names in the narrative → 422 "
    "IDENTITY_IN_TEXT. Writes `sensitive_field_read` and an `export` audit row (purpose = body).",
    responses=error_responses(401, 403, 404, 409, 422),
)
def generate_notification_pack(
    requirement_id: uuid.UUID, body: FuPackCreate, user: CurrentUser, db: DB
) -> FuPackRead:
    return packs.generate(db, user, requirement_id, body)


@router.get(
    "/projects/{project_id}/notification-packs",
    response_model=FuPackPage,
    summary="Pack register (215 without Viewer / Client; identity content only with 29)",
    responses=error_responses(401, 403, 404),
)
def list_notification_packs(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[FuPackStatus] | None, Query(alias="status")] = None,
    requirement_id: uuid.UUID | None = None,
) -> FuPackPage:
    return packs.list_packs(db, user, project_id, status_, requirement_id, pg.page, pg.page_size)


@router.get(
    "/notification-packs/{pack_id}",
    response_model=FuPackRead,
    summary="One pack (PK-2 'incident changed since generation')",
    responses=error_responses(401, 403, 404),
)
def get_notification_pack(pack_id: uuid.UUID, user: CurrentUser, db: DB) -> FuPackRead:
    return packs.read_pack(db, user, pack_id)


@router.patch(
    "/notification-packs/{pack_id}",
    response_model=FuPackRead,
    summary="Edit a Draft pack (216; Submitted → 409 PACK_IMMUTABLE)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_notification_pack(
    pack_id: uuid.UUID, body: FuPackUpdate, user: CurrentUser, db: DB
) -> FuPackRead:
    return packs.update_pack(db, user, pack_id, body)


@router.post(
    "/notification-packs/{pack_id}/transitions",
    response_model=FuPackRead,
    summary="Approve (file rendered) or return to Draft (217; PK-6)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_notification_pack(
    pack_id: uuid.UUID, body: FuPackTransition, user: CurrentUser, db: DB
) -> FuPackRead:
    return packs.transition_pack(db, user, pack_id, body)


@router.get(
    "/notification-packs/{pack_id}/file-url",
    response_model=SignedUrlRead,
    summary="Signed URL of the rendered pack (identity packs ≤ 5 min; audited, P6f-4)",
    responses=error_responses(401, 403, 404, 409),
)
def get_notification_pack_file_url(pack_id: uuid.UUID, user: CurrentUser, db: DB) -> SignedUrlRead:
    return packs.file_url(db, user, pack_id)


@router.post(
    "/notification-requirements/{requirement_id}/submissions",
    response_model=FuSubmissionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a submission (216; SB-1…SB-4)",
    description="422 PACK_NOT_APPROVED, CHANNEL_NOT_ALLOWED, EVIDENCE_REQUIRED, "
    "SUBMITTED_AT_INVALID.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def record_notification_submission(
    requirement_id: uuid.UUID, body: FuSubmissionCreate, user: CurrentUser, db: DB
) -> FuSubmissionRead:
    return submissions.record(db, user, requirement_id, body)


@router.get(
    "/projects/{project_id}/notification-submissions",
    response_model=FuSubmissionPage,
    summary="Submissions (215; Viewer / Client without evidence files)",
    responses=error_responses(401, 403, 404),
)
def list_notification_submissions(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    requirement_id: uuid.UUID | None = None,
) -> FuSubmissionPage:
    return submissions.list_submissions(db, user, project_id, requirement_id, pg.page, pg.page_size)


@router.patch(
    "/notification-submissions/{submission_id}",
    response_model=FuSubmissionRead,
    summary="Edit a submission (recorder, 24 h; then 409 SUBMISSION_LOCKED, SB-5)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_notification_submission(
    submission_id: uuid.UUID, body: FuSubmissionUpdate, user: CurrentUser, db: DB
) -> FuSubmissionRead:
    return submissions.update(db, user, submission_id, body)


@router.post(
    "/notification-submissions/{submission_id}/acknowledge",
    response_model=FuSubmissionRead,
    summary="Record the body's acknowledgement (216)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def acknowledge_notification_submission(
    submission_id: uuid.UUID, body: FuSubmissionAck, user: CurrentUser, db: DB
) -> FuSubmissionRead:
    return submissions.acknowledge(db, user, submission_id, body)


@router.post(
    "/notification-submissions/{submission_id}/void",
    response_model=FuSubmissionRead,
    summary="Void a submission (217, reason ≥ 20 chars; the requirement returns to due / overdue)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_notification_submission(
    submission_id: uuid.UUID, body: FuSubmissionVoid, user: CurrentUser, db: DB
) -> FuSubmissionRead:
    return submissions.void(db, user, submission_id, body)


@router.get(
    "/projects/{project_id}/followup-band",
    response_model=FuBand,
    summary="Follow-up band (§8.1 item 2; 215)",
    responses=error_responses(401, 403, 404),
)
def get_followup_band(project_id: uuid.UUID, user: CurrentUser, db: DB) -> FuBand:
    return board.band(db, user, project_id)


@router.get(
    "/projects/{project_id}/followup-action-panel",
    response_model=FuActionPanel,
    summary="Follow-up action-panel items (§8.2; 215)",
    responses=error_responses(401, 403, 404),
)
def get_followup_action_panel(project_id: uuid.UUID, user: CurrentUser, db: DB) -> FuActionPanel:
    return board.action_panel(db, user, project_id)
