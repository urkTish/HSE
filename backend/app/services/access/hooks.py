"""Hook provider interface for requirements owned by later phases (spec 2-access-permits HK-1…HK-5).

Phases 4/5/6 register a provider per hook kind; Phase 2 stores the requirement codes and asks the
provider. Without a provider the result is `not_evaluated`, which the project's hook policy turns
into `warn` (HOOK_NOT_AVAILABLE, never blocks) or `not_met` (block).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

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
