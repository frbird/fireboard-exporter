"""FireBoard client parsing and HTTP behavior."""

from __future__ import annotations

import httpx
import pytest
import respx

from fireboard_exporter.config import get_settings
from fireboard_exporter.fireboard_client import (
    FireboardClient,
    FireboardRateLimitError,
)


@pytest.mark.asyncio
async def test_parse_devices_fahrenheit(
    grafana_env: None,
    sample_devices: list[dict],
) -> None:
    settings = get_settings()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=sample_devices))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://fireboard.io",
    ) as http:
        client = FireboardClient(settings, client=http)
        result = await client.poll(include_sessions=False)

    assert result.success
    assert len(result.channels) == 2
    brisket = next(c for c in result.channels if c.channel == 1)
    assert brisket.channel_label == "Brisket"
    assert round(brisket.temp_f, 1) == 195.0
    assert round(brisket.temp_c, 2) == round((195.0 - 32) * 5 / 9, 2)


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_raises(grafana_env: None) -> None:
    settings = get_settings()
    respx.get("https://fireboard.io/api/v1/devices.json").mock(
        return_value=httpx.Response(429, json={"detail": "slow down"})
    )
    async with httpx.AsyncClient(base_url="https://fireboard.io") as http:
        client = FireboardClient(settings, client=http)
        with pytest.raises(FireboardRateLimitError):
            await client.list_devices()


@pytest.mark.asyncio
@respx.mock
async def test_active_sessions_only(
    grafana_env: None,
    sample_devices: list[dict],
    sample_sessions: list[dict],
) -> None:
    settings = get_settings()
    respx.get("https://fireboard.io/api/v1/devices.json").mock(
        return_value=httpx.Response(200, json=sample_devices)
    )
    respx.get("https://fireboard.io/api/v1/sessions.json").mock(
        return_value=httpx.Response(200, json=sample_sessions)
    )
    async with httpx.AsyncClient(base_url="https://fireboard.io") as http:
        client = FireboardClient(settings, client=http)
        result = await client.poll(include_sessions=True)

    assert len(result.sessions) == 1
    assert result.sessions[0].session_id == "42"
