"""Worker fitness status and the data-subject report (OH-2, P6-9).
Contract stubs (stage 1)."""

from typing import Any

from app.core.errors import not_implemented
from app.schemas.medical import (
    FitnessDataSubjectReport,
    WorkerFitnessRead,
)


def worker_fitness(*_: Any) -> WorkerFitnessRead:
    raise not_implemented()


def subject_report(*_: Any) -> FitnessDataSubjectReport:
    raise not_implemented()
