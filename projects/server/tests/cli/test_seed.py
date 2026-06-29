from interactors.cli.seed import seed_default_team


def test_seed_creates_team_with_three_agents(session_factory):
    team_id = seed_default_team(session_factory, owner_id="u1")

    from adapters.database.uow import SqlUnitOfWork
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        teams = uow.teams.read_multi().results
        agents = uow.agent_definitions.read_multi(filters={"team_id": team_id}).results
    assert len(teams) == 1
    assert {a.role.value for a in agents} == {"lead", "backend", "qa"}


def test_seed_is_idempotent(session_factory):
    seed_default_team(session_factory, owner_id="u1")
    seed_default_team(session_factory, owner_id="u1")
    from adapters.database.uow import SqlUnitOfWork
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        assert uow.teams.read_multi().total == 1
