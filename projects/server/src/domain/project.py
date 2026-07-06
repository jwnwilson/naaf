import re
from collections.abc import Collection
from enum import StrEnum

from domain.base import Entity


class AutonomyLevel(StrEnum):
    GATED_ALL = "gated_all"
    GATED_MERGE = "gated_merge"
    FULL_AUTO = "full_auto"


def derive_project_key(name: str, taken: Collection[str] = frozenset()) -> str:
    """A short uppercase key from the project name, unique against `taken`."""
    base = re.sub(r"[^A-Za-z0-9]", "", name or "").upper()[:4] or "PROJ"
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


class Project(Entity):
    owner_id: str
    name: str
    description: str = ""
    key: str | None = None
    repo_url: str | None = None
    repo_path: str | None = None
    team_id: str | None = None
    autonomy_level: AutonomyLevel = AutonomyLevel.GATED_ALL
