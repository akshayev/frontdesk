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
    app_db_password: SecretStr | None = None
    session_secret: SecretStr | None = None
    app_env: str = "development"
    public_base_url: str = "http://localhost:8000"
    sweep_enabled: bool = True  # ARCHITECTURE §9 loop; tests set SWEEP_ENABLED=false
    seed_demo_password: SecretStr | None = None  # scripts/seed.py only; never hard-coded
    static_dir: str | None = None  # built SPA; default app/static, else ../frontend/dist (app.spa)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()
