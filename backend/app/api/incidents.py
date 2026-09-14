"""Historical incident retrieval endpoints (design-doc §5.7, Phase 1 item 5)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import incident_service

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("/search")
def search(query: str, limit: int = 3, db: Session = Depends(get_db)):
    return {"query": query, "results": incident_service.search_historical_incidents(db, query, limit)}
