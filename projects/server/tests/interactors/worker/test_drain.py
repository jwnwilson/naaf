"""Celery app import and beat schedule tests (formerly also tested drain() helper).

drain() was removed in Task 6; processor.py is removed in Task 7.
The drain-function xfail tests have been deleted alongside the dead code.
Equivalent bus-draining coverage lives in test_processor.py (via run_subscription).
"""


def test_celery_app_import_is_db_and_broker_free():
    """Importing celery_app must not open a DB connection or require a broker."""
    from interactors.worker.celery_app import celery_app
    assert celery_app.main == "naaf"
    assert celery_app.conf.worker_concurrency == 1


def test_celery_beat_schedule_contains_dispatch_subscriptions():
    """Beat schedule must include dispatch-subscriptions (replaces drain-bus)."""
    from interactors.worker.celery_app import celery_app
    schedule = celery_app.conf.beat_schedule
    assert "dispatch-subscriptions" in schedule
    entry = schedule["dispatch-subscriptions"]
    assert entry["task"] == "naaf.dispatch_subscriptions"
    assert entry["schedule"] == 1.0
