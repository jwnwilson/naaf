from adapters.database.engine import build_engine, build_session_factory
from adapters.database.uow import SqlUnitOfWork
from domain.team import AgentDefinition, AgentRole, Team
from sqlalchemy.orm import sessionmaker

from interactors.api.settings import Settings

DEFAULT_TEAM_NAME = "Default Team"
DEFAULT_ROLES = [AgentRole.LEAD, AgentRole.BACKEND, AgentRole.QA]


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


def main() -> None:
    settings = Settings()
    engine = build_engine(settings.db_url)
    seed_default_team(build_session_factory(engine), owner_id=settings.dev_owner_id)


if __name__ == "__main__":
    main()
