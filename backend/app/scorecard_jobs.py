"""Phase 6g scheduled jobs (6g-scorecard-reports §4, §7, SC-1…SC-4, EX-7, EX-8).

`scorecard_monthly` (06:00): issue the previous month's cards once the month is Locked (SC-1).
`scorecard_daily` (00:20): comment window, dispute due / overdue, finalise due, PIP, restatement.
`report_pack_daily` (07:00): MCR / OSHA300 / HEAT drafts, due alerts, restatement watch.
`export_jobs` (every minute): queued exports. `export_subscriptions` (05:30). `export_purge`
(03:00): expired export files.

Every step is de-duplicated per (subject, step) through JobMark."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import now


def scorecard_monthly(db: Session) -> dict[str, Any]:
    from app.services.scorecard import cards  # noqa: PLC0415

    return cards.run_monthly(db, now())


def scorecard_daily(db: Session) -> dict[str, Any]:
    from app.services.scorecard import cards  # noqa: PLC0415

    return cards.run_daily(db, now())


def report_pack_daily(db: Session) -> dict[str, Any]:
    from app.services.scorecard import packs  # noqa: PLC0415

    return packs.run_daily(db, now())


def export_jobs(db: Session) -> dict[str, Any]:
    from app.services.scorecard import exports  # noqa: PLC0415

    return {"processed": exports.run_queue(db, now())}


def export_subscriptions(db: Session) -> dict[str, Any]:
    from app.services.scorecard import exports  # noqa: PLC0415

    return {"created": exports.run_subscriptions(db, now())}


def export_purge(db: Session) -> dict[str, Any]:
    from app.services.scorecard import exports  # noqa: PLC0415

    return {"expired": exports.purge(db, now())}


PHASE6G_JOBS = {
    "scorecard_monthly": scorecard_monthly,
    "scorecard_daily": scorecard_daily,
    "report_pack_daily": report_pack_daily,
    "export_jobs": export_jobs,
    "export_subscriptions": export_subscriptions,
    "export_purge": export_purge,
}
