from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables or .env."""

    # hide_input_in_errors keeps secrets like DATABASE_URL out of startup error logs.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    supabase_url: str
    supabase_publishable_key: str
    anthropic_api_key: str | None = None  # optional until the AI features land
    allowed_origins: str = "http://localhost:3000"  # comma-separated
    env: str = "local"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
