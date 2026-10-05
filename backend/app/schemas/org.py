"""Sites and zones (spec §3.2, §3.3, §4.4, §5.3)."""

import uuid

from pydantic import Field, field_validator, model_validator

from app.core.enums import MOVEMENT_AREAS, AirsideArea, SiteSide, SiteStatus, ZoneStatus, ZoneType
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps, has_arabic

SITE_CODE = r"^[A-Za-z0-9-]{1,12}$"
ZONE_CODE = r"^[A-Za-z0-9-]{1,16}$"
RUNWAY_REF = r"^\d{2}[LRC]?/\d{2}[LRC]?$"


def _check_ar(v: str | None) -> str | None:
    if v is not None and not has_arabic(v):
        raise ValueError("must contain Arabic script")
    return v


class SiteCreate(StrictInput):
    code: str = Field(pattern=SITE_CODE, description="Unique within the project, e.g. S-AIR.")
    name_en: str = Field(min_length=1, max_length=150)
    name_ar: str = Field(min_length=1, max_length=150)
    site_side: SiteSide = Field(description="airside/mixed only on airport projects.")
    gps_lat: float | None = Field(default=None, ge=16, le=33, description="KSA bbox latitude.")
    gps_lng: float | None = Field(default=None, ge=34, le=56, description="KSA bbox longitude.")

    _ar = field_validator("name_ar")(_check_ar)


class SiteUpdate(PatchInput):
    non_nullable = frozenset({"code", "name_en", "name_ar", "site_side"})

    code: str | None = Field(default=None, pattern=SITE_CODE)
    name_en: str | None = Field(default=None, min_length=1, max_length=150)
    name_ar: str | None = Field(default=None, min_length=1, max_length=150)
    site_side: SiteSide | None = None
    gps_lat: float | None = Field(default=None, ge=16, le=33)
    gps_lng: float | None = Field(default=None, ge=34, le=56)

    _ar = field_validator("name_ar")(_check_ar)


class SiteRead(Timestamps):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    site_side: SiteSide
    gps_lat: float | None
    gps_lng: float | None
    status: SiteStatus


class SitePage(Page[SiteRead]):
    pass


class SiteTransitionRequest(StrictInput):
    """active ↔ inactive. Sites are never deleted (rule 23)."""

    to_status: SiteStatus
    reason: str | None = Field(default=None, max_length=500)


class AirsideAttributesInput(StrictInput):
    """Airside attribute block (§3.3). Required iff zone_type = airside, else must be null."""

    airside_area: AirsideArea
    in_movement_area: bool = Field(
        description="Must be true for runway, runway_strip, resa, taxiway, taxiway_strip, apron."
    )
    runway_ref: str | None = Field(default=None, pattern=RUNWAY_REF, examples=["15L/33R"])
    security_restricted_area: bool = True
    notam_required_for_works: bool | None = Field(
        default=None, description="Defaults to in_movement_area when omitted."
    )
    ols_height_limit_m_amsl: float | None = Field(default=None, ge=0, le=3000)
    max_equipment_height_m_agl: float | None = Field(default=None, ge=0, le=300)
    escort_required: bool
    adp_required: bool = Field(description="Airside driving permit required.")
    fod_control_required: bool = True
    works_safety_plan_ref: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _movement_area(self) -> "AirsideAttributesInput":
        if self.airside_area in MOVEMENT_AREAS and not self.in_movement_area:
            raise ValueError(
                f"in_movement_area must be true when airside_area is {self.airside_area.value}"
            )
        if self.notam_required_for_works is None:
            self.notam_required_for_works = self.in_movement_area
        return self


class AirsideAttributes(ApiModel):
    airside_area: AirsideArea
    in_movement_area: bool
    runway_ref: str | None
    security_restricted_area: bool
    notam_required_for_works: bool
    ols_height_limit_m_amsl: float | None
    max_equipment_height_m_agl: float | None
    escort_required: bool
    adp_required: bool
    fod_control_required: bool
    works_safety_plan_ref: str | None


class ZoneCreate(StrictInput):
    code: str = Field(pattern=ZONE_CODE, description="Unique within the site, e.g. Z-APR-21.")
    name_en: str = Field(min_length=1, max_length=150)
    name_ar: str = Field(min_length=1, max_length=150)
    zone_type: ZoneType = Field(
        description="airside/landside only on airport projects and consistent with site_side."
    )
    airside: AirsideAttributesInput | None = Field(
        default=None, description="Required iff zone_type = airside; must be null otherwise."
    )

    _ar = field_validator("name_ar")(_check_ar)

    @model_validator(mode="after")
    def _airside_block(self) -> "ZoneCreate":
        if self.zone_type == ZoneType.airside and self.airside is None:
            raise ValueError("airside attributes are required when zone_type is airside")
        if self.zone_type != ZoneType.airside and self.airside is not None:
            raise ValueError("airside attributes must be null when zone_type is not airside")
        return self


class ZoneUpdate(PatchInput):
    """Partial update. Sending ``airside`` replaces the whole block. Airside changes are
    audited with before/after (rule 21)."""

    non_nullable = frozenset({"code", "name_en", "name_ar", "zone_type"})

    code: str | None = Field(default=None, pattern=ZONE_CODE)
    name_en: str | None = Field(default=None, min_length=1, max_length=150)
    name_ar: str | None = Field(default=None, min_length=1, max_length=150)
    zone_type: ZoneType | None = None
    airside: AirsideAttributesInput | None = None

    _ar = field_validator("name_ar")(_check_ar)


class ZoneRead(Timestamps):
    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    zone_type: ZoneType
    status: ZoneStatus
    status_reason: str | None
    airside: AirsideAttributes | None = Field(description="Present iff zone_type = airside.")


class ZonePage(Page[ZoneRead]):
    pass


class ZoneTransitionRequest(StrictInput):
    """active → temporarily_closed → active; active/temporarily_closed → archived (§4.4)."""

    to_status: ZoneStatus
    reason: str | None = Field(default=None, max_length=500)
