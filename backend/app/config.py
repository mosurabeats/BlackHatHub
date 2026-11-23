"""Application configuration.

All settings can be supplied through environment variables prefixed with
``EXECHUB_`` or through a ``.env`` file located in the project root. Secrets
(API keys) are read from the environment / ``.env`` only and are never stored
in the database or returned by the API.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EXECHUB_",
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- runtime ---------------------------------------------------------
    environment: str = "production"  # production | development | test
    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path = PROJECT_ROOT / "data"
    database_url: str | None = None  # defaults to sqlite in data_dir
    static_dir: Path = PROJECT_ROOT / "frontend" / "dist"

    # --- sessions & security ---------------------------------------------
    session_hours: int = 12
    session_idle_minutes: int = 120
    vault_idle_minutes: int = 15
    cookie_secure: bool = False  # set true when served over HTTPS (Tailscale serve)
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    vault_max_failures: int = 5
    vault_lockout_minutes: int = 15
    initial_vault_pin: str = "2653"
    api_rate_limit_per_minute: int = 300

    # --- scheduler ---------------------------------------------------------
    scheduler_enabled: bool = True
    scheduler_poll_seconds: float = 5.0
    job_heartbeat_timeout_seconds: int = 900
    worker_threads: int = 2

    # --- research HTTP ------------------------------------------------------
    http_user_agent: str = "ExecutiveHub/1.0 (private research tool; respects robots and rate limits)"
    http_timeout_seconds: float = 30.0
    http_cache_minutes: int = 60

    # --- AI providers (secrets: env only) ------------------------------------
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    sam_gov_api_key: str | None = Field(default=None, validation_alias="SAM_GOV_API_KEY")
    socrata_app_token: str | None = Field(default=None, validation_alias="SOCRATA_APP_TOKEN")
    ai_enabled: bool = True

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'executive_hub.db').as_posix()}"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s


def reset_settings_cache() -> None:
    get_settings.cache_clear()


def running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ
