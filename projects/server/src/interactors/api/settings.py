from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="naaf_")

    db_url: str = "sqlite://"
    auth_mode: str = "dev"
    dev_owner_id: str = "dev-user"
    celery_broker_url: str = "redis://localhost:6379/0"
    worker_roles: str = ""

    llm_provider: str = "claude"           # "claude" | "litellm"
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""           # blank = Anthropic default
    litellm_base_url: str = ""
    litellm_key: str = ""
    model_aliases: dict[str, str] = {
        "opus": "claude-opus-4-8",
        "sonnet": "claude-sonnet-4-6",
        "haiku": "claude-haiku-4-5",
    }
    agent_max_iterations: int = 25
    agent_bash_timeout_s: int = 120
    agent_runtime: str = "claude_code"
    workspace_root: str = "/tmp/naaf-workspaces"
    role_model_aliases: dict[str, str] = {
        "lead": "opus",
        "architect": "opus",
        "engineer": "sonnet",
        "backend": "sonnet",
        "frontend": "sonnet",
        "qa": "haiku",
        "curator": "haiku",
        "devops": "sonnet",
    }

    @property
    def worker_roles_list(self) -> list[str]:
        return [r.strip() for r in self.worker_roles.split(",") if r.strip()]
