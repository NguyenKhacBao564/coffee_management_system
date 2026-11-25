from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://nhutung:nhutung@localhost:5432/nhutung"
    session_ttl_seconds: int = Field(default=28_800, gt=0)
    login_failure_limit: int = Field(default=5, gt=0)
    login_lockout_enabled: bool = True
    login_failure_window_seconds: int = Field(default=900, gt=0)
    scale_ingestion_max_future_seconds: int = Field(default=300, gt=0, le=3600)
    scale_ingestion_max_body_bytes: int = Field(default=65_536, gt=1024, le=1_048_576)
    pilot_evidence_root: str = "/data/evidence"
    pilot_evidence_max_file_bytes: int = Field(default=10_485_760, gt=0, le=52_428_800)
    pilot_evidence_quota_per_facility_bytes: int = Field(default=5_368_709_120, gt=0)
    pilot_evidence_retention_days: int = Field(default=30, ge=1, le=3650)
    pilot_ai_mode: str = "disabled"
    pilot_ai_queue_limit: int = Field(default=20, ge=1, le=20)
    gemini_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def session_cookie_name(self) -> str:
        return "__Host-nt_session" if self.app_env.lower() not in {"local", "development", "test"} else "nt_session"

    @property
    def session_cookie_secure(self) -> bool:
        return self.app_env.lower() not in {"local", "development", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
