"""Helpers for Phase 5 tests (5-training Appendix A world, clock 2026-10-06 10:00 Riyadh).

Tests use the ``train_seed`` fixture (Phase 0-4 template + the Phase 5 seed, cloned per test)
and ``clock``. Service calls take a Principal from ``P(db, "noura.qahtani")``; API calls use
``tests.conftest.Api``.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    TrainingCourse,
    TrainingProvider,
    TrainingRecord,
    TrainingSession,
    Worker,
)
from tests.cert_helpers import API, CLOCK, P, at, err_code, project, riyadh

__all__ = [
    "API",
    "CLOCK",
    "P",
    "at",
    "course",
    "err_code",
    "kpi",
    "project",
    "provider",
    "record",
    "riyadh",
    "session",
    "to_csv",
    "worker",
]


def worker(db: Session, no_or_name: str) -> Worker:
    q = (
        select(Worker).where(Worker.worker_no == no_or_name)
        if no_or_name.startswith("WKR-")
        else select(Worker).where(Worker.full_name_en == no_or_name).order_by(Worker.worker_no)
    )
    w = db.scalars(q).first()
    assert w is not None, no_or_name
    return w


def session(db: Session, no: str) -> TrainingSession:
    s = db.scalar(select(TrainingSession).where(TrainingSession.session_no == no))
    assert s is not None, no
    return s


def provider(db: Session, code: str) -> TrainingProvider:
    pv = db.scalar(select(TrainingProvider).where(TrainingProvider.provider_code == code))
    assert pv is not None, code
    return pv


def course(db: Session, code: str) -> TrainingCourse:
    c = db.scalar(select(TrainingCourse).where(TrainingCourse.code == code))
    assert c is not None, code
    return c


def record(db: Session, worker_no: str, code: str) -> TrainingRecord:
    w = worker(db, worker_no)
    r = db.scalars(
        select(TrainingRecord)
        .where(TrainingRecord.worker_id == w.id, TrainingRecord.course_code == code)
        .order_by(TrainingRecord.completed_on.desc())
    ).first()
    assert r is not None, (worker_no, code)
    return r


def kpi(body: dict[str, Any], metric: str) -> dict[str, Any]:
    if "-" not in metric:
        metric = f"{metric[0]}-{metric[1:]}"
    for m in body["metrics"]:
        if m["metric"] == metric:
            return m  # type: ignore[no-any-return]
    raise AssertionError(metric)


def to_csv(head: list[str], rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=head)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in head})
    return buf.getvalue().encode()
