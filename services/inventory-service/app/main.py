"""Inventory service — demo mesh leaf node.

Reserves stock for an order. In the dependency graph this service has an
edge to "database" (the shared Postgres instance) — see ml/../backend
graph_service, which loads that edge from the `dependencies` table rather
than this service making a real DB call. Keeping the demo mesh's business
logic in-memory keeps this container self-contained and easy to reason about.

Also hosts two of the three failure-injection scenarios from design-doc §9:
latency injection (`asyncio.sleep`) and error injection (`HTTPException(500)`
at a configurable rate). Toggled via /admin/inject/* so the demo is
reproducible without redeploying — see backend/app/api/failure_injection.py
for the single API surface a client (or the UI) actually calls.
"""
import asyncio
import random

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.metrics import MetricsMiddleware, metrics_response

app = FastAPI(title="inventory-service")
app.add_middleware(MetricsMiddleware)

STOCK = {
    # High enough that the background load generator (services/load-generator,
    # ~1 req/s per item at steady state) won't deplete stock and create an
    # unrelated "reserved: false" behavior change during a demo session.
    "widget": 1_000_000,
    "gadget": 1_000_000,
    "gizmo": 1_000_000,
}

INJECTION_STATE = {
    "latency_enabled": False,
    "latency_seconds": 2.0,
    "errors_enabled": False,
    "error_rate": 0.2,
}


class ReserveRequest(BaseModel):
    item: str
    quantity: int


class ReserveResponse(BaseModel):
    reserved: bool
    remaining: int


class LatencyInjectionRequest(BaseModel):
    enabled: bool
    seconds: float = 2.0


class ErrorInjectionRequest(BaseModel):
    enabled: bool
    rate: float = 0.2


@app.get("/health")
def health():
    return {"status": "ok", "service": "inventory-service"}


@app.get("/api/metrics")
def metrics():
    return metrics_response()


@app.get("/stock/{item}")
def get_stock(item: str):
    if item not in STOCK:
        raise HTTPException(status_code=404, detail=f"unknown item: {item}")
    return {"item": item, "quantity": STOCK[item]}


@app.get("/admin/inject/status")
def injection_status():
    return INJECTION_STATE


@app.post("/admin/inject/latency")
def set_latency_injection(req: LatencyInjectionRequest):
    INJECTION_STATE["latency_enabled"] = req.enabled
    INJECTION_STATE["latency_seconds"] = req.seconds
    return INJECTION_STATE


@app.post("/admin/inject/errors")
def set_error_injection(req: ErrorInjectionRequest):
    INJECTION_STATE["errors_enabled"] = req.enabled
    INJECTION_STATE["error_rate"] = req.rate
    return INJECTION_STATE


@app.post("/reserve", response_model=ReserveResponse)
async def reserve(req: ReserveRequest):
    if INJECTION_STATE["latency_enabled"]:
        await asyncio.sleep(INJECTION_STATE["latency_seconds"])

    if INJECTION_STATE["errors_enabled"] and random.random() < INJECTION_STATE["error_rate"]:
        raise HTTPException(status_code=500, detail="injected failure")

    if req.item not in STOCK:
        raise HTTPException(status_code=404, detail=f"unknown item: {req.item}")
    available = STOCK[req.item]
    if available < req.quantity:
        return ReserveResponse(reserved=False, remaining=available)
    STOCK[req.item] -= req.quantity
    return ReserveResponse(reserved=True, remaining=STOCK[req.item])
