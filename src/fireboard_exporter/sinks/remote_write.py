"""Minimal Prometheus remote_write (prompb) encoder + HTTP client."""

from __future__ import annotations

import struct
from dataclasses import dataclass

import httpx
import snappy


@dataclass(frozen=True, slots=True)
class RemoteSample:
    """One labeled sample for remote_write."""

    name: str
    labels: dict[str, str]
    value: float
    timestamp_ms: int


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value & 0x7F)
    return bytes(out)


def _encode_key(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)


def _encode_bytes(field_number: int, data: bytes) -> bytes:
    return _encode_key(field_number, 2) + _encode_varint(len(data)) + data


def _encode_string(field_number: int, value: str) -> bytes:
    return _encode_bytes(field_number, value.encode("utf-8"))


def _encode_double(field_number: int, value: float) -> bytes:
    return _encode_key(field_number, 1) + struct.pack("<d", value)


def _encode_int64(field_number: int, value: int) -> bytes:
    return _encode_key(field_number, 0) + _encode_varint(value)


def _encode_label(name: str, value: str) -> bytes:
    # Label { name = 1; value = 2; }
    return _encode_string(1, name) + _encode_string(2, value)


def _encode_sample(value: float, timestamp_ms: int) -> bytes:
    # Sample { value = 1; timestamp = 2; } — value is double, timestamp int64
    return _encode_double(1, value) + _encode_int64(2, timestamp_ms)


def _encode_time_series(sample: RemoteSample) -> bytes:
    # TimeSeries { labels = 1; samples = 2; }
    labels = dict(sample.labels)
    labels["__name__"] = sample.name
    body = bytearray()
    for key in sorted(labels):
        body.extend(_encode_bytes(1, _encode_label(key, labels[key])))
    body.extend(_encode_bytes(2, _encode_sample(sample.value, sample.timestamp_ms)))
    return bytes(body)


def encode_write_request(samples: list[RemoteSample]) -> bytes:
    """Encode a Prometheus remote_write WriteRequest protobuf payload."""
    body = bytearray()
    for sample in samples:
        body.extend(_encode_bytes(1, _encode_time_series(sample)))
    return snappy.compress(bytes(body))


async def push_remote_write(
    *,
    url: str,
    username: str,
    token: str,
    samples: list[RemoteSample],
    user_agent: str,
    client: httpx.AsyncClient | None = None,
) -> None:
    """POST snappy-compressed WriteRequest to a Prometheus remote_write endpoint."""
    if not samples:
        return
    payload = encode_write_request(samples)
    headers = {
        "Content-Type": "application/x-protobuf",
        "Content-Encoding": "snappy",
        "X-Prometheus-Remote-Write-Version": "0.1.0",
        "User-Agent": user_agent,
    }
    owns = client is None
    http = client or httpx.AsyncClient(timeout=30.0)
    try:
        response = await http.post(
            url,
            content=payload,
            headers=headers,
            auth=(username, token),
        )
        response.raise_for_status()
    finally:
        if owns:
            await http.aclose()
