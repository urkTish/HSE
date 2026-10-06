"""HSE meetings (spec 1-dashboard §3.9, leading indicator K-39)."""

import uuid
from datetime import date

from pydantic import Field, model_validator

from app.core.hse_enums import MeetingType
from app.schemas.common import Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import EngagementRef


class HseMeetingCreate(StrictInput):
    engagement_id: uuid.UUID | None = None
    meeting_type: MeetingType
    planned_date: date
    held_date: date | None = None
    invited_count: int = Field(ge=0)
    attended_count: int | None = Field(
        default=None, ge=0, description="Required once held; ≤ invited."
    )
    title: str | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def _rules(self) -> "HseMeetingCreate":
        if self.attended_count is not None and self.attended_count > self.invited_count:
            raise ValueError("attended_count must be ≤ invited_count")
        if self.held_date is not None and self.attended_count is None:
            raise ValueError("attended_count is required when held_date is set")
        return self


class HseMeetingUpdate(PatchInput):
    non_nullable = frozenset({"meeting_type", "planned_date", "invited_count"})

    engagement_id: uuid.UUID | None = None
    meeting_type: MeetingType | None = None
    planned_date: date | None = None
    held_date: date | None = None
    invited_count: int | None = Field(default=None, ge=0)
    attended_count: int | None = Field(default=None, ge=0)
    title: str | None = Field(default=None, max_length=150)


class HseMeetingRead(Timestamps):
    id: uuid.UUID
    project_id: uuid.UUID
    engagement: EngagementRef | None
    meeting_type: MeetingType
    title: str | None
    planned_date: date
    held_date: date | None
    invited_count: int
    attended_count: int | None
    has_minutes: bool


class HseMeetingPage(Page[HseMeetingRead]):
    pass
