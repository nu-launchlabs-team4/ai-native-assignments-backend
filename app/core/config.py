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
    # Emails that become professors when they sign up or log in. Comma-separated.
    professor_emails: str = ""
    env: str = "local"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def professor_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.professor_emails.split(",") if e.strip()}

    @property
    def cookie_secure(self) -> bool:
        """Session cookies need HTTPS everywhere except a local http:// setup."""
        return self.env != "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
