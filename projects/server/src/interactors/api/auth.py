from fastapi import Request


def get_owner_id(request: Request) -> str:
    """Dev auth: every request is attributed to the configured dev owner.
    Auth0 integration (remote profile) plugs in here later."""
    settings = request.app.state.settings
    if settings.auth_mode == "dev":
        return settings.dev_owner_id
    raise NotImplementedError(f"auth_mode {settings.auth_mode} not supported in A1")
