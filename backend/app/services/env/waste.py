"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def create_area(*_: Any) -> NoReturn:
    raise not_implemented()


def create_consignment(*_: Any) -> NoReturn:
    raise not_implemented()


def list_areas(*_: Any) -> NoReturn:
    raise not_implemented()


def list_consignments(*_: Any) -> NoReturn:
    raise not_implemented()


def list_streams(*_: Any) -> NoReturn:
    raise not_implemented()


def read_area(*_: Any) -> NoReturn:
    raise not_implemented()


def read_consignment(*_: Any) -> NoReturn:
    raise not_implemented()


def record_receipt(*_: Any) -> NoReturn:
    raise not_implemented()


def transition_consignment(*_: Any) -> NoReturn:
    raise not_implemented()


def update_area(*_: Any) -> NoReturn:
    raise not_implemented()


def update_consignment(*_: Any) -> NoReturn:
    raise not_implemented()


def upsert_stream(*_: Any) -> NoReturn:
    raise not_implemented()
