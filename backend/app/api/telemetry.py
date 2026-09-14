"""Telemetry + anomaly detection endpoints (design-doc §5.5/§5.6, Phase 1 item 4)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import anomaly_service, telemetry_service

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

MESH_SERVICES = ["gateway", "order-service", "inventory-service", "payment-service"]


@router.get("")
def telemetry(service: str, db: Session = Depends(get_db)):
    data = telemetry_service.get_service_telemetry(service)
    telemetry_service.record_telemetry_snapshot(db, service, data)
    return {"service": service, "telemetry": data}


@router.get("/anomalies")
def anomalies(db: Session = Depends(get_db)):
    return {"results": anomaly_service.score_all_services(db, MESH_SERVICES)}


@router.get("/anomalies/recent")
def recent_anomalies(db: Session = Depends(get_db)):
    rows = anomaly_service.get_recent_anomalies(db)
    return {
        "anomalies": [
            {
                "service": a.service_id,
                "metric": a.metric,
                "score": a.score,
                "timestamp": a.timestamp,
            }
            for a in rows
        ]
    }
