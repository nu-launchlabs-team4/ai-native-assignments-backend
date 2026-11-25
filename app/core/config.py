from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables or .env."""

    # hide_input_in_errors keeps secrets like DATABASE_URL out of startup error logs.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    supabase_url: str
    supabase_publishable_key: str
    # Which model the AI features use (app/ai/llm.py): claude_code while developing
    # (local only), anthropic with the API key for staging and the showcase, fake offline.
    ai_provider: Literal["claude_code", "anthropic", "fake"] = "claude_code"
    anthropic_api_key: str | None = None
    # From `claude setup-token`: logs the Claude Code CLI in inside Docker. A secret.
    claude_code_oauth_token: str | None = None
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
