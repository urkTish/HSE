"""Airport pass categories, area codes, applications and issued passes
(spec 2-access-permits §3.6-§3.9, §4.4, §4.5, §5.4)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import (
    BackgroundCheckStatus,
    CardColour,
    PassApplicationStatus,
    PassApplicationType,
    PassAreaKind,
)
from app.schemas.access_common import (
    HookRequirement,
    HookRequirementRead,
    ValidityBlock,
    WorkerRef,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import ApiWarning, EngagementRef, UserRef, ZoneRef
from app.schemas.inductions import EligibilityItem

SENSITIVE_BG = (
    "Sensitive (P2-1): present only for capability 56 (reads audited as sensitive_field_read); "
    "the key is absent for other callers (AP-13)."
)

# ---- reference lists AP-CAT / AP-AREA (capability 80; codes immutable) ---------------------------


class PassCategoryCreate(StrictInput):
    code: str = Field(min_length=1, max_length=8, examples=["PERM"])
    name_en: str = Field(min_length=1, max_length=120)
    name_ar: str = Field(min_length=1, max_length=120)
    escorted: bool
    background_check_required: bool = Field(description="True for unescorted categories (AP-4).")
    max_validity_days: int = Field(ge=1, description="≤ pass_max_validity_months × 31.")
    card_colour: CardColour
    allows_adp: bool = Field(description="False when escorted (DP-3).")
    hook_requirements: list[HookRequirement] = Field(
        default_factory=list, description="Checked at Endorse (HK-2), e.g. AVSEC-AWR."
    )
    active: bool = True


class PassCategoryUpdate(PatchInput):
    non_nullable = frozenset(
        {
            "name_en",
            "name_ar",
            "escorted",
            "background_check_required",
            "max_validity_days",
            "card_colour",
            "allows_adp",
            "hook_requirements",
            "active",
        }
    )

    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    name_ar: str | None = Field(default=None, min_length=1, max_length=120)
    escorted: bool | None = None
    background_check_required: bool | None = None
    max_validity_days: int | None = Field(default=None, ge=1)
    card_colour: CardColour | None = None
    allows_adp: bool | None = None
    hook_requirements: list[HookRequirement] | None = None
    active: bool | None = None


class PassCategoryRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    escorted: bool
    background_check_required: bool
    max_validity_days: int
    card_colour: CardColour
    allows_adp: bool
    hook_requirements: list[HookRequirementRead]
    active: bool


class PassCategoryList(ApiModel):
    items: list[PassCategoryRead]


class PassAreaCreate(StrictInput):
    code: str = Field(min_length=1, max_length=4, examples=["A"])
    name_en: str = Field(min_length=1, max_length=120)
    name_ar: str = Field(min_length=1, max_length=120)
    colour: CardColour
    area_kind: PassAreaKind
    zone_ids: list[uuid.UUID] = Field(default_factory=list, description="Airside zones.")
    active: bool = True


class PassAreaUpdate(PatchInput):
    non_nullable = frozenset({"name_en", "name_ar", "colour", "area_kind", "zone_ids", "active"})

    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    name_ar: str | None = Field(default=None, min_length=1, max_length=120)
    colour: CardColour | None = None
    area_kind: PassAreaKind | None = None
    zone_ids: list[uuid.UUID] | None = None
    active: bool | None = None


class PassAreaRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    colour: CardColour
    area_kind: PassAreaKind
    zones: list[ZoneRef]
    active: bool


class PassAreaList(ApiModel):
    items: list[PassAreaRead]


# ---- applications -------------------------------------------------------------------------------


class PassApplicationCreate(StrictInput):
    """Capability 53 → status draft. 422 NOT_AIRPORT_PROJECT (AP-2), 409 APPLICATION_OPEN
    (AP-3), 422 VALIDITY_EXCEEDS_LIMIT with meta.limiting_factor (AP-6). The ID copy is
    uploaded afterwards (POST /attachments, owner_type pass_application_id_copy; required for
    new/renewal before Submit)."""

    application_type: PassApplicationType
    deployment_id: uuid.UUID
    sponsor_letter_ref: str = Field(min_length=1, max_length=40)
    pass_category: str = Field(min_length=1, max_length=8, examples=["PERM"])
    requested_area_codes: list[str] = Field(min_length=1, examples=[["A", "M"]])
    requested_valid_until: date
    justification: str = Field(
        min_length=1,
        max_length=500,
        description="P3 hint; ≥ 20 chars when an area maps to no zone in the deployment's sites.",
    )


class PassApplicationUpdate(PatchInput):
    """Draft only."""

    non_nullable = frozenset(
        {
            "sponsor_letter_ref",
            "pass_category",
            "requested_area_codes",
            "requested_valid_until",
            "justification",
        }
    )

    sponsor_letter_ref: str | None = Field(default=None, min_length=1, max_length=40)
    pass_category: str | None = Field(default=None, min_length=1, max_length=8)
    requested_area_codes: list[str] | None = Field(default=None, min_length=1)
    requested_valid_until: date | None = None
    justification: str | None = Field(default=None, min_length=1, max_length=500)


class PassApplicationTransitionRequest(StrictInput):
    """§4.4 transitions:

    * draft → submitted (53): required fields, photo (PHOTO_REQUIRED), ID copy for new/renewal,
      AP-5 (deployment mobilised, ID expiry > today + 30 → ID_EXPIRES_SOON, contractor not
      suspended → CONTRACTOR_SUSPENDED, worker not banned → WORKER_BANNED)
    * submitted → draft (54): `reason` = return comment
    * submitted → endorsed (54): `client_sponsor_user_id` (employer client / pmc_consultant;
      ≠ submitter → ENDORSER_NOT_ALLOWED, AP-8); prerequisites (AP-7) met or hook warn, else
      PREREQUISITES_NOT_MET with meta.requirements; snapshot stored
    * endorsed → lodged (55): `lodged_at`, `authority_ref`
    * lodged → approved (55): background cleared for categories that require it
      (BACKGROUND_NOT_CLEARED, AP-4)
    * lodged → refused (55): optional `outcome_note` (no security reasons, P2-4)
    * draft/submitted/endorsed/lodged → withdrawn (53 own / 54): `reason`
    * approved → cancelled (55): `reason`
    * approved → issued: use POST /pass-applications/{id}/issue.
    """

    to_status: PassApplicationStatus
    reason: str | None = Field(default=None, max_length=500)
    client_sponsor_user_id: uuid.UUID | None = None
    lodged_at: datetime | None = None
    authority_ref: str | None = Field(default=None, max_length=40)
    outcome_note: str | None = Field(
        default=None, max_length=300, description="Do not record security reasons (P2-4)."
    )


class BackgroundCheckUpdate(StrictInput):
    """Capability 55 + 56. recheck_due = date + bg_recheck_months (§6.2). Status and dates
    only — never the reason or the authority's report (P2-4)."""

    status: BackgroundCheckStatus
    check_date: date | None = Field(default=None, description="Required for cleared.")


