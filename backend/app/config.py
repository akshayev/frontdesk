"""Settings read from environment (.env in development). Secrets never logged."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings; see ARCHITECTURE §12 for the env contract."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), extra="ignore", case_sensitive=False
    )

    database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    session_secret: SecretStr | None = None
    app_env: str = "development"
    public_base_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()
