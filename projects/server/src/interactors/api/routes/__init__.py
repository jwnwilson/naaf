from fastapi import FastAPI

from interactors.api.deps import get_uow
from interactors.api.routes.projects import build_projects_router
from interactors.api.routes.work_items import (
    build_project_work_items_router,
    build_work_items_router,
)


def register_routers(app: FastAPI) -> None:
    app.include_router(build_projects_router(get_uow))
    app.include_router(build_work_items_router(get_uow))
    app.include_router(build_project_work_items_router(get_uow))
