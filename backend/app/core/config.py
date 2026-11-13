from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://cadence@127.0.0.1:54329/cadence_dev"
    test_database_url: str = "postgresql+asyncpg://cadence@127.0.0.1:54329/cadence_test"

    jwt_secret: str = Field(default="dev-only-secret-change-me-dev-only-secret-change-me", min_length=32)
    jwt_algorithm: str = "HS256"
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 30
    session_refresh_ttl_hours: int = 24
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    refresh_cookie_name: str = "refresh_token"

    cors_origins: str = "http://localhost:5173"
    app_base_url: str = "http://localhost:5173"
    api_base_url: str = "http://localhost:8000"
    max_body_bytes: int = 1_000_000

    resend_api_key: str = ""
    email_from: str = "Cadence <no-reply@cadence.local>"
    google_client_id: str = ""
    google_client_secret: str = ""
    sentry_dsn: str = ""
    export_dir: str = "./var/exports"

    # AI (PRD section 6). With no key the offline FakeProvider is used so the full flow works without one.
    anthropic_api_key: str = ""
    llm_provider: str = "auto"  # auto | anthropic | fake
    llm_model_extract: str = "claude-sonnet-5-5"
    llm_timeout_seconds: int = 45
    llm_max_tokens: int = 4096
    llm_enabled: bool = True  # kill switch (PRD Phase 5)
    # Speech-to-text fallback (FR-016): used where the browser has no working Web Speech API (Firefox, Brave, app shells)
    openai_api_key: str = ""
    stt_provider: str = "auto"  # auto (OpenAI when a key is set, otherwise unavailable) | openai | fake (tests only)
    stt_model: str = "gpt-4o-mini-transcribe"
    stt_timeout_seconds: int = 30
    stt_max_bytes: int = 10 * 1024 * 1024
    stt_per_hour: int = 20
    ai_daily_job_limit: int = 30
    ai_regenerations_per_day: int = 5
    embedded_worker: bool = True  # run the job worker inside the API process; set false when running a separate worker

    login_max_failures: int = 5
    login_window_seconds: int = 900
    api_rate_limit_per_minute: int = 300

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _require_real_secret_in_production(self) -> "Settings":
        if self.is_production and self.jwt_secret.startswith("dev-only"):
            raise ValueError("JWT_SECRET must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
