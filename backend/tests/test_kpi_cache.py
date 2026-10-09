"""Per-process KPI facts cache (frontend report: a dashboard fires ~15 /kpi requests)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import AuditAction, EntityType
from app.kpi import data
from app.models import HseMeeting, Project, User
from app.services import audit, hse_settings
from app.services.audit import AuditActor


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


@pytest.mark.usefixtures("hse_seed", "cache_on")
def test_a_write_from_another_process_invalidates(db: Session) -> None:
    """D-42: another API worker's committed write advances kpi_generation_seq; the next read
    here drops the cached facts instead of waiting for the TTL."""
    first = _load(db)
    assert _load(db).meetings is first.meetings
    with db.get_bind().engine.connect() as other:  # stands in for another process
        other.execute(text("SELECT nextval('kpi_generation_seq')"))
        other.commit()
    assert _load(db).meetings is not first.meetings


@pytest.mark.usefixtures("hse_seed", "cache_on")
def test_bookkeeping_writes_keep_the_cache(db: Session) -> None:
    """Logins (users.last_login_at, sessions, audit rows) and dashboard preferences are not
    KPI facts and must not force every dashboard after a login to rebuild."""
    first = _load(db)
    u = db.scalars(select(User)).first()
    assert u is not None
    u.last_login_at = now()
    audit.record(
        db, AuditAction.login_success, AuditActor(u.id), entity_type=EntityType.user, entity_id=u.id
    )
    db.commit()
    assert _load(db).meetings is first.meetings
