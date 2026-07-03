"""Celery application + Beat schedule for the NAAF worker.

Beat fires ``dispatch-subscriptions`` every second.  That task spawns one
child ``process-subscription`` task per entry in the SUBSCRIPTIONS registry
(currently: "agent-bus" and "notifications").

The engine/session-factory/runtime are built LAZILY (on first task invocation)
so that importing this module never opens a DB connection or requires a running
Redis broker — keeping unit tests import-safe.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from celery import Celery

from interactors.api.settings import Settings

if TYPE_CHECKING:
    from domain.agent.runtime import AgentRuntime
    from sqlalchemy.orm import sessionmaker


settings = Settings()
celery_app = Celery("naaf", broker=settings.celery_broker_url)
celery_app.conf.task_ignore_result = True
celery_app.conf.worker_concurrency = 1  # single dispatcher: preserves one-in-flight-per-recipient
celery_app.conf.beat_schedule = {
    "dispatch-subscriptions": {
        "task": "naaf.dispatch_subscriptions",
        "schedule": 1.0,
    },
}


@lru_cache(maxsize=1)
def _deps() -> tuple[sessionmaker, AgentRuntime, object]:
    """Build heavy resources once, on first use."""
    from adapters.agent.factory import build_chat_responder, build_runtime
    from adapters.database.engine import build_engine, build_session_factory

    s = Settings()
    engine = build_engine(s.db_url)
    session_factory = build_session_factory(engine)
    runtime: AgentRuntime = build_runtime(s)
    chat_responder = build_chat_responder(s)
    return session_factory, runtime, chat_responder


@celery_app.task(name="naaf.dispatch_subscriptions")
def dispatch_subscriptions_task() -> None:
    """Enqueue one child process-subscription task per registered subscription."""
    from interactors.worker.registry import SUBSCRIPTIONS

    for sub in SUBSCRIPTIONS:
        process_subscription_task.apply_async(args=[sub.name])


@celery_app.task(name="naaf.process_subscription")
def process_subscription_task(name: str) -> int:
    """Drain a single named subscription and return the number of items handled."""
    from interactors.worker.subscription_runner import run_subscription

    session_factory, runtime, chat_responder = _deps()
    return run_subscription(name, session_factory, runtime, chat_responder=chat_responder)
