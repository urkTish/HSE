"""JSA / risk assessment: templates and permit instances (spec 3-ptw §3.8, §4.3, §5.3, §6.1)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.hse_enums import ControlLevel
from app.core.ptw_enums import Hazard, JsaStatus, JsaWarningCode, PermitType, RiskBand
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import EngagementRef, UserRef
from app.schemas.ptw_common import PermitRef


class JsaControlInput(StrictInput):
    text: str = Field(min_length=1, max_length=300)
    level: ControlLevel


class JsaHazardLineInput(StrictInput):
    """L and S are integers 1–5 (S = Phase 1 severity list S). residual ≤ initial for both
    (RESIDUAL_ABOVE_INITIAL, JS-5); PPE-only controls cannot lower the band (PPE_ONLY_CONTROLS,
    JS-8)."""

    hazard_code: Hazard
    description: str = Field(min_length=1, max_length=300)
    initial_l: int = Field(ge=1, le=5)
    initial_s: int = Field(ge=1, le=5)
    controls: list[JsaControlInput] = Field(min_length=1)
    residual_l: int = Field(ge=1, le=5)
    residual_s: int = Field(ge=1, le=5)


class JsaStepInput(StrictInput):
    step_no: int = Field(ge=1, le=100)
    description_en: str = Field(min_length=1, max_length=500)
    description_ar: str | None = Field(default=None, max_length=500)
    hazards: list[JsaHazardLineInput] = Field(min_length=1)


class JsaControlRead(ApiModel):
    text: str
    level: ControlLevel


class JsaHazardLineRead(ApiModel):
    id: uuid.UUID
    hazard_code: Hazard
    description: str
    initial_l: int
    initial_s: int
    initial_score: int
    initial_band: RiskBand
    controls: list[JsaControlRead]
    residual_l: int
    residual_s: int
    residual_score: int
    residual_band: RiskBand
    has_higher_control: bool = Field(description="Any control at engineering level or higher.")
    warnings: list[JsaWarningCode]


class JsaStepRead(ApiModel):
    step_no: int
    description_en: str
    description_ar: str | None
    hazards: list[JsaHazardLineRead]


class ResidualAcceptanceRead(ApiModel):
    band: RiskBand
    accepted_by: UserRef
    accepted_as: str = Field(examples=["receiver", "issuer", "hse"])
    accepted_at: datetime
    alarp_justification: str | None


class CrewBriefingRead(ApiModel):
    shift_no: int
    worker_count: int
    briefed_by: UserRef
    at: datetime


class JsaTemplateCreate(StrictInput):
    """Capability 96 (Contractor HSE Reps propose for their engagement; HSE Officer/Manager
    approve). Project-wide when engagement_id is null."""

    engagement_id: uuid.UUID | None = None
    work_types: list[PermitType] = Field(min_length=1)
    title_en: str = Field(min_length=1, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    steps: list[JsaStepInput] = Field(min_length=1)


class JsaInstanceCreate(StrictInput):
    """Capability 83: the permit's JSA instance (one per permit, JS-1), blank or copied from
    an Approved template (TEMPLATE_REVIEW_DUE when its review is due, JS-9). work_types must
    include every permit type (JSA_TYPE_MISMATCH, JS-3)."""

    template_id: uuid.UUID | None = None
    work_types: list[PermitType] | None = Field(
        default=None, description="Default: the template's, else the permit's."
    )
    title_en: str | None = Field(default=None, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    steps: list[JsaStepInput] | None = Field(
        default=None, description="Required without template_id."
    )


class JsaUpdate(PatchInput):
    """Draft only. An Approved instance is frozen (JSA_FROZEN): POST …/revisions instead
    (JS-10, returns the permit to Reviewed)."""

    non_nullable = frozenset({"work_types", "title_en", "steps"})

    work_types: list[PermitType] | None = Field(default=None, min_length=1)
    title_en: str | None = Field(default=None, min_length=1, max_length=150)
    title_ar: str | None = Field(default=None, max_length=150)
    steps: list[JsaStepInput] | None = Field(default=None, min_length=1)


class JsaTransition(StrictInput):
    """§4.3: draft → submitted (every line complete; JS-4 mandatory hazards, else
    JSA_MANDATORY_HAZARD_MISSING); submitted → approved (instance: the issuer, after residual
    acceptance JS-7; template: capability 96); submitted → draft with comment."""

    to_status: JsaStatus
    comment: str | None = Field(default=None, max_length=500)


class ResidualAcceptanceInput(StrictInput):
    """JS-7 by governing band: Low → receiver; Medium → issuer; High → issuer AND an HSE
    Officer/Manager (capability 86) with ALARP ≥ 30 chars and an engineering-or-higher control
    on each High line (HIGHER_CONTROL_REQUIRED). The author cannot accept High
    (SOD_CONFLICT, PR-5 i). Signed (PT-15)."""

    alarp_justification: str | None = Field(default=None, min_length=30, max_length=1000)


class JsaTemplateRef(ApiModel):
    id: uuid.UUID
    jsa_no: str
    title_en: str
    status: JsaStatus
    review_due_on: date | None


class JsaRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    jsa_no: str = Field(examples=["JSA-ANIA-EXP-2026-0413", "JSA-T-RBT-52-0004"])
    revision: int
    is_template: bool
    template: JsaTemplateRef | None
    engagement: EngagementRef | None
    permit: PermitRef | None
    work_types: list[PermitType]
    title_en: str
    title_ar: str | None
    steps: list[JsaStepRead]
    governing_residual_band: RiskBand | None
    max_initial_score: int | None
    max_residual_score: int | None
    mandatory_hazards: list[Hazard] = Field(description="JS-4 for the permit (or template types).")
    missing_mandatory_hazards: list[Hazard]
    required_acceptances: list[str] = Field(
        description="Who still has to accept: receiver / issuer / hse (JS-7)."
    )
    residual_acceptances: list[ResidualAcceptanceRead]
    review_due_on: date | None = Field(description="Templates: approval + jsa_review_months.")
    status: JsaStatus
    returned_comment: str | None
    approved_by: UserRef | None
    approved_at: datetime | None
    crew_briefings: list[CrewBriefingRead]
    created_by: UserRef
    created_at: datetime
    updated_at: datetime


class JsaListItem(ApiModel):
    id: uuid.UUID
    jsa_no: str
    revision: int
    is_template: bool
    engagement: EngagementRef | None
    permit: PermitRef | None
    work_types: list[PermitType]
    title_en: str
    title_ar: str | None
    governing_residual_band: RiskBand | None
    status: JsaStatus
    review_due_on: date | None
    updated_at: datetime


JsaPage = Page[JsaListItem]
