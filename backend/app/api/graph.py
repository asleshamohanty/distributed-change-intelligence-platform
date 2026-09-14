"""Dependency graph + blast radius endpoints (design-doc §5.2/§5.3, Phase 1 item 3)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import graph_service

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("")
def get_graph(db: Session = Depends(get_db)):
    graph = graph_service.load_graph(db)
    return {
        "nodes": list(graph.nodes),
        "edges": [{"source": u, "target": v} for u, v in graph.edges],
    }


@router.get("/dependencies")
def dependencies(service: str, db: Session = Depends(get_db)):
    graph = graph_service.load_graph(db)
    return {"service": service, "dependencies": graph_service.get_dependencies(graph, service)}


@router.get("/dependents")
def dependents(service: str, db: Session = Depends(get_db)):
    graph = graph_service.load_graph(db)
    return {"service": service, "dependents": graph_service.get_dependents(graph, service)}


@router.get("/blast-radius")
def blast_radius(service: str, db: Session = Depends(get_db)):
    graph = graph_service.load_graph(db)
    if service not in graph:
        raise HTTPException(status_code=404, detail=f"unknown service: {service}")
    return {
        "changed_service": service,
        "potentially_impacted": graph_service.get_blast_radius_enriched(graph, service),
    }
