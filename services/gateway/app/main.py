"""Gateway service — single public entrypoint for the demo mesh, mirrors the
API Gateway in doc §2's topology diagram."""
import os

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.metrics import MetricsMiddleware, metrics_response

app = FastAPI(title="gateway-service")
app.add_middleware(MetricsMiddleware)

ORDER_URL = os.environ.get("ORDER_SERVICE_URL", "http://order-service:8000")


class CheckoutRequest(BaseModel):
    item: str
    quantity: int
    user: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "gateway"}


@app.get("/api/metrics")
def metrics():
    return metrics_response()


@app.post("/api/checkout")
async def checkout(req: CheckoutRequest):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{ORDER_URL}/orders", json=req.model_dump())
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"order-service error: {exc}") from exc
    return resp.json()
