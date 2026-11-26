"""Normalized FireBoard reading models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ChannelReading:
    """Single probe/channel temperature sample."""

    device_uuid: str
    device_title: str
    channel: int
    channel_label: str
    temp_c: float
    temp_f: float
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    """Device-level metadata from the last poll."""

    device_uuid: str
    device_title: str
    last_templog: datetime | None = None


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Lightweight cook session metadata."""

    session_id: str
    session_title: str


@dataclass(slots=True)
class PollResult:
    """Normalized result of one FireBoard poll cycle."""

    channels: list[ChannelReading] = field(default_factory=list)
    devices: list[DeviceStatus] = field(default_factory=list)
    sessions: list[SessionInfo] = field(default_factory=list)
    success: bool = True
    error: str | None = None


def fahrenheit_to_celsius(temp_f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (temp_f - 32.0) * 5.0 / 9.0


def celsius_to_fahrenheit(temp_c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (temp_c * 9.0 / 5.0) + 32.0
