"""Application settings, read from environment variables (see root .env.example)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

CONTRACT_VERSION = "0.11.0"
API_PREFIX = "/api/v1"
SESSION_COOKIE_NAME = "hse_session"
GATE_SESSION_COOKIE = "hse_gate_session"


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

    # ---- Phase 1 ----
    # AI (spec 1-dashboard §5.9). No key → the assistant answers AI_UNAVAILABLE (AI-18).
    anthropic_api_key: str | None = None
    ai_model_default: str = "claude-sonnet-5-5"
    ai_model_deep: str = "claude-opus-5-5"
    ai_server_fallbacks: bool = Field(
        default=True, description="Send the server-side refusal fallback (beta) with requests."
    )
    ai_timeout_seconds: float = 60.0
    ai_max_tool_rounds: int = 8
    # KPI facts cache (per API process): a dashboard fires ~15 /kpi requests over the same
    # facts. A committed fact write in any process clears it (kpi_generation_seq); this bounds
    # how long one snapshot is reused. 0 disables (the test suite runs with 0).
    kpi_cache_seconds: int = 300
    # Rebuild dropped KPI cache scopes in the background once writes settle (app.kpi.warm).
    kpi_warm: bool = True
    ai_questions_per_user_day: int = 60  # AI-17
    ai_reports_per_project_month: int = 10  # AI-17
    ai_insights_cache_minutes: int = 360

    # Field encryption for ID numbers (P2). Dev default only; set FIELD_ENCRYPTION_KEY in prod.
    field_encryption_key: str = Field(
        default="dev-only-field-key-change-me-dev-only-field-key", min_length=32
    )
    # Phase 2 blind index for worker ID lookup (P2-2): HMAC key separate from the encryption key.
    blind_index_key: str = Field(
        default="dev-only-blind-index-key-change-me-dev-only-blind-index", min_length=32
    )
    gate_device_idle_hours: int = 12  # GC-1
    gate_checks_per_minute: int = 120  # GC-3

    # Attachments: local storage root (S3/MinIO adapter later) and signed-URL secret (P1-3)
    storage_dir: str = "./var/storage"
    attachment_url_secret: str = Field(
        default="dev-only-attachment-url-secret-change-me", min_length=32
    )
    attachment_max_bytes: int = 20 * 1024 * 1024
    import_max_bytes: int = 5 * 1024 * 1024
    import_max_rows: int = 20_000

    # Seed (only used by app.seed)
    seed_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
