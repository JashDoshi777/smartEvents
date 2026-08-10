"""
LiveIQ — Entity Metrics (Time-Series)
Stored in TimescaleDB hypertable for efficient time-series queries.
One row per entity per collection cycle (~6 hours).
"""

from datetime import datetime
from sqlalchemy import (
    Column, Float, Integer, BigInteger, ForeignKey,
    String, Index, PrimaryKeyConstraint
)
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import relationship
from app.core.database import Base


class EntityMetric(Base):
    __tablename__ = "entity_metrics"

    # TimescaleDB requires time as part of primary key for hypertable
    time = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)

    # ─── Streaming / Listen Metrics ────────────────────────────
    spotify_popularity = Column(Float)              # 0-100, Spotify's own score
    spotify_monthly_listeners = Column(BigInteger)  # Monthly listeners count
    spotify_followers = Column(BigInteger)          # Total followers
    spotify_follower_growth_7d = Column(Float)      # % growth in 7 days

    youtube_subscribers = Column(BigInteger)
    youtube_views_30d = Column(BigInteger)          # Views in last 30 days
    youtube_views_7d = Column(BigInteger)
    youtube_subscriber_growth_7d = Column(Float)    # % growth

    lastfm_weekly_plays = Column(BigInteger)
    lastfm_listeners = Column(Integer)

    # ─── Social Metrics ────────────────────────────────────────
    instagram_followers = Column(BigInteger)
    instagram_following = Column(BigInteger)
    instagram_growth_7d = Column(Float)             # % follower growth
    instagram_engagement_rate = Column(Float)       # Avg likes+comments/followers
    instagram_reels_avg_views = Column(BigInteger)
    instagram_reels_saves_7d = Column(Integer)      # Saves = strong intent signal

    twitter_followers = Column(BigInteger)
    twitter_mentions_7d = Column(Integer)
    twitter_engagement_7d = Column(Integer)

    reddit_posts_7d = Column(Integer)
    reddit_comments_7d = Column(Integer)
    reddit_upvotes_7d = Column(Integer)

    # ─── Discovery / Search Metrics ────────────────────────────
    google_trend_score = Column(Float)              # 0-100, normalized
    google_trend_delta_7d = Column(Float)           # Change vs 7 days ago
    google_trend_delta_30d = Column(Float)          # Change vs 30 days ago

    # ─── Events & Live Metrics ─────────────────────────────────
    bandsintown_rsvps = Column(Integer)             # Event RSVPs on Bandsintown
    bandsintown_tracker_count = Column(Integer)     # People tracking the artist
    songkick_popularity = Column(Float)
    upcoming_events_count = Column(Integer)         # Total upcoming events globally

    # ─── Sentiment Metrics ─────────────────────────────────────
    sentiment_positive = Column(Float)              # 0-1
    sentiment_negative = Column(Float)              # 0-1
    sentiment_neutral = Column(Float)               # 0-1
    sentiment_compound = Column(Float)              # -1 to 1
    sentiment_sample_size = Column(Integer)         # How many posts were analyzed

    # ─── News & Press ──────────────────────────────────────────
    news_mentions_7d = Column(Integer)
    news_sentiment_7d = Column(Float)               # Avg sentiment of news articles

    # ─── Composite Scores (Computed) ───────────────────────────
    composite_score = Column(Float)                 # 0-100, LiveIQ score
    trend_velocity = Column(Float)                  # Change in composite score (7d)
    demand_score = Column(Float)                    # 0-100, booking demand signal
    risk_score = Column(Float)                      # 0-100, booking risk (lower = safer)
    breakout_probability = Column(Float)            # 0-1, ML-predicted breakout chance

    # ─── Metadata ──────────────────────────────────────────────
    data_completeness = Column(Float)               # 0-1, how many signals were available
    collection_source = Column(String(100))         # Which worker collected this

    # ─── Relationships ─────────────────────────────────────────
    entity = relationship("Entity", back_populates="metrics")

    __table_args__ = (
        PrimaryKeyConstraint("time", "entity_id"),
        Index("ix_entity_metrics_entity_id", "entity_id"),
        Index("ix_entity_metrics_time", "time"),
        Index("ix_entity_metrics_composite", "entity_id", "composite_score"),
        # NOTE: TimescaleDB hypertable is created via SQL in init_db.sql
        # SELECT create_hypertable('entity_metrics', 'time');
    )

    def __repr__(self) -> str:
        return f"<EntityMetric entity={self.entity_id} score={self.composite_score} at={self.time}>"
