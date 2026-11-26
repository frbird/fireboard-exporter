"""InfluxDB v2 sink."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from fireboard_exporter.config import Settings
from fireboard_exporter.models import PollResult

logger = structlog.get_logger(__name__)


class InfluxSink:
    """Write FireBoard readings to InfluxDB v2."""

    name = "influx"

    def __init__(self, settings: Settings, client: InfluxDBClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or InfluxDBClient(
            url=settings.influx_url or "",
            token=settings.influx_token or "",
            org=settings.influx_org or "",
        )
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        self._bucket = settings.influx_bucket or ""
        self._org = settings.influx_org or ""

    async def write(self, result: PollResult) -> None:
        if not result.success:
            return

        now = datetime.now(tz=timezone.utc)
        points: list[Point] = []
        for reading in result.channels:
            ts = reading.observed_at or now
            point = (
                Point("fireboard_temperature")
                .tag("device_uuid", reading.device_uuid)
                .tag("device_title", reading.device_title)
                .tag("channel", str(reading.channel))
                .tag("channel_label", reading.channel_label)
                .field("temp_c", reading.temp_c)
                .field("temp_f", reading.temp_f)
                .time(ts)
            )
            points.append(point)

        for device in result.devices:
            if device.last_templog is None:
                continue
            points.append(
                Point("fireboard_device")
                .tag("device_uuid", device.device_uuid)
                .tag("device_title", device.device_title)
                .field("last_templog_unix", int(device.last_templog.timestamp()))
                .time(now)
            )

        for session in result.sessions:
            points.append(
                Point("fireboard_session")
                .tag("session_id", session.session_id)
                .tag("session_title", session.session_title)
                .field("active", 1)
                .time(now)
            )

        if not points:
            return

        try:
            self._write_api.write(bucket=self._bucket, org=self._org, record=points)
            logger.info("influx_write_ok", points=len(points))
        except Exception as exc:  # noqa: BLE001
            logger.error("influx_write_failed", error=str(exc))
            raise

    async def aclose(self) -> None:
        if self._owns_client:
            self._client.close()
