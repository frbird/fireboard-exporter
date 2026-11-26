"""Metric sinks for FireBoard poll results."""

from fireboard_exporter.sinks.base import Sink, build_sinks
from fireboard_exporter.sinks.grafana import GrafanaSink
from fireboard_exporter.sinks.influx import InfluxSink

__all__ = ["Sink", "GrafanaSink", "InfluxSink", "build_sinks"]
