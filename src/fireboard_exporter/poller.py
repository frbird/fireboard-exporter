"""Background FireBoard poll loop."""

from __future__ import annotations

import asyncio
import time

import structlog

from fireboard_exporter.config import Settings
from fireboard_exporter.fireboard_client import (
    FireboardClient,
    FireboardRateLimitError,
)
from fireboard_exporter.models import PollResult
from fireboard_exporter.sinks.base import Sink
from fireboard_exporter.sinks.grafana import GrafanaSink

logger = structlog.get_logger(__name__)


class Poller:
    """Poll FireBoard on an interval and fan out to configured sinks."""

    def __init__(
        self,
        settings: Settings,
        client: FireboardClient,
        sinks: list[Sink],
    ) -> None:
        self._settings = settings
        self._client = client
        self._sinks = sinks
        self._stop = asyncio.Event()
        self._last_result: PollResult | None = None
        self._next_session_poll = 0.0
        self._backoff_seconds = 0

    @property
    def last_result(self) -> PollResult | None:
        return self._last_result

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        logger.info(
            "poller_started",
            poll_interval=self._settings.poll_interval_seconds,
            sinks=[sink.name for sink in self._sinks],
        )
        while not self._stop.is_set():
            started = time.perf_counter()
            include_sessions = time.monotonic() >= self._next_session_poll
            try:
                result = await self._client.poll(include_sessions=include_sessions)
                if include_sessions and result.success:
                    self._next_session_poll = (
                        time.monotonic() + self._settings.session_poll_interval_seconds
                    )
                self._backoff_seconds = 0
            except FireboardRateLimitError:
                self._backoff_seconds = max(self._backoff_seconds * 2, 300)
                logger.warning(
                    "fireboard_rate_limited",
                    backoff_seconds=self._backoff_seconds,
                )
                result = PollResult(success=False, error="rate_limited")
            except Exception as exc:  # noqa: BLE001
                logger.exception("poll_cycle_failed", error=str(exc))
                result = PollResult(success=False, error=str(exc))

            duration = time.perf_counter() - started
            self._last_result = result
            for sink in self._sinks:
                if isinstance(sink, GrafanaSink):
                    sink.observe_poll_duration(duration)
                    sink.record_api_request(
                        "devices",
                        "ok" if result.success else "error",
                    )
                try:
                    await sink.write(result)
                except Exception as exc:  # noqa: BLE001
                    logger.error("sink_write_failed", sink=sink.name, error=str(exc))

            sleep_for = (
                self._backoff_seconds
                if self._backoff_seconds
                else self._settings.poll_interval_seconds
            )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=sleep_for)
            except TimeoutError:
                continue
