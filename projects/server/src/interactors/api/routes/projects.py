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


def _project_out(p: Project, uow: SqlUnitOfWork) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        name=p.name,
        description=p.description,
        repoUrl=p.repo_url or "",
        itemCount=_item_count(p.id, uow),
        createdAt=iso(p.created_at),
        updatedAt=iso(p.updated_at),
    )


@router.post("", status_code=201, response_model=Envelope[ProjectOut])
def create_project(
    body: ProjectCreateIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    p = uow.projects.create(Project(
        owner_id="",  # stamped by repo from required_filters; key derived in repo
        name=body.name,
        description=body.description,
        repo_url=body.repoUrl or None,
        autonomy_level=body.autonomyLevel,
    ))
    return ok(_project_out(p, uow))


@router.get("/{id}", response_model=Envelope[ProjectOut])
def read_project(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    return ok(_project_out(uow.projects.read(id.hex), uow))


@router.get("", response_model=Envelope[list[ProjectOut]])
def list_projects(
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
    page_size: int = 50,
    page_number: int = 1,
):
    page = uow.projects.read_multi(page_size=page_size, page_number=page_number)
    results = [_project_out(p, uow) for p in page.results]
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
    # Only forward fields the client actually sent: UpdateProject/model_dump(exclude_unset=True)
    # treats any explicitly-passed kwarg (even None) as "set", so passing all three unconditionally
    # would null out NOT NULL columns (e.g. description) on partial patches.
    fields = body.model_dump(exclude_unset=True)
    if "repoUrl" in fields:
        fields["repo_url"] = fields.pop("repoUrl")
    p = uow.projects.update(id.hex, UpdateProject(**fields))
    return ok(_project_out(p, uow))


@router.delete("/{id}", status_code=204, response_class=Response)
def delete_project(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    uow.delete_project_cascade(id.hex)
    return Response(status_code=204)
