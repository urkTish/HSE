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
    # Phase 4 (spec 4-third-party-cert §4 jobs at 00:05:45, §7 alerts at 07:00, HK4-4 switch)
    sched.add_job(_job, "cron", hour=0, minute=0, second=30, args=["cert_switch"])
    sched.add_job(_job, "cron", hour=0, minute=5, second=45, args=["cert_daily"])
    sched.add_job(_job, "cron", hour=7, minute=1, args=["cert_alerts"])
    sched.add_job(_job, "interval", minutes=1, args=["cert_minute"])
    sched.add_job(_job, "cron", hour=0, minute=6, second=0, args=["training_daily"])
    sched.add_job(_job, "cron", hour=7, minute=2, args=["training_alerts"])
    sched.add_job(_job, "interval", minutes=1, args=["training_minute"])
    sched.add_job(_job, "cron", hour=0, minute=6, second=30, args=["medical_daily"])
    sched.add_job(_job, "cron", hour=7, minute=3, args=["medical_alerts"])
    sched.add_job(_job, "interval", minutes=1, args=["medical_minute"])
    # Phase 6b (spec 6b-heat-stress §4 jobs, §7 alerts)
    sched.add_job(_job, "cron", hour=0, minute=7, args=["heat_daily"])
    sched.add_job(_job, "cron", hour=7, minute=4, args=["heat_alerts"])
    sched.add_job(_job, "interval", minutes=1, args=["heat_minute"])
    # Phase 6c (spec 6c-emergency-drills §4, §7, P6c-4)
    sched.add_job(_job, "cron", hour=0, minute=8, args=["emergency_daily"])
    sched.add_job(_job, "cron", hour=7, minute=5, args=["emergency_alerts"])
    sched.add_job(_job, "interval", minutes=1, args=["emergency_minute"])
    # Phase 6d (spec 6d-field-assurance §4, §7, P6d-3)
    sched.add_job(_job, "cron", hour=0, minute=9, args=["field_daily"])
    sched.add_job(_job, "cron", hour=7, minute=6, args=["field_alerts"])
    sched.add_job(_job, "interval", minutes=1, args=["field_minute"])
    # Phase 6e (spec 6e-environmental §4, §7, P6e-2)
    sched.add_job(_job, "cron", hour=0, minute=11, args=["env_daily"])
    sched.add_job(_job, "cron", hour=7, minute=8, args=["env_alerts"])
    sched.add_job(_job, "interval", minutes=1, args=["env_minute"])
    sched.start()


if __name__ == "__main__":
    main()
