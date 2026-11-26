"""Sink selection and write behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry

from fireboard_exporter.config import get_settings
from fireboard_exporter.models import ChannelReading, DeviceStatus, PollResult, SessionInfo
from fireboard_exporter.sinks.base import build_sinks
from fireboard_exporter.sinks.grafana import GrafanaSink
from fireboard_exporter.sinks.influx import InfluxSink
from fireboard_exporter.sinks.remote_write import encode_write_request, RemoteSample


def _sample_result() -> PollResult:
    return PollResult(
        success=True,
        channels=[
            ChannelReading(
                device_uuid="device-1",
                device_title="Backyard FB2",
                channel=1,
                channel_label="Brisket",
                temp_c=90.56,
                temp_f=195.0,
                observed_at=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
            )
        ],
        devices=[
            DeviceStatus(
                device_uuid="device-1",
                device_title="Backyard FB2",
                last_templog=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
            )
        ],
        sessions=[SessionInfo(session_id="42", session_title="Saturday brisket")],
    )


def test_build_sinks_grafana_only(grafana_env: None) -> None:
    sinks = build_sinks(get_settings())
    assert [s.name for s in sinks] == ["grafana"]


def test_build_sinks_influx_only(influx_env: None) -> None:
    sinks = build_sinks(get_settings())
    assert [s.name for s in sinks] == ["influx"]


def test_build_sinks_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SINKS", "grafana,influx")
    monkeypatch.setenv("FIREBOARD_TOKEN", "tok")
    monkeypatch.setenv("INFLUX_URL", "http://localhost:8086")
    monkeypatch.setenv("INFLUX_TOKEN", "t")
    monkeypatch.setenv("INFLUX_ORG", "o")
    monkeypatch.setenv("INFLUX_BUCKET", "b")
    sinks = build_sinks(get_settings())
    assert {s.name for s in sinks} == {"grafana", "influx"}


@pytest.mark.asyncio
async def test_grafana_clears_stale_channels(grafana_env: None) -> None:
    sink = GrafanaSink(get_settings(), registry=CollectorRegistry())
    await sink.write(_sample_result())
    payload = sink.metrics_payload().decode()
    assert "fireboard_channel_temperature_celsius" in payload
    assert 'channel_label="Brisket"' in payload

    empty = PollResult(success=True, channels=[], devices=[], sessions=[])
    await sink.write(empty)
    payload = sink.metrics_payload().decode()
    assert 'channel_label="Brisket"' not in payload


@pytest.mark.asyncio
async def test_grafana_omits_temps_without_active_session(grafana_env: None) -> None:
    sink = GrafanaSink(get_settings(), registry=CollectorRegistry())
    await sink.write(_sample_result())
    assert 'channel_label="Brisket"' in sink.metrics_payload().decode()

    no_session = PollResult(
        success=True,
        channels=_sample_result().channels,
        devices=_sample_result().devices,
        sessions=[],
    )
    await sink.write(no_session)
    payload = sink.metrics_payload().decode()
    assert 'channel_label="Brisket"' not in payload
    assert "fireboard_up 1.0" in payload or "fireboard_up 1" in payload


def test_registry_samples_include_api_counter(grafana_env: None) -> None:
    sink = GrafanaSink(get_settings(), registry=CollectorRegistry())
    sink.record_api_request("devices", "ok")
    sink.up.set(1)
    names = {sample.name for sample in sink.registry_samples(timestamp_ms=1)}
    assert "fireboard_api_requests_total" in names
    assert "fireboard_up" in names


@pytest.mark.asyncio
async def test_influx_write_points(influx_env: None) -> None:
    settings = get_settings()
    mock_client = MagicMock()
    mock_write_api = MagicMock()
    mock_client.write_api.return_value = mock_write_api
    sink = InfluxSink(settings, client=mock_client)
    await sink.write(_sample_result())
    mock_write_api.write.assert_called_once()
    kwargs = mock_write_api.write.call_args.kwargs
    assert kwargs["bucket"] == "fireboard"
    assert len(kwargs["record"]) >= 1


def test_remote_write_encode_not_empty() -> None:
    payload = encode_write_request(
        [
            RemoteSample(
                name="fireboard_up",
                labels={},
                value=1.0,
                timestamp_ms=1_700_000_000_000,
            )
        ]
    )
    assert isinstance(payload, (bytes, bytearray))
    assert len(payload) > 0
