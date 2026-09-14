"""Order service — calls inventory-service then payment-service.

This is the service the demo's deployment event targets (see backend
change_service in Phase 1 item 2): a change here is what the platform
investigates, and inventory-service/payment-service are its blast radius.

Also hosts the third failure-injection scenario from design-doc §9:
increased downstream call volume ("order-service starts calling inventory
more often"). Toggled via /admin/inject/load — see backend/app/api/
failure_injection.py for the single API surface a client actually calls.
"""
import os
import uuid

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.metrics import MetricsMiddleware, metrics_response

app = FastAPI(title="order-service")
app.add_middleware(MetricsMiddleware)

INVENTORY_URL = os.environ.get("INVENTORY_SERVICE_URL", "http://inventory-service:8000")
PAYMENT_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://payment-service:8000")
UNIT_PRICE = 9.99

INJECTION_STATE = {
    "load_enabled": False,
    # Extra read-only /stock calls fired to inventory-service per order, on
    # top of the one real /reserve call — simulates order-service calling
    # inventory more often, without changing order correctness.
    "load_multiplier": 3,
}


class OrderRequest(BaseModel):
    item: str
    quantity: int
    user: str


class OrderResponse(BaseModel):
    order_id: str
    item: str
    quantity: int
    reserved: bool
    charged: bool
    total: float


class LoadInjectionRequest(BaseModel):
    enabled: bool
    multiplier: int = 3


@app.get("/health")
def health():
    return {"status": "ok", "service": "order-service"}


@app.get("/api/metrics")
def metrics():
    return metrics_response()


@app.get("/admin/inject/status")
def injection_status():
    return INJECTION_STATE


@app.post("/admin/inject/load")
def set_load_injection(req: LoadInjectionRequest):
    INJECTION_STATE["load_enabled"] = req.enabled
    INJECTION_STATE["load_multiplier"] = req.multiplier
    return INJECTION_STATE


@app.post("/orders", response_model=OrderResponse)
async def create_order(req: OrderRequest):
    async with httpx.AsyncClient(timeout=10.0) as client:
        if INJECTION_STATE["load_enabled"]:
            for _ in range(max(INJECTION_STATE["load_multiplier"] - 1, 0)):
                try:
                    await client.get(f"{INVENTORY_URL}/stock/{req.item}")
                except httpx.HTTPError:
                    pass

        try:
            reserve_resp = await client.post(
                f"{INVENTORY_URL}/reserve",
                json={"item": req.item, "quantity": req.quantity},
            )
            reserve_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"inventory-service error: {exc}") from exc

        reserved = reserve_resp.json()["reserved"]
        if not reserved:
            return OrderResponse(
                order_id=str(uuid.uuid4()),
                item=req.item,
                quantity=req.quantity,
                reserved=False,
                charged=False,
                total=0.0,
            )

        total = round(req.quantity * UNIT_PRICE, 2)
        try:
            charge_resp = await client.post(
                f"{PAYMENT_URL}/charge",
                json={"user": req.user, "amount": total},
            )
            charge_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"payment-service error: {exc}") from exc

        charged = charge_resp.json()["charged"]

    return OrderResponse(
        order_id=str(uuid.uuid4()),
        item=req.item,
        quantity=req.quantity,
        reserved=reserved,
        charged=charged,
        total=total,
    )
