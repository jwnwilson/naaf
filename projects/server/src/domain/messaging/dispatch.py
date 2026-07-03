from domain.messaging.mentions import route_targets

MAX_FANOUT_DEPTH = 4  # max agent->agent hops before the thread pauses for a human


def plan_dispatch(text: str, depth: int) -> list[str]:
    """Roles to dispatch a message to at ``depth``.

    Below the cap, honour @mentions (or default to lead). At/above the cap,
    return no targets so an agent->agent chain cannot loop forever — a human
    message (depth 0) is required to continue.
    """
    if depth >= MAX_FANOUT_DEPTH:
        return []
    return route_targets(text)
