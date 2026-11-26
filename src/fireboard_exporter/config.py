"""Environment-driven configuration with sink validation."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SinkName = Literal["grafana", "influx"]

MIN_POLL_INTERVAL_SECONDS = 20


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    sinks: str = Field(default="", validation_alias="SINKS")

    fireboard_base_url: str = "https://fireboard.io"
    fireboard_token: str | None = None
    fireboard_username: str | None = None
    fireboard_password: str | None = None
    fireboard_user_agent: str = "FireboardExporter/0.1.0"

    poll_interval_seconds: int = 60
    session_poll_interval_seconds: int = 300
    http_timeout_seconds: float = 15.0

    grafana_remote_write_url: str | None = None
    grafana_remote_write_username: str | None = None
    grafana_remote_write_token: str | None = None

    influx_url: str | None = None
    influx_token: str | None = None
    influx_org: str | None = None
    influx_bucket: str | None = None

    @field_validator("poll_interval_seconds")
    @classmethod
    def enforce_min_poll_interval(cls, value: int) -> int:
        if value < MIN_POLL_INTERVAL_SECONDS:
            return MIN_POLL_INTERVAL_SECONDS
        return value

    @field_validator("sinks")
    @classmethod
    def normalize_sinks(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_auth_and_sinks(self) -> Self:
        enabled = self.enabled_sinks
        if not enabled:
            raise ValueError(
                "SINKS must include at least one of: grafana, influx "
                "(example: SINKS=grafana or SINKS=influx or SINKS=grafana,influx)"
            )

        has_token = bool(self.fireboard_token)
        has_password = bool(self.fireboard_username and self.fireboard_password)
        if not has_token and not has_password:
            raise ValueError(
                "Set FIREBOARD_TOKEN or both FIREBOARD_USERNAME and FIREBOARD_PASSWORD"
            )

        if "influx" in enabled:
            missing = [
                name
                for name, val in (
                    ("INFLUX_URL", self.influx_url),
                    ("INFLUX_TOKEN", self.influx_token),
                    ("INFLUX_ORG", self.influx_org),
                    ("INFLUX_BUCKET", self.influx_bucket),
                )
                if not val
            ]
            if missing:
                raise ValueError(
                    f"SINKS includes influx but missing required env: {', '.join(missing)}"
                )

        return self

    @property
    def enabled_sinks(self) -> set[SinkName]:
        """Return the validated set of enabled sink names."""
        parts = {part.strip() for part in self.sinks.split(",") if part.strip()}
        allowed: set[SinkName] = set()
        for part in parts:
            if part not in {"grafana", "influx"}:
                raise ValueError(
                    f"Unknown sink '{part}' in SINKS; allowed: grafana, influx"
                )
            allowed.add(part)  # type: ignore[arg-type]
        return allowed

    @property
    def grafana_enabled(self) -> bool:
        return "grafana" in self.enabled_sinks

    @property
    def influx_enabled(self) -> bool:
        return "influx" in self.enabled_sinks

    @property
    def grafana_remote_write_configured(self) -> bool:
        return bool(
            self.grafana_remote_write_url
            and self.grafana_remote_write_username
            and self.grafana_remote_write_token
        )


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings (cleared in tests via get_settings.cache_clear())."""
    return Settings()
