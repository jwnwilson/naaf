from domain.errors import InvalidHierarchy
from domain.work_item import WorkItem
from domain.work_item import WorkItemKind as K

# Each kind's required parent kind. None means "must be a root".
REQUIRED_PARENT_KIND: dict[K, K | None] = {
    K.EPIC: None,
    K.FEATURE: K.EPIC,
    K.TASK: K.FEATURE,
}


def validate_hierarchy(child_kind: K, parent: WorkItem | None) -> None:
    """Raise InvalidHierarchy unless `parent` is a legal parent for `child_kind`.

    Pure: the caller fetches the parent (owner/project-scoped) and passes it in.
    """
    required = REQUIRED_PARENT_KIND[child_kind]
    if required is None:
        if parent is not None:
            raise InvalidHierarchy(f"{child_kind.value} must be a root (no parent)")
        return
    if parent is None:
        raise InvalidHierarchy(
            f"{child_kind.value} requires a {required.value} parent"
        )
    if parent.kind is not required:
        raise InvalidHierarchy(
            f"{child_kind.value} parent must be a {required.value}, "
            f"got {parent.kind.value}"
        )
