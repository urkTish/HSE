"""Worker register and project deployments (spec 2-access-permits §3.1, §3.2, §4.1, §4.2,
§5.1, §5.12)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import (
    AccessCardReissueReason,
    DeploymentStatus,
    InductionStatus,
    QrTokenStatus,
    UnmaskReason,
    ValidityStatus,
    WorkerIdType,
    WorkerLanguage,
    WorkerPersonType,
    WorkerStatus,
)
from app.core.hse_enums import ExportPurpose, Trade
from app.schemas.access_common import MASKED_ID_DOC, QR_PAYLOAD_DOC
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import ApiWarning, EngagementRef, SiteRef, UserRef

ISO2 = r"^[A-Z]{2}$"
NO_SECURITY = "P3 hint: no medical or criminal details."


# ---- deployments --------------------------------------------------------------------------------


class DeploymentFields(StrictInput):
    engagement_id: uuid.UUID | None = Field(
        default=None,
        description="Required iff person_type = contractor_worker; engagement on the project "
        "with an Approved contractor.",
    )
    employee_no: str | None = Field(
        default=None, max_length=20, description="Unique per engagement."
    )
    trade: Trade
    site_ids: list[uuid.UUID] = Field(
        min_length=1, description="⊆ engagement.site_ids (contractor) or project sites."
    )
    mobilised_on: date = Field(description="≥ engagement mobilisation_date.")
    planned_demob_on: date | None = Field(
        default=None, description="≥ mobilised_on; ≤ engagement demobilisation_date if set."
    )


class DeploymentCreate(DeploymentFields):
    """New deployment → status pending_induction (§4.2). One non-demobilised deployment per
    worker per project (409 DEPLOYMENT_EXISTS, WK-10); banned worker → 409 WORKER_BANNED."""

    worker_id: uuid.UUID


class DeploymentUpdate(PatchInput):
    non_nullable = frozenset({"trade", "site_ids", "mobilised_on"})

    employee_no: str | None = Field(default=None, max_length=20)
    trade: Trade | None = None
    site_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    mobilised_on: date | None = None
    planned_demob_on: date | None = None


class DeploymentTransitionRequest(StrictInput):
    """mobilised/pending_induction → demobilised (capability 47): `demobilised_on` (default
    today) — cascades LC-10 (pass + ADP revoked `demobilised`, custody return due, access card
    revoked, WAP crew entries removed). pending_induction → mobilised is system-only (first
    passed general_site induction)."""

    to_status: DeploymentStatus
    demobilised_on: date | None = None
    reason: str | None = Field(default=None, max_length=500)


class InductionBadge(ApiModel):
    course_code: str
    status: InductionStatus
    valid_until: date | None


class CredentialBadge(ApiModel):
    """Compact credential summary for lists (no sensitive data)."""

    kind: str = Field(examples=["airport_pass", "adp"])
    id: uuid.UUID
    number: str = Field(examples=["ANIA-AP-26-01877"])
    validity_status: ValidityStatus
    effective_valid_until: date | None
    detail: str | None = Field(
        default=None, examples=["PERM · red · A, M", "manoeuvring"], description="Category etc."
    )


class AccessCardSummary(ApiModel):
    issued_on: date | None
    reissue_count: int
    token_status: QrTokenStatus | None = Field(description="Null until the first issue (IN-1).")


class DeploymentRead(Timestamps):
    id: uuid.UUID
    worker_id: uuid.UUID
    worker_no: str
    full_name_en: str | None = Field(description="Null for callers without capability 46.")
    full_name_ar: str | None
    project_id: uuid.UUID
    engagement: EngagementRef | None
    employee_no: str | None
    trade: Trade
    sites: list[SiteRef]
    mobilised_on: date
    planned_demob_on: date | None
    demobilised_on: date | None
    status: DeploymentStatus
    access_card: AccessCardSummary
    inductions: list[InductionBadge]
    credentials: list[CredentialBadge]
    warnings: list[ApiWarning] = Field(default_factory=list)


class DeploymentPage(Page[DeploymentRead]):
    pass


class AccessCardRead(ApiModel):
    """Access card to print (capability 47). The token is opaque; no personal data in the QR."""

    deployment_id: uuid.UUID
    worker_no: str
    full_name_en: str
    full_name_ar: str
    employer_short_code: str | None
    photo_attachment_id: uuid.UUID | None
    qr_payload: str = Field(
        pattern=r"^HSE2:AC:[A-Za-z0-9_-]{22}$",
        examples=["HSE2:AC:q8Xb2mJf0Q9nZr4tYc1wKA"],
        description=QR_PAYLOAD_DOC,
    )
    printed_ref: str = Field(examples=["WKR-000002 / ANIA-EXP"])
    issued_on: date
    reissue_count: int
    token_status: QrTokenStatus


class AccessCardReissueRequest(StrictInput):
    """Rotates the token (old one → `rotated`; scans of it return CREDENTIAL_REVOKED or, for a
    loss, CREDENTIAL_LOST — GC-16, LC-12). Loss reports go through
    POST /credentials/access_card/{deployment_id}/loss."""

    reason: AccessCardReissueReason
    reason_text: str | None = Field(default=None, max_length=500)


# ---- workers ------------------------------------------------------------------------------------


class WorkerFields(StrictInput):
    person_type: WorkerPersonType
    full_name_en: str = Field(min_length=1, max_length=120, description="As on the ID.")
    full_name_ar: str = Field(min_length=1, max_length=120, description="Arabic script.")
    id_type: WorkerIdType
    id_number: str = Field(
        min_length=6,
        max_length=15,
        description="iqama ^2\\d{9}$, national_id ^1\\d{9}$ (check digit), gcc_id "
        "^[A-Z0-9]{6,15}$, passport ^[A-Z0-9]{6,9}$. Encrypted at rest; never returned except "
        "by the unmask endpoint.",
    )
    passport_country: str | None = Field(
        default=None, pattern=ISO2, description="Required iff id_type = passport."
    )
    id_expiry_date: date = Field(description="> today at creation (warning only on edit).")
    nationality: str = Field(pattern=ISO2)
    adult_attestation: bool = Field(description="Must be true (WK-6 ADULT_ATTESTATION_REQUIRED).")
    primary_language: WorkerLanguage
    user_id: uuid.UUID | None = Field(default=None, description="Link to a platform user.")


class WorkerCreate(WorkerFields):
    """Create a worker (capability 47). A Contractor HSE Rep must include `deployment` for an
    engagement in their C scope (WK-11). Duplicate ID (blind index) → 409 WORKER_EXISTS with
    `meta.worker_no` / `meta.worker_id` if the caller can see that worker, else 409
    WORKER_EXISTS_OUT_OF_SCOPE with no identifying data (WK-2). The photo is uploaded after
    creation via POST /attachments (owner_type worker_photo)."""

    deployment: "WorkerDeploymentInput | None" = Field(
        default=None, description="Optional first deployment (required for contractor reps)."
    )


class WorkerDeploymentInput(DeploymentFields):
    project_id: uuid.UUID


class WorkerUpdate(PatchInput):
    """Changing id_type/id_number needs capability 47; the old value is kept encrypted in
    history and audits show masked values only (WK-9)."""

    non_nullable = frozenset(
        {
            "full_name_en",
            "full_name_ar",
            "id_type",
            "id_number",
            "id_expiry_date",
            "nationality",
            "primary_language",
        }
    )

    full_name_en: str | None = Field(default=None, min_length=1, max_length=120)
    full_name_ar: str | None = Field(default=None, min_length=1, max_length=120)
    id_type: WorkerIdType | None = None
    id_number: str | None = Field(default=None, min_length=6, max_length=15)
    passport_country: str | None = Field(default=None, pattern=ISO2)
    id_expiry_date: date | None = None
    nationality: str | None = Field(default=None, pattern=ISO2)
    primary_language: WorkerLanguage | None = None
    user_id: uuid.UUID | None = None


class WorkerTransitionRequest(StrictInput):
    """active → banned / banned → active (capability 49), reason required. Ban cascades LC-9
    (every credential on every project revoked `worker_banned`); lifting a ban does not restore
    credentials."""

    to_status: WorkerStatus
    reason: str = Field(min_length=10, max_length=500, description=NO_SECURITY)


class WorkerDeploymentSummary(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_code: str
    engagement: EngagementRef | None
    trade: Trade
    status: DeploymentStatus
    mobilised_on: date
    demobilised_on: date | None


class WorkerRead(Timestamps):
    """`id_number_masked` per WK-4. Personal fields (names, nationality, photo, ID expiry) are
    returned to holders of capability 46 in scope. Anonymised workers carry
    "Anonymised worker WKR-nnnnnn" and no identity data (P2-7)."""

    id: uuid.UUID
    worker_no: str = Field(examples=["WKR-000002"])
    person_type: WorkerPersonType
    full_name_en: str
    full_name_ar: str
    id_type: WorkerIdType | None
    id_number_masked: str | None = Field(examples=["2*******02"], description=MASKED_ID_DOC)
    passport_country: str | None
    id_expiry_date: date | None
    id_expired: bool
    nationality: str | None
    adult_attestation: bool
    primary_language: WorkerLanguage
    user: UserRef | None
    photo_attachment_id: uuid.UUID | None = Field(
        description="Open via POST /attachments/{id}/signed-url (≤ 5 min)."
    )
    status: WorkerStatus
    ban_reason: str | None
    deployments: list[WorkerDeploymentSummary] = Field(description="Only deployments in scope.")
    warnings: list[ApiWarning] = Field(default_factory=list)


class WorkerListItem(ApiModel):
    id: uuid.UUID
    worker_no: str
    person_type: WorkerPersonType
    full_name_en: str
    full_name_ar: str
    id_type: WorkerIdType | None
    id_number_masked: str | None = Field(description=MASKED_ID_DOC)
    id_expiry_date: date | None
    nationality: str | None
    status: WorkerStatus
    has_photo: bool
    deployment: DeploymentRead | None = Field(
        description="The deployment on the filtered project (when project_id is given)."
    )


class WorkerPage(Page[WorkerListItem]):
    pass


class WorkerIdLookup(StrictInput):
    """WK-3: exact full-number match through the blind index; no prefix/partial search.
    Returns at most one worker, only if in the caller's scope (otherwise an empty list)."""

    id_type: WorkerIdType
    id_number: str = Field(min_length=6, max_length=15)
    passport_country: str | None = Field(default=None, pattern=ISO2)


