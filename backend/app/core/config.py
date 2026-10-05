"""Application settings, read from environment variables (see root .env.example)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

CONTRACT_VERSION = "0.1.0"
API_PREFIX = "/api/v1"
SESSION_COOKIE_NAME = "hse_session"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="development", description="development | test | production")
    database_url: str = "postgresql+psycopg://hse:hse@localhost:5432/hse"
    test_database_url: str = "postgresql+psycopg://hse:hse@localhost:5432/hse_test"

    # JWT / sessions (spec 0-foundation §5.1 rule 4)
    jwt_secret: str = Field(default="dev-only-change-me-dev-only-change-me", min_length=32)
    jwt_algorithm: str = "HS256"
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    cookie_secure: bool = False
    trust_proxy_headers: bool = False

    # Lockout (§5.1 rule 3)
    lockout_threshold: int = 5
    lockout_window_minutes: int = 15
    lockout_minutes: int = 15

    # Tokens (§5.1 rule 5)
    invite_token_hours: int = 72
    reset_token_minutes: int = 60

    # Privacy notice (§5.1 rule 6, P13)
    privacy_notice_version: str = "PN-1.0"

    # Audit retention for entries that belong to no project (§5.6 rule 40)
    org_audit_retention_years: int = 5

    # Public base URL of the frontend, used in emailed links
    frontend_base_url: str = "http://localhost:3000"

    # Seed (only used by app.seed)
    seed_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
