from domain.project import Project
from domain.team import AgentDefinition, Team
from domain.work_item import WorkItem

from adapters.database.orm import (
    AgentDefinitionRow,
    ProjectRow,
    TeamRow,
    WorkItemRow,
)
from adapters.database.repository import SqlRepository


class ProjectRepository(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project


class WorkItemRepository(SqlRepository[WorkItem]):
    orm_model = WorkItemRow
    dto = WorkItem


class TeamRepository(SqlRepository[Team]):
    orm_model = TeamRow
    dto = Team


class AgentDefinitionRepository(SqlRepository[AgentDefinition]):
    orm_model = AgentDefinitionRow
    dto = AgentDefinition
