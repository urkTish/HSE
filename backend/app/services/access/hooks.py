"""Hook provider interface for requirements owned by later phases (spec 2-access-permits HK-1…HK-5).

Phases 4/5/6 register a provider per hook kind; Phase 2 stores the requirement codes and asks the
provider. Without a provider the result is `not_evaluated`, which the project's hook policy turns
into `warn` (HOOK_NOT_AVAILABLE, never blocks) or `not_met` (block).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from app.core.access_enums import HookKind, HookProviderStatus, HookSubjectType

AVAILABLE_FROM_PHASE: dict[HookKind, int] = {
    HookKind.training_course: 5,
    HookKind.personnel_certificate: 4,
    HookKind.equipment_certificate: 4,
    HookKind.medical_fitness: 6,
}


@dataclass(frozen=True)
class HookCheck:
    """HK-3 provider result."""

    status: HookProviderStatus
    valid_until: date | None = None
    ref: str | None = None
    reason_code: str | None = None
    # v1.2 (4-third-party-cert HK4-3, HK4-8): hard stops block in every stage
    hard_stop: bool = False
    conditions: tuple[dict[str, Any], ...] = ()
    swl_t: Decimal | None = None


@dataclass(frozen=True)
class HookContext:
    """v1.2 HK-3 context (4-third-party-cert HK4-8): project_id is required for subject
    equipment_tag; equipment_ref is the vehicle or {category, tag} (or the Phase 4 item)."""

    project_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    permit_id: uuid.UUID | None = None
    critical: bool = False
    use: str | None = None
    vehicle_id: uuid.UUID | None = None
    equipment_category: str | None = None
    equipment_tag: str | None = None
    equipment_item_id: uuid.UUID | None = None
    rated_capacity_t: Decimal | None = None
    operator_worker_id: uuid.UUID | None = None
    crew_role: str | None = None
    scaffold_design: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class HookProvider(Protocol):
    """HK-3: check(subject_type, subject_id, kind, code, at). Results may be cached ≤ 60 s."""

    def check(
        self,
        subject_type: HookSubjectType,
        subject_id: uuid.UUID,
        kind: HookKind,
        code: str,
        at: datetime,
    ) -> HookCheck: ...


_PROVIDERS: dict[HookKind, HookProvider] = {}


def register_provider(kind: HookKind, provider: HookProvider) -> None:
    _PROVIDERS[kind] = provider


def unregister_provider(kind: HookKind) -> None:
    _PROVIDERS.pop(kind, None)


def provider_for(kind: HookKind) -> HookProvider | None:
    return _PROVIDERS.get(kind)


def is_registered(kind: HookKind) -> bool:
    return kind in _PROVIDERS


def registered_on_project(db: Any, project_id: Any, kind: HookKind) -> bool:
    """HK4-1: Phase 4 registers `personnel_certificate` / `equipment_certificate` per project
    when the HSE Manager enables Phase 4 there; other kinds are registered globally."""
    if is_registered(kind):
        return True
    from app.services.cert import policy as cpolicy  # noqa: PLC0415

    return kind in cpolicy.KINDS and cpolicy.enabled(db, project_id, kind)
