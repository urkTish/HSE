"""Shared schema building blocks."""

import re
from datetime import datetime
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")

ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def has_arabic(value: str) -> bool:
    return bool(ARABIC_RE.search(value))


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=False)


class StrictInput(BaseModel):
    """Base for request bodies: unknown fields are rejected (helps catch typos)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PatchInput(StrictInput):
    """Base for PATCH bodies. Only fields that are sent are applied.

    Fields listed in ``non_nullable`` may be omitted but not sent as ``null``.
    """

    non_nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> "PatchInput":
        for name in self.model_fields_set & self.non_nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class Page(ApiModel, Generic[T]):
    items: list[T]
    total: int = Field(description="Total number of matching items across all pages.")
    page: int = Field(description="1-based page number.")
    page_size: int = Field(description="Items per page (max 200).")


class Timestamps(ApiModel):
    created_at: datetime = Field(description="UTC timestamp.")
    updated_at: datetime = Field(description="UTC timestamp.")


class TransitionReason(StrictInput):
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Reason / comment. Required by some transitions (see the state tables in "
        "spec §4). Do not enter ID or medical details.",
    )
