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


def test_seed_demo_creates_hierarchy_with_keys(session_factory):
    from adapters.database.uow import SqlUnitOfWork
    from interactors.cli.seed import seed_demo

    seed_demo(session_factory, owner_id="u1")
    uow = SqlUnitOfWork(session_factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        project = uow.projects.read_multi(filters={"name": "Demo Project"}).results[0]
        items = uow.work_items.read_multi(
            filters={"project_id": project.id}, page_size=0, order_by="seq"
        ).results

    assert project.key == "DEMO"
    assert {i.seq for i in items} == set(range(1, len(items) + 1))
    # at least one task hangs under a feature under an epic
    by_id = {i.id: i for i in items}
    tasks = [i for i in items if i.kind.value == "task"]
    assert any(
        (feat := by_id.get(t.parent_id)) is not None
        and feat.kind.value == "feature"
        and by_id.get(feat.parent_id) is not None
        and by_id[feat.parent_id].kind.value == "epic"
        for t in tasks
    )
