from domain.messaging.mentions import parse_mentions, route_targets

MAX_FANOUT_DEPTH = 4  # max agent->agent hops before the thread pauses for a human


def plan_dispatch(text: str, depth: int) -> list[str]:
    """Targets for a HUMAN post entering the thread.

    Below the cap, honour @mentions or default to lead (a human with no mention
    is addressing the team, so the lead picks it up). At/above the cap, return
    no targets. Human posts arrive at depth 0, so the cap is a safety net here.
    """
    if depth >= MAX_FANOUT_DEPTH:
        return []
    return route_targets(text)


def plan_fanout(text: str, depth: int) -> list[str]:
    """Targets when fanning out an AGENT reply — EXPLICIT @mentions only.

    Unlike a human post, an agent reply that mentions no one is addressing no
    one: it must NOT default to lead, or every mention-less reply would cascade
    to @lead up to the depth cap. At/above the cap, return no targets so an
    agent->agent chain terminates — a human message (depth 0) is required to
    continue it.
    """
    if depth >= MAX_FANOUT_DEPTH:
        return []
    return parse_mentions(text)
