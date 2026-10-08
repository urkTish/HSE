"""Phase 5 project settings, enabling training hooks and the training hours report (spec
5-training §3.16, §4.7, HK5-1, TH-1…TH-9)."""

import uuid
from datetime import date

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.core.errors import error_responses
from app.schemas.cert_config import HookPolicyRead
from app.schemas.training_config import (
    TrainingHooksEnableRequest,
    TrainingHoursReport,
    TrainingSettingsRead,
    TrainingSettingsUpdate,
)
from app.services.train import config as tconfig

router = APIRouter(tags=["training-settings"])


@router.get(
    "/projects/{project_id}/training-settings",
    response_model=TrainingSettingsRead,
    summary="Phase 5 project settings (§3.16; capability 125 to read)",
    responses=error_responses(401, 403, 404),
)
def get_training_settings(project_id: uuid.UUID, user: CurrentUser, db: DB) -> TrainingSettingsRead:
    return tconfig.get_settings(db, user, project_id)


@router.patch(
    "/projects/{project_id}/training-settings",
    response_model=TrainingSettingsRead,
    summary="Edit Phase 5 settings (capability 145, HSE Manager; allowed ranges only; audited)",
    responses=error_responses(401, 403, 404, 422),
)
def update_training_settings(
    project_id: uuid.UUID, body: TrainingSettingsUpdate, user: CurrentUser, db: DB
) -> TrainingSettingsRead:
    return tconfig.update_settings(db, user, project_id, body)


@router.post(
    "/projects/{project_id}/training-hooks/enable",
    response_model=HookPolicyRead,
    summary="Enable training hooks → kind training_course in transition (HK5-1; capability "
    "145; needs training_register_from ≤ today — 422 TRAINING_REGISTER_NOT_LIVE)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def enable_training_hooks(
    project_id: uuid.UUID, body: TrainingHooksEnableRequest, user: CurrentUser, db: DB
) -> HookPolicyRead:
    return tconfig.enable_hooks(db, user, project_id, body)


@router.get(
    "/projects/{project_id}/training-hours",
    response_model=TrainingHoursReport,
    summary="Training hours report per engagement and month: register vs daily returns and "
    "the K-37 source (§8.4, TH-6, TH-7; capability 143)",
    responses=error_responses(401, 403, 404, 422),
)
def get_training_hours_report(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    date_from: date,
    date_to: date,
    engagement_id: uuid.UUID | None = None,
    include_subcontractors: bool = True,
) -> TrainingHoursReport:
    return tconfig.hours_report(
        db, user, project_id, date_from, date_to, engagement_id, include_subcontractors
    )
