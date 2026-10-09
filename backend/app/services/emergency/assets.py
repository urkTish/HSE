"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def _stub(*_: Any) -> NoReturn:
    raise not_implemented()


list_assets = _stub
create_asset = _stub
read_asset = _stub
update_asset = _stub
transition_asset = _stub
list_checks = _stub
create_check = _stub
void_check = _stub
