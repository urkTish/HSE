"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def _stub(*_: Any) -> NoReturn:
    raise not_implemented()


list_erps = _stub
create_erp = _stub
read_erp = _stub
update_erp = _stub
transition_erp = _stub
list_aps = _stub
create_ap = _stub
update_ap = _stub
list_contacts = _stub
create_contact = _stub
update_contact = _stub
list_profiles = _stub
put_profile = _stub
