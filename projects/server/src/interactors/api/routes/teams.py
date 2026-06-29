from collections.abc import Callable

from crud_router import CrudRouter
from domain.team import AgentDefinition, Team

from interactors.api.schemas import (
    CreateAgentDefinition,
    CreateTeam,
    UpdateAgentDefinition,
    UpdateTeam,
)


def build_teams_router(db_dependency: Callable) -> CrudRouter:
    return CrudRouter(
        db_dependency=db_dependency,
        repository="teams",
        response_dto=Team,
        create_schema=CreateTeam,
        update_schema=UpdateTeam,
        methods=["CREATE", "READ", "UPDATE", "DELETE"],
        prefix="/teams",
        tags=["teams"],
    )


def build_agent_definitions_router(db_dependency: Callable) -> CrudRouter:
    return CrudRouter(
        db_dependency=db_dependency,
        repository="agent_definitions",
        response_dto=AgentDefinition,
        create_schema=CreateAgentDefinition,
        update_schema=UpdateAgentDefinition,
        methods=["CREATE", "READ", "UPDATE", "DELETE"],
        prefix="/agent-definitions",
        tags=["agent-definitions"],
    )
