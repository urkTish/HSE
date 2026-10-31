"""Fixtures of the Q2 tests (the shared `qsetup` / `q_seed` live in `tests/quality/conftest.py`).
`q2` = Quality configured on both projects plus the Q2 libraries (test types, competence
requirements, cert types, courses) and the workers of the quality users; the clock is
HSE_CLOCK_AT 2026-10-06 10:00 Riyadh."""

from collections.abc import Iterator

import pytest

from app.db.session import get_sessionmaker


@pytest.fixture
def q2(qsetup: None) -> Iterator[None]:
    from app.seed_quality_q2 import seed_libraries, seed_people

    with get_sessionmaker()() as db:
        seed_libraries(db)
        seed_people(db)
        db.commit()
    yield
