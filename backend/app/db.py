"""Sync SQLAlchemy engine/session.

Design note: the rest of this service is async (FastAPI route handlers,
httpx calls to the demo mesh, Prometheus, and Gemini) because those are the
genuinely I/O-bound calls worth overlapping. Local Postgres queries here are
fast and simple enough that a sync SQLAlchemy session — run in FastAPI's
default threadpool for sync `def` routes — keeps the ORM layer easy to
reason about without asyncpg/async-session boilerplate. That's a deliberate
scope choice, not an oversight, and worth being able to explain as such.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://postgres:postgres@postgres:5432/dcip"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
