"""Per-process KPI facts cache (frontend report: a dashboard fires ~15 /kpi requests)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.kpi import data
from app.models import HseMeeting, Project
from app.services import hse_settings


@pytest.fixture
def cache_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(get_settings(), "kpi_cache_seconds", 20)
    data.clear_cache()
    yield
    data.clear_cache()


def _load(db: Session) -> data.Facts:
    projects = list(db.scalars(select(Project).order_by(Project.code)))
    return data.load(db, projects, {p.id: hse_settings.get(db, p.id) for p in projects})


@pytest.mark.usefixtures("hse_seed", "cache_on")
def test_cache_reuses_facts_until_a_write_commits(db: Session) -> None:
    first = _load(db)
    second = _load(db)
    assert second is not first  # each request gets its own shallow copy …
    assert second.meetings is first.meetings  # … over the same cached lists
    m = db.scalars(select(HseMeeting)).first()
    assert m is not None
    m.attended_count = (m.attended_count or 0) + 1
    db.commit()
    third = _load(db)
    assert third.meetings is not first.meetings
    assert any(x.attended == m.attended_count for x in third.meetings if x.id == m.id)


@pytest.mark.usefixtures("hse_seed", "cache_on")
def test_access_facts_load_once_and_are_shared(db: Session) -> None:
    _load(db)
    second = _load(db)
    acc = second.access
    assert acc is not None
    third = _load(db)
    assert third.access is acc
