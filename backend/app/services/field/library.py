"""Contract stub (stage 1)."""

from typing import Any, NoReturn

from app.core.errors import not_implemented


def _stub(*_: Any) -> NoReturn:
    raise not_implemented()


list_templates = _stub
create_template = _stub
read_template = _stub
update_template = _stub
delete_template = _stub
new_version = _stub
transition_template = _stub
list_topics = _stub
create_topic = _stub
read_topic = _stub
update_topic = _stub
delete_topic = _stub
new_topic_version = _stub
transition_topic = _stub
