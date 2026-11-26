"""Grafana sink via Prometheus /metrics and optional remote_write."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from fireboard_exporter.config import Settings
from fireboard_exporter.models import PollResult
from fireboard_exporter.sinks.remote_write import RemoteSample, push_remote_write

logger = structlog.get_logger(__name__)


class GrafanaSink:
    """Expose FireBoard readings as Prometheus metrics; optionally remote_write."""

    name = "grafana"

    def __init__(self, settings: Settings, registry: CollectorRegistry | None = None) -> None:
        self._settings = settings
        self.registry = registry or CollectorRegistry()
        self._channel_temps: dict[tuple[str, str, str, str], float] = {}
        self._device_last: dict[tuple[str, str], float] = {}
        self._session_keys: set[tuple[str, str]] = set()

        self.channel_temp = Gauge(
            "fireboard_channel_temperature_celsius",
            "Latest FireBoard channel temperature in Celsius",
            ["device_uuid", "device_title", "channel", "channel_label"],
            registry=self.registry,
        )
        self.device_last_templog = Gauge(
            "fireboard_device_last_templog_timestamp_seconds",
            "Unix timestamp of last FireBoard device templog",
            ["device_uuid", "device_title"],
            registry=self.registry,
        )
        self.session_info = Gauge(
            "fireboard_session_info",
            "Active FireBoard cook session (1 = open)",
            ["session_id", "session_title"],
            registry=self.registry,
        )
        self.up = Gauge(
            "fireboard_up",
            "1 if the last FireBoard poll succeeded",
            registry=self.registry,
        )
        self.api_requests = Counter(
            "fireboard_api_requests_total",
            "FireBoard API requests made by the exporter",
            ["endpoint", "status"],
            registry=self.registry,
        )
        self.poll_duration = Histogram(
            "fireboard_poll_duration_seconds",
            "Duration of FireBoard poll cycles",
            registry=self.registry,
        )
        self.up.set(0)

    def observe_poll_duration(self, seconds: float) -> None:
        self.poll_duration.observe(seconds)

    def record_api_request(self, endpoint: str, status: str) -> None:
        self.api_requests.labels(endpoint=endpoint, status=status).inc()

    def metrics_payload(self) -> bytes:
        """Return Prometheus text exposition for this sink's registry."""
        return generate_latest(self.registry)

    async def write(self, result: PollResult) -> None:
        self.up.set(1 if result.success else 0)
        if not result.success:
            return

        seen_channels: set[tuple[str, str, str, str]] = set()
        for reading in result.channels:
            key = (
                reading.device_uuid,
                reading.device_title,
                str(reading.channel),
                reading.channel_label,
            )
            seen_channels.add(key)
            self.channel_temp.labels(*key).set(reading.temp_c)
            self._channel_temps[key] = reading.temp_c

        for stale in set(self._channel_temps) - seen_channels:
            self.channel_temp.remove(*stale)
            del self._channel_temps[stale]

        seen_devices: set[tuple[str, str]] = set()
        for device in result.devices:
            key = (device.device_uuid, device.device_title)
            seen_devices.add(key)
            ts = device.last_templog.timestamp() if device.last_templog else 0.0
            self.device_last_templog.labels(*key).set(ts)
            self._device_last[key] = ts

        for stale in set(self._device_last) - seen_devices:
            self.device_last_templog.remove(*stale)
            del self._device_last[stale]

        seen_sessions: set[tuple[str, str]] = set()
        for session in result.sessions:
            key = (session.session_id, session.session_title)
            seen_sessions.add(key)
            self.session_info.labels(*key).set(1)
        for stale in self._session_keys - seen_sessions:
            self.session_info.remove(*stale)
        self._session_keys = seen_sessions

        if self._settings.grafana_remote_write_configured:
            await self._remote_write(result)

    async def _remote_write(self, result: PollResult) -> None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        samples: list[RemoteSample] = [
            RemoteSample(
                name="fireboard_up",
                labels={},
                value=1.0 if result.success else 0.0,
                timestamp_ms=now_ms,
            )
        ]
        for reading in result.channels:
            samples.append(
                RemoteSample(
                    name="fireboard_channel_temperature_celsius",
                    labels={
                        "device_uuid": reading.device_uuid,
                        "device_title": reading.device_title,
                        "channel": str(reading.channel),
                        "channel_label": reading.channel_label,
                    },
                    value=reading.temp_c,
                    timestamp_ms=now_ms,
                )
            )
        for device in result.devices:
            samples.append(
                RemoteSample(
                    name="fireboard_device_last_templog_timestamp_seconds",
                    labels={
                        "device_uuid": device.device_uuid,
                        "device_title": device.device_title,
                    },
                    value=device.last_templog.timestamp() if device.last_templog else 0.0,
                    timestamp_ms=now_ms,
                )
            )
        for session in result.sessions:
            samples.append(
                RemoteSample(
                    name="fireboard_session_info",
                    labels={
                        "session_id": session.session_id,
                        "session_title": session.session_title,
                    },
                    value=1.0,
                    timestamp_ms=now_ms,
                )
            )
        try:
            await push_remote_write(
                url=self._settings.grafana_remote_write_url or "",
                username=self._settings.grafana_remote_write_username or "",
                token=self._settings.grafana_remote_write_token or "",
                samples=samples,
                user_agent=self._settings.fireboard_user_agent,
            )
            logger.info("grafana_remote_write_ok", samples=len(samples))
        except Exception as exc:  # noqa: BLE001
            logger.error("grafana_remote_write_failed", error=str(exc))

    async def aclose(self) -> None:
        return
