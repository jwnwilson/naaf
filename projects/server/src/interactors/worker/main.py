import logging
import time

from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.bus.sql import SqlMessageBus
from adapters.database.engine import build_engine, build_session_factory

from interactors.api.settings import Settings
from interactors.worker.processor import process_next

_IDLE_SLEEP_SECONDS = 0.5


def run_forever() -> None:
    settings = Settings()
    session_factory = build_session_factory(build_engine(settings.db_url))
    bus, runtime = SqlMessageBus(), FakeAgentRuntime()
    while True:
        try:
            if not process_next(session_factory, bus, runtime):
                time.sleep(_IDLE_SLEEP_SECONDS)
        except Exception:
            logging.exception("worker: unhandled error in process_next loop")


if __name__ == "__main__":
    run_forever()
