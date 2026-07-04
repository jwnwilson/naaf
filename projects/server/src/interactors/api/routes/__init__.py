from fastapi import FastAPI

from interactors.api.routes.agents import router as agents_router
from interactors.api.routes.attachments import router as attachments_router
from interactors.api.routes.notifications import router as notifications_router
from interactors.api.routes.projects import router as projects_router
from interactors.api.routes.runs import router as runs_router
from interactors.api.routes.runs import work_items_router as run_start_router
from interactors.api.routes.secrets import router as secrets_router
from interactors.api.routes.teams import agent_definitions_router, teams_router
from interactors.api.routes.threads import router as threads_router
from interactors.api.routes.work_items import project_router as project_work_items_router
from interactors.api.routes.work_items import router as work_items_router


def register_routers(app: FastAPI) -> None:
    app.include_router(agents_router)
    app.include_router(projects_router)
    app.include_router(work_items_router)
    app.include_router(project_work_items_router)
    app.include_router(teams_router)
    app.include_router(agent_definitions_router)
    app.include_router(runs_router)
    app.include_router(run_start_router)
    app.include_router(notifications_router)
    app.include_router(threads_router)
    app.include_router(attachments_router)
    app.include_router(secrets_router)
