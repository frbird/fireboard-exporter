"""Sink protocol and factory."""

from __future__ import annotations

from typing import Protocol

import structlog

from fireboard_exporter.config import Settings
from fireboard_exporter.models import PollResult

logger = structlog.get_logger(__name__)


class Sink(Protocol):
    """Writes a normalized poll result to a downstream store."""

    name: str

    async def write(self, result: PollResult) -> None:
        """Persist readings from a successful (or failed) poll."""

    async def aclose(self) -> None:
        """Release sink resources."""


def build_sinks(settings: Settings) -> list[Sink]:
    """Construct enabled sinks from settings."""
    sinks: list[Sink] = []
    if settings.grafana_enabled:
        from fireboard_exporter.sinks.grafana import GrafanaSink

        sinks.append(GrafanaSink(settings))
        if not settings.grafana_remote_write_configured:
            logger.warning(
                "grafana_sink_scrape_only",
                message=(
                    "Grafana sink enabled without GRAFANA_REMOTE_WRITE_*; "
                    "expose /metrics for Alloy (or another scraper) to persist data"
                ),
            )
    if settings.influx_enabled:
        from fireboard_exporter.sinks.influx import InfluxSink

        sinks.append(InfluxSink(settings))
    return sinks
