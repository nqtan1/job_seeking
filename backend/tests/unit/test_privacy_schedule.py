"""The retention sweeps and the daily reminder digest are registered as periodic tasks on the worker app (P2-31)."""

from recruitai.worker import app


def test_the_sweeps_reminders_and_radar_are_scheduled_on_the_worker():
    scheduled = {p.task.name for p in app.periodic_registry.periodic_tasks.values()}
    assert scheduled == {
        "privacy:sweep_job_search_cache",
        "privacy:sweep_exports",
        "privacy:sweep_ai_calls",
        "privacy:sweep_inactive_accounts",
        "privacy:sweep_radar_runs",
        "identity:send_application_reminders",
        "radar:run_all",
        "radar:retry_interrupted",
    }
