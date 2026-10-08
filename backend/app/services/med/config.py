"""Phase 6a settings and enabling medical hooks (§3.12, HK6-1).
Contract stubs (stage 1)."""

from typing import Any

from app.core.errors import not_implemented
from app.schemas.cert_config import HookPolicyRead
from app.schemas.medical import (
    MedicalSettingsRead,
    MedicalSettingsUpdateResult,
)


def get_settings(*_: Any) -> MedicalSettingsRead:
    raise not_implemented()


def update_settings(*_: Any) -> MedicalSettingsUpdateResult:
    raise not_implemented()


def enable_hooks(*_: Any) -> HookPolicyRead:
    raise not_implemented()
