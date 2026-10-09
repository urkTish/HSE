"""Contract stubs (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def reference(*_: Any) -> NoReturn:
    raise not_implemented()


def read_settings(*_: Any) -> NoReturn:
    raise not_implemented()


def update_settings(*_: Any) -> NoReturn:
    raise not_implemented()


def read_regime_table(*_: Any) -> NoReturn:
    raise not_implemented()


def update_regime_table(*_: Any) -> NoReturn:
    raise not_implemented()
