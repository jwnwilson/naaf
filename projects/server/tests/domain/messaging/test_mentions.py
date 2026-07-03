from domain.messaging.mentions import DEFAULT_ROLE, parse_mentions, route_targets


def test_parses_known_roles_deduped_in_order():
    text = "@backend please sync with @qa and @backend again"
    assert parse_mentions(text) == ["backend", "qa"]


def test_ignores_unknown_and_bare_at():
    assert parse_mentions("hey @nobody and @ and plain text") == []


def test_route_targets_defaults_to_lead_when_no_mention():
    assert route_targets("no mention here") == [DEFAULT_ROLE]


def test_route_targets_uses_mentions_when_present():
    assert route_targets("@frontend take this") == ["frontend"]
