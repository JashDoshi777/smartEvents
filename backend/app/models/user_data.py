"""
LiveIQ — Per-User Data (Sprint 7B)
Tables scoped to an individual user: watchlisted entities, and per-user
notification read-state.

NotificationRead exists because TrendSignal.is_read is a single GLOBAL
flag shared by every user — a real bug exposed once Sprint 7A introduced
multi-user auth (one user marking a signal read hid it for everyone).
Read-state is now tracked per (user_id, trend_signal_id) pair instead of
mutating the shared TrendSignal row.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from app.core.database import Base


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "entity_id", name="uq_watchlist_user_entity"),
        Index("ix_watchlist_user_id", "user_id"),
        Index("ix_watchlist_entity_id", "entity_id"),
    )


class NotificationRead(Base):
    __tablename__ = "notification_reads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    trend_signal_id = Column(UUID(as_uuid=True), ForeignKey("trend_signals.id", ondelete="CASCADE"), nullable=False)
    read_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "trend_signal_id", name="uq_notification_read_user_signal"),
        Index("ix_notification_reads_user_id", "user_id"),
    )
