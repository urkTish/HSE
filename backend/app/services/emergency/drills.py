"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def _stub(*_: Any) -> NoReturn:
    raise not_implemented()


list_drills = _stub
create_drill = _stub
read_drill = _stub
update_drill = _stub
transition_drill = _stub
evaluate = _stub
