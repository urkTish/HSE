"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def _stub(*_: Any) -> NoReturn:
    raise not_implemented()


list_events = _stub
declare = _stub
read_event = _stub
update_event = _stub
transition = _stub
review = _stub
