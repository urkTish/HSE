"""Projects and project settings (spec §3.1, §3.9, §4.1)."""

import uuid
from datetime import date, datetime

from pydantic import Field, field_validator, model_validator

from app.core.enums import (
    DateFormatEn,
    DigitStyle,
    HijriCalendar,
    KpiBaseHours,
    Language,
    ProjectStatus,
    ProjectTimezone,
    ProjectType,
    WeekStart,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps, has_arabic

PROJECT_CODE = r"^[A-Z0-9-]{3,12}$"
ICAO = r"^[A-Z]{4}$"


def _check_ar(v: str | None) -> str | None:
    if v is not None and not has_arabic(v):
        raise ValueError("must contain Arabic script")
    return v


class ProjectCreate(StrictInput):
    code: str = Field(pattern=PROJECT_CODE, description="Unique, e.g. ANIA-EXP. Immutable.")
    name_en: str = Field(min_length=1, max_length=150)
    name_ar: str = Field(min_length=1, max_length=150, description="Must contain Arabic script.")
    project_type: ProjectType
    client_name_en: str = Field(min_length=1, max_length=150)
    client_name_ar: str = Field(min_length=1, max_length=150)
    city: str = Field(min_length=1, max_length=80)
    start_date: date
    planned_end_date: date | None = None
    airport_icao: str | None = Field(
        default=None,
        pattern=ICAO,
        description="Required iff project_type = airport; Saudi codes start with OE.",
    )

    _ar = field_validator("name_ar")(_check_ar)

    @model_validator(mode="after")
    def _rules(self) -> "ProjectCreate":
        if self.planned_end_date and self.planned_end_date < self.start_date:
            raise ValueError("planned_end_date must be on or after start_date")
        if self.project_type == ProjectType.airport and not self.airport_icao:
            raise ValueError("airport_icao is required for airport projects")
        if self.project_type != ProjectType.airport and self.airport_icao:
            raise ValueError("airport_icao is only allowed for airport projects")
        return self


class ProjectUpdate(PatchInput):
    """Partial update. Rejected with 409 PROJECT_CLOSED when the project is closed."""

    non_nullable = frozenset(
        {
            "name_en",
            "name_ar",
            "project_type",
            "client_name_en",
            "client_name_ar",
            "city",
            "start_date",
        }
    )

    name_en: str | None = Field(default=None, min_length=1, max_length=150)
    name_ar: str | None = Field(default=None, min_length=1, max_length=150)
    project_type: ProjectType | None = None
    client_name_en: str | None = Field(default=None, min_length=1, max_length=150)
    client_name_ar: str | None = Field(default=None, min_length=1, max_length=150)
    city: str | None = Field(default=None, min_length=1, max_length=80)
    start_date: date | None = None
    planned_end_date: date | None = None
    airport_icao: str | None = Field(default=None, pattern=ICAO)

    _ar = field_validator("name_ar")(_check_ar)


class ProjectRead(Timestamps):
    id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    project_type: ProjectType
    is_airport: bool = Field(description="Derived: project_type = airport.")
    client_name_en: str
    client_name_ar: str
    city: str
    start_date: date
    planned_end_date: date | None
    status: ProjectStatus
    status_reason: str | None = Field(description="Reason of the last status change, if any.")
    airport_icao: str | None


class ProjectPage(Page[ProjectRead]):
    pass


class ProjectTransitionRequest(StrictInput):
    """Allowed (§4.1): planning→active (≥1 site and settings saved), active→on_hold (reason),
    on_hold→active, active/on_hold→closed (reason), closed→active (reason, reopen)."""

    to_status: ProjectStatus
    reason: str | None = Field(default=None, max_length=500)


class ProjectSettingsRead(ApiModel):
    project_id: uuid.UUID
    ltifr_base_hours: KpiBaseHours = Field(description="LTIFR normalisation base.")
    rate_base_hours: KpiBaseHours = Field(description="Base for TRIR, DART, LTISR, other rates.")
    ltifr_base_label_en: str = Field(examples=["per 1,000,000 h"])
    ltifr_base_label_ar: str = Field(examples=["لكل 1,000,000 ساعة"])
    rate_base_label_en: str = Field(examples=["per 200,000 h"])
    rate_base_label_ar: str
    timezone: ProjectTimezone
    show_hijri: bool
    hijri_calendar: HijriCalendar
    default_language: Language
    week_start: WeekStart
    digits: DigitStyle
    date_format_en: DateFormatEn
    audit_retention_years: int = Field(ge=1, le=10)
    inactive_account_days: int = Field(ge=30, le=365)
    saved_at: datetime | None = Field(
        description="First explicit save by an HSE Manager; required before planning→active."
    )
    updated_at: datetime
    updated_by_user_id: uuid.UUID | None


class ProjectSettingsUpdate(PatchInput):
    """Partial update (HSE Manager only, rule 30). An empty body still marks settings saved."""

    non_nullable = frozenset(
        {
            "ltifr_base_hours",
            "rate_base_hours",
            "timezone",
            "show_hijri",
            "hijri_calendar",
            "default_language",
            "week_start",
            "digits",
            "date_format_en",
            "audit_retention_years",
            "inactive_account_days",
        }
    )

    ltifr_base_hours: KpiBaseHours | None = None
    rate_base_hours: KpiBaseHours | None = None
    timezone: ProjectTimezone | None = None
    show_hijri: bool | None = None
    hijri_calendar: HijriCalendar | None = None
    default_language: Language | None = None
    week_start: WeekStart | None = None
    digits: DigitStyle | None = None
    date_format_en: DateFormatEn | None = None
    audit_retention_years: int | None = Field(default=None, ge=1, le=10)
    inactive_account_days: int | None = Field(default=None, ge=30, le=365)
