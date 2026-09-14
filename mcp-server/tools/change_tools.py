"""get_change_details (design-doc §5.9), wrapping Change Intelligence (§5.1)."""
import httpx

from tools.config import BACKEND_URL


def get_change_details(service: str) -> dict:
    resp = httpx.get(
        f"{BACKEND_URL}/api/events/latest-deployment", params={"service": service}, timeout=10.0
    )
    if resp.status_code == 404:
        return {"error": f"no deployments found for service: {service}"}
    resp.raise_for_status()
    return resp.json()
