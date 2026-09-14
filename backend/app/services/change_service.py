"""Change Intelligence (design-doc §5.1).

Ingests a commit+deploy event and stores it. This is the anchor event every
other signal (graph, telemetry, anomalies, history) gets correlated against
in the Investigation Layer (§5.8) — it answers "what changed?"
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Change, Deployment
from app.schemas.change import DeployEventIn, DeployEventOut


def ingest_deploy_event(db: Session, event: DeployEventIn) -> DeployEventOut:
    timestamp = event.timestamp or datetime.now(timezone.utc)

    change = Change(
        service_id=event.service,
        commit_sha=event.commit_sha,
        author=event.author,
        files_changed=event.files_changed,
        timestamp=timestamp,
    )
    db.add(change)
    db.flush()  # populate change.id before the deployment FK needs it

    deployment = Deployment(
        service_id=event.service,
        change_id=change.id,
        status="completed",
        timestamp=timestamp,
    )
    db.add(deployment)
    db.commit()

    return DeployEventOut(
        change_id=change.id,
        deployment_id=deployment.id,
        service=change.service_id,
        commit_sha=change.commit_sha,
        author=change.author,
        files_changed=change.files_changed,
        timestamp=change.timestamp,
    )


def get_change_details(db: Session, change_id: str) -> Change | None:
    return db.get(Change, change_id)


def get_latest_deployment(db: Session, service: str) -> dict | None:
    """Most recent deployment + its change, for a service — the entry point
    the MCP get_change_details tool (§5.9) and the investigation flow (§5.8)
    both key off ("what's the most recent thing that changed here?")."""
    deployment = (
        db.query(Deployment)
        .filter(Deployment.service_id == service)
        .order_by(Deployment.timestamp.desc())
        .first()
    )
    if deployment is None:
        return None
    change = db.get(Change, deployment.change_id)
    return {
        "deployment_id": deployment.id,
        "status": deployment.status,
        "deployment_timestamp": deployment.timestamp,
        "change_id": change.id,
        "service": change.service_id,
        "commit_sha": change.commit_sha,
        "author": change.author,
        "files_changed": change.files_changed,
        "change_timestamp": change.timestamp,
    }


def get_recent_deployments(db: Session, limit: int = 20) -> list[Deployment]:
    return (
        db.query(Deployment)
        .order_by(Deployment.timestamp.desc())
        .limit(limit)
        .all()
    )
