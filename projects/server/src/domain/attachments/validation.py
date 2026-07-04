ALLOWED_CONTENT_TYPES: set[str] = {
    # text / docs
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/xml",
    "text/xml",
    # images
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}


def is_allowed_content_type(content_type: str) -> bool:
    return content_type.split(";")[0].strip().lower() in ALLOWED_CONTENT_TYPES


def validate_filename(name: str) -> str:
    """Return a safe single-segment filename or raise ValueError."""
    cleaned = (name or "").strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or cleaned in (".", ".."):
        raise ValueError(f"invalid filename: {name!r}")
    return cleaned
