"""get_service_telemetry / get_anomalies (design-doc §5.9), wrapping
Telemetry Collection (§5.5) and ML-Based Anomaly Detection (§5.6).
"""
import httpx

from tools.config import BACKEND_URL


def get_service_telemetry(service: str) -> dict:
    resp = httpx.get(f"{BACKEND_URL}/api/telemetry", params={"service": service}, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def get_anomalies() -> dict:
    resp = httpx.get(f"{BACKEND_URL}/api/telemetry/anomalies", timeout=20.0)
    resp.raise_for_status()
    return resp.json()
