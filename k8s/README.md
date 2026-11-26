# Fireboard exporter — Kubernetes

## Apply

```bash
kubectl apply -f k8s/namespace.yaml
# Edit credentials first
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

Set `SINKS` in the ConfigMap to `grafana`, `influx`, or `grafana,influx`. When using Influx, add `INFLUX_*` keys to the Secret and include `influx` in `SINKS`.

## Scraping into Grafana Cloud

Point Grafana Alloy at the ClusterIP service (see [`deploy/alloy/scrape-fireboard.alloy.example`](../deploy/alloy/scrape-fireboard.alloy.example)), or set `GRAFANA_REMOTE_WRITE_*` on the Secret for direct push.

Metrics stay in-cluster by default (no public HTTPRoute).
