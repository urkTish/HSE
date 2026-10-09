"""Contract stubs (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def list_instruments(*_: Any) -> NoReturn:
    raise not_implemented()


def create_instrument(*_: Any) -> NoReturn:
    raise not_implemented()


def read_instrument(*_: Any) -> NoReturn:
    raise not_implemented()


def transition_instrument(*_: Any) -> NoReturn:
    raise not_implemented()


def register_device(*_: Any) -> NoReturn:
    raise not_implemented()


def revoke_device(*_: Any) -> NoReturn:
    raise not_implemented()


def list_points(*_: Any) -> NoReturn:
    raise not_implemented()


def create_point(*_: Any) -> NoReturn:
    raise not_implemented()


def update_point(*_: Any) -> NoReturn:
    raise not_implemented()


def list_stations(*_: Any) -> NoReturn:
    raise not_implemented()


def create_station(*_: Any) -> NoReturn:
    raise not_implemented()


def update_station(*_: Any) -> NoReturn:
    raise not_implemented()
