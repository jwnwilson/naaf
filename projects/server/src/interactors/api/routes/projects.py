from collections.abc import Callable

from crud_router import CrudRouter
from domain.project import Project

from interactors.api.schemas import CreateProject, UpdateProject


def build_projects_router(db_dependency: Callable) -> CrudRouter:
    return CrudRouter(
        db_dependency=db_dependency,
        repository="projects",
        response_dto=Project,
        create_schema=CreateProject,
        update_schema=UpdateProject,
        methods=["CREATE", "READ", "UPDATE", "DELETE"],
        prefix="/projects",
        tags=["projects"],
    )
