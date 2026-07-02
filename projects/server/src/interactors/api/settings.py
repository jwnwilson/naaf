from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="naaf_")

    db_url: str = "sqlite://"
    auth_mode: str = "dev"
    dev_owner_id: str = "dev-user"
    celery_broker_url: str = "redis://localhost:6379/0"
    worker_roles: str = ""

    @property
    def worker_roles_list(self) -> list[str]:
        return [r.strip() for r in self.worker_roles.split(",") if r.strip()]
