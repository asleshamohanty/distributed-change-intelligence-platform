"""LLM-synthesized investigation endpoint (design-doc §5.10, Phase 1 item 7)."""
from fastapi import APIRouter

from app.schemas.investigation import InvestigationResult
from app.services import investigation_service

router = APIRouter(prefix="/api/investigate", tags=["investigation"])


@router.post("", response_model=InvestigationResult)
async def investigate(service: str):
    return await investigation_service.run_investigation(service)
