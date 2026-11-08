"""Scheduler bookkeeping: one row per job execution + a lease row per job name (cross-worker lock)."""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB

from app.core.database import Base


class JobRun(Base):
    __tablename__ = "job_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_name = Column(String(100), nullable=False, index=True)
    started_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    finished_at = Column(TIMESTAMP(timezone=True))
    status = Column(String(20), nullable=False, default="running")   # running|success|error|skipped
    rows_affected = Column(Integer)
    error = Column(Text)
    trigger = Column(String(20), default="schedule")                  # schedule|manual
    detail = Column(JSONB)


class JobLock(Base):
    """Lease lock. A runner claims a job with an atomic upsert that only succeeds when the previous lease expired,
    so two uvicorn workers (or a worker + a manual trigger) never run the same job at once. Works through the
    Neon PgBouncer pooler (session-level advisory locks do not)."""
    __tablename__ = "job_locks"

    name = Column(String(100), primary_key=True)
    holder = Column(String(100))
    locked_until = Column(TIMESTAMP(timezone=True), nullable=False)
