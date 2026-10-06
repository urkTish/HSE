"""Test fixtures: a fresh migrated test database, re-seeded before every test."""

import os
import tempfile

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://hse:hse@localhost:5432/hse_test"
)
os.environ["DATABASE_URL"] = TEST_DB
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("SEED_PASSWORD", "Seed-Passw0rd!2026")
os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp(prefix="hse-test-storage-"))
os.environ["ANTHROPIC_API_KEY"] = ""

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Contractor, Project, ProjectEngagement, Site, User, Zone  # noqa: E402
from app.seed import seed  # noqa: E402
from app.seed_hse import seed_data  # noqa: E402

PASSWORD = os.environ["SEED_PASSWORD"]
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _migrated() -> None:
    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB)
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _fresh_data(_migrated: None) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with get_sessionmaker()() as db:
        seed(db, PASSWORD)
        db.commit()


@pytest.fixture
def db() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


class Api:
    """Thin client wrapper: ``api.as_("noura.qahtani")`` returns a logged-in client."""

    def __init__(self) -> None:
        self.anon = TestClient(app)

    def login(self, email: str, password: str = PASSWORD) -> Any:
        return TestClient(app).post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )

    def as_(self, who: str) -> TestClient:
        email = who if "@" in who else f"{who}@example.com"
        res = self.login(email)
        assert res.status_code == 200, res.text
        client = TestClient(app)
        client.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
        return client


@pytest.fixture
def api() -> Api:
    return Api()


class Ids:
    """Look up seeded ids by natural key."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def project(self, code: str) -> str:
        return str(self.db.scalar(select(Project.id).where(Project.code == code)))

    def site(self, code: str) -> str:
        return str(self.db.scalar(select(Site.id).where(Site.code == code)))

    def zone(self, code: str) -> str:
        return str(self.db.scalar(select(Zone.id).where(Zone.code == code)))

    def contractor(self, code: str) -> str:
        return str(self.db.scalar(select(Contractor.id).where(Contractor.short_code == code)))

    def engagement(self, code: str) -> str:
        return str(
            self.db.scalar(
                select(ProjectEngagement.id)
                .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
                .where(Contractor.short_code == code)
            )
        )

    def user(self, who: str) -> str:
        email = who if "@" in who else f"{who}@example.com"
        return str(self.db.scalar(select(User.id).where(User.email == email)))


@pytest.fixture
def ids(db: Session) -> Ids:
    return Ids(db)


@pytest.fixture
def hse_seed(_fresh_data: None) -> None:
    """Phase 1 volume seed (Appendix A, 13 months); loaded only by the tests that use it."""
    with get_sessionmaker()() as db:
        seed_data(db)
        db.commit()
