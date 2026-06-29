from collections.abc import Callable

from adapters.database.uow import SqlUnitOfWork
from crud_router import CrudRouter, Envelope, ok
from domain.board import BoardNode, build_board_tree
from domain.errors import InvalidHierarchy
from domain.hierarchy import validate_hierarchy
from domain.transitions import validate_transition
from domain.work_item import WorkItem
from fastapi import APIRouter, Depends

from interactors.api.schemas import CreateWorkItem, TransitionRequest, UpdateWorkItem


def build_work_items_router(db_dependency: Callable) -> CrudRouter:
    """Prefix /work-items: generic READ/UPDATE/DELETE (no CREATE) + transition.
    Paths added here are relative to the prefix."""
    router = CrudRouter(
        db_dependency=db_dependency,
        repository="work_items",
        response_dto=WorkItem,
        create_schema=CreateWorkItem,
        update_schema=UpdateWorkItem,
        methods=["READ", "UPDATE", "DELETE"],  # no generic CREATE
        prefix="/work-items",
        tags=["work-items"],
    )

    @router.post("/{id}/transition", response_model=Envelope[WorkItem])
    def transition_work_item(
        id: str,
        body: TransitionRequest,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        current = uow.work_items.read(id)
        new_status = validate_transition(current.status, body.status)
        updated = current.model_copy(update={"status": new_status})
        return ok(uow.work_items.update(id, updated))

    return router


def build_project_work_items_router(db_dependency: Callable) -> APIRouter:
    """No prefix: the /projects/{project_id}-scoped nested-create and board routes."""
    router = APIRouter(tags=["work-items"])

    @router.post("/projects/{project_id}/work-items", status_code=201,
                 response_model=Envelope[WorkItem])
    def create_work_item(
        project_id: str,
        body: CreateWorkItem,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        uow.projects.read(project_id)  # owner-scoped: missing or foreign project -> 404
        parent = uow.work_items.read(body.parent_id) if body.parent_id else None
        validate_hierarchy(body.kind, parent)
        if parent is not None and parent.project_id != project_id:
            raise InvalidHierarchy("parent must belong to the same project")
        item = WorkItem(
            owner_id="",  # stamped by repo from required_filters
            project_id=project_id,
            parent_id=body.parent_id,
            kind=body.kind,
            title=body.title,
            body=body.body,
            acceptance_criteria=body.acceptance_criteria,
        )
        return ok(uow.work_items.create(item))

    @router.get("/projects/{project_id}/board", response_model=Envelope[list[BoardNode]])
    def board(project_id: str, uow: SqlUnitOfWork = Depends(db_dependency)):  # noqa: B008
        page = uow.work_items.read_multi(
            filters={"project_id": project_id}, page_size=0, order_by="created_at"
        )
        return ok(build_board_tree(page.results))

    return router
