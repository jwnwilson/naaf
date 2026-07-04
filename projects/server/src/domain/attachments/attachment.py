from domain.base import Entity


class Attachment(Entity):
    """A file attached to a work item. Bytes live in storage under
    work-item/<work_item_id>/<filename>; this row is the queryable metadata."""

    owner_id: str
    work_item_id: str
    filename: str
    content_type: str
    size: int
