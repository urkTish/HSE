"""Per-process KPI facts cache (frontend report: a dashboard fires ~15 /kpi requests)."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import AuditAction, EntityType
from app.kpi import data
from app.kpi.facts import Facts
from app.models import HseMeeting, Project, User
from app.services import audit, hse_settings
from app.services.audit import AuditActor


@pytest.fixture
def cache_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(get_settings(), "kpi_cache_seconds", 20)
    monkeypatch.setattr(get_settings(), "kpi_warm", False)  # no background rebuilds here
    data.clear_cache()
    yield
    data.clear_cache()


def _load(db: Session) -> Facts:
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


@pytest.mark.usefixtures("hse_seed", "cache_on")
def test_warm_builds_every_section_of_a_scope(db: Session) -> None:
    """Dashboard cold load: app.kpi.warm builds a scope's facts and every lazy section (and
    the training requirement base) off the request path, so the next read finds them."""
    from app.kpi import train_facts, warm

    p = db.scalars(select(Project).where(Project.code == "ANIA-EXP")).one()
    key = (p.id,)
    db.commit()  # the warm session must see the seeded rows
    warm.warm(key)
    facts = data.cached(db, key)
    assert facts is not None
    for part in ("_access", "_ptw", "_cert", "_train", "_med"):
        assert getattr(facts, part) is not None, part
    assert ("base", p.id) in train_facts._SHARED


def test_warm_is_off_without_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.kpi import warm

    monkeypatch.setattr(get_settings(), "kpi_cache_seconds", 0)
    assert not warm.enabled()
    warm.note([(uuid.uuid4(),)])
    assert not warm._PENDING


@pytest.mark.usefixtures("hse_seed", "cache_on")
def test_ai_insight_cache_writes_keep_the_cache(db: Session) -> None:
    """The dashboard's insights panel stores its result on a view; that is not a KPI fact."""
    from app.models import AiInsightCache

    first = _load(db)
    p = db.scalars(select(Project)).first()
    assert p is not None
    db.add(AiInsightCache(cache_key=uuid.uuid4().hex, project_id=p.id, payload={}))
    db.commit()
    assert _load(db).meetings is first.meetings


@pytest.mark.usefixtures("hse_seed", "cache_on")
def test_a_default_settings_row_keeps_the_cache(db: Session) -> None:
    """Every module creates a project's settings row with its defaults on first read (the
    All-projects dashboard did so for a project made by an earlier test), which cleared every
    cached scope; editing settings still does."""
    from app.models import FieldSettings
    from app.services.field import common as fcommon

    p = db.scalars(select(Project).where(Project.code == "ANIA-EXP")).one()
    row = db.get(FieldSettings, p.id)
    if row is not None:
        db.delete(row)
        db.commit()
    first = _load(db)
    created = fcommon.settings_row(db, p.id)
    db.commit()
    assert _load(db).meetings is first.meetings
    created.values = {**created.values, "tbt_min_minutes": 20}
    db.commit()
    assert _load(db).meetings is not first.meetings


@pytest.mark.usefixtures("emergency_seed", "cache_on")
def test_emergency_readiness_is_shared_by_requests(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dashboard's warnings ask for K-107 asset readiness four times per request (about
    0.7 s each); requests over the same cached facts now compute it once."""
    from datetime import date

    from app.kpi import emergency
    from app.kpi.periods import Window
    from app.services.emergency import assets

    calls: list[object] = []
    real = assets.ready_map
    monkeypatch.setattr(assets, "ready_map", lambda *a, **k: calls.append(a) or real(*a, **k))
    p = db.scalars(select(Project).where(Project.code == "ANIA-EXP")).one()
    w = Window(date(2026, 9, 1), date(2026, 9, 30))

    def stats() -> object:
        from app.hse_jobs import project_scope

        return emergency.asset_stats(project_scope(db, p, date(2026, 10, 2)).engine, w)

    first = stats()
    n = len(calls)
    assert n > 0
    assert stats() == first
    assert len(calls) == n  # a second request over the same cached facts: no recomputation


@pytest.mark.usefixtures("hse_seed")
def test_snapshot_ignores_row_order(db: Session) -> None:
    """CI run 85 (AC65): the AI answer cache keys on the KPI snapshot; the fact loads have no
    ORDER BY, so a plan change between two asks reordered rows and missed the cache."""
    from datetime import date

    from app.hse_jobs import project_scope
    from app.kpi import service

    p = db.scalars(select(Project).where(Project.code == "ANIA-EXP")).one()
    sc = project_scope(db, p, date(2026, 10, 2))
    first = service.snapshot(sc)
    e = sc.engine
    for rows in (e.wf, e.all_cases, e.events, e.obs, e.insp, e.cas, e.meetings):
        assert len(rows) > 1
        rows.reverse()
    sc.facts.memo.clear()
    assert service.snapshot(sc) == first
