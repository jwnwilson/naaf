from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from fastapi import APIRouter, Depends, Response

from interactors.api.contract import (
    AgentDefinitionOut,
    AgentDefinitionUpdateIn,
    TeamCreateIn,
    TeamOut,
    TeamUpdateIn,
)
from interactors.api.deps import get_uow
from interactors.api.schemas import CreateTeam, UpdateAgentDefinition, UpdateTeam

teams_router = APIRouter(prefix="/teams", tags=["teams"])
# No CREATE: the UI contract has no POST /agent-definitions — agent definitions
# are provisioned as part of team setup, not via this route.
agent_definitions_router = APIRouter(prefix="/agent-definitions", tags=["agent-definitions"])


@teams_router.post("", status_code=201, response_model=Envelope[TeamOut])
def create_team(
    body: TeamCreateIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    t = uow.teams.create(CreateTeam(name=body.name))
    return ok(TeamOut(id=t.id, name=t.name))


@teams_router.get("/{id}", response_model=Envelope[TeamOut])
def read_team(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    t = uow.teams.read(id.hex)
    return ok(TeamOut(id=t.id, name=t.name))


@teams_router.get("", response_model=Envelope[list[TeamOut]])
def list_teams(
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    page_size: int = 50,
    page_number: int = 1,
):
    page = uow.teams.read_multi(page_size=page_size, page_number=page_number)
    results = [TeamOut(id=t.id, name=t.name) for t in page.results]
    return ok(results, meta={
        "total": page.total,
        "page_size": page.page_size,
        "page_number": page.page_number,
    })


@teams_router.patch("/{id}", response_model=Envelope[TeamOut])
def update_team(
    id: UUID,
    body: TeamUpdateIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    t = uow.teams.update(id.hex, UpdateTeam(name=body.name))
    return ok(TeamOut(id=t.id, name=t.name))


@teams_router.delete("/{id}", status_code=204, response_class=Response)
def delete_team(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    uow.teams.delete(id.hex)
    return Response(status_code=204)


def _agent_definition_out(a) -> AgentDefinitionOut:
    return AgentDefinitionOut(
        id=a.id,
        teamId=a.team_id,
        role=a.role.value,
        model=a.model_alias,
        tokenLimit=a.token_limit,
        systemPrompt=a.persona_prompt or None,
        enabled=a.enabled,
    )


@agent_definitions_router.get("/{id}", response_model=Envelope[AgentDefinitionOut])
def read_agent_definition(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    return ok(_agent_definition_out(uow.agent_definitions.read(id.hex)))


@agent_definitions_router.get("", response_model=Envelope[list[AgentDefinitionOut]])
def list_agent_definitions(
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    page_size: int = 50,
    page_number: int = 1,
):
    page = uow.agent_definitions.read_multi(page_size=page_size, page_number=page_number)
    results = [_agent_definition_out(a) for a in page.results]
    return ok(results, meta={
        "total": page.total,
        "page_size": page.page_size,
        "page_number": page.page_number,
    })


@agent_definitions_router.patch("/{id}", response_model=Envelope[AgentDefinitionOut])
def update_agent_definition(
    id: UUID,
    body: AgentDefinitionUpdateIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    updated = uow.agent_definitions.update(id.hex, UpdateAgentDefinition(
        model_alias=body.model,
        persona_prompt=body.systemPrompt,
        token_limit=body.tokenLimit,
        enabled=body.enabled,
    ))
    return ok(_agent_definition_out(updated))


@agent_definitions_router.delete("/{id}", status_code=204, response_class=Response)
def delete_agent_definition(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    uow.agent_definitions.delete(id.hex)
    return Response(status_code=204)
