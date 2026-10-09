"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def create_background(*_: Any) -> NoReturn:
    raise not_implemented()


def create_instrument(*_: Any) -> NoReturn:
    raise not_implemented()


def create_point(*_: Any) -> NoReturn:
    raise not_implemented()


def create_reading(*_: Any) -> NoReturn:
    raise not_implemented()


def ingest(*_: Any) -> NoReturn:
    raise not_implemented()


def list_backgrounds(*_: Any) -> NoReturn:
    raise not_implemented()


def list_instruments(*_: Any) -> NoReturn:
    raise not_implemented()


def list_points(*_: Any) -> NoReturn:
    raise not_implemented()


def list_readings(*_: Any) -> NoReturn:
    raise not_implemented()


def read_point(*_: Any) -> NoReturn:
    raise not_implemented()


def read_reading(*_: Any) -> NoReturn:
    raise not_implemented()


def register_device(*_: Any) -> NoReturn:
    raise not_implemented()


def revoke_device(*_: Any) -> NoReturn:
    raise not_implemented()


def station_session(*_: Any) -> NoReturn:
    raise not_implemented()


def transition_instrument(*_: Any) -> NoReturn:
    raise not_implemented()


def update_instrument(*_: Any) -> NoReturn:
    raise not_implemented()


def update_point(*_: Any) -> NoReturn:
    raise not_implemented()


def void_reading(*_: Any) -> NoReturn:
    raise not_implemented()
