"""Contract stubs (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def board(*_: Any) -> NoReturn:
    raise not_implemented()


def zone_state(*_: Any) -> NoReturn:
    raise not_implemented()


def duty_list(*_: Any) -> NoReturn:
    raise not_implemented()


def acclimatisation_status(*_: Any) -> NoReturn:
    raise not_implemented()
