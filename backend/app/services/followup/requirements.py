"""6f requirements (stage 1 stubs)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def list_requirements(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def read_requirement(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def waive(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()
