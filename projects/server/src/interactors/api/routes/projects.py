from collections.abc import Callable
from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from fastapi import APIRouter, Depends, Response

from interactors.api.contract import ProjectCreateIn, ProjectOut, ProjectUpdateIn
from interactors.api.mappers import project_create_to_domain, project_out, project_update_to_domain


def _item_count(project_id: str, uow: SqlUnitOfWork) -> int:
    return uow.work_items.read_multi(
        filters={"project_id": project_id}, page_size=1
    ).total


def build_projects_router(db_dependency: Callable) -> APIRouter:
    router = APIRouter(prefix="/projects", tags=["projects"])

    @router.post("/", status_code=201, response_model=Envelope[ProjectOut])
    def create_project(
        body: ProjectCreateIn,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        p = uow.projects.create(project_create_to_domain(body))
        return ok(project_out(p, item_count=_item_count(p.id, uow)))

    @router.get("/{id}", response_model=Envelope[ProjectOut])
    def read_project(
        id: UUID,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        p = uow.projects.read(id.hex)
        return ok(project_out(p, item_count=_item_count(p.id, uow)))

    @router.get("/", response_model=Envelope[list[ProjectOut]])
    def list_projects(
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
        page_size: int = 50,
        page_number: int = 1,
    ):
        page = uow.projects.read_multi(page_size=page_size, page_number=page_number)
        results = [project_out(p, item_count=_item_count(p.id, uow)) for p in page.results]
        return ok(results, meta={
            "total": page.total,
            "page_size": page.page_size,
            "page_number": page.page_number,
        })

    @router.patch("/{id}", response_model=Envelope[ProjectOut])
    def update_project(
        id: UUID,
        body: ProjectUpdateIn,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        p = uow.projects.update(id.hex, project_update_to_domain(body))
        return ok(project_out(p, item_count=_item_count(p.id, uow)))

    @router.delete("/{id}", status_code=204, response_class=Response)
    def delete_project(
        id: UUID,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        uow.projects.delete(id.hex)
        return Response(status_code=204)

    return router
