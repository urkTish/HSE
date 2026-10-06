"""Workforce daily returns, month locks and CSV/Excel import (spec 1-dashboard §3.1, §3.2, §4.1,
§5.1)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, model_validator

from app.core.hse_enums import (
    ImportCode,
    ImportMode,
    ImportRowStatus,
    ImportStatus,
    MonthLockStatus,
    Shift,
    TierClass,
    WorkforceSource,
    WorkforceStatus,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import (
    ApiWarning,
    EngagementRef,
    Hours8,
    ManHours,
    SiteRef,
    UserRef,
    ZoneRef,
)

MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"
REMARKS_HINT = "Do not enter names, ID or medical details (P3)."


class WorkforceReturnCreate(StrictInput):
    """One row per work_date × site × zone (optional) × engagement × shift (rule W-1).

    Server-side validation (409/422): uniqueness `DUPLICATE_RETURN`; work_date ≤ today (project
    tz) and ≥ project start; engagement on the project, site in engagement.site_ids, work_date
    within mobilisation–demobilisation (`OUTSIDE_MOBILISATION`); man_hours ≤ headcount ×
    max_hours_per_person_day; locked month `PERIOD_LOCKED`."""

    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    engagement_id: uuid.UUID
    work_date: date = Field(description="Local date (project timezone).")
    shift: Shift
    no_work: bool = Field(default=False, description="If true headcount and man_hours must be 0.")
    headcount: int = Field(ge=0, le=20_000)
    man_hours: ManHours = Field(description="Row total Σ headcount × hours, 2 dp.")
    toolbox_talks: int = Field(default=0, ge=0)
    toolbox_attendees: int = Field(default=0, ge=0, description="≤ headcount × 2.")
    inductions: int = Field(default=0, ge=0)
    training_hours: Hours8 = Field(default=Decimal(0), description="≤ man_hours.")
    remarks: str | None = Field(default=None, max_length=500, description=REMARKS_HINT)
    submit: bool = Field(
        default=False, description="true = create directly as submitted (Draft → Submitted)."
    )

    @model_validator(mode="after")
    def _rules(self) -> "WorkforceReturnCreate":
        if self.no_work and (self.headcount or self.man_hours):
            raise ValueError("no_work = true requires headcount = 0 and man_hours = 0")
        if self.headcount == 0 and self.man_hours > 0:
            raise ValueError("headcount = 0 requires man_hours = 0")
        if self.toolbox_attendees > self.headcount * 2:
            raise ValueError("toolbox_attendees must be ≤ headcount × 2")
        if self.training_hours > self.man_hours:
            raise ValueError("training_hours must be ≤ man_hours")
        return self


class WorkforceReturnUpdate(PatchInput):
    """Edit a draft or submitted row (status unchanged; same validations as create). Verified
    rows → 409 INVALID_TRANSITION (move back to submitted first); locked rows → 409
    PERIOD_LOCKED (HSE Manager unlocks the row first)."""

    non_nullable = frozenset(
        {"headcount", "man_hours", "no_work", "shift", "toolbox_talks", "inductions"}
    )

    zone_id: uuid.UUID | None = None
    shift: Shift | None = None
    no_work: bool | None = None
    headcount: int | None = Field(default=None, ge=0, le=20_000)
    man_hours: ManHours | None = None
    toolbox_talks: int | None = Field(default=None, ge=0)
    toolbox_attendees: int | None = Field(default=None, ge=0)
    inductions: int | None = Field(default=None, ge=0)
    training_hours: Hours8 | None = None
    remarks: str | None = Field(default=None, max_length=500, description=REMARKS_HINT)


class WorkforceReturnRead(Timestamps):
    id: uuid.UUID
    project_id: uuid.UUID
    site: SiteRef
    zone: ZoneRef | None
    engagement: EngagementRef
    tier_class: TierClass = Field(description="Derived: tier 1 = direct, ≥ 2 = subcontractor.")
    work_date: date
    shift: Shift
    no_work: bool
    headcount: int
    man_hours: ManHours
    toolbox_talks: int
    toolbox_attendees: int
    inductions: int
    training_hours: Hours8
    remarks: str | None
    source: WorkforceSource
    import_batch_id: uuid.UUID | None
    status: WorkforceStatus
    created_by: UserRef | None
    verified_by: UserRef | None
    verified_at: datetime | None
    warnings: list[ApiWarning] = Field(
        default_factory=list, description="Stored import warnings (W-7) or save-time warnings."
    )


class WorkforceReturnPage(Page[WorkforceReturnRead]):
    pass


class WorkforceTransitionRequest(StrictInput):
    """§4.1: draft→submitted; submitted→draft (creator, HSE Officer); submitted→verified
    (HSE Officer/Manager, verifier ≠ creator → `VERIFIER_IS_CREATOR`); verified→submitted
    (correction, reason); locked→verified (HSE Manager, reason; marks the month restated)."""

    to_status: WorkforceStatus
    reason: str | None = Field(default=None, max_length=500)


class BulkVerifyRequest(StrictInput):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class BulkItemError(ApiModel):
    id: uuid.UUID
    code: str
    message: str
    message_ar: str | None = None


class BulkVerifyResult(ApiModel):
    verified: list[uuid.UUID]
    failed: list[BulkItemError]


class WorkforceMonthRead(ApiModel):
    """Lock state of one project month (§4.1)."""

    project_id: uuid.UUID
    month: str = Field(pattern=MONTH, examples=["2026-08"])
    status: MonthLockStatus
    auto_lock_date: date = Field(description="month_lock_day of the following month.")
    locked_at: datetime | None
    locked_by: UserRef | None
    restated: bool = Field(description="Inputs changed after lock (W-10, I-9).")
    restated_at: datetime | None
    rows_by_status: dict[WorkforceStatus, int]
    man_hours: ManHours = Field(description="Σ man_hours of submitted/verified/locked rows.")


class WorkforceMonthList(ApiModel):
    items: list[WorkforceMonthRead]


class MonthLockRequest(StrictInput):
    reason: str | None = Field(default=None, max_length=500)


class MonthUnlockRequest(StrictInput):
    reason: str = Field(min_length=1, max_length=500)


# ---- import (§3.2, rule W-5) ---------------------------------------------------------------------


class ImportCounts(ApiModel):
    rows_total: int
    rows_ok: int
    rows_warning: int
    rows_error: int
    rows_inserted: int = Field(description="0 until committed.")
    rows_replaced: int = Field(description="0 until committed (upsert mode).")


class ImportIssue(ApiModel):
    code: ImportCode
    column: str | None = None
    message_en: str
    message_ar: str


class ImportRowReport(ApiModel):
    row_no: int = Field(description="1-based data row number (header row excluded).")
    status: ImportRowStatus
    codes: list[ImportCode]
    issues: list[ImportIssue]
    work_date: date | None = None
    site_code: str | None = None
    zone_code: str | None = None
    contractor_code: str | None = None
    shift: Shift | None = None
    action: str | None = Field(
        default=None, description="insert | replace | none (what commit would do / did)."
    )


class WorkforceImportRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    file_name: str
    file_sha256: str
    file_size: int
    mode: ImportMode
    status: ImportStatus
    counts: ImportCounts
    file_issues: list[ImportIssue] = Field(
        description="Whole-file problems (E14 missing column, size/row limits)."
    )
    report: list[ImportRowReport] = Field(
        description="Rows with status warning/error, then ok rows when `include_ok_rows`."
    )
    uploaded_by: UserRef
    created_at: datetime
    expires_at: datetime = Field(description="Commit must happen before this (60 min).")
    committed_at: datetime | None


class WorkforceImportSummary(ApiModel):
    id: uuid.UUID
    file_name: str
    mode: ImportMode
    status: ImportStatus
    counts: ImportCounts
    uploaded_by: UserRef
    created_at: datetime
    committed_at: datetime | None


class WorkforceImportPage(Page[WorkforceImportSummary]):
    pass
