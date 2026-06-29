from enum import StrEnum

from domain.base import Entity


class AutonomyLevel(StrEnum):
    GATED_ALL = "gated_all"
    GATED_MERGE = "gated_merge"
    FULL_AUTO = "full_auto"


class Project(Entity):
    owner_id: str
    name: str
    repo_url: str | None = None
    repo_path: str | None = None
    team_id: str | None = None
    autonomy_level: AutonomyLevel = AutonomyLevel.GATED_ALL
