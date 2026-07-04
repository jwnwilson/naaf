from domain.base import Entity

# The known, injectable secret names the API accepts and the resolver consumes.
SECRET_NAMES: tuple[str, ...] = ("anthropic_api_key", "github_token")


class Secret(Entity):
    """An owner-scoped, encrypted credential. `value_encrypted` is opaque to the
    domain; `hint` (last 4 plaintext chars) is safe to display."""

    owner_id: str
    name: str
    value_encrypted: str
    hint: str = ""
