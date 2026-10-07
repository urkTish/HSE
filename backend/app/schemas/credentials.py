"""Common credential lifecycle: suspension, reinstatement, revocation, return and loss
(spec 2-access-permits §3.18, §4.5, §4.9, §5.9). Applies to induction records, airport passes,
ADPs, AVPs and access cards through /credentials/{kind}/{id}/…"""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import (
    CredentialKind,
    CredentialReason,
    CustodyStatus,
    InductionStatus,
    LimitingFactor,
    QrTokenStatus,
    ValidityStatus,
)
from app.schemas.access_common import CredentialEventRead, CredentialSuspension, WorkerRef
from app.schemas.common import ApiModel, Page, StrictInput
from app.schemas.hse_common import EngagementRef, UserRef

REASON_TEXT = "≥ 10 characters (LC-4). P3 hint: no medical or criminal details."


class SuspendRequest(StrictInput):
    """Holders of capability 57 only *raise* a suspension (lifts automatically after
    raised_suspension_max_hours unless confirmed, LC-3); holders of 58 (52 for inductions)
    suspend with a confirmed suspension. Dependency reason codes (dependency_invalid,
    id_expired, licence_expired, vehicle_document_expired) are system-only → 422."""

    reason_code: CredentialReason
    reason_text: str = Field(min_length=10, max_length=500, description=REASON_TEXT)


class ConfirmSuspensionRequest(StrictInput):
    """Confirm a raised suspension (capability 58; inductions 52)."""

    reason_text: str = Field(min_length=10, max_length=500, description=REASON_TEXT)


class ReinstateRequest(StrictInput):
    """Lift manual suspensions (capability 58). System suspensions lift automatically (409
    SYSTEM_SUSPENSION); DP-8 points suspensions only after suspension_end (422
    SUSPENSION_PERIOD_RUNNING). Inductions: only if valid_until ≥ today."""

    reason_code: CredentialReason
    reason_text: str = Field(min_length=10, max_length=500, description=REASON_TEXT)


class RevokeRequest(StrictInput):
    """Terminal (LC-5); custody → return_due (passes, ADPs, AVPs). Capability 58; inductions 52
    (re-induction required)."""

    reason_code: CredentialReason
    reason_text: str = Field(min_length=10, max_length=500, description=REASON_TEXT)


class ReturnRequest(StrictInput):
    """return_due → returned (capability 59): returned_at ≤ now, received_by = the caller.
    Late when local date(returned_at) > return_due_on (LC-11)."""

    returned_at: datetime | None = Field(default=None, description="Default now.")
    notes: str | None = Field(default=None, max_length=300)


class LossReportRequest(StrictInput):
    """held/return_due → lost (capability 59; terminal). Rotates the access-card token or marks
    the pass/ADP/AVP lost; authority_notified_at must follow within lost_report_hours (LC-12)."""

    lost_reported_at: datetime | None = Field(default=None, description="Default now.")
    authority_notified_at: datetime | None = None
    reason_code: CredentialReason = CredentialReason.lost_stolen
    reason_text: str = Field(min_length=10, max_length=500, description=REASON_TEXT)


class AuthorityNotifiedRequest(StrictInput):
    authority_notified_at: datetime


class CredentialState(ApiModel):
    """Result of every lifecycle call: the credential's validity/custody after the action."""

    kind: CredentialKind
    id: uuid.UUID
    number: str = Field(examples=["ANIA-AP-26-01877", "IND-ANIA-EXP-2026-03117"])
    worker: WorkerRef | None
    vehicle_no: str | None
    engagement: EngagementRef | None
    validity_status: ValidityStatus | None = Field(description="Passes, ADPs, AVPs.")
    induction_status: InductionStatus | None = Field(description="Induction records.")
    token_status: QrTokenStatus | None = Field(description="Access cards.")
    effective_valid_until: date | None
    limiting_factor: LimitingFactor | None
    custody_status: CustodyStatus | None
    return_due_on: date | None
    returned_at: datetime | None
    received_by: UserRef | None
    lost_reported_at: datetime | None
    authority_notified_at: datetime | None
    open_suspensions: list[CredentialSuspension]
    events: list[CredentialEventRead] = Field(description="Latest first.")


class CredentialEventPage(Page[CredentialEventRead]):
    pass
