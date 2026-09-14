import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import events, failure_injection, graph, incidents, investigation, telemetry
from app.db import Base, SessionLocal, engine
from app.seed import seed_dependencies, seed_services

logger = logging.getLogger("dcip.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_services(db)
        seed_dependencies(db)
    finally:
        db.close()

    if os.environ.get("GEMINI_API_KEY"):
        try:
            from scripts.seed_incidents import seed_incidents

            seed_incidents()
        except Exception:
            # Historical-incident retrieval is one signal among several the
            # Investigation Layer combines (§5.8) — a seeding failure (bad
            # key, no network) shouldn't take down the rest of the API.
            logger.exception("Incident seeding failed; continuing without it")
    else:
        logger.warning("GEMINI_API_KEY not set — skipping incident seeding")

    yield


app = FastAPI(title="Distributed Change Intelligence Platform API", lifespan=lifespan)

app.include_router(events.router)
app.include_router(graph.router)
app.include_router(telemetry.router)
app.include_router(incidents.router)
app.include_router(investigation.router)
app.include_router(failure_injection.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "backend"}


# Minimal dashboard (Phase 1 item 9) — mounted last so it never shadows the
# /api/* and /health routes above; Starlette matches routes in registration
# order, and this mount is a catch-all fallback for everything else.
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
