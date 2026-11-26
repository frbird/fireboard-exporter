"""Config validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fireboard_exporter.config import Settings, get_settings


def test_requires_at_least_one_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIREBOARD_TOKEN", "tok")
    monkeypatch.setenv("SINKS", "")
    with pytest.raises(ValidationError, match="SINKS"):
        Settings()


def test_grafana_only(grafana_env: None) -> None:
    settings = get_settings()
    assert settings.grafana_enabled is True
    assert settings.influx_enabled is False


def test_influx_only(influx_env: None) -> None:
    settings = get_settings()
    assert settings.grafana_enabled is False
    assert settings.influx_enabled is True


def test_both_sinks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SINKS", "grafana,influx")
    monkeypatch.setenv("FIREBOARD_TOKEN", "tok")
    monkeypatch.setenv("INFLUX_URL", "http://localhost:8086")
    monkeypatch.setenv("INFLUX_TOKEN", "t")
    monkeypatch.setenv("INFLUX_ORG", "o")
    monkeypatch.setenv("INFLUX_BUCKET", "b")
    settings = get_settings()
    assert settings.enabled_sinks == {"grafana", "influx"}


def test_influx_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SINKS", "influx")
    monkeypatch.setenv("FIREBOARD_TOKEN", "tok")
    with pytest.raises(ValidationError, match="INFLUX_URL"):
        Settings()


def test_poll_interval_floor(grafana_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "5")
    settings = get_settings()
    assert settings.poll_interval_seconds == 20


def test_unknown_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SINKS", "prometheus")
    monkeypatch.setenv("FIREBOARD_TOKEN", "tok")
    with pytest.raises(ValidationError, match="Unknown sink"):
        Settings()
