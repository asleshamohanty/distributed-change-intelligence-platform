"""ML-Based Anomaly Detection orchestration (design-doc §5.6).

Pulls current telemetry for a service (telemetry_service), scores it with
the trained Isolation Forest (ml/anomaly_model.py), and persists a row when
the service is flagged. The model answers "is this unusual?", nothing more
— narrative explanation of *why* is the LLM layer's job (§5.10), downstream
of this and only once it has this model's output as evidence.
"""
from sqlalchemy.orm import Session

from app.models import Anomaly
from app.services import telemetry_service
from ml.anomaly_model import score
from ml.features import build_feature_vector


def score_service(db: Session, service: str) -> dict:
    telemetry = telemetry_service.get_service_telemetry(service)
    telemetry_service.record_telemetry_snapshot(db, service, telemetry)

    feature_vector = build_feature_vector(telemetry)
    result = score(feature_vector)

    if result["is_anomalous"]:
        db.add(
            Anomaly(
                service_id=service,
                metric=result["driving_metric"],
                score=result["anomaly_score"],
            )
        )
        db.commit()

    return {"service": service, "telemetry": telemetry, **result}


def score_all_services(db: Session, services: list[str]) -> list[dict]:
    return [score_service(db, service) for service in services]


def get_recent_anomalies(db: Session, limit: int = 20) -> list[Anomaly]:
    return db.query(Anomaly).order_by(Anomaly.timestamp.desc()).limit(limit).all()
