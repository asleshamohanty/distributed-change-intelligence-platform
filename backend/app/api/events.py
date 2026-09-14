"""Change/deployment ingestion endpoints (design-doc §5.1, Phase 1 item 2).

POST /api/events/deploy accepts a webhook-shaped payload. POST
/api/events/generate-demo-deploy is the "simple event generator" the doc
allows in place of a real GitHub webhook, so the demo is reproducible
without wiring up an actual GitHub App.
"""
import random
import string

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.change import DeployEventIn, DeployEventOut
from app.services import change_service

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("/deploy", response_model=DeployEventOut)
def deploy_event(event: DeployEventIn, db: Session = Depends(get_db)):
    return change_service.ingest_deploy_event(db, event)


@router.get("/latest-deployment")
def latest_deployment(service: str, db: Session = Depends(get_db)):
    result = change_service.get_latest_deployment(db, service)
    if result is None:
        raise HTTPException(status_code=404, detail=f"no deployments found for service: {service}")
    return result


@router.post("/generate-demo-deploy", response_model=DeployEventOut)
def generate_demo_deploy(db: Session = Depends(get_db)):
    commit_sha = "".join(random.choices(string.hexdigits.lower(), k=7))
    event = DeployEventIn(
        service="order-service",
        commit_sha=commit_sha,
        author="developer",
        files_changed=["payment_client.py", "order_service.py"],
    )
    return change_service.ingest_deploy_event(db, event)
