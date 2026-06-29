from fastapi import FastAPI

from interactors.api.deps import get_uow
from interactors.api.routes.projects import build_projects_router


def register_routers(app: FastAPI) -> None:
    app.include_router(build_projects_router(get_uow))
