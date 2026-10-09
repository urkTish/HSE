"""Contract stubs (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def list_patrols(*_: Any) -> NoReturn:
    raise not_implemented()


def create_patrol(*_: Any) -> NoReturn:
    raise not_implemented()


def void_patrol(*_: Any) -> NoReturn:
    raise not_implemented()


def list_exemptions(*_: Any) -> NoReturn:
    raise not_implemented()


def grant(*_: Any) -> NoReturn:
    raise not_implemented()


def revoke(*_: Any) -> NoReturn:
    raise not_implemented()
