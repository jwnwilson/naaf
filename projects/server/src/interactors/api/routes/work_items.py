from typing import NamedTuple
from uuid import UUID

from adapters.database.uow import SqlUnitOfWork
from crud_router import Envelope, ok
from domain.board import BoardNode, build_board_tree
from domain.errors import InvalidHierarchy
from domain.hierarchy import validate_hierarchy
from domain.transitions import validate_transition
from domain.work_item import WorkItem, WorkItemKind
from fastapi import APIRouter, Depends, Response

from interactors.api.contract import (
    AttachmentOut,
    WorkItemCreateIn,
    WorkItemOut,
    WorkItemUpdateIn,
    iso,
)
from interactors.api.deps import get_uow
from interactors.api.schemas import TransitionRequest, UpdateWorkItem

# /work-items: item + collection routes.
router = APIRouter(prefix="/work-items", tags=["work-items"])
# /projects/{project_id}-scoped nested-create + board (no /work-items prefix).
project_router = APIRouter(tags=["work-items"])


class Lineage(NamedTuple):
    epic_id: str | None = None
    epic_name: str | None = None
    feature_id: str | None = None
    feature_name: str | None = None


def _resolve_lineage(item: WorkItem, uow: SqlUnitOfWork) -> Lineage:
    """Return the epic/feature ids + names by walking the parent chain (≤2 reads)."""
    if item.parent_id is None:
        return Lineage()
    parent = uow.work_items.read(item.parent_id)
    if parent.kind == WorkItemKind.EPIC:
        return Lineage(epic_id=parent.id, epic_name=parent.title)
    if parent.kind == WorkItemKind.FEATURE:
        epic_id: str | None = None
        epic_name: str | None = None
        if parent.parent_id:
            epic = uow.work_items.read(parent.parent_id)
            epic_id, epic_name = epic.id, epic.title
        return Lineage(epic_id, epic_name, parent.id, parent.title)
    return Lineage()


def _compose_key(item: WorkItem, project_key: str | None) -> str:
    """Human-readable key, e.g. 'NAAF-42'. Falls back to the raw id if unset."""
    if project_key and item.seq is not None:
        return f"{project_key}-{item.seq}"
    return item.id


def _work_item_out(
    item: WorkItem,
    lineage: Lineage,
    project_key: str | None,
    attachments: list | None = None,
) -> WorkItemOut:
    """Build the camelCase contract response for a work item.

    epicId/epicName/featureId/featureName aren't stored on the item — the
    route resolves them from the parent chain (see _resolve_lineage). key is
    composed from the owning project's key + this item's per-project seq.
    Agent-run fields (assignedAgent, token usage) have no backend source yet
    and emit null. Attachments are populated only for single-item reads to
    avoid N+1 on list/board endpoints.
    """
    return WorkItemOut(
        id=item.id,
        key=_compose_key(item, project_key),
        type=item.kind.value,
        title=item.title,
        status=item.status.value,
        priority=item.priority.value,
        assignedAgent=None,
        epicId=lineage.epic_id,
        epicName=lineage.epic_name,
        featureId=lineage.feature_id,
        featureName=lineage.feature_name,
        projectId=item.project_id,
        tokenUsageThisRun=None,
        tokenUsageAllRuns=None,
        tokenLimit=None,
        spec=item.body or None,
        attachments=attachments or [],
        createdAt=iso(item.created_at),
        updatedAt=iso(item.updated_at),
    )


@router.get("/{id}", response_model=Envelope[WorkItemOut])
def read_work_item(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    item = uow.work_items.read(id.hex)
    project = uow.projects.read(item.project_id)
    atts = uow.attachments.read_multi(
        filters={"work_item_id": item.id}, order_by="created_at"
    ).results
    att_out = [
        AttachmentOut(
            id=a.id,
            filename=a.filename,
            contentType=a.content_type,
            size=a.size,
            url=f"/work-items/{item.id}/attachments/{a.id}",
            createdAt=iso(a.created_at),
        ).model_dump()
        for a in atts
    ]
    return ok(_work_item_out(item, _resolve_lineage(item, uow), project.key, attachments=att_out))


@router.patch("/{id}", response_model=Envelope[WorkItemOut])
def update_work_item(
    id: UUID,
    body: WorkItemUpdateIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    # Forward only the fields the client actually sent: an absent `spec` must
    # not become body=None (which would null the NOT NULL column).
    sent = body.model_fields_set
    data: dict[str, object] = {}
    if "title" in sent:
        data["title"] = body.title
    if "priority" in sent:
        data["priority"] = body.priority
    if "spec" in sent:
        data["body"] = body.spec
    updated = uow.work_items.update(id.hex, UpdateWorkItem(**data))  # type: ignore[arg-type]
    project = uow.projects.read(updated.project_id)
    return ok(_work_item_out(updated, _resolve_lineage(updated, uow), project.key))


@router.get("", response_model=Envelope[list[WorkItemOut]])
def list_work_items(
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
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
    project_keys: dict[str, str | None] = {}
    for item in page.results:
        lineage = _resolve_lineage(item, uow)
        if epic and lineage.epic_id != epic:
            continue
        if item.project_id not in project_keys:
            project_keys[item.project_id] = uow.projects.read(item.project_id).key
        results.append(_work_item_out(item, lineage, project_keys[item.project_id]))
    # epicId is computed (not a DB column), so ?epic= filters in Python after
    # the query; report the filtered length as the single-page total.
    total = len(results) if epic else page.total
    return ok(results, meta={
        "total": total,
        "page_size": page.page_size,
        "page_number": page.page_number,
    })


@router.delete("/{id}", status_code=204, response_class=Response)
def delete_work_item(id: UUID, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    uow.work_items.delete(id.hex)
    return Response(status_code=204)


@router.post("/{id}/transition", response_model=Envelope[WorkItemOut])
def transition_work_item(
    id: UUID,
    body: TransitionRequest,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    current = uow.work_items.read(id.hex)
    new_status = validate_transition(current.status, body.status)
    saved = uow.work_items.update(id.hex, current.model_copy(update={"status": new_status}))
    project = uow.projects.read(saved.project_id)
    return ok(_work_item_out(saved, _resolve_lineage(saved, uow), project.key))


@project_router.post(
    "/projects/{project_id}/work-items", status_code=201,
    response_model=Envelope[WorkItemOut],
)
def create_work_item(
    project_id: str,
    body: WorkItemCreateIn,
    uow: SqlUnitOfWork = Depends(get_uow),  # noqa: B008
):
    project = uow.projects.read(project_id)  # owner-scoped: missing or foreign project → 404
    parent_id = body.featureId or body.epicId or None
    parent = uow.work_items.read(parent_id) if parent_id else None
    validate_hierarchy(body.type, parent)
    if parent is not None and parent.project_id != project_id:
        raise InvalidHierarchy("parent must belong to the same project")
    item = WorkItem(
        owner_id="",  # stamped by repo from required_filters
        project_id=project_id,
        parent_id=parent_id,
        kind=body.type,
        title=body.title,
        body=body.spec or "",
        priority=body.priority,
        status=body.status,
    )
    saved = uow.work_items.create(item)
    return ok(_work_item_out(saved, _resolve_lineage(saved, uow), project.key))


@project_router.get(
    "/projects/{project_id}/board", response_model=Envelope[list[BoardNode]]
)
def board(project_id: str, uow: SqlUnitOfWork = Depends(get_uow)):  # noqa: B008
    page = uow.work_items.read_multi(
        filters={"project_id": project_id}, page_size=0, order_by="created_at"
    )
    return ok(build_board_tree(page.results))
