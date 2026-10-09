"""Background warming of the KPI facts cache (dashboard cold load).

A cold dashboard read loads every fact section of its scope (incidents and hours, access, PTW,
certification, training with the per-project requirement base, medical): about 5 s for
ANIA-EXP and 4 s more for All projects, while any committed fact write clears the whole cache.
This module rebuilds, off the request path, the scopes that were cached when a write cleared
them (and, at startup, each project and the all-projects scope), once the writes have settled
for `KPI_WARM_DELAY` seconds. A request that arrives mid-build waits on the same single-flight
locks (app.kpi.data) instead of starting a second build.

Off when the cache is off (kpi_cache_seconds = 0, as in the test suite) or kpi_warm is false.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterable

from sqlalchemy import select

from app.core.config import get_settings

log = logging.getLogger(__name__)

KPI_WARM_DELAY = 1.5  # seconds without a new fact write before rebuilding

_LOCK = threading.Lock()
_PENDING: set[tuple[uuid.UUID, ...]] = set()
_LAST_NOTE = [0.0]
_WAKE = threading.Event()
_THREAD: list[threading.Thread | None] = [None]


def enabled() -> bool:
    s = get_settings()
    return s.kpi_cache_seconds > 0 and s.kpi_warm


def note(keys: Iterable[tuple[uuid.UUID, ...]]) -> None:
    """Scopes whose cached facts were just dropped; rebuilt once writes settle."""
    keys = [k for k in keys if k]
    if not keys or not enabled():
        return
    with _LOCK:
        _PENDING.update(keys)
        _LAST_NOTE[0] = time.monotonic()
    _ensure_thread()
    _WAKE.set()


def start() -> None:
    """Warm each project and the all-projects scope (app startup)."""
    if not enabled():
        return
    from app.db.session import get_sessionmaker  # noqa: PLC0415
    from app.models import Project  # noqa: PLC0415

    try:
        with get_sessionmaker()() as db:
            pids = sorted(db.scalars(select(Project.id)))
    except Exception:  # noqa: BLE001 - database not ready / not migrated: nothing to warm
        log.warning("kpi warm: project list unavailable", exc_info=True)
        return
    note([(p,) for p in pids] + ([tuple(pids)] if len(pids) > 1 else []))


def _ensure_thread() -> None:
    with _LOCK:
        t = _THREAD[0]
        if t is not None and t.is_alive():
            return
        t = threading.Thread(target=_run, name="kpi-warm", daemon=True)
        _THREAD[0] = t
    t.start()


def _run() -> None:
    while True:
        _WAKE.wait()
        while True:  # debounce: wait until no write has been noted for KPI_WARM_DELAY
            with _LOCK:
                left = _LAST_NOTE[0] + KPI_WARM_DELAY - time.monotonic()
            if left <= 0:
                break
            time.sleep(left)
        with _LOCK:
            keys = sorted(_PENDING)
            _PENDING.clear()
            _WAKE.clear()
        for key in keys:
            with _LOCK:
                if _PENDING:  # a newer write: its rebuild supersedes this one
                    break
            try:
                warm(key)
            except Exception:  # noqa: BLE001 - warming is best effort; requests still build
                log.warning("kpi warm failed for %s", key, exc_info=True)


def warm(key: tuple[uuid.UUID, ...]) -> None:
    """Build and cache every fact section of one scope (the projects in `key`)."""
    from app.db.session import get_sessionmaker  # noqa: PLC0415
    from app.kpi import data  # noqa: PLC0415
    from app.models import Project  # noqa: PLC0415
    from app.services import hse_settings  # noqa: PLC0415

    with get_sessionmaker()() as db:
        projects = list(db.scalars(select(Project).where(Project.id.in_(key))))
        if len(projects) != len(key):
            return  # a project went away
        hse = {p.id: hse_settings.get(db, p.id) for p in projects}
        data.load(db, projects, hse)
        facts = data.cached(db, key)
        if facts is None:  # a write landed during the build
            return
        _ = (facts.access, facts.ptw, facts.cert, facts.med)
        train = facts.train
        if train is not None:
            for pid in key:
                train._base(pid)
        db.rollback()
