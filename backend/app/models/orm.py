"""SQLAlchemy models for the seven tables from design-doc §7.

`Service.id` is the service *name* itself (e.g. "order-service") rather than
a synthetic UUID — the dependency graph, blast radius, and telemetry all key
off service names, so using the name as the primary key avoids an extra
name<->id lookup everywhere. "database" and "external-api" are seeded as
Service rows too (infra/external nodes), matching how the design doc's own
NetworkX examples treat them as plain graph nodes rather than live services.
"""
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Dimension of Gemini's text-embedding-004 output (see backend/app/services/incident_service.py).
EMBEDDING_DIM = 768


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Dependency(Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint("source_service_id", "target_service_id", name="uq_dependency_edge"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source_service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), nullable=False)
    target_service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), nullable=False)


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)
    files_changed: Mapped[list] = mapped_column(JSON, default=list)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), nullable=False)
    change_id: Mapped[str] = mapped_column(ForeignKey("changes.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="completed")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), nullable=False)
    metric_name: Mapped[str] = mapped_column(String, nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), nullable=False)
    metric: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    embedding: Mapped[list | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
