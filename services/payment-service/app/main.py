"""Payment service — demo mesh leaf node.

Has a graph edge to "external-api" (a payment processor), also modeled only
as a dependency-table edge rather than a real live container — see
inventory-service's docstring for why.
"""
import time
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from app.metrics import MetricsMiddleware, metrics_response

app = FastAPI(title="payment-service")
app.add_middleware(MetricsMiddleware)


class ChargeRequest(BaseModel):
    user: str
    amount: float


class ChargeResponse(BaseModel):
    charged: bool
    transaction_id: str
    amount: float


@app.get("/health")
def health():
    return {"status": "ok", "service": "payment-service"}


@app.get("/api/metrics")
def metrics():
    return metrics_response()


@app.post("/charge", response_model=ChargeResponse)
async def charge(req: ChargeRequest):
    # simulated external-payment-processor round trip
    time.sleep(0.05)
    return ChargeResponse(charged=True, transaction_id=str(uuid.uuid4()), amount=req.amount)
