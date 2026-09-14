"""MCP server exposing the Distributed Change Intelligence Platform's six
investigation tools (design-doc §5.9).

Each tool below is a thin, typed wrapper around the backend's existing REST
API — nothing here talks to Postgres, Prometheus, or Gemini directly. That
means the LLM (§5.10) only ever reaches this system through a narrow,
auditable set of named tools with typed arguments, never through open-ended
access to raw infrastructure. Runs as its own container, reachable over
MCP's Streamable HTTP transport so the backend's Investigation Layer (acting
as the MCP client) can call it over the network rather than as a subprocess.
"""
from mcp.server.fastmcp import FastMCP

from tools.change_tools import get_change_details as _get_change_details
from tools.graph_tools import get_blast_radius as _get_blast_radius
from tools.graph_tools import get_dependency_graph as _get_dependency_graph
from tools.incident_tools import search_historical_incidents as _search_historical_incidents
from tools.telemetry_tools import get_anomalies as _get_anomalies
from tools.telemetry_tools import get_service_telemetry as _get_service_telemetry

mcp = FastMCP("dcip-investigation-tools", host="0.0.0.0", port=8100)


@mcp.tool()
def get_change_details(service: str) -> dict:
    """Git diff metadata (commit SHA, author, changed files, timestamp) for
    a service's most recent deployment."""
    return _get_change_details(service)


@mcp.tool()
def get_dependency_graph(service: str | None = None) -> dict:
    """Service dependency graph. Pass `service` for just its direct
    dependencies/dependents; omit it for the full graph (all nodes/edges)."""
    return _get_dependency_graph(service)


@mcp.tool()
def get_blast_radius(service: str) -> dict:
    """Services potentially impacted downstream of a change to `service`,
    ranked by dependency distance. A hypothesis space, not a diagnosis."""
    return _get_blast_radius(service)


@mcp.tool()
def get_service_telemetry(service: str) -> dict:
    """Current latency (ms), error rate, request rate, CPU%, and memory
    (MB) for a service, pulled live from Prometheus."""
    return _get_service_telemetry(service)


@mcp.tool()
def get_anomalies() -> dict:
    """Runs the trained Isolation Forest across the demo mesh services and
    returns which ones are behaving anomalously right now, and on which
    metric. Answers "is this unusual?" only — never "why?"."""
    return _get_anomalies()


@mcp.tool()
def search_historical_incidents(query: str, limit: int = 3) -> dict:
    """Semantically similar past incidents for a free-text description of
    current evidence, via pgvector cosine similarity. A high-similarity
    match means "semantically similar", not "confirmed same root cause"."""
    return _search_historical_incidents(query, limit)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
