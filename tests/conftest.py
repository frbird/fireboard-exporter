"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from fireboard_exporter.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def grafana_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SINKS", "grafana")
    monkeypatch.setenv("FIREBOARD_TOKEN", "test-token")
    monkeypatch.delenv("FIREBOARD_USERNAME", raising=False)
    monkeypatch.delenv("FIREBOARD_PASSWORD", raising=False)
    monkeypatch.delenv("INFLUX_URL", raising=False)
    monkeypatch.delenv("INFLUX_TOKEN", raising=False)
    monkeypatch.delenv("INFLUX_ORG", raising=False)
    monkeypatch.delenv("INFLUX_BUCKET", raising=False)


@pytest.fixture
def influx_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SINKS", "influx")
    monkeypatch.setenv("FIREBOARD_TOKEN", "test-token")
    monkeypatch.setenv("INFLUX_URL", "http://localhost:8086")
    monkeypatch.setenv("INFLUX_TOKEN", "influx-token")
    monkeypatch.setenv("INFLUX_ORG", "home")
    monkeypatch.setenv("INFLUX_BUCKET", "fireboard")


@pytest.fixture
def sample_devices() -> list[dict]:
    return [
        {
            "uuid": "device-1",
            "title": "Backyard FB2",
            "last_templog": "2026-03-20T18:00:00Z",
            "channels": [
                {"channel": 1, "channel_label": "Brisket"},
                {"channel": 2, "channel_label": "Pit"},
            ],
            "latest_temps": [
                {
                    "temp": 195.0,
                    "created": "2026-03-20T18:00:00Z",
                    "degreetype": 2,
                    "channel": 1,
                },
                {
                    "temp": 250.0,
                    "created": "2026-03-20T18:00:00Z",
                    "degreetype": 2,
                    "channel": 2,
                },
            ],
        }
    ]


@pytest.fixture
def sample_sessions() -> list[dict]:
    return [
        {"id": 42, "title": "Saturday brisket", "end_time": None},
        {"id": 41, "title": "Old cook", "end_time": "2026-03-01T00:00:00Z"},
    ]
