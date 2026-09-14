"""Unit tests for the dependency graph (design-doc §5.2) — pure NetworkX
logic, no database needed."""
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


def test_get_dependencies_returns_direct_successors():
    graph = _mesh_graph()
    assert set(graph_service.get_dependencies(graph, "order-service")) == {
        "inventory-service",
        "payment-service",
    }


def test_get_dependencies_unknown_service_returns_empty():
    graph = _mesh_graph()
    assert graph_service.get_dependencies(graph, "nonexistent") == []


def test_get_dependents_returns_direct_predecessors():
    graph = _mesh_graph()
    assert graph_service.get_dependents(graph, "order-service") == ["gateway"]


def test_get_dependents_of_leaf_node():
    graph = _mesh_graph()
    assert graph_service.get_dependents(graph, "database") == ["inventory-service"]


def test_get_dependents_of_root_node_is_empty():
    graph = _mesh_graph()
    assert graph_service.get_dependents(graph, "gateway") == []
