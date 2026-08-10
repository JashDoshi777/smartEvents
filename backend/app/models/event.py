"""
LiveIQ — Event Model
Tracks all events across all platforms and categories.
Includes secondary market (resale) support inspired by District's "Book Now, Sell Anytime".
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, ForeignKey,
    Text, ARRAY, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP, NUMERIC
from sqlalchemy.orm import relationship
from app.core.database import Base


class EventCategory(str, enum.Enum):
    MUSIC = "music"
    MOVIE = "movie"
    SPORTS = "sports"
    COMEDY = "comedy"
    THEATRE = "theatre"
    EXPERIENCE = "experience"
    WORKSHOP = "workshop"
    DINING = "dining"
    NIGHTLIFE = "nightlife"


class EventStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    ON_SALE = "on_sale"
    FILLING_FAST = "filling_fast"
    SOLD_OUT = "sold_out"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"


class EventSource(str, enum.Enum):
    DISTRICT = "district"
    BOOKMYSHOW = "bookmyshow"
    INSIDER = "insider"
    PAYTM = "paytm"
    TICKETMASTER = "ticketmaster"
    EVENTBRITE = "eventbrite"
    PREDICTHQ = "predicthq"
    MANUAL = "manual"


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id = Column(String(255))               # ID on source platform
    source = Column(String(50))                     # EventSource enum value

    # Core info
    title = Column(String(500), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)   # EventCategory enum value
    sub_category = Column(String(100))
    language = Column(String(50))
    age_restriction = Column(Integer, default=0)    # Minimum age

    # Relationships
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    venue_id = Column(UUID(as_uuid=True), ForeignKey("venues.id", ondelete="SET NULL"), nullable=True)

    # Timing
    event_date = Column(TIMESTAMP(timezone=True), nullable=False)
    event_end_date = Column(TIMESTAMP(timezone=True))            # For multi-day events
    doors_open = Column(TIMESTAMP(timezone=True))
    is_multi_day = Column(Boolean, default=False)

    # Ticketing
    ticket_price_min = Column(NUMERIC(10, 2))       # INR
    ticket_price_max = Column(NUMERIC(10, 2))       # INR
    ticket_price_vip = Column(NUMERIC(10, 2))       # INR
    ticket_tiers = Column(JSONB, default={})        # {"GA": 2500, "Seated": 4500, "VIP": 12000}
    booking_url = Column(String(500))

    # Capacity & Sales
    total_capacity = Column(Integer)
    tickets_available = Column(Integer)
    tickets_sold = Column(Integer)
    fill_rate = Column(Float)                       # 0-1
    gross_revenue = Column(NUMERIC(14, 2))          # INR

    # Status
    status = Column(String(50), default=EventStatus.UPCOMING.value)  # Store as string 'upcoming'
    is_district_exclusive = Column(Boolean, default=False)

    # Secondary Market (District "Book Now, Sell Anytime" feature)
    secondary_market_enabled = Column(Boolean, default=False)
    secondary_tickets_listed = Column(Integer, default=0)
    secondary_avg_resale_price = Column(NUMERIC(10, 2))
    secondary_max_multiplier = Column(Float, default=2.0)  # Max 2x resale price cap

    # Image
    cover_image_url = Column(String(500))
    thumbnail_url = Column(String(500))

    # Post-event analytics
    actual_attendance = Column(Integer)
    actual_revenue = Column(NUMERIC(14, 2))
    post_event_sentiment = Column(Float)            # -1 to 1
    social_mentions_post = Column(Integer)

    # AI predictions (stored for comparison)
    predicted_fill_rate = Column(Float)
    predicted_revenue = Column(NUMERIC(14, 2))
    prediction_model_version = Column(String(20))

    # PredictHQ real demand-intelligence signals (Sprint 5A/master-data) —
    # only populated for events also matched/sourced via PredictHQ; NULL
    # means "no PredictHQ data available for this event," never a
    # fabricated zero.
    predicthq_rank = Column(Integer)               # 0-100, event significance
    predicthq_local_rank = Column(Integer)         # 0-100, local-area impact
    predicthq_predicted_attendance = Column(Integer)  # real predicted attendance count

    # Metadata
    tags = Column(ARRAY(String), default=[])
    scraped_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # ─── Relationships ─────────────────────────────────────────
    entity = relationship("Entity", back_populates="events")
    venue = relationship("Venue", back_populates="events")

    __table_args__ = (
        UniqueConstraint("external_id", "source", name="uq_event_external_source"),
        Index("ix_events_entity_id", "entity_id"),
        Index("ix_events_event_date", "event_date"),
        Index("ix_events_category", "category"),
        Index("ix_events_status", "status"),
        Index("ix_events_source", "source"),
    )

    def __repr__(self) -> str:
        return f"<Event {self.title} on {self.event_date}>"
