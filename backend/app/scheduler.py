"""Job timetable (Asia/Riyadh). Run as a separate process: ``uv run python -m app.scheduler``."""

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.clock import pin_from_env
from app.core.config import get_settings
from app.jobs import run

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hse.scheduler")


def _job(name: str) -> None:
    log.info("%s: %s", name, run(name))


def main() -> None:
    pin_from_env(
        os.environ.get("HSE_CLOCK_AT"), os.environ.get("HSE_CLOCK_MODE"), get_settings().environment
    )
    sched = BlockingScheduler(timezone="Asia/Riyadh")
    sched.add_job(_job, "interval", minutes=1, args=["unlock_expired"])
    sched.add_job(_job, "interval", hours=1, args=["invite_followups"])
    for i, name in enumerate(
        ["verify_audit_chain", "inactive_accounts", "cr_expiry_alerts", "role_assignment_ending"]
    ):
        sched.add_job(_job, "cron", hour=2, minute=i * 5, args=[name])
    sched.add_job(_job, "cron", day=1, hour=3, args=["purge_audit"])
    sched.add_job(_job, "cron", day_of_week="sun", hour=8, args=["last_manager_risk"])
    # Phase 1 (spec 1-dashboard §7 alerts, D-11 month lock, inspection generation)
    sched.add_job(_job, "cron", hour=0, minute=5, args=["inspections_missed"])
    sched.add_job(_job, "cron", hour=0, minute=10, args=["inspections_generate"])
    sched.add_job(_job, "cron", hour=1, minute=0, args=["month_auto_lock"])
    sched.add_job(_job, "cron", hour=6, minute=0, args=["completeness_check"])
    sched.add_job(_job, "cron", hour=6, minute=10, args=["leading_warnings"])
    sched.add_job(_job, "cron", hour=6, minute=20, args=["lti_free_milestones"])
    sched.add_job(_job, "cron", hour=7, minute=0, args=["ca_alerts"])
    sched.add_job(_job, "cron", hour=7, minute=5, args=["inspection_due_alerts"])
    for i, name in enumerate(["incident_alerts", "high_risk_observations", "daily_return_missing"]):
        sched.add_job(_job, "cron", minute=15 + i * 5, args=[name])
    sched.add_job(_job, "cron", day_of_week="fri", hour=3, args=["anonymise_injury_identity"])
    # Phase 2 (spec 2-access-permits §4 jobs at 00:05, §7 alerts at 07:00, 60 s cascades)
    sched.add_job(_job, "cron", hour=0, minute=5, second=30, args=["access_daily"])
    sched.add_job(_job, "cron", hour=7, minute=0, second=30, args=["credential_alerts"])
    sched.add_job(_job, "interval", minutes=1, args=["access_minute"])
    sched.add_job(_job, "cron", day_of_week="fri", hour=3, minute=30, args=["access_retention"])
    # Phase 3 (spec 3-ptw §4.1/§4.2 timers, §7 alerts, PT-16 recompute every minute)
    sched.add_job(_job, "interval", minutes=1, args=["ptw_minute"])
    sched.add_job(_job, "cron", hour=0, minute=15, args=["ptw_daily"])
    sched.start()


if __name__ == "__main__":
    main()
