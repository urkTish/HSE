"""Fixtures of the integration tests (spec 8-quality §6, handover §7.5): where the packages meet.

`qi_world` = the full Appendix A world of every part (Q0 … Q4 seeds, both profiles) saved once per
session as a template database and cloned per test, with the clock at HSE_CLOCK_AT
(2026-10-06 10:00 Riyadh). `qi_libs` = Quality set up on both projects plus the Q1 checklist
library, the Q2 libraries and people, and the Q3 set-up layer (zones, points, loggers, products),
without records."""

from collections.abc import Iterator

import pytest
from sqlalchemy import text

from app.db.base import Base
from app.db.session import get_engine, get_sessionmaker
from tests.conftest import (
    PASSWORD,
    TEST_DB,
    _admin_exec,
    _clone,
    _db_name,
    _terminate,
)

QI_TEMPLATE = TEST_DB.rsplit("/", 1)[1] + "_qi_tpl"


@pytest.fixture(scope="session")
def _qi_template(_migrated: None) -> str:
    from datetime import UTC, datetime

    from app.core.clock import set_now
    from app.seed import seed
    from app.seed_quality import seed_quality_data

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    set_now(datetime(2026, 10, 6, 7, 0, tzinfo=UTC))
    try:
        with get_sessionmaker()() as db:
            seed(db, PASSWORD)
            db.commit()
            seed_quality_data(db)
            db.commit()
    finally:
        set_now(None)
    get_engine().dispose()
    name = _db_name()
    _admin_exec(
        _terminate(name),
        f"DROP DATABASE IF EXISTS {QI_TEMPLATE}",
        f"CREATE DATABASE {QI_TEMPLATE} TEMPLATE {name}",
    )
    return QI_TEMPLATE


@pytest.fixture
def qi_world(_fresh_data: None, _qi_template: str, clock: None) -> Iterator[None]:
    """A copy of the full Quality world (every part's Appendix A seed, both profiles)."""
    _clone(_qi_template)
    yield


@pytest.fixture
def qi_libs(qsetup: None) -> Iterator[None]:
    from app.seed_quality_q1 import ensure_library
    from app.seed_quality_q2 import seed_libraries, seed_people
    from app.seed_quality_q3 import seed_setup

    with get_sessionmaker()() as db:
        ensure_library(db)
        seed_libraries(db)
        seed_people(db)
        seed_setup(db)
        db.commit()
    yield
