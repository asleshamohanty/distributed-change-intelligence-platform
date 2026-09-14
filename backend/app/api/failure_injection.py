"""Failure injection controls (design-doc §9/§18, Phase 1 item 8).

A single, consistent API surface — proxying to the demo mesh services'
own /admin/inject/* endpoints — so a client (curl, or the UI in item 9)
doesn't need to know internal mesh service URLs directly.
"""
import os

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api/failure-injection", tags=["failure-injection"])

INVENTORY_URL = os.environ.get("INVENTORY_SERVICE_URL", "http://inventory-service:8000")
ORDER_URL = os.environ.get("ORDER_SERVICE_URL", "http://order-service:8000")


@router.post("/latency")
async def toggle_latency(enabled: bool, seconds: float = 2.0):
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{INVENTORY_URL}/admin/inject/latency", json={"enabled": enabled, "seconds": seconds}
        )
        resp.raise_for_status()
    return resp.json()


@router.post("/errors")
async def toggle_errors(enabled: bool, rate: float = 0.2):
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{INVENTORY_URL}/admin/inject/errors", json={"enabled": enabled, "rate": rate}
        )
        resp.raise_for_status()
    return resp.json()


@router.post("/load")
async def toggle_load(enabled: bool, multiplier: int = 3):
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{ORDER_URL}/admin/inject/load", json={"enabled": enabled, "multiplier": multiplier}
        )
        resp.raise_for_status()
    return resp.json()


@router.get("/status")
async def status():
    async with httpx.AsyncClient(timeout=5.0) as client:
        inventory_status = await client.get(f"{INVENTORY_URL}/admin/inject/status")
        order_status = await client.get(f"{ORDER_URL}/admin/inject/status")
    return {"inventory-service": inventory_status.json(), "order-service": order_status.json()}
