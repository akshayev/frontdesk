"""Settings read from environment (.env in development). Secrets never logged."""

from functools import lru_cache

from pydantic import Field, SecretStr
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
    # D-045/D-046: position from the right of the client's X-Forwarded-For entry;
    # 0 = socket peer (dev/tests), 3 = Render production.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    sweep_enabled: bool = True  # ARCHITECTURE §9 loop; tests set SWEEP_ENABLED=false
    seed_demo_password: SecretStr | None = None  # scripts/seed.py only; never hard-coded
    static_dir: str | None = None  # built SPA; default app/static, else ../frontend/dist (app.spa)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()
