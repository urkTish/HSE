"""Contract stubs (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def list_entries(*_: Any) -> NoReturn:
    raise not_implemented()


def read_entry(*_: Any) -> NoReturn:
    raise not_implemented()


def review(*_: Any) -> NoReturn:
    raise not_implemented()


def reopen(*_: Any) -> NoReturn:
    raise not_implemented()
