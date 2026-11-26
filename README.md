# Fireboard Exporter

Poll your FireBoard2 cloud temps once a minute and store them in **Grafana Cloud**, **local InfluxDB**, or both — you pick with `SINKS`.

```bash
export SINKS=grafana
export FIREBOARD_TOKEN=your-token
pip install -e .
fireboard-exporter
# → http://localhost:8080/metrics
```

| Sink | When | How data lands |
|------|------|----------------|
| `grafana` | `SINKS` includes `grafana` | `/metrics` for Alloy scrape, and/or Prometheus remote_write |
| `influx` | `SINKS` includes `influx` | InfluxDB v2 line protocol writes |
| both | `SINKS=grafana,influx` | Every successful poll fans out to both |

FireBoard’s API allows **17 calls / 5 minutes**. This exporter defaults to **one** `devices.json` call every 60s (~5/5min), plus an optional slower sessions poll.

## Quick start

### Local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# edit .env — set SINKS + FireBoard auth (+ Influx if needed)
fireboard-exporter
```

Endpoints: `GET /healthz`, `GET /metrics`, `GET /api/latest`.

### Docker

```bash
cp .env.example .env
docker compose up --build
```

### Kubernetes

See [`k8s/README.md`](k8s/README.md). Image tag in manifests: `ghcr.io/frbird/fireboard-exporter:0.1.0`.

## Configuration

Copy [`.env.example`](.env.example). Important variables:

| Variable | Required | Notes |
|----------|----------|-------|
| `SINKS` | yes | `grafana`, `influx`, or `grafana,influx` |
| `FIREBOARD_TOKEN` | one of | Prefer token auth |
| `FIREBOARD_USERNAME` / `FIREBOARD_PASSWORD` | one of | Used if token unset |
| `POLL_INTERVAL_SECONDS` | no | Default `60`, floor `20` |
| `GRAFANA_REMOTE_WRITE_*` | no | Direct push when grafana sink enabled |
| `INFLUX_URL` / `TOKEN` / `ORG` / `BUCKET` | if influx | Fail-fast if missing |

### Grafana-only (Alloy scrape)

1. Set `SINKS=grafana` and FireBoard credentials.
2. Point Alloy at the exporter — see [`deploy/alloy/scrape-fireboard.alloy.example`](deploy/alloy/scrape-fireboard.alloy.example).
3. Import [`grafana/dashboards/fireboard-overview.json`](grafana/dashboards/fireboard-overview.json).

Dashboard notes:

- **Temperatures are session-scoped:** the exporter only writes probe temps while a FireBoard cook session is open. No session → no temp series (health/API metrics still flow).
- Name your pit probe `Pit`, `Chamber`, `Grill`, or `Air` so chamber panels match (or edit `chamber_regex`).
- **Meat time-at-temp histogram** / **heatmap** exclude chamber-labeled probes — stall ≈ 150–170°F.

### Influx-only

```bash
SINKS=influx
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=...
INFLUX_ORG=home
INFLUX_BUCKET=fireboard
```

Explore with Flux:

```flux
from(bucket: "fireboard")
  |> range(start: -6h)
  |> filter(fn: (r) => r._measurement == "fireboard_temperature")
```

## Metrics

- `fireboard_channel_temperature_celsius{device_uuid,device_title,channel,channel_label}`
- `fireboard_device_last_templog_timestamp_seconds{device_uuid,device_title}`
- `fireboard_session_info{session_id,session_title}`
- `fireboard_up`
- `fireboard_api_requests_total{endpoint,status}`
- `fireboard_poll_duration_seconds`

Temperatures are normalized to Celsius (FireBoard `degreetype` 1=C, 2=F).

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## Deferred

- Keg Monitor dashboard widget (can use `GET /api/latest` so only this process hits FireBoard)
- Cook-time ML / prediction on stored history
