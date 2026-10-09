"""Contract stubs (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def list_plans(*_: Any) -> NoReturn:
    raise not_implemented()


def read_plan(*_: Any) -> NoReturn:
    raise not_implemented()


def prior_experience(*_: Any) -> NoReturn:
    raise not_implemented()


def confirm_day(*_: Any) -> NoReturn:
    raise not_implemented()


def cancel(*_: Any) -> NoReturn:
    raise not_implemented()
