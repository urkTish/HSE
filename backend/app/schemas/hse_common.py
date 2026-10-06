"""Building blocks shared by the Phase 1 schemas (spec 1-dashboard)."""

import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import Field, PlainSerializer, WithJsonSchema

from app.core.enums import ZoneType
from app.schemas.common import ApiModel


def _dec_to_str(v: Decimal) -> str:
    return format(v, "f")


DecimalStr = Annotated[
    Decimal,
    PlainSerializer(_dec_to_str, return_type=str, when_used="json"),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^-?\d+(\.\d+)?$",
            "description": "Decimal number serialised as a string (exact, no float rounding).",
        },
        mode="serialization",
    ),
]
"""Decimal output as a JSON string; input accepts a number or a numeric string."""

ManHours = Annotated[DecimalStr, Field(ge=0, max_digits=10, decimal_places=2)]
Hours8 = Annotated[DecimalStr, Field(ge=0, max_digits=8, decimal_places=2)]
SarAmount = Annotated[DecimalStr, Field(ge=0, max_digits=12, decimal_places=2)]


class ApiWarning(ApiModel):
    """A non-blocking warning returned with a successful write (e.g. P1-8 possible ID number,
    CA-6 PPE-only control, W03 suspended contractor)."""

    code: str = Field(description="Stable machine code, e.g. POSSIBLE_ID_NUMBER, W03.")
    message: str
    message_ar: str | None = None
    field: str | None = Field(default=None, description="Field the warning refers to, if any.")


class SiteRef(ApiModel):
    id: uuid.UUID
    code: str
    name_en: str
    name_ar: str


class ZoneRef(ApiModel):
    id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    zone_type: ZoneType


class EngagementRef(ApiModel):
    """Project engagement shown by its contractor short code (e.g. NAJD@ANIA-EXP)."""

    id: uuid.UUID
    contractor_id: uuid.UUID
    short_code: str = Field(examples=["NAJD"])
    name_en: str
    name_ar: str
    tier: int = Field(ge=1, le=3)


class UserRef(ApiModel):
    """A user reference (personal data, not sensitive)."""

    id: uuid.UUID
    full_name_en: str
    full_name_ar: str | None = None


class LabelledCode(ApiModel):
    """A reference-list code with its current EN/AR label (§3.11)."""

    code: str
    label_en: str
    label_ar: str
