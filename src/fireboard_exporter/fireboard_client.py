"""FireBoard Cloud API client."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from fireboard_exporter.config import Settings
from fireboard_exporter.models import (
    ChannelReading,
    DeviceStatus,
    PollResult,
    SessionInfo,
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
)

logger = structlog.get_logger(__name__)


class FireboardRateLimitError(Exception):
    """Raised when FireBoard returns HTTP 429."""


class FireboardAuthError(Exception):
    """Raised when authentication fails."""


class FireboardClient:
    """Thin async client for FireBoard REST API v1."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.fireboard_base_url.rstrip("/"),
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": settings.fireboard_user_agent},
        )
        self._token = settings.fireboard_token
        self._api_requests = 0

    @property
    def api_request_count(self) -> int:
        return self._api_requests

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def ensure_token(self) -> str:
        """Return a valid auth token, logging in when needed."""
        if self._token:
            return self._token
        return await self.login()

    async def login(self) -> str:
        """Authenticate and cache the account token."""
        if not self._settings.fireboard_username or not self._settings.fireboard_password:
            raise FireboardAuthError("username/password required when FIREBOARD_TOKEN is unset")

        response = await self._request(
            "POST",
            "/api/rest-auth/login/",
            json={
                "username": self._settings.fireboard_username,
                "password": self._settings.fireboard_password,
            },
            auth=False,
        )
        data = response.json()
        key = data.get("key")
        if not key:
            raise FireboardAuthError("login response missing key")
        self._token = key
        logger.info("fireboard_login_ok")
        return key

    async def list_devices(self) -> list[dict[str, Any]]:
        """GET /api/v1/devices.json"""
        response = await self._request("GET", "/api/v1/devices.json")
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("unexpected devices payload")
        return payload

    async def list_sessions(self) -> list[dict[str, Any]]:
        """GET /api/v1/sessions.json"""
        response = await self._request("GET", "/api/v1/sessions.json")
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("unexpected sessions payload")
        return payload

    async def poll(self, *, include_sessions: bool = False) -> PollResult:
        """Fetch devices (and optionally sessions) and normalize readings."""
        try:
            devices_raw = await self.list_devices()
            sessions_raw: list[dict[str, Any]] = []
            if include_sessions:
                sessions_raw = await self.list_sessions()
        except FireboardRateLimitError:
            raise
        except FireboardAuthError:
            # Retry once after re-login when using password auth.
            if self._settings.fireboard_username and self._settings.fireboard_password:
                self._token = None
                await self.login()
                devices_raw = await self.list_devices()
                sessions_raw = await self.list_sessions() if include_sessions else []
            else:
                raise
        except Exception as exc:  # noqa: BLE001 — surfaced to poller as PollResult
            logger.exception("fireboard_poll_failed", error=str(exc))
            return PollResult(success=False, error=str(exc))

        return PollResult(
            channels=self._parse_channels(devices_raw),
            devices=self._parse_devices(devices_raw),
            sessions=self._parse_sessions(sessions_raw),
            success=True,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        if auth:
            token = await self.ensure_token()
            headers["Authorization"] = f"Token {token}"

        self._api_requests += 1
        response = await self._client.request(method, path, json=json, headers=headers)

        if response.status_code == 429:
            raise FireboardRateLimitError("FireBoard API rate limit exceeded")
        if response.status_code in {401, 403}:
            raise FireboardAuthError(f"auth failed: HTTP {response.status_code}")
        response.raise_for_status()
        return response

    def _parse_channels(self, devices: list[dict[str, Any]]) -> list[ChannelReading]:
        readings: list[ChannelReading] = []
        for device in devices:
            device_uuid = str(device.get("uuid") or device.get("UUID") or "")
            device_title = str(device.get("title") or device_uuid or "unknown")
            channel_labels = {
                int(ch.get("channel")): str(ch.get("channel_label") or ch.get("label") or f"CH{ch.get('channel')}")
                for ch in (device.get("channels") or [])
                if ch.get("channel") is not None
            }
            for temp in device.get("latest_temps") or []:
                channel = int(temp["channel"])
                raw_temp = float(temp["temp"])
                degree_type = int(temp.get("degreetype") or 2)
                if degree_type == 1:
                    temp_c = raw_temp
                    temp_f = celsius_to_fahrenheit(raw_temp)
                else:
                    temp_f = raw_temp
                    temp_c = fahrenheit_to_celsius(raw_temp)
                observed_at = _parse_dt(temp.get("created"))
                readings.append(
                    ChannelReading(
                        device_uuid=device_uuid,
                        device_title=device_title,
                        channel=channel,
                        channel_label=channel_labels.get(channel, f"CH{channel}"),
                        temp_c=temp_c,
                        temp_f=temp_f,
                        observed_at=observed_at,
                    )
                )
        return readings

    def _parse_devices(self, devices: list[dict[str, Any]]) -> list[DeviceStatus]:
        result: list[DeviceStatus] = []
        for device in devices:
            device_uuid = str(device.get("uuid") or device.get("UUID") or "")
            device_title = str(device.get("title") or device_uuid or "unknown")
            result.append(
                DeviceStatus(
                    device_uuid=device_uuid,
                    device_title=device_title,
                    last_templog=_parse_dt(device.get("last_templog")),
                )
            )
        return result

    def _parse_sessions(self, sessions: list[dict[str, Any]]) -> list[SessionInfo]:
        result: list[SessionInfo] = []
        for session in sessions:
            end_time = session.get("end_time")
            # Treat missing/null end_time as active/open session.
            if end_time:
                continue
            session_id = str(session.get("id") or "")
            title = str(session.get("title") or session_id or "session")
            if session_id:
                result.append(SessionInfo(session_id=session_id, session_title=title))
        return result


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
