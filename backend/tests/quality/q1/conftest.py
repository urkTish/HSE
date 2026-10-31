"""Fixtures of the Q1 tests. The shared fixtures (`qsetup`, `q_seed`) live in
`tests/quality/conftest.py`; `q1lib` adds the Part B checklist library on top of `qsetup`."""

from collections.abc import Iterator

import pytest

from app.db.session import get_sessionmaker


@pytest.fixture
def q1lib(qsetup: None) -> Iterator[None]:
    from app.seed_quality_q1 import ensure_library

    with get_sessionmaker()() as db:
        ensure_library(db)
        db.commit()
    yield
