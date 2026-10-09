"""Contract stubs (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def list_checks(*_: Any) -> NoReturn:
    raise not_implemented()


def create_check(*_: Any) -> NoReturn:
    raise not_implemented()


def void(*_: Any) -> NoReturn:
    raise not_implemented()
