from fastapi import FastAPI

from interactors.api.routes.projects import router as projects_router
from interactors.api.routes.teams import agent_definitions_router, teams_router
from interactors.api.routes.work_items import project_router as project_work_items_router
from interactors.api.routes.work_items import router as work_items_router


def register_routers(app: FastAPI) -> None:
    app.include_router(projects_router)
    app.include_router(work_items_router)
    app.include_router(project_work_items_router)
    app.include_router(teams_router)
    app.include_router(agent_definitions_router)
