"""HTTP handler tests (no live network poller)."""

from __future__ import annotations

import json

import pytest
from prometheus_client import CollectorRegistry

from fireboard_exporter.config import get_settings
from fireboard_exporter.main import healthz, latest, metrics, state
from fireboard_exporter.models import PollResult
from fireboard_exporter.poller import Poller
from fireboard_exporter.sinks.grafana import GrafanaSink


@pytest.mark.asyncio
async def test_healthz(grafana_env: None) -> None:
    state.settings = get_settings()
    response = await healthz()
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body == {"status": "ok", "version": "0.1.0"}


@pytest.mark.asyncio
async def test_metrics_with_grafana(grafana_env: None) -> None:
    settings = get_settings()
    state.settings = settings
    state.grafana = GrafanaSink(settings, registry=CollectorRegistry())
    response = await metrics()
    assert response.status_code == 200
    assert b"fireboard_up" in response.body


@pytest.mark.asyncio
async def test_metrics_without_grafana(influx_env: None) -> None:
    state.settings = get_settings()
    state.grafana = None
    response = await metrics()
    assert response.status_code == 200
    assert b"non-grafana" in response.body


@pytest.mark.asyncio
async def test_latest_empty(grafana_env: None) -> None:
    state.poller = None
    body = await latest()
    assert body["success"] is False
    assert body["channels"] == []


@pytest.mark.asyncio
async def test_latest_with_result(grafana_env: None) -> None:
    poller = object.__new__(Poller)
    poller._last_result = PollResult(success=True, channels=[], devices=[], sessions=[])
    state.poller = poller
    body = await latest()
    assert body["success"] is True
