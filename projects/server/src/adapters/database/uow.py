from naaf_db.async_uow import AsyncUnitOfWorkBase
from naaf_db.uow import SqlUnitOfWorkBase

from adapters.database.repositories import (
    AgentDefinitionRepository,
    AgentEventRepository,
    AsyncAgentEventRepository,
    AsyncRunEventRepository,
    AttachmentRepository,
    BusMessageRepository,
    MessageRepository,
    NotificationRepository,
    ProjectRepository,
    RunEventRepository,
    RunRepository,
    SecretRepository,
    TeamRepository,
    WorkItemRepository,
)


class SqlUnitOfWork(SqlUnitOfWorkBase):
    """Owns one session + transaction boundary. Repositories share that session
    and apply required_filters for owner-scoping."""

    @property
    def attachments(self) -> AttachmentRepository:
        return self._repo("attachments", AttachmentRepository)

    @property
    def projects(self) -> ProjectRepository:
        return self._repo("projects", ProjectRepository)

    @property
    def secrets(self) -> SecretRepository:
        return self._repo("secrets", SecretRepository)

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
    def agent_events(self) -> AgentEventRepository:
        return self._repo("agent_events", AgentEventRepository)

    @property
    def notifications(self) -> NotificationRepository:
        return self._repo("notifications", NotificationRepository)

    @property
    def messages(self) -> MessageRepository:
        return self._repo("messages", MessageRepository)

    @property
    def bus_messages(self) -> BusMessageRepository:
        return self._repo("bus_messages", BusMessageRepository)

    def delete_project_cascade(self, project_id: str) -> None:
        """Delete a project and every descendant, in dependency order, within
        this transaction. Un-FK'd tables (runs/events/notifications/bus_messages/
        messages/agent_events) are cleaned up explicitly because a DB-level
        ON DELETE CASCADE cannot reach them."""
        wi_ids = [
            w.id
            for w in self.work_items.read_multi(
                filters={"project_id": project_id}, page_size=0
            ).results
        ]
        run_ids = [
            r.id
            for r in self.runs.read_multi(
                filters={"project_id": project_id}, page_size=0
            ).results
        ]

        if run_ids:
            self.run_events.delete_where(run_id__in=run_ids)
            self.notifications.delete_where(run_id__in=run_ids)
            self.bus_messages.delete_by_run_ids(run_ids)

        scopes = (
            [f"run:{rid}" for rid in run_ids]
            + [f"thread:{wid}" for wid in wi_ids]
            + [f"thread:project:{project_id}"]
        )
        self.agent_events.delete_where(scope__in=scopes)

        thread_ids = [*wi_ids, f"project:{project_id}"]
        self.messages.delete_where(thread_id__in=thread_ids)

        if wi_ids:
            self.attachments.delete_where(work_item_id__in=wi_ids)

        self.runs.delete_where(project_id=project_id)
        self.work_items.delete_where(project_id=project_id)
        self.projects.delete(project_id)


class AsyncUnitOfWork(AsyncUnitOfWorkBase):
    """Async sibling of SqlUnitOfWork. Read-mostly repos for streaming reads
    off the event loop; writes stay on the sync path via SqlUnitOfWork."""

    @property
    def agent_events(self) -> AsyncAgentEventRepository:
        return self._repo("agent_events", AsyncAgentEventRepository)

    @property
    def run_events(self) -> AsyncRunEventRepository:
        return self._repo("run_events", AsyncRunEventRepository)
