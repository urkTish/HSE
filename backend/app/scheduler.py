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
    sched.start()


if __name__ == "__main__":
    main()
