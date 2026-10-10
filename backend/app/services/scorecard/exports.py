"""6g exports (stage 1 stubs)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def datasets(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def request(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def list_jobs(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def read(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def file_url(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def list_subscriptions(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def subscribe(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def unsubscribe(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()


def dashboard_pdf(*args: Any, **kw: Any) -> NoReturn:
    raise not_implemented()
