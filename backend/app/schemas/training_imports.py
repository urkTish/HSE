"""Training import batches: CSV/XLSX dry-run → commit valid rows (spec 5-training §3.13, §4.8,
IM5-1…IM5-7). Same lifecycle as Phase 1 §3.2 and Phase 4 cert imports."""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.hse_enums import ImportRowStatus
from app.core.train_enums import (
    TrainingImportCode,
    TrainingImportSource,
    TrainingImportStatus,
    TrainingImportTemplate,
)
from app.schemas.common import ApiModel, Page
from app.schemas.hse_common import UserRef


class TrainingImportCounts(ApiModel):
    rows_total: int
    rows_ok: int
    rows_warning: int
    rows_error: int
    records_created: int = Field(description="training_records: 0 until committed.")
    records_left_draft: int = Field(
        description="0 until committed: rows without a scan in the zip stay Draft (W03, IM5-5)."
    )
    attendance_rows_applied: int = Field(description="session_attendance: 0 until committed.")


class TrainingImportIssue(ApiModel):
    code: TrainingImportCode
    column: str | None = None
    message_en: str
    message_ar: str
    meta: dict[str, str] = Field(
        default_factory=dict,
        description="E.g. {'reason': 'ACCREDITATION_INVALID'} for E03, {'missing': 'FIRST-AID'} "
        "for E11.",
    )


class TrainingImportRowReport(ApiModel):
    """IDs are never echoed (IM5-4): rows show worker_no and the masked ID (WK-4)."""

    row_no: int = Field(description="1-based data row number (header row excluded).")
    status: ImportRowStatus
    codes: list[TrainingImportCode]
    issues: list[TrainingImportIssue]
    worker_no: str | None = None
    id_masked: str | None = None
    course_code: str | None = None
    provider_code: str | None = None
    certificate_no: str | None = None
    day_no: int | None = Field(default=None, description="session_attendance.")
    scan_found: bool | None = Field(default=None, description="Null when no scans_zip.")


class TrainingImportRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    template: TrainingImportTemplate
    source: TrainingImportSource
    session_id: uuid.UUID | None = Field(description="session_attendance only (Delivered).")
    provider_code: str | None = Field(
        description="provider_register_file: the evidence's provider."
    )
    file_name: str
    file_sha256: str
    file_size: int
    sensitive: bool = Field(description="The file has an ID column (IM5-4).")
    scans_zip_name: str | None
    scans_count: int | None
    evidence_file_name: str | None
    evidence_sha256: str | None
    status: TrainingImportStatus
    counts: TrainingImportCounts
    file_issues: list[TrainingImportIssue] = Field(
        description="Whole-file problems (E12 missing column / unparseable, limits)."
    )
    report: list[TrainingImportRowReport]
    uploaded_by: UserRef
    created_at: datetime
    expires_at: datetime = Field(description="Commit before this (60 min).")
    committed_at: datetime | None
    committed_record_ids: list[uuid.UUID] = Field(
        default_factory=list, description="After commit (first 500)."
    )


class TrainingImportSummary(ApiModel):
    id: uuid.UUID
    template: TrainingImportTemplate
    source: TrainingImportSource
    file_name: str
    status: TrainingImportStatus
    counts: TrainingImportCounts
    uploaded_by: UserRef
    created_at: datetime
    committed_at: datetime | None


class TrainingImportPage(Page[TrainingImportSummary]):
    pass
