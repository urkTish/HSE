"""Spec 2-access-permits §4 jobs, §6.3 alert dates and §7 alerts (AC9, AC16, AC31, AC38, LC-3)."""

from sqlalchemy.orm import Session

from app import access_jobs
from app.core.clock import frozen
from app.core.enums import NotificationKind
from tests.access_helpers import NOON, notifications, worker
from tests.conftest import Ids


def test_P2AC9_worker_id_14_day_alert_to_rep_without_id_number(
    access_seed: None, db: Session, ids: Ids
) -> None:
    with frozen(NOON):
        access_jobs.credential_alerts(db)
        db.commit()
    w = worker(db, "Osman Idris")
    rows = notifications(db, NotificationKind.worker_id_expiry, w.id)
    assert rows, "no worker_id_expiry alert"
    assert {str(n.user_id) for n in rows} >= {ids.user("ahmed.zahrani")}
    for n in rows:
        assert "(14 days)" in n.title_en
        assert "2000001009" not in n.title_en + n.title_ar
    with frozen(NOON):
        again = access_jobs.credential_alerts(db)
    assert again["worker_id"] == 0
