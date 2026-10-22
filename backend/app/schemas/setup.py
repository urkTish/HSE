"""First-time setup (D-306): organisation, first project and first administrator."""

from pydantic import EmailStr, Field, field_validator

from app.core.enums import Language
from app.schemas.auth import MOBILE_PATTERN, PASSWORD_DESCRIPTION
from app.schemas.common import ApiModel, StrictInput
from app.schemas.projects import ProjectCreate


class SetupStatus(ApiModel):
    needed: bool = Field(
        description="True only while the install has no users and has never been set up."
    )
    token_required: bool = Field(description="The setup asks for the SETUP_TOKEN code.")
    organisation_name_en: str | None = None
    organisation_name_ar: str | None = None


class SetupAdmin(StrictInput):
    email: EmailStr
    full_name_en: str = Field(min_length=1, max_length=120)
    full_name_ar: str | None = Field(default=None, max_length=120)
    mobile: str | None = Field(default=None, pattern=MOBILE_PATTERN, description="E.164.")
    job_title: str | None = Field(default=None, max_length=80)
    preferred_language: Language = Language.en
    password: str = Field(min_length=12, max_length=256, description=PASSWORD_DESCRIPTION)


class SetupRequest(StrictInput):
    setup_token: str | None = Field(
        default=None, max_length=200, description="Required when the server sets SETUP_TOKEN."
    )
    organisation_name_en: str = Field(min_length=1, max_length=150)
    organisation_name_ar: str = Field(min_length=1, max_length=150)
    project: ProjectCreate
    admin: SetupAdmin
    privacy_notice_version: str = Field(description="The privacy notice the admin acknowledged.")

    @field_validator("organisation_name_ar")
    @classmethod
    def _arabic(cls, v: str) -> str:
        if not any("؀" <= ch <= "ۿ" for ch in v):
            raise ValueError("must contain Arabic script")
        return v
