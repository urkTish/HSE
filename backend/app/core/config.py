"""Application settings, read from environment variables (see root .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CONTRACT_VERSION = "0.16.0"  # contract: licence v1 (trial readiness B)
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
    lockout_threshold: int = 10
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
    # Comma-separated emails allowed to permanently delete a project (D-265). Empty = nobody.
    project_delete_emails: str = ""
    # Rebuild dropped KPI cache scopes in the background once writes settle (app.kpi.warm).
    kpi_warm: bool = True
    # Heavy KPI / dashboard reads computing at once per process (app.api.deps.cpu_slot); the GIL
    # serialises them anyway, and more only makes short requests wait behind them.
    kpi_cpu_slots: int = 3
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

    # Outgoing email (D-279): any SMTP provider. No SMTP_HOST / SMTP_FROM = emails stay in the
    # outbox (email_outbox) and the `email_send` job only reports how many are waiting.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = Field(default="", description='e.g. "HSE Platform <hse@example.sa>"')
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = 30.0
    email_batch_size: int = 50  # rows per job run (the job runs every minute)
    email_max_attempts: int = 6  # message-level failures before a row is marked failed
    email_retry_base_seconds: int = 60  # backoff: base, 2x, 4x … (capped at one hour)
    email_max_age_hours: int = 72  # older queued rows are marked failed, not sent (stale links)

    # Licence (trial readiness, D-289…D-298). No key anywhere = unlimited (dev, tests). The key
    # pasted by the HSE Manager is stored in the database and wins over LICENCE_KEY / LICENCE_FILE,
    # which only bootstrap an install. LICENCE_PUBLIC_KEY (PEM, or base64 of the 32 raw bytes)
    # overrides the public key shipped in app/data/licence_public_key.pem.
    licence_key: str | None = None
    licence_file: str | None = None
    licence_public_key: str | None = None
    # How long a process reuses the active key and the usage figures (renewal is picked up by
    # every worker within this time, without a restart). 0 = read every time (tests, e2e).
    licence_cache_seconds: int = 30

    # Seed (only used by app.seed)
    seed_password: str | None = None

    @model_validator(mode="after")
    def _production_secrets(self) -> "Settings":
        """A production process never starts on the dev-only defaults or a plain-HTTP cookie."""
        if self.environment != "production":
            return self
        for name in ("jwt_secret", "field_encryption_key", "blind_index_key"):
            if str(getattr(self, name, "")).startswith("dev-only"):
                raise RuntimeError(f"{name.upper()} must be set in production")
        if not self.cookie_secure:
            raise RuntimeError("COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def project_deleters() -> frozenset[str]:
    raw = get_settings().project_delete_emails
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())
