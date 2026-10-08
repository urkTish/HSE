"""Medical imports (§3.11, IM6).
Contract stubs (stage 1)."""

from typing import Any

from app.core.errors import not_implemented
from app.schemas.medical import (
    MedicalImportBatchPage,
    MedicalImportBatchRead,
)


def template(*_: Any) -> tuple[bytes, str, str]:
    raise not_implemented()


def upload(*_: Any) -> MedicalImportBatchRead:
    raise not_implemented()


def list_batches(*_: Any) -> MedicalImportBatchPage:
    raise not_implemented()


def get(*_: Any) -> MedicalImportBatchRead:
    raise not_implemented()


def commit(*_: Any) -> MedicalImportBatchRead:
    raise not_implemented()


def discard(*_: Any) -> MedicalImportBatchRead:
    raise not_implemented()
