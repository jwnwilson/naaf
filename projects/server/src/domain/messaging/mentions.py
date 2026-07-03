import re

TEAM_ROLES: tuple[str, ...] = ("lead", "architect", "backend", "frontend", "qa", "devops")
DEFAULT_ROLE = "lead"

_MENTION_RE = re.compile(r"@([a-z]+)")


def parse_mentions(text: str) -> list[str]:
    """Return known team roles @-mentioned in ``text``, deduped, first-seen order."""
    seen: list[str] = []
    for token in _MENTION_RE.findall(text or ""):
        if token in TEAM_ROLES and token not in seen:
            seen.append(token)
    return seen


def route_targets(text: str) -> list[str]:
    """Dispatch targets: explicit mentions, else the default (lead)."""
    mentions = parse_mentions(text)
    return mentions or [DEFAULT_ROLE]
