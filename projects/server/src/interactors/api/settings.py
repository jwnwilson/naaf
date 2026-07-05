from pydantic_settings import BaseSettings, SettingsConfigDict

from domain.pricing import ModelPrice


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="naaf_")

    db_url: str = "sqlite://"
    auth_mode: str = "dev"
    dev_owner_id: str = "dev-user"
    celery_broker_url: str = "redis://localhost:6379/0"
    worker_roles: str = ""

    # Fernet key (base64) for encrypting stored secrets at rest. Empty = writes
    # fail closed; reads/injection fall back to the env values below.
    secret_key: str = ""

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
    model_prices: dict[str, ModelPrice] = {
        "opus": ModelPrice(input=0.015, output=0.075),
        "sonnet": ModelPrice(input=0.003, output=0.015),
        "haiku": ModelPrice(input=0.001, output=0.005),
    }
    budget_limit_usd: float = 100.0
    agent_max_iterations: int = 25
    agent_bash_timeout_s: int = 120
    agent_runtime: str = "claude_code"
    # llm_provider="claude_cli" runs agents on the Claude subscription via `claude -p`
    # (no Anthropic key). These configure that path:
    claude_bin: str = "claude"
    claude_timeout_s: int = 900
    workspace_root: str = "/tmp/naaf-workspaces"
    attachments_root: str = "~/.naaf"
    storage_backend: str = "local"          # "local" | "s3"
    s3_bucket: str = ""
    s3_region: str = ""
    max_attachment_bytes: int = 10_485_760  # 10 MB
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
