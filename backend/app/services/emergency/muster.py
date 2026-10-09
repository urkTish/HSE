"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def _stub(*_: Any) -> NoReturn:
    raise not_implemented()


read_muster = _stub
scan = _stub
tick = _stub
resolve = _stub
put_counts = _stub
sheet = _stub
void = _stub
register_device = _stub
revoke_device = _stub
device_session = _stub
device_scan = _stub
