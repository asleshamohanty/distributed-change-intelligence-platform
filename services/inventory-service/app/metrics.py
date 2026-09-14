"""Prometheus instrumentation shared shape across the demo mesh services.

Each service in services/ is an independently deployable container, so this
module is duplicated per service rather than imported from a shared package
— that mirrors how a real microservice repo keeps each service self-contained.

CPU/memory sampling uses only the Python stdlib (`resource`, `/proc/self`)
rather than adding a psutil dependency: `ru_utime`/`ru_stime` deltas between
scrapes give a process CPU% estimate, and `/proc/self/status`'s VmRSS gives
current resident memory on Linux (the containers this runs in). This is a
demo-scale approximation, not production-grade instrumentation — good enough
to make the failure-injection scenarios visible in the metrics.
"""
import resource
import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

registry = CollectorRegistry()

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
    registry=registry,
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    registry=registry,
)

PROCESS_CPU_USAGE = Gauge(
    "process_cpu_usage", "Process CPU usage percent (see metrics.py docstring)", registry=registry
)
PROCESS_MEMORY_USAGE = Gauge(
    "process_memory_usage", "Process resident memory usage in MB", registry=registry
)

_last_sample = {"wall": time.perf_counter(), "cpu": None}


def _cpu_time() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def _sample_process_metrics() -> None:
    now = time.perf_counter()
    cpu_now = _cpu_time()
    if _last_sample["cpu"] is not None:
        elapsed_wall = max(now - _last_sample["wall"], 1e-6)
        elapsed_cpu = max(cpu_now - _last_sample["cpu"], 0.0)
        PROCESS_CPU_USAGE.set(min(elapsed_cpu / elapsed_wall * 100, 100.0))
    _last_sample["wall"] = now
    _last_sample["cpu"] = cpu_now

    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    memory_kb = float(line.split()[1])
                    PROCESS_MEMORY_USAGE.set(memory_kb / 1024)
                    break
    except FileNotFoundError:
        # not running on Linux (e.g. local dev outside Docker) - leave the
        # gauge at its last known value rather than fail the scrape.
        pass


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        path = request.url.path
        if path != "/api/metrics":
            REQUEST_COUNT.labels(request.method, path, response.status_code).inc()
            REQUEST_LATENCY.labels(request.method, path).observe(duration)
        return response


def metrics_response() -> Response:
    _sample_process_metrics()
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
