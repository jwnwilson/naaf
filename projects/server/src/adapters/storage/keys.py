def attachment_key(work_item_id: str, filename: str) -> str:
    return f"work-item/{work_item_id}/{filename}"


def attachment_prefix(work_item_id: str) -> str:
    return f"work-item/{work_item_id}/"
