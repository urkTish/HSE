"""Medical providers and examiner registrations (§3.2, §3.3, §4.1, §4.2, MP, EX).
Contract stubs (stage 1)."""

from typing import Any

from app.core.errors import not_implemented
from app.schemas.access_common import WorkerRef
from app.schemas.medical import (
    ExaminerPage,
    ExaminerRead,
    MedicalProviderPage,
    MedicalProviderRead,
)


def list_providers(*_: Any) -> MedicalProviderPage:
    raise not_implemented()


def create_provider(*_: Any) -> MedicalProviderRead:
    raise not_implemented()


def get_provider(*_: Any) -> MedicalProviderRead:
    raise not_implemented()


def update_provider(*_: Any) -> MedicalProviderRead:
    raise not_implemented()


def transition_provider(*_: Any) -> MedicalProviderRead:
    raise not_implemented()


def affected(*_: Any) -> list[WorkerRef]:
    raise not_implemented()


def list_examiners(*_: Any) -> ExaminerPage:
    raise not_implemented()


def create_examiner(*_: Any) -> ExaminerRead:
    raise not_implemented()


def get_examiner(*_: Any) -> ExaminerRead:
    raise not_implemented()


def update_examiner(*_: Any) -> ExaminerRead:
    raise not_implemented()


def transition_examiner(*_: Any) -> ExaminerRead:
    raise not_implemented()
