"""Medical fitness code catalogue (§3.1, §4.3, MC). Contract stubs (stage 1)."""

from typing import Any

from app.core.errors import not_implemented
from app.schemas.medical import FitnessCodeList, FitnessCodeRead, FitnessReference


def reference(*_: Any) -> FitnessReference:
    raise not_implemented()


def list_codes(*_: Any) -> FitnessCodeList:
    raise not_implemented()


def create_code(*_: Any) -> FitnessCodeRead:
    raise not_implemented()


def get_code(*_: Any) -> FitnessCodeRead:
    raise not_implemented()


def update_code(*_: Any) -> FitnessCodeRead:
    raise not_implemented()


def delete_code(*_: Any) -> None:
    raise not_implemented()
