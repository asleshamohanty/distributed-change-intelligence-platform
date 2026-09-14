"""Unit tests for blast-radius analysis (design-doc §5.3) — descendant
traversal + dependency-distance enrichment."""
import networkx as nx

from app.services import graph_service


def _mesh_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_edge("gateway", "order-service")
    graph.add_edge("order-service", "inventory-service")
    graph.add_edge("order-service", "payment-service")
    graph.add_edge("inventory-service", "database")
    graph.add_edge("payment-service", "external-api")
    return graph


def test_blast_radius_matches_docs_worked_example():
    graph = _mesh_graph()
    # design-doc §5.3/§18: get_blast_radius(graph, "order-service")
    # -> {"inventory-service", "payment-service", "database", "external-api"}
    assert graph_service.get_blast_radius(graph, "order-service") == {
        "inventory-service",
        "payment-service",
        "database",
        "external-api",
    }


def test_blast_radius_of_leaf_node_is_empty():
    graph = _mesh_graph()
    assert graph_service.get_blast_radius(graph, "database") == set()


def test_blast_radius_of_unknown_service_is_empty():
    graph = _mesh_graph()
    assert graph_service.get_blast_radius(graph, "nonexistent") == set()


def test_blast_radius_excludes_upstream_and_sibling_nodes():
    graph = _mesh_graph()
    impacted = graph_service.get_blast_radius(graph, "inventory-service")
    assert "gateway" not in impacted  # upstream of the changed service
    assert "payment-service" not in impacted  # sibling, not downstream
    assert impacted == {"database"}


def test_enriched_blast_radius_reports_correct_dependency_distance():
    graph = _mesh_graph()
    enriched = graph_service.get_blast_radius_enriched(graph, "order-service")
    distances = {entry["service"]: entry["dependency_distance"] for entry in enriched}
    assert distances == {
        "inventory-service": 1,
        "payment-service": 1,
        "database": 2,
        "external-api": 2,
    }


def test_enriched_blast_radius_is_sorted_nearest_first():
    graph = _mesh_graph()
    enriched = graph_service.get_blast_radius_enriched(graph, "order-service")
    distances = [entry["dependency_distance"] for entry in enriched]
    assert distances == sorted(distances)


def test_enriched_blast_radius_empty_for_leaf_node():
    graph = _mesh_graph()
    assert graph_service.get_blast_radius_enriched(graph, "database") == []


def test_diamond_dependency_uses_shortest_path_distance():
    # A -> B -> D and A -> C -> D: D is reachable via two equal-length
    # paths here; distance should report the minimum regardless of how
    # many paths reach a node.
    graph = nx.DiGraph()
    graph.add_edge("A", "B")
    graph.add_edge("A", "C")
    graph.add_edge("B", "D")
    graph.add_edge("C", "D")
    enriched = graph_service.get_blast_radius_enriched(graph, "A")
    distances = {entry["service"]: entry["dependency_distance"] for entry in enriched}
    assert distances == {"B": 1, "C": 1, "D": 2}
