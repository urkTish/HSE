"""6f config (stage 1 stubs)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def reference(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def get_settings(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def update_settings(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def list_rules(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def create_rule(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def update_rule(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()
