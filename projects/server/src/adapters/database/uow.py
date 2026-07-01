from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from adapters.database.repositories import (
    AgentDefinitionRepository,
    NotificationRepository,
    ProjectRepository,
    RunEventRepository,
    RunRepository,
    TeamRepository,
    WorkItemRepository,
)


class SqlUnitOfWork:
    """Owns one session + transaction boundary. Repositories share that session
    and apply required_filters for owner-scoping."""

    def __init__(
        self,
        session_factory: sessionmaker,
        required_filters: dict[str, Any] | None = None,
    ):
        self._session_factory = session_factory
        self._required_filters = required_filters or {}
        self._session: Session | None = None
        self._repos: dict[str, Any] = {}

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = self._session_factory()
        return self._session

    @contextmanager
    def transaction(self) -> Iterator["SqlUnitOfWork"]:
        session = self.session
        try:
            yield self
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            self._session = None
            self._repos = {}

    def _repo(self, name: str, cls: type) -> Any:
        if name not in self._repos:
            self._repos[name] = cls(self.session, required_filters=self._required_filters)
        return self._repos[name]

    @property
    def projects(self) -> ProjectRepository:
        return self._repo("projects", ProjectRepository)

    @property
    def work_items(self) -> WorkItemRepository:
        return self._repo("work_items", WorkItemRepository)

    @property
    def teams(self) -> TeamRepository:
        return self._repo("teams", TeamRepository)

    @property
    def agent_definitions(self) -> AgentDefinitionRepository:
        return self._repo("agent_definitions", AgentDefinitionRepository)

    @property
    def runs(self) -> RunRepository:
        return self._repo("runs", RunRepository)

    @property
    def run_events(self) -> RunEventRepository:
        return self._repo("run_events", RunEventRepository)

    @property
    def notifications(self) -> NotificationRepository:
        return self._repo("notifications", NotificationRepository)
