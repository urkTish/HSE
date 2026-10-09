"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def _stub(*_: Any) -> NoReturn:
    raise not_implemented()


list_talks = _stub
create_talk = _stub
read_talk = _stub
add_attendance = _stub
remove_attendance = _stub
void_talk = _stub
suggestions = _stub
