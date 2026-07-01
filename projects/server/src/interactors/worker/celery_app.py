"""Celery application + Beat schedule for the NAAF agent-bus drain task.

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
celery_app.conf.beat_schedule = {
    "drain-bus": {
        "task": "naaf.drain_bus",
        "schedule": 1.0,
    }
}


@lru_cache(maxsize=1)
def _deps() -> tuple[sessionmaker, AgentRuntime]:
    """Build heavy resources once, on first use."""
    from adapters.agent.runtime.fake import FakeAgentRuntime
    from adapters.database.engine import build_engine, build_session_factory

    engine = build_engine(Settings().db_url)
    session_factory = build_session_factory(engine)
    runtime: AgentRuntime = FakeAgentRuntime()
    return session_factory, runtime


def drain(session_factory: sessionmaker, runtime: AgentRuntime, max_per_tick: int = 100) -> int:
    """Drain the message bus, processing up to *max_per_tick* messages.

    Returns the number of messages processed.  Pure function — no Celery
    dependency — so it can be tested without a broker.
    """
    from interactors.worker.processor import process_next

    count = 0
    while count < max_per_tick:
        processed = process_next(session_factory, runtime)
        if not processed:
            break
        count += 1
    return count


@celery_app.task(name="naaf.drain_bus")
def drain_bus() -> int:
    sf, rt = _deps()
    return drain(sf, rt)
