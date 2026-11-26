"""FastAPI entrypoint for the FireBoard exporter."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import structlog
import uvicorn
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST

from fireboard_exporter import __version__
from fireboard_exporter.config import Settings, get_settings
from fireboard_exporter.fireboard_client import FireboardClient
from fireboard_exporter.logging_config import configure_logging
from fireboard_exporter.poller import Poller
from fireboard_exporter.sinks.base import Sink, build_sinks
from fireboard_exporter.sinks.grafana import GrafanaSink

logger = structlog.get_logger(__name__)


class AppState:
    """Mutable runtime handles attached to the FastAPI app."""

    def __init__(self) -> None:
        self.settings: Settings | None = None
        self.client: FireboardClient | None = None
        self.sinks: list[Sink] = []
        self.poller: Poller | None = None
        self.poller_task: asyncio.Task[None] | None = None
        self.grafana: GrafanaSink | None = None


state = AppState()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    state.settings = settings
    state.client = FireboardClient(settings)
    state.sinks = build_sinks(settings)
    state.grafana = next(
        (sink for sink in state.sinks if isinstance(sink, GrafanaSink)),
        None,
    )
    state.poller = Poller(settings, state.client, state.sinks)
    state.poller_task = asyncio.create_task(state.poller.run(), name="fireboard-poller")
    logger.info(
        "exporter_started",
        version=settings.app_version,
        sinks=[sink.name for sink in state.sinks],
    )
    try:
        yield
    finally:
        if state.poller:
            state.poller.stop()
        if state.poller_task:
            state.poller_task.cancel()
            try:
                await state.poller_task
            except asyncio.CancelledError:
                pass
        for sink in state.sinks:
            await sink.aclose()
        if state.client:
            await state.client.aclose()
        logger.info("exporter_stopped")


app = FastAPI(
    title="Fireboard Exporter",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Liveness/readiness health endpoint."""
    version = state.settings.app_version if state.settings else __version__
    return JSONResponse({"status": "ok", "version": version})


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus exposition (FireBoard series only when grafana sink is enabled)."""
    if state.grafana is None:
        body = (
            b"# HELP fireboard_exporter_info Exporter process info\n"
            b"# TYPE fireboard_exporter_info gauge\n"
            b'fireboard_exporter_info{sinks="non-grafana"} 1\n'
        )
        return Response(content=body, media_type=CONTENT_TYPE_LATEST)
    return Response(content=state.grafana.metrics_payload(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/latest")
async def latest() -> dict[str, Any]:
    """Latest normalized poll result (handy for future dashboard widgets)."""
    if state.poller is None or state.poller.last_result is None:
        return {"success": False, "channels": [], "devices": [], "sessions": []}
    result = state.poller.last_result
    return {
        "success": result.success,
        "error": result.error,
        "channels": [
            {
                "device_uuid": c.device_uuid,
                "device_title": c.device_title,
                "channel": c.channel,
                "channel_label": c.channel_label,
                "temp_c": c.temp_c,
                "temp_f": c.temp_f,
                "observed_at": c.observed_at.isoformat() if c.observed_at else None,
            }
            for c in result.channels
        ],
        "devices": [
            {
                "device_uuid": d.device_uuid,
                "device_title": d.device_title,
                "last_templog": d.last_templog.isoformat() if d.last_templog else None,
            }
            for d in result.devices
        ],
        "sessions": [
            {"session_id": s.session_id, "session_title": s.session_title}
            for s in result.sessions
        ],
    }


def run() -> None:
    """CLI entrypoint used by the `fireboard-exporter` script."""
    settings = get_settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        "fireboard_exporter.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
