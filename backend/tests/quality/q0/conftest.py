"""Fixtures of the Q0 tests (spec 8-quality §A.16). Every test starts from the Phase 0 seed (which
includes the Quality base layer: RUH-CCH and the quality users of Appendix A.1) with the clock at
HSE_CLOCK_AT 2026-10-06 10:00 Riyadh; `qsetup` configures Quality on both projects (profiles,
positions and holders, default matrix, suppliers, criteria, customers, systems) without records,
and `q_seed` loads the full Q0 Appendix A records on top."""

from collections.abc import Iterator

import pytest

from app.db.session import get_sessionmaker


@pytest.fixture
def qsetup(_fresh_data: None, clock: None) -> Iterator[None]:
    from app.seed_quality import seed_quality_setup

    with get_sessionmaker()() as db:
        seed_quality_setup(db)
        db.commit()
    yield


@pytest.fixture
def q_seed(_fresh_data: None, clock: None) -> Iterator[None]:
    from app.seed_quality import seed_quality_data

    with get_sessionmaker()() as db:
        seed_quality_data(db)
        db.commit()
    yield