class PassIssueRequest(StrictInput):
    """approved → issued (capability 55): creates the pass (§3.9). area_codes ⊆ requested
    (AREA_NOT_REQUESTED, AP-9); dates as printed. A renewal/replacement/area change revokes the
    previous Active pass (`superseded`) with custody return due (AP-11)."""

    pass_no: str = Field(min_length=1, max_length=30, examples=["ANIA-AP-26-01877"])
    area_codes: list[str] = Field(min_length=1)
    issued_on: date
    card_expiry_date: date


class BackgroundCheckRead(ApiModel):
    status: BackgroundCheckStatus
    check_date: date | None
    recheck_due: date | None


class PassApplicationRead(Timestamps):
    """For callers without capability 56 a refused application shows
    `status_label_en` "Refused by issuing authority" and `background_check` / `outcome_note`
    are absent (AP-13)."""

    id: uuid.UUID
    application_no: str = Field(examples=["APA-ANIA-EXP-2026-0142"])
    project_id: uuid.UUID
    application_type: PassApplicationType
    worker: WorkerRef
    deployment_id: uuid.UUID
    sponsor_engagement: EngagementRef | None
    sponsor_letter_ref: str
    client_sponsor: UserRef | None
    pass_category: str
    requested_area_codes: list[str]
    requested_valid_until: date
    max_valid_until: date | None = Field(description="AP-6 limit today, for the form.")
    justification: str
    has_id_copy: bool
    id_copy_attachment_id: uuid.UUID | None = Field(
        default=None, description="Present only for capability 48 (opening it is audited)."
    )
    prerequisite_snapshot: list[EligibilityItem] | None
    submitted_at: datetime | None
    submitted_by: UserRef | None
    lodged_at: datetime | None
    authority_ref: str | None
    days_lodged: int | None = Field(description="Ageing for the tracker (AP-14).")
    stale: bool
    background_check: BackgroundCheckRead | None = Field(default=None, description=SENSITIVE_BG)
    outcome_note: str | None = Field(default=None, description=SENSITIVE_BG)
    status: PassApplicationStatus
    status_label_en: str
    status_label_ar: str
    issued_pass_id: uuid.UUID | None
    warnings: list[ApiWarning] = Field(default_factory=list)


class PassApplicationPage(Page[PassApplicationRead]):
    pass


# ---- passes -------------------------------------------------------------------------------------


class AirportPassRead(Timestamps):
    """Validity per §4.5 / §6.2; lifecycle actions via /credentials/airport_pass/{id}/…"""

    id: uuid.UUID
    pass_no: str
    project_id: uuid.UUID
    application_id: uuid.UUID
    worker: WorkerRef
    deployment_id: uuid.UUID
    engagement: EngagementRef | None
    pass_category: str
    area_codes: list[str]
    card_colour: CardColour
    escorted: bool
    issued_on: date
    card_expiry_date: date
    validity: ValidityBlock
    background_recheck_due: date | None = Field(default=None, description=SENSITIVE_BG)


class AirportPassPage(Page[AirportPassRead]):
    pass
