"""Certificate import batches: CSV/XLSX dry-run → commit valid rows (spec 4-third-party-cert
§3.15, §4.9, IM-1…IM-7). Same lifecycle as Phase 1 §3.2 (workforce import)."""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.cert_enums import (
    CertImportCode,
    CertImportSource,
    CertImportStatus,
    CertImportTemplate,
)
from app.core.hse_enums import ImportRowStatus
from app.schemas.common import ApiModel, Page
from app.schemas.hse_common import UserRef


class CertImportCounts(ApiModel):
    rows_total: int
    rows_ok: int
    rows_warning: int
    rows_error: int
    certificates_valid: int = Field(
        description="Certificates the valid rows form (rows sharing tpi_code + cert_no are one "
        "multi-line equipment certificate, IM-2)."
    )
    items_to_create: int = Field(description="Unknown tags with create_items = Y (IM-2).")
    certificates_created: int = Field(description="0 until committed.")
    certificates_left_draft: int = Field(
        description="0 until committed: rows without a scan in the zip stay Draft (W03, IM-5)."
    )
    items_created: int = Field(description="0 until committed.")


class CertImportIssue(ApiModel):
    code: CertImportCode
    column: str | None = None
    message_en: str
    message_ar: str
    meta: dict[str, str] = Field(
        default_factory=dict, description="E.g. {'reason': 'not_client_approved'} for E04."
    )


class CertImportRowReport(ApiModel):
    """IDs are never echoed (IM-4): rows show worker_no and the masked ID (WK-4)."""

    row_no: int = Field(description="1-based data row number (header row excluded).")
    status: ImportRowStatus
    codes: list[CertImportCode]
    issues: list[CertImportIssue]
    tpi_code: str | None = None
    cert_no: str | None = None
    tag: str | None = Field(default=None, description="Equipment template.")
    category: str | None = Field(default=None, description="Equipment template.")
    worker_no: str | None = Field(default=None, description="Personnel template.")
    id_masked: str | None = Field(default=None, description="Personnel template (WK-4).")
    cert_type: str | None = Field(default=None, description="Personnel template.")
    scan_found: bool | None = Field(default=None, description="Null when no scans_zip.")
    action: str | None = Field(
        default=None,
        description="create_certificate | add_line | create_item_and_certificate | none.",
    )


class CertImportRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    template: CertImportTemplate
    source: CertImportSource
    tpi_code: str | None = Field(description="tpi_register_file: the TPI of the evidence file.")
    file_name: str
    file_sha256: str
    file_size: int
    sensitive: bool = Field(description="The file has an ID column (IM-4).")
    create_items: bool
    scans_zip_name: str | None
    scans_count: int | None
    evidence_file_name: str | None
    evidence_sha256: str | None
    status: CertImportStatus
    counts: CertImportCounts
    file_issues: list[CertImportIssue] = Field(
        description="Whole-file problems (E12 missing column / unparseable, limits)."
    )
    report: list[CertImportRowReport] = Field(
        description="Rows with status warning/error, then ok rows when `include_ok_rows`."
    )
    uploaded_by: UserRef
    created_at: datetime
    expires_at: datetime = Field(description="Commit must happen before this (60 min).")
    committed_at: datetime | None
    committed_certificate_ids: list[uuid.UUID] = Field(
        default_factory=list, description="After commit (first 500)."
    )


class CertImportSummary(ApiModel):
    id: uuid.UUID
    template: CertImportTemplate
    source: CertImportSource
    file_name: str
    status: CertImportStatus
    counts: CertImportCounts
    uploaded_by: UserRef
    created_at: datetime
    committed_at: datetime | None


class CertImportPage(Page[CertImportSummary]):
    pass
