from domain.team import AgentDefinition, AgentRole, Team


def test_team_defaults():
    t = Team(owner_id="u1", name="Default")
    assert len(t.id) == 32


def test_agent_definition_defaults():
    a = AgentDefinition(owner_id="u1", team_id="t1", role=AgentRole.LEAD)
    assert a.runtime_adapter == "claude_code"
    assert a.memory_scope == "project"
    assert a.role is AgentRole.LEAD


def test_agent_definition_config_defaults():
    from domain.team import AgentDefinition, AgentRole
    a = AgentDefinition(owner_id="u1", team_id="t1", role=AgentRole.LEAD)
    assert a.enabled is True
    assert a.token_limit == 200000
