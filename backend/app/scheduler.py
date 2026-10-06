"""Job timetable (Asia/Riyadh). Run as a separate process: ``uv run python -m app.scheduler``."""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app.jobs import run

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hse.scheduler")


def _job(name: str) -> None:
    log.info("%s: %s", name, run(name))


def main() -> None:
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
    sched.start()


if __name__ == "__main__":
    main()
