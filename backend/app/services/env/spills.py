"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def create_spill(*_: Any) -> NoReturn:
    raise not_implemented()


def list_spills(*_: Any) -> NoReturn:
    raise not_implemented()


def read_spill(*_: Any) -> NoReturn:
    raise not_implemented()


def transition_spill(*_: Any) -> NoReturn:
    raise not_implemented()
