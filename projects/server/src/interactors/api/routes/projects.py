from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.project import Project
from fastapi import APIRouter, Depends, Response

from interactors.api.contract import ProjectCreateIn, ProjectOut, ProjectUpdateIn, iso
from interactors.api.deps import get_uow
from interactors.api.schemas import UpdateProject

router = APIRouter(prefix="/projects", tags=["projects"])


def _item_count(project_id: str, uow: SqlUnitOfWork) -> int:
    return uow.work_items.read_multi(
        filters={"project_id": project_id}, page_size=0
    ).total


@router.post("", status_code=201, response_model=Envelope[ProjectOut])
def create_project(
    body: ProjectCreateIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    p = uow.projects.create(Project(
        owner_id="",  # stamped by repo from required_filters; key derived in repo
        name=body.name,
        repo_url=body.repoUrl or None,
        autonomy_level=body.autonomyLevel,
    ))
    return ok(ProjectOut(
        id=p.id, name=p.name, repoUrl=p.repo_url or "",
        itemCount=_item_count(p.id, uow),
        createdAt=iso(p.created_at), updatedAt=iso(p.updated_at),
    ))


@router.get("/{id}", response_model=Envelope[ProjectOut])
def read_project(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    p = uow.projects.read(id.hex)
    return ok(ProjectOut(
        id=p.id, name=p.name, repoUrl=p.repo_url or "",
        itemCount=_item_count(p.id, uow),
        createdAt=iso(p.created_at), updatedAt=iso(p.updated_at),
    ))


@router.get("", response_model=Envelope[list[ProjectOut]])
def list_projects(
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    page_size: int = 50,
    page_number: int = 1,
):
    page = uow.projects.read_multi(page_size=page_size, page_number=page_number)
    results = [
        ProjectOut(
            id=p.id, name=p.name, repoUrl=p.repo_url or "",
            itemCount=_item_count(p.id, uow),
            createdAt=iso(p.created_at), updatedAt=iso(p.updated_at),
        )
        for p in page.results
    ]
    return ok(results, meta={
        "total": page.total,
        "page_size": page.page_size,
        "page_number": page.page_number,
    })


@router.patch("/{id}", response_model=Envelope[ProjectOut])
def update_project(
    id: UUID,
    body: ProjectUpdateIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    p = uow.projects.update(id.hex, UpdateProject(name=body.name, repo_url=body.repoUrl))
    return ok(ProjectOut(
        id=p.id, name=p.name, repoUrl=p.repo_url or "",
        itemCount=_item_count(p.id, uow),
        createdAt=iso(p.created_at), updatedAt=iso(p.updated_at),
    ))


@router.delete("/{id}", status_code=204, response_class=Response)
def delete_project(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    uow.projects.delete(id.hex)
    return Response(status_code=204)
