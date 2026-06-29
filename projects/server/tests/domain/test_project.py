from domain.project import AutonomyLevel, Project


def test_project_defaults():
    p = Project(owner_id="u1", name="naaf")
    assert p.autonomy_level is AutonomyLevel.GATED_ALL
    assert p.repo_url is None
    assert p.team_id is None
    assert len(p.id) == 32


def test_project_immutable_update():
    p = Project(owner_id="u1", name="naaf")
    p2 = p.model_copy(update={"team_id": "t1"})
    assert p.team_id is None
    assert p2.team_id == "t1"
