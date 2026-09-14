"""search_historical_incidents (design-doc §5.9), wrapping Historical
Incident Retrieval (§5.7)."""
import httpx

from tools.config import BACKEND_URL


def search_historical_incidents(query: str, limit: int = 3) -> dict:
    resp = httpx.get(
        f"{BACKEND_URL}/api/incidents/search", params={"query": query, "limit": limit}, timeout=20.0
    )
    resp.raise_for_status()
    return resp.json()
