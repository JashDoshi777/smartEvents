"""
LiveIQ — Intelligence Models
Predictions, competitor data, social listening, trend signals, AI outputs.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, ForeignKey,
    Text, ARRAY, Date, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP, NUMERIC
from sqlalchemy.orm import relationship
from app.core.database import Base


# ═══════════════════════════════════════════════════════════════════
# Entity Predictions
# ═══════════════════════════════════════════════════════════════════

class EntityPrediction(Base):
    """ML model output: event success + revenue prediction."""
    __tablename__ = "entity_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    venue_id = Column(UUID(as_uuid=True), ForeignKey("venues.id"), nullable=True)
    city = Column(String(100))
    prediction_type = Column(String(50))  # 'event_success', 'revenue', 'demand', 'trend'

    # Input parameters
    event_date = Column(Date)
    ticket_price_input = Column(NUMERIC(10, 2))
    venue_capacity_input = Column(Integer)
    day_of_week = Column(Integer)       # 0=Mon, 6=Sun

    # Predictions
    predicted_fill_rate = Column(Float)
    predicted_revenue = Column(NUMERIC(14, 2))
    predicted_attendance = Column(Integer)
    sellout_probability = Column(Float)  # 0-1

    # Risk analysis
    risk_score = Column(Float)          # 0-100 (lower = less risky)
    risk_factors = Column(JSONB, default=[])  # List of identified risk factors

    # Pricing recommendation
    recommended_price_min = Column(NUMERIC(10, 2))
    recommended_price_max = Column(NUMERIC(10, 2))
    optimal_price = Column(NUMERIC(10, 2))
    price_uplift_vs_input = Column(Float)  # % revenue uplift if optimal price used

    # Confidence
    confidence = Column(Float)          # 0-1
    model_version = Column(String(20))

    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    entity = relationship("Entity", back_populates="predictions")

    __table_args__ = (
        Index("ix_predictions_entity", "entity_id"),
        Index("ix_predictions_city", "city"),
    )


# ═══════════════════════════════════════════════════════════════════
# Competitor Listings
# ═══════════════════════════════════════════════════════════════════

class CompetitorListing(Base):
    """Events scraped from BookMyShow, Insider, Paytm, etc."""
    __tablename__ = "competitor_listings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform = Column(String(50), nullable=False)   # 'bookmyshow', 'insider', 'paytm'
    external_id = Column(String(255))

    # Event details
    entity_name = Column(String(500))
    city = Column(String(100))
    category = Column(String(100))
    sub_category = Column(String(100))
    event_date = Column(Date)
    venue_name = Column(String(255))

    # Pricing (scraped)
    price_range_min = Column(NUMERIC(10, 2))
    price_range_max = Column(NUMERIC(10, 2))

    # Status
    status = Column(String(50))         # 'available', 'filling_fast', 'sold_out'
    is_sold_out = Column(Boolean, default=False)

    # Metadata
    scraped_at = Column(TIMESTAMP(timezone=True), nullable=False)
    raw_data = Column(JSONB, default={})  # Full scraped payload

    __table_args__ = (
        UniqueConstraint("platform", "external_id", name="uq_competitor_listing"),
        Index("ix_competitor_city", "city"),
        Index("ix_competitor_category", "category"),
        Index("ix_competitor_date", "event_date"),
        Index("ix_competitor_platform", "platform"),
    )


# ═══════════════════════════════════════════════════════════════════
# Social Posts (raw social data — stored in MongoDB, ref here)
# ═══════════════════════════════════════════════════════════════════

class SocialPost(Base):
    """Reference table for social posts analyzed for an entity."""
    __tablename__ = "social_posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)
    platform = Column(String(50))       # 'twitter', 'reddit', 'instagram', 'youtube'
    post_id = Column(String(255))       # Platform's own ID
    content_snippet = Column(String(500))   # First 500 chars
    mongo_doc_id = Column(String(50))   # Full text in MongoDB

    # Sentiment
    sentiment_score = Column(Float)     # -1 to 1
    sentiment_label = Column(String(20))  # 'positive', 'negative', 'neutral'
    themes = Column(ARRAY(String), default=[])   # Detected topics

    # Engagement
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    views = Column(Integer, default=0)

    posted_at = Column(TIMESTAMP(timezone=True))
    analyzed_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    entity = relationship("Entity", back_populates="social_posts")

    __table_args__ = (
        UniqueConstraint("platform", "post_id", name="uq_social_post"),
        Index("ix_social_entity", "entity_id"),
        Index("ix_social_platform", "platform"),
        Index("ix_social_posted_at", "posted_at"),
    )


# ═══════════════════════════════════════════════════════════════════
# Trend Signals
# ═══════════════════════════════════════════════════════════════════

class TrendSignal(Base):
    """Detected anomalies and breakout signals for entities."""
    __tablename__ = "trend_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    signal_type = Column(String(100))
    # Types: 'reels_spike', 'search_breakout', 'news_burst', 'rsvp_surge',
    #        'sentiment_flip_positive', 'competitor_gap', 'spotify_trending_now'

    # Signal strength
    current_value = Column(Float)
    previous_value = Column(Float)
    delta_7d = Column(Float)            # % change in 7 days
    delta_30d = Column(Float)           # % change in 30 days
    z_score = Column(Float)             # Standard deviations from mean (anomaly strength)

    # Alert metadata
    severity = Column(String(20))       # 'low', 'medium', 'high', 'critical'
    is_read = Column(Boolean, default=False)
    alert_message = Column(String(500))

    detected_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    entity = relationship("Entity", back_populates="trend_signals")

    __table_args__ = (
        Index("ix_trend_entity", "entity_id"),
        Index("ix_trend_type", "signal_type"),
        Index("ix_trend_detected", "detected_at"),
    )


# ═══════════════════════════════════════════════════════════════════
# AI / Executive Layer
# ═══════════════════════════════════════════════════════════════════

class ExecBriefing(Base):
    """AI-generated executive briefings (daily/weekly)."""
    __tablename__ = "exec_briefings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    briefing_date = Column(Date, nullable=False)
    briefing_type = Column(String(50), default="daily")  # 'daily', 'weekly', 'monthly'
    city = Column(String(100), default="")  # City-specific or empty string for global
    # NOTE: empty string default avoids NULL != NULL issue in UniqueConstraint

    # Content (Gemini-generated)
    headline = Column(String(500))
    content = Column(Text, nullable=False)
    recommendations = Column(JSONB, default=[])  # List of action items
    kpi_snapshot = Column(JSONB, default={})      # KPI values at time of generation

    # Metadata
    model_version = Column(String(50))
    generated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    is_sent = Column(Boolean, default=False)       # Whether sent to users

    __table_args__ = (
        UniqueConstraint("briefing_date", "briefing_type", "city", name="uq_briefing"),
    )


class AISession(Base):
    """AI Copilot chat sessions."""
    __tablename__ = "ai_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_title = Column(String(255))  # Auto-generated from first question
    messages = Column(JSONB, default=[]) # [{"role": "user", "content": "...", "ts": "..."}, ...]
    pinned_insights = Column(JSONB, default=[])   # User-pinned answers

    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class AIEmbedding(Base):
    """pgvector embeddings for RAG pipeline."""
    __tablename__ = "ai_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(String(50))    # 'entity_profile', 'event_record', 'briefing', 'trend_report'
    source_id = Column(String(255))     # UUID or identifier of source document
    content_chunk = Column(Text, nullable=False)
    # embedding = Column(Vector(768))   # pgvector — enabled after extension installed
    # Stored as JSONB until pgvector extension is confirmed
    embedding_json = Column(JSONB)
    token_count = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_embeddings_source", "source_type", "source_id"),
    )
