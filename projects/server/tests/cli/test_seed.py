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


def test_seed_demo_creates_project_and_items(session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from interactors.cli.seed import seed_demo
    seed_demo(session_factory, owner_id="u1")
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        projects = uow.projects.read_multi().results
        items = uow.work_items.read_multi().results
    assert len(projects) >= 1
    assert {i.status.value for i in items} >= {"backlog", "todo", "in_progress", "done"}


def test_seed_demo_is_idempotent(session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from interactors.cli.seed import seed_demo
    seed_demo(session_factory, owner_id="u1")
    seed_demo(session_factory, owner_id="u1")
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        assert uow.projects.read_multi(filters={"name": "Demo Project"}).total == 1
