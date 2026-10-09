"""Contract stubs (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def list_readings(*_: Any) -> NoReturn:
    raise not_implemented()


def create_manual(*_: Any) -> NoReturn:
    raise not_implemented()


def void(*_: Any) -> NoReturn:
    raise not_implemented()


def import_csv(*_: Any) -> NoReturn:
    raise not_implemented()


def station_session(*_: Any) -> NoReturn:
    raise not_implemented()


def ingest(*_: Any) -> NoReturn:
    raise not_implemented()
