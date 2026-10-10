"""6g config (stage 1 stubs)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def reference(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def get_settings(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def update_settings(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def confirm_sources(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def list_profiles(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def create_profile(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def get_profile(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def update_profile(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def activate_profile(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()
