"""Idempotent startup seeding: the service registry (nodes of the dependency
graph). Edges are seeded separately in Phase 1 item 3 (graph_service)."""
from sqlalchemy.orm import Session

from app.models import Dependency, Service

# ("database" and "external-api" are infra/external nodes, not live
# containers — see models/orm.py docstring.)
KNOWN_SERVICES = {
    "gateway": "Public entrypoint for the demo mesh",
    "order-service": "Places orders; calls inventory-service and payment-service",
    "inventory-service": "Reserves stock for an order",
    "payment-service": "Charges the user for an order",
    "database": "Shared Postgres instance backing inventory-service",
    "external-api": "External payment processor called by payment-service",
}


def seed_services(db: Session) -> None:
    existing = {s.id for s in db.query(Service.id).all()}
    for name, description in KNOWN_SERVICES.items():
        if name not in existing:
            db.add(Service(id=name, description=description))
    db.commit()


# Mirrors the demo mesh's actual call graph (services/*/app/main.py) plus the
# doc §5.2 example edges to "database"/"external-api".
KNOWN_EDGES = [
    ("gateway", "order-service"),
    ("order-service", "inventory-service"),
    ("order-service", "payment-service"),
    ("inventory-service", "database"),
    ("payment-service", "external-api"),
]


def seed_dependencies(db: Session) -> None:
    existing = {
        (d.source_service_id, d.target_service_id) for d in db.query(Dependency).all()
    }
    for source, target in KNOWN_EDGES:
        if (source, target) not in existing:
            db.add(Dependency(source_service_id=source, target_service_id=target))
    db.commit()
