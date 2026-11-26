# Fireboard Exporter — Context

- **What it is:** Polls FireBoard Cloud API and writes temps to Grafana Cloud and/or InfluxDB v2
- **Current stage:** v0.1.0 scaffold complete (local / Docker / K8s)
- **Key constraint:** FireBoard API rate limit = 17 calls / 5 minutes per IP
- **Default poll:** one `GET /api/v1/devices.json` every 60s; sessions every 300s

## 2026-03-25 — Initial implementation

- Configurable `SINKS=grafana|influx|grafana,influx` (neither required exclusively; at least one required)
- Grafana: Prometheus `/metrics` + optional remote_write
- Influx: measurement `fireboard_temperature`
- Deferred: Keg Monitor widget, cook-time ML
