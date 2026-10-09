"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def _stub(*_: Any) -> NoReturn:
    raise not_implemented()


list_roster = _stub
create_assignment = _stub
end_assignment = _stub
list_teams = _stub
create_team = _stub
read_team = _stub
update_team = _stub
coverage = _stub
