"""Toolbox talks and briefing campaigns (spec 6d-field-assurance §3.11–§3.13, §4.5, §4.6,
TBT-1…TBT-10, CMP-1…CMP-4): talks with named attendance (card scan or list), signatures, language
check, suggested topics and mandatory briefing campaigns."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.field_enums import CampaignStatus, TalkStatus
from app.schemas.field import (
    AttendanceAdd,
    CampaignCreate,
    CampaignPage,
    CampaignRead,
    CampaignTransition,
    CampaignUpdate,
    FieldVoid,
    SuggestionList,
    TalkCreate,
    TalkPage,
    TalkRead,
)
from app.services.field import campaigns, talks

router = APIRouter(tags=["field-toolbox"])


@router.get(
    "/projects/{project_id}/toolbox-talks",
    response_model=TalkPage,
    summary="Toolbox talk register (200; names per 199)",
    responses=error_responses(401, 403, 404),
)
def list_toolbox_talks(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    site_id: uuid.UUID | None = None,
    host_engagement_id: uuid.UUID | None = None,
    status_: Annotated[list[TalkStatus] | None, Query(alias="status")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    topic_code: str | None = None,
) -> TalkPage:
    return talks.list_talks(
        db, user, project_id, site_id, host_engagement_id, status_, date_from, date_to,
        topic_code, pg.page, pg.page_size,
    )  # fmt: skip


@router.post(
    "/projects/{project_id}/toolbox-talks",
    response_model=TalkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a toolbox talk with attendance (198; TBT-3…TBT-7)",
    description="Idempotent on client_uuid. Rows with an unknown or revoked scanned token are "
    "rejected (TOKEN_UNKNOWN, listed in rejected_rows) and the talk is saved. Warnings: "
    "TBT_SHORT, LANGUAGE_MISMATCH, TOPIC_REVIEW_OVERDUE, POSSIBLE_ID_NUMBER.",
    responses=error_responses(401, 403, 404, 422),
)
def create_toolbox_talk(
    project_id: uuid.UUID, body: TalkCreate, user: CurrentUser, db: DB
) -> TalkRead:
    return talks.create_talk(db, user, project_id, body)


@router.get(
    "/toolbox-talks/{talk_id}",
    response_model=TalkRead,
    summary="One toolbox talk",
    responses=error_responses(401, 403, 404),
)
def get_toolbox_talk(talk_id: uuid.UUID, user: CurrentUser, db: DB) -> TalkRead:
    return talks.read_talk(db, user, talk_id)


@router.post(
    "/toolbox-talks/{talk_id}/attendance",
    response_model=TalkRead,
    summary="Add attendance rows until Locked (198; 409 TALK_LOCKED)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def add_toolbox_attendance(
    talk_id: uuid.UUID, body: AttendanceAdd, user: CurrentUser, db: DB
) -> TalkRead:
    return talks.add_attendance(db, user, talk_id, body)


@router.delete(
    "/toolbox-talks/{talk_id}/attendance/{row_id}",
    response_model=TalkRead,
    summary="Remove an attendance row until Locked (198)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def remove_toolbox_attendance(
    talk_id: uuid.UUID, row_id: uuid.UUID, user: CurrentUser, db: DB
) -> TalkRead:
    return talks.remove_attendance(db, user, talk_id, row_id)


@router.post(
    "/toolbox-talks/{talk_id}/void",
    response_model=TalkRead,
    summary="Void a talk (201, reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def void_toolbox_talk(talk_id: uuid.UUID, body: FieldVoid, user: CurrentUser, db: DB) -> TalkRead:
    return talks.void_talk(db, user, talk_id, body)


@router.get(
    "/projects/{project_id}/toolbox-suggestions",
    response_model=SuggestionList,
    summary="Suggested topics for a host engagement on a site (TBT-9 order)",
    responses=error_responses(401, 403, 404),
)
def get_toolbox_suggestions(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    site_id: uuid.UUID,
    host_engagement_id: uuid.UUID,
) -> SuggestionList:
    return talks.suggestions(db, user, project_id, site_id, host_engagement_id)


# ---- campaigns -----------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/briefing-campaigns",
    response_model=CampaignPage,
    summary="Briefing campaign register with pairs (200)",
    responses=error_responses(401, 403, 404),
)
def list_briefing_campaigns(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[CampaignStatus] | None, Query(alias="status")] = None,
) -> CampaignPage:
    return campaigns.list_campaigns(db, user, project_id, status_, pg.page, pg.page_size)


@router.post(
    "/projects/{project_id}/briefing-campaigns",
    response_model=CampaignRead,
    status_code=status.HTTP_201_CREATED,
    summary="Draft a briefing campaign (197; CMP-1)",
    responses=error_responses(401, 403, 404, 422),
)
def create_briefing_campaign(
    project_id: uuid.UUID, body: CampaignCreate, user: CurrentUser, db: DB
) -> CampaignRead:
    return campaigns.create_campaign(db, user, project_id, body)


@router.get(
    "/briefing-campaigns/{campaign_id}",
    response_model=CampaignRead,
    summary="One campaign with pairs met / unmet (CMP-3)",
    responses=error_responses(401, 403, 404),
)
def get_briefing_campaign(campaign_id: uuid.UUID, user: CurrentUser, db: DB) -> CampaignRead:
    return campaigns.read_campaign(db, user, campaign_id)


@router.patch(
    "/briefing-campaigns/{campaign_id}",
    response_model=CampaignRead,
    summary="Edit a Draft campaign (197)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_briefing_campaign(
    campaign_id: uuid.UUID, body: CampaignUpdate, user: CurrentUser, db: DB
) -> CampaignRead:
    return campaigns.update_campaign(db, user, campaign_id, body)


@router.post(
    "/briefing-campaigns/{campaign_id}/transitions",
    response_model=CampaignRead,
    summary="Issue (pairs fixed, CMP-2) or cancel a campaign (197)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_briefing_campaign(
    campaign_id: uuid.UUID, body: CampaignTransition, user: CurrentUser, db: DB
) -> CampaignRead:
    return campaigns.transition_campaign(db, user, campaign_id, body)
