"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def _stub(*_: Any) -> NoReturn:
    raise not_implemented()


list_audits = _stub
create_audit = _stub
read_audit = _stub
update_audit = _stub
save_answers = _stub
transition_audit = _stub
programme = _stub
