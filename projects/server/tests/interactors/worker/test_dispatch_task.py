"""Beat schedule now uses dispatch-subscriptions (Task 6).
Old dispatch-events entry was removed; covered by test_celery_subscriptions.py.
"""


def test_celery_registers_dispatch_subscriptions_beat():
    from interactors.worker.celery_app import celery_app
    assert "dispatch-subscriptions" in celery_app.conf.beat_schedule
    assert (
        celery_app.conf.beat_schedule["dispatch-subscriptions"]["task"]
        == "naaf.dispatch_subscriptions"
    )
