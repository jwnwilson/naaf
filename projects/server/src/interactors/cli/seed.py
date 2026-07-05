from adapters.database.engine import build_engine, build_session_factory
from adapters.database.uow import SqlUnitOfWork
from domain.project import Project
from domain.team import AgentDefinition, AgentRole, Team
from domain.work_item import Priority, WorkItem, WorkItemKind, WorkItemStatus
from sqlalchemy.orm import sessionmaker

from interactors.api.settings import Settings

DEFAULT_TEAM_NAME = "Default Team"
DEFAULT_ROLES = [AgentRole.LEAD, AgentRole.BACKEND, AgentRole.QA]

DEMO_PROJECT_NAME = "Demo Project"
DEMO_PROJECT_REPO = "git@github.com:acme/demo.git"

# epic → feature → tasks, so seeded items carry real lineage (key/epicName/featureName)
DEMO_EPIC = (WorkItemKind.EPIC, "Core Infrastructure", WorkItemStatus.DONE, Priority.HIGH)
DEMO_FEATURE = (WorkItemKind.FEATURE, "CI & Auth", WorkItemStatus.IN_PROGRESS, Priority.HIGH)
# tasks hang under the feature
_DEMO_TASKS: list[tuple[str, WorkItemStatus, Priority]] = [
    ("Set up CI pipeline", WorkItemStatus.IN_REVIEW, Priority.HIGH),
    ("Implement authentication", WorkItemStatus.IN_PROGRESS, Priority.URGENT),
    ("Design database schema", WorkItemStatus.TODO, Priority.MEDIUM),
    ("Write API documentation", WorkItemStatus.BACKLOG, Priority.LOW),
    ("Add end-to-end tests", WorkItemStatus.BACKLOG, Priority.MEDIUM),
]


def seed_default_team(session_factory: sessionmaker, owner_id: str) -> str:
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner_id})
    with uow.transaction():
        existing = uow.teams.read_multi(filters={"name": DEFAULT_TEAM_NAME})
        if existing.total:
            return existing.results[0].id
        team = uow.teams.create(Team(owner_id=owner_id, name=DEFAULT_TEAM_NAME))
        for role in DEFAULT_ROLES:
            uow.agent_definitions.create(
                AgentDefinition(owner_id=owner_id, team_id=team.id, role=role)
            )
        return team.id


def seed_demo(session_factory: sessionmaker, owner_id: str) -> str:
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": owner_id})
    with uow.transaction():
        existing = uow.projects.read_multi(filters={"name": DEMO_PROJECT_NAME})
        if existing.total:
            return existing.results[0].id
        project = uow.projects.create(
            Project(owner_id=owner_id, name=DEMO_PROJECT_NAME, repo_url=DEMO_PROJECT_REPO)
        )
        kind, title, status, priority = DEMO_EPIC
        epic = uow.work_items.create(
            WorkItem(
                owner_id=owner_id,
                project_id=project.id,
                kind=kind,
                title=title,
                status=status,
                priority=priority,
            )
        )
        kind, title, status, priority = DEMO_FEATURE
        feature = uow.work_items.create(
            WorkItem(
                owner_id=owner_id,
                project_id=project.id,
                parent_id=epic.id,
                kind=kind,
                title=title,
                status=status,
                priority=priority,
            )
        )
        for title, status, priority in _DEMO_TASKS:
            uow.work_items.create(
                WorkItem(
                    owner_id=owner_id,
                    project_id=project.id,
                    parent_id=feature.id,
                    kind=WorkItemKind.TASK,
                    title=title,
                    status=status,
                    priority=priority,
                )
            )
        return project.id


def main() -> None:
    settings = Settings()
    engine = build_engine(settings.db_url)
    session_factory = build_session_factory(engine)
    seed_default_team(session_factory, owner_id=settings.dev_owner_id)
    seed_demo(session_factory, owner_id=settings.dev_owner_id)


if __name__ == "__main__":
    main()
