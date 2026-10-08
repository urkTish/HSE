"""Fitness holds and referrals (spec 6a-occupational-health §3.7, §3.8, §4.4, §4.5, FH, RF)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.med_enums import HoldStatus, ReferralStatus
from app.schemas.medical import (
    FitnessHoldCancel,
    FitnessHoldCreate,
    FitnessHoldPage,
    FitnessHoldRead,
    FitnessReferralCancel,
    FitnessReferralCreate,
    FitnessReferralPage,
    FitnessReferralRead,
)
from app.services.med import holds

router = APIRouter(tags=["fitness-holds"])


@router.get(
    "/projects/{project_id}/fitness-holds",
    response_model=FitnessHoldPage,
    response_model_exclude_unset=True,
    summary="Holds register (capability 156; reasons tier 3; C scope)",
    responses=error_responses(401, 403, 404, 422),
)
def list_fitness_holds(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[HoldStatus] | None, Query(alias="status")] = None,
    worker_id: uuid.UUID | None = None,
    with_work_during_hold: bool | None = None,
) -> FitnessHoldPage:
    return holds.list_holds(
        db, user, project_id, pg.page, pg.page_size, status_, worker_id, with_work_during_hold
    )


@router.post(
    "/projects/{project_id}/fitness-holds",
    response_model=FitnessHoldRead,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_unset=True,
    summary="Place a manual hold (capability 159; reason_text ≥ 20 chars, FH-1c)",
    responses=error_responses(401, 403, 404, 422),
)
def create_fitness_hold(
    project_id: uuid.UUID, body: FitnessHoldCreate, user: CurrentUser, db: DB
) -> FitnessHoldRead:
    return holds.create_manual(db, user, project_id, body)


@router.get(
    "/fitness-holds/{hold_id}",
    response_model=FitnessHoldRead,
    response_model_exclude_unset=True,
    summary="One hold (tier 2: existence and dates; tier 3: reason and source)",
    responses=error_responses(401, 403, 404),
)
def get_fitness_hold(hold_id: uuid.UUID, user: CurrentUser, db: DB) -> FitnessHoldRead:
    return holds.read_hold(db, user, hold_id)


@router.post(
    "/fitness-holds/{hold_id}/cancel",
    response_model=FitnessHoldRead,
    response_model_exclude_unset=True,
    summary="Cancel a hold (capability 159, OH Practitioner / HSE Manager; reason ≥ 20 chars)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def cancel_fitness_hold(
    hold_id: uuid.UUID, body: FitnessHoldCancel, user: CurrentUser, db: DB
) -> FitnessHoldRead:
    return holds.cancel_hold(db, user, hold_id, body)


@router.post(
    "/fitness-holds/{hold_id}/release",
    response_model=FitnessHoldRead,
    summary="Always 422 HOLD_RELEASE_REQUIRES_ASSESSMENT: a hold is released only by an "
    "accepted return-to-work / referral assessment (FH-3)",
    responses=error_responses(401, 403, 404, 422),
)
def release_fitness_hold(hold_id: uuid.UUID, user: CurrentUser, db: DB) -> FitnessHoldRead:
    return holds.release_hold(db, user, hold_id)


@router.get(
    "/projects/{project_id}/fitness-referrals",
    response_model=FitnessReferralPage,
    response_model_exclude_unset=True,
    summary="Referrals register (capability 156, or the referrer's own; reasons tier 3)",
    responses=error_responses(401, 403, 404, 422),
)
def list_fitness_referrals(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[ReferralStatus] | None, Query(alias="status")] = None,
    overdue: bool | None = None,
    worker_id: uuid.UUID | None = None,
) -> FitnessReferralPage:
    return holds.list_referrals(
        db, user, project_id, pg.page, pg.page_size, status_, overdue, worker_id
    )


@router.post(
    "/projects/{project_id}/fitness-referrals",
    response_model=FitnessReferralRead,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_unset=True,
    summary="Raise a referral (capability 158 within RF-2 scope); remove_from_work creates a "
    "hold (FH-1b); heat_illness_episode warns INCIDENT_RECORD_EXPECTED (RF-6)",
    responses=error_responses(401, 403, 404, 422),
)
def create_fitness_referral(
    project_id: uuid.UUID, body: FitnessReferralCreate, user: CurrentUser, db: DB
) -> FitnessReferralRead:
    return holds.create_referral(db, user, project_id, body)


@router.get(
    "/fitness-referrals/{referral_id}",
    response_model=FitnessReferralRead,
    response_model_exclude_unset=True,
    summary="One referral",
    responses=error_responses(401, 403, 404),
)
def get_fitness_referral(referral_id: uuid.UUID, user: CurrentUser, db: DB) -> FitnessReferralRead:
    return holds.read_referral(db, user, referral_id)


@router.post(
    "/fitness-referrals/{referral_id}/cancel",
    response_model=FitnessReferralRead,
    response_model_exclude_unset=True,
    summary="Cancel a referral (referrer before due_at when not removed from work; otherwise "
    "capability 159; reason ≥ 20 chars, RF-5)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def cancel_fitness_referral(
    referral_id: uuid.UUID, body: FitnessReferralCancel, user: CurrentUser, db: DB
) -> FitnessReferralRead:
    return holds.cancel_referral(db, user, referral_id, body)
