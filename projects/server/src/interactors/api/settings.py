from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="naaf_")

    db_url: str = "sqlite://"
    auth_mode: str = "dev"
    dev_owner_id: str = "dev-user"
    celery_broker_url: str = "redis://localhost:6379/0"

    llm_provider: str = "claude"           # "claude" | "litellm"
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""           # blank = Anthropic default
    litellm_base_url: str = ""
    litellm_key: str = ""
    model_aliases: dict[str, str] = {}     # alias -> concrete model id (claude adapter)
    agent_max_iterations: int = 25
    agent_bash_timeout_s: int = 120
    agent_runtime: str = "claude_code"
