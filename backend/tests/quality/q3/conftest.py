"""Fixtures of the Q3 tests (spec 8-quality Part D). The shared fixtures (`qsetup`, `q_seed`) live
in `tests/quality/conftest.py`; `q3setup` adds the Q3 set-up layer (zones, points, loggers,
products, checklists, stations, schedules) without records."""

from collections.abc import Iterator

import pytest

from app.db.session import get_sessionmaker


@pytest.fixture
def q3setup(qsetup: None) -> Iterator[None]:
    from app.seed_quality_q3 import seed_setup

    with get_sessionmaker()() as db:
        seed_setup(db)
        db.commit()
    yield
