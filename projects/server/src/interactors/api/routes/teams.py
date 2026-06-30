from collections.abc import Callable

from crud_router import CrudRouter

from interactors.api.contract import (
    AgentDefinitionOut,
    AgentDefinitionUpdateIn,
    TeamCreateIn,
    TeamOut,
    TeamUpdateIn,
)
from interactors.api.mappers import (
    agent_definition_out,
    agent_definition_update_to_domain,
    team_create_to_domain,
    team_out,
    team_update_to_domain,
)


def build_teams_router(db_dependency: Callable) -> CrudRouter:
    return CrudRouter(
        db_dependency=db_dependency,
        repository="teams",
        response_dto=TeamOut,
        create_schema=TeamCreateIn,
        update_schema=TeamUpdateIn,
        to_response=team_out,
        to_domain_create=team_create_to_domain,  # type: ignore[arg-type]
        to_domain_update=team_update_to_domain,  # type: ignore[arg-type]
        methods=["CREATE", "READ", "UPDATE", "DELETE"],
        prefix="/teams",
        tags=["teams"],
    )


def build_agent_definitions_router(db_dependency: Callable) -> CrudRouter:
    # No CREATE: the UI contract has no POST /agent-definitions — agent
    # definitions are provisioned as part of team setup, not via this route.
    return CrudRouter(
        db_dependency=db_dependency,
        repository="agent_definitions",
        response_dto=AgentDefinitionOut,
        create_schema=AgentDefinitionUpdateIn,  # unused — no CREATE in methods
        update_schema=AgentDefinitionUpdateIn,
        to_response=agent_definition_out,
        to_domain_update=agent_definition_update_to_domain,  # type: ignore[arg-type]
        methods=["READ", "UPDATE", "DELETE"],
        prefix="/agent-definitions",
        tags=["agent-definitions"],
    )
