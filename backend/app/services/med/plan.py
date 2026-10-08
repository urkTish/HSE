"""Requirement plan, health profiles, requirements and gaps (§3.4, §3.5, §6.3, MR, WP).
Contract stubs (stage 1)."""

from typing import Any

from app.core.errors import not_implemented
from app.schemas.medical import (
    FitnessGapPage,
    FitnessRequirementList,
    HealthProfileRead,
    MedicalPlanLineRead,
    MedicalPlanLineVersions,
    MedicalPlanRead,
)


def read_plan(*_: Any) -> MedicalPlanRead:
    raise not_implemented()


def create_line(*_: Any) -> MedicalPlanLineRead:
    raise not_implemented()


def update_line(*_: Any) -> MedicalPlanLineRead:
    raise not_implemented()


def remove_line(*_: Any) -> MedicalPlanLineRead:
    raise not_implemented()


def versions(*_: Any) -> MedicalPlanLineVersions:
    raise not_implemented()


def exemption(*_: Any) -> None:
    raise not_implemented()


def get_profile(*_: Any) -> HealthProfileRead:
    raise not_implemented()


def update_profile(*_: Any) -> HealthProfileRead:
    raise not_implemented()


def requirements(*_: Any) -> FitnessRequirementList:
    raise not_implemented()


def gaps(*_: Any) -> FitnessGapPage:
    raise not_implemented()
