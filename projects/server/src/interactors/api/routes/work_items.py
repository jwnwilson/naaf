from collections.abc import Callable
from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from crud_router import CrudRouter, Envelope, ok
from domain.board import BoardNode, build_board_tree
from domain.errors import InvalidHierarchy
from domain.hierarchy import validate_hierarchy
from domain.transitions import validate_transition
from domain.work_item import WorkItem, WorkItemKind
from fastapi import APIRouter, Depends

from interactors.api.contract import WorkItemCreateIn, WorkItemOut, WorkItemUpdateIn
from interactors.api.mappers import (
    work_item_create_to_domain,
    work_item_out,
    work_item_update_to_domain,
)
from interactors.api.schemas import TransitionRequest


def _resolve_lineage(item: WorkItem, uow: SqlUnitOfWork) -> tuple[str | None, str | None]:
    """Return (epic_id, feature_id) by walking parent chain (≤2 reads)."""
    if item.parent_id is None:
        return None, None
    parent = uow.work_items.read(item.parent_id)
    if parent.kind == WorkItemKind.EPIC:
        return parent.id, None
    if parent.kind == WorkItemKind.FEATURE:
        epic_id: str | None = None
        if parent.parent_id:
            grandparent = uow.work_items.read(parent.parent_id)
            epic_id = grandparent.id
        return epic_id, parent.id
    return None, None


def build_work_items_router(db_dependency: Callable) -> CrudRouter:
    """Prefix /work-items: UPDATE/DELETE + overridden GET routes + transition."""
    router = CrudRouter(
        db_dependency=db_dependency,
        repository="work_items",
        response_dto=WorkItemOut,
        create_schema=WorkItemCreateIn,  # unused — no CREATE in methods
        update_schema=WorkItemUpdateIn,  # unused — PATCH is hand-written below
        # READ + UPDATE are hand-written below so lineage (epicId/featureId)
        # can be resolved via the request uow; the generic CrudRouter to_response
        # has no uow, so it would always emit null lineage.
        methods=["DELETE"],
        prefix="/work-items",
        tags=["work-items"],
    )

    @router.get("/{id}", response_model=Envelope[WorkItemOut])
    def read_work_item(
        id: UUID,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        item = uow.work_items.read(id.hex)
        epic_id, feature_id = _resolve_lineage(item, uow)
        return ok(work_item_out(item, epic_id=epic_id, feature_id=feature_id))

    @router.patch("/{id}", response_model=Envelope[WorkItemOut])
    def update_work_item(
        id: UUID,
        body: WorkItemUpdateIn,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        updated = uow.work_items.update(id.hex, work_item_update_to_domain(body))
        epic_id, feature_id = _resolve_lineage(updated, uow)
        return ok(work_item_out(updated, epic_id=epic_id, feature_id=feature_id))

    @router.get("/", response_model=Envelope[list[WorkItemOut]])
    def list_work_items(
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
        project: str | None = None,
        status: str | None = None,
        epic: str | None = None,
        page_size: int = 50,
        page_number: int = 1,
    ):
        filters: dict = {}
        if project:
            filters["project_id"] = project
        if status:
            filters["status"] = status
        page = uow.work_items.read_multi(
            filters=filters, page_size=page_size, page_number=page_number
        )
        results = []
        for item in page.results:
            epic_id, feature_id = _resolve_lineage(item, uow)
            if epic and epic_id != epic:
                continue
            results.append(work_item_out(item, epic_id=epic_id, feature_id=feature_id))
        # epicId is computed (not a DB column), so the ?epic= filter is applied
        # in Python after the query. The DB-level page.total would over-count, so
        # report the filtered length as a single-page truth.
        total = len(results) if epic else page.total
        return ok(results, meta={
            "total": total,
            "page_size": page.page_size,
            "page_number": page.page_number,
        })

    @router.post("/{id}/transition", response_model=Envelope[WorkItemOut])
    def transition_work_item(
        id: UUID,
        body: TransitionRequest,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        current = uow.work_items.read(id.hex)
        new_status = validate_transition(current.status, body.status)
        updated = current.model_copy(update={"status": new_status})
        saved = uow.work_items.update(id.hex, updated)
        epic_id, feature_id = _resolve_lineage(saved, uow)
        return ok(work_item_out(saved, epic_id=epic_id, feature_id=feature_id))

    return router


def build_project_work_items_router(db_dependency: Callable) -> APIRouter:
    """No prefix: /projects/{project_id}-scoped nested-create and board routes."""
    router = APIRouter(tags=["work-items"])

    @router.post("/projects/{project_id}/work-items", status_code=201,
                 response_model=Envelope[WorkItemOut])
    def create_work_item(
        project_id: str,
        body: WorkItemCreateIn,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        uow.projects.read(project_id)  # owner-scoped: missing or foreign project → 404
        parent_id = body.epicId or body.featureId or None
        parent = uow.work_items.read(parent_id) if parent_id else None
        validate_hierarchy(body.type, parent)
        if parent is not None and parent.project_id != project_id:
            raise InvalidHierarchy("parent must belong to the same project")
        domain_in = work_item_create_to_domain(body)
        item = WorkItem(
            owner_id="",  # stamped by repo from required_filters
            project_id=project_id,
            parent_id=parent_id,
            kind=domain_in.kind,
            title=domain_in.title,
            body=domain_in.body,
            acceptance_criteria=domain_in.acceptance_criteria,
            priority=domain_in.priority,
            status=domain_in.status,
        )
        saved = uow.work_items.create(item)
        epic_id, feature_id = _resolve_lineage(saved, uow)
        return ok(work_item_out(saved, epic_id=epic_id, feature_id=feature_id))

    @router.get("/projects/{project_id}/board", response_model=Envelope[list[BoardNode]])
    def board(
        project_id: str,
        uow: SqlUnitOfWork = Depends(db_dependency),  # noqa: B008
    ):
        page = uow.work_items.read_multi(
            filters={"project_id": project_id}, page_size=0, order_by="created_at"
        )
        return ok(build_board_tree(page.results))

    return router
