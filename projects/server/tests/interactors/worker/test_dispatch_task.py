def test_celery_registers_dispatch_events_beat():
    from interactors.worker.celery_app import celery_app
    assert "dispatch-events" in celery_app.conf.beat_schedule
    assert celery_app.conf.beat_schedule["dispatch-events"]["task"] == "naaf.dispatch_events"
