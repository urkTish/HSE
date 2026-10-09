"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def _stub(*_: Any) -> NoReturn:
    raise not_implemented()


list_campaigns = _stub
create_campaign = _stub
read_campaign = _stub
update_campaign = _stub
transition_campaign = _stub
