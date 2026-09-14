"""get_dependency_graph / get_blast_radius (design-doc §5.9), wrapping the
Service Dependency Graph + Blast Radius Analysis (§5.2/§5.3).
"""
import httpx

from tools.config import BACKEND_URL


def get_dependency_graph(service: str | None = None) -> dict:
    if service:
        deps = httpx.get(
            f"{BACKEND_URL}/api/graph/dependencies", params={"service": service}, timeout=10.0
        )
        dependents = httpx.get(
            f"{BACKEND_URL}/api/graph/dependents", params={"service": service}, timeout=10.0
        )
        deps.raise_for_status()
        dependents.raise_for_status()
        return {
            "service": service,
            "dependencies": deps.json()["dependencies"],
            "dependents": dependents.json()["dependents"],
        }
    resp = httpx.get(f"{BACKEND_URL}/api/graph", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def get_blast_radius(service: str) -> dict:
    resp = httpx.get(f"{BACKEND_URL}/api/graph/blast-radius", params={"service": service}, timeout=10.0)
    if resp.status_code == 404:
        return {"error": f"unknown service: {service}"}
    resp.raise_for_status()
    return resp.json()