class WorkerLookupResult(ApiModel):
    items: list[WorkerListItem]


class UnmaskRequest(StrictInput):
    """WK-5 (capability 48). Writes `sensitive_field_read` with the reason."""

    reason: UnmaskReason
    reason_text: str | None = Field(
        default=None, max_length=200, description="Required when reason = other."
    )


class WorkerIdNumberRead(ApiModel):
    worker_id: uuid.UUID
    id_type: WorkerIdType
    id_number: str
    passport_country: str | None
    revealed_at: datetime


class WorkerDataReportRequest(StrictInput):
    """P2-11 per-worker data report (capability 79): every Phase 2 record of the person."""

    purpose: ExportPurpose = Field(
        description="P2-10: pass_office / authority_request / legal / other."
    )
    purpose_text: str | None = Field(
        default=None, max_length=200, description="Required when purpose = other."
    )


class WorkerDataReport(ApiModel):
    """JSON report; sections are lists of records as returned by the detail endpoints."""

    worker: WorkerRead
    generated_at: datetime
    sections: dict[str, list[dict[str, object]]] = Field(
        description="deployments, inductions, pass_applications, airport_passes, adps, "
        "offences, wap_crew, gate_log (counts only for gate log), credential_events."
    )


WorkerCreate.model_rebuild()
