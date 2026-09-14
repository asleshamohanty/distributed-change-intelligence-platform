"""Telemetry Collection (design-doc §5.5).

Queries Prometheus's HTTP query API — rather than scraping the demo services
directly from the backend — and normalizes the result into the feature
shape the anomaly model expects (ml/features.py). Each mesh service's
Prometheus scrape job is named after the service itself (see
prometheus/prometheus.yml), so Prometheus's built-in `job` label is all
that's needed to select one service's series; no extra relabeling required.
"""
import math
import os

import httpx
from sqlalchemy.orm import Session

from app.models import TelemetryEvent

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")

# 2m rate window: long enough to smooth over Prometheus's 5s scrape jitter,
# short enough that a failure-injection toggle shows up within the demo.
_RATE_WINDOW = "2m"

# Plain str.format() templates (`{{` / `}}` escape literal PromQL braces) —
# filled in with both `service` and `window` at query time.
QUERIES = {
    "latency_ms": (
        '1000 * sum(rate(http_request_duration_seconds_sum{{job="{service}"}}[{window}])) '
        '/ sum(rate(http_request_duration_seconds_count{{job="{service}"}}[{window}]))'
    ),
    "error_rate": (
        'sum(rate(http_requests_total{{job="{service}",status=~"5.."}}[{window}])) '
        '/ sum(rate(http_requests_total{{job="{service}"}}[{window}]))'
    ),
    "request_rate": 'sum(rate(http_requests_total{{job="{service}"}}[{window}]))',
    "cpu_percent": 'avg(process_cpu_usage{{job="{service}"}})',
    "memory_mb": 'avg(process_memory_usage{{job="{service}"}})',
}


def _instant_query(promql: str) -> float | None:
    resp = httpx.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": promql}, timeout=5.0)
    resp.raise_for_status()
    result = resp.json()["data"]["result"]
    if not result:
        return None
    value = float(result[0]["value"][1])
    return None if math.isnan(value) else value


def get_service_telemetry(service: str) -> dict:
    telemetry = {}
    for metric_name, template in QUERIES.items():
        query = template.format(service=service, window=_RATE_WINDOW)
        value = _instant_query(query)
        telemetry[metric_name] = value if value is not None else 0.0
    return telemetry


def record_telemetry_snapshot(db: Session, service: str, telemetry: dict) -> None:
    for metric_name, value in telemetry.items():
        db.add(TelemetryEvent(service_id=service, metric_name=metric_name, metric_value=value))
    db.commit()
