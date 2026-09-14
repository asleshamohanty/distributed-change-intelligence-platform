"""Service Dependency Graph + Blast Radius Analysis (design-doc §5.2/§5.3).

The graph is rebuilt in-memory from the `dependencies` edge-list table on
every call that needs it — at this project's scale (single-digit nodes,
sub-millisecond query) there's no reason to cache it across requests, and
rebuilding avoids an entire class of "graph went stale after an edge
changed" bugs. This mirrors the doc's own framing: Postgres is the source of
truth, NetworkX is a derived in-memory view (§5.2, §7).
"""
import networkx as nx
from sqlalchemy.orm import Session

from app.models import Dependency


def load_graph(db: Session) -> nx.DiGraph:
    graph = nx.DiGraph()
    for edge in db.query(Dependency).all():
        graph.add_edge(edge.source_service_id, edge.target_service_id)
    return graph


def get_dependencies(graph: nx.DiGraph, service: str) -> list[str]:
    """Direct downstream calls made BY `service` ("who does X call")."""
    if service not in graph:
        return []
    return list(graph.successors(service))


def get_dependents(graph: nx.DiGraph, service: str) -> list[str]:
    """Direct callers OF `service` ("who calls X")."""
    if service not in graph:
        return []
    return list(graph.predecessors(service))


def get_blast_radius(graph: nx.DiGraph, changed_service: str) -> set[str]:
    """Every service reachable downstream of a change — a hypothesis space
    of what *could* be affected, never a diagnosis of what *was* (doc §5.3's
    "Wording matters" callout: "potentially impacted", not "affected" or
    "broken")."""
    if changed_service not in graph:
        return set()
    return nx.descendants(graph, changed_service)


def get_blast_radius_enriched(graph: nx.DiGraph, changed_service: str) -> list[dict]:
    """Blast radius enriched with BFS dependency distance, nearest first, so
    an engineer can prioritize instead of investigating every downstream
    service at once (doc §5.3's worked example). Recent-anomaly/error-state
    enrichment is layered on top of this by the Investigation Layer (§5.8)
    once telemetry/anomaly data exists — that's a runtime-evidence concern,
    not a graph-structure one, so it doesn't belong in this function.
    """
    impacted = get_blast_radius(graph, changed_service)
    if not impacted:
        return []
    distances = nx.shortest_path_length(graph, source=changed_service)
    return sorted(
        (
            {"service": service, "dependency_distance": distances[service]}
            for service in impacted
        ),
        key=lambda entry: entry["dependency_distance"],
    )
