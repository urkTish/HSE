"""Trainer authorisations per project (spec 5-training §3.3, §4.2, TA-1…TA-6)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.train_enums import (
    TrainerAuthorisationAction,
    TrainerAuthorisationStatus,
    TrainerRole,
)
from app.schemas.access_common import WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import UserRef
from app.schemas.training_common import P5_HINT, TrainingProviderRef


class TrainerAuthorisationCreate(StrictInput):
    """Capability 131. Exactly one of `trainer_user_id` / `trainer_worker_id`; authoriser ≠
    trainer (422 SOD_CONFLICT); provider internal / contractor_internal and every course
    allowed for it (PV-3, 422 PROVIDER_NOT_ACCEPTABLE); `valid_to` ≤ valid_from +
    trainer_authorisation_max_months − 1 day (422 AUTHORISATION_TOO_LONG); evidence for
    high_risk_task / ptw_role / emergency_response courses (422 TRAINER_EVIDENCE_REQUIRED);
    a Contractor HSE Rep trainer only under their own contractor_internal provider (TA-6)."""

    trainer_user_id: uuid.UUID | None = None
    trainer_worker_id: uuid.UUID | None = None
    provider_id: uuid.UUID
    course_codes: list[str] = Field(min_length=1)
    roles: list[TrainerRole] = Field(min_length=1)
    basis: str = Field(min_length=20, max_length=500, description=P5_HINT)
    evidence_attachment_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Owner trainer_authorisation_evidence (PDF ≤ 10 MB)."
    )
    valid_from: date
    valid_to: date


class TrainerAuthorisationUpdate(PatchInput):
    """Active only; same checks as create. Narrowing courses or roles applies at once and
    flags Scheduled sessions (TRAINER_NOT_AUTHORISED)."""

    non_nullable = frozenset({"course_codes", "roles", "basis", "valid_to"})

    course_codes: list[str] | None = Field(default=None, min_length=1)
    roles: list[TrainerRole] | None = Field(default=None, min_length=1)
    basis: str | None = Field(default=None, min_length=20, max_length=500)
    evidence_attachment_ids: list[uuid.UUID] | None = None
    valid_to: date | None = None


class TrainerAuthorisationTransition(StrictInput):
    """§4.2 (capability 131): suspend (reason) / reinstate / withdraw (reason; terminal).
    Expired is set by the job only."""

    action: TrainerAuthorisationAction
    reason: str | None = Field(default=None, max_length=500, description=P5_HINT)


class TrainerAuthorisationRead(ApiModel):
    """Personal data (P5-1); names of worker trainers only with capability 46."""

    id: uuid.UUID
    authorisation_no: str = Field(examples=["TA-ANIA-EXP-0003"])
    project_id: uuid.UUID
    trainer_user: UserRef | None
    trainer_worker: WorkerRef | None
    provider: TrainingProviderRef
    course_codes: list[str]
    roles: list[TrainerRole]
    basis: str
    evidence_attachment_ids: list[uuid.UUID]
    valid_from: date
    valid_to: date
    days_left: int
    status: TrainerAuthorisationStatus
    status_reason: str | None
    authorised_by: UserRef
    authorised_at: datetime
    scheduled_sessions_affected: int = Field(
        description="Scheduled sessions whose trainer would no longer be authorised."
    )
    created_at: datetime
    updated_at: datetime


class TrainerAuthorisationPage(Page[TrainerAuthorisationRead]):
    pass
