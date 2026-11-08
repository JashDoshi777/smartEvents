"""
LiveIQ — Entity Model
The central model that represents any bookable entity:
Artists, Movies, Sports Teams, Comedians, Theatre Groups,
Attractions, Workshops, Restaurants, Brands.
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Float,
    ARRAY, Text, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship
from app.core.database import Base


class EntityType(str, enum.Enum):
    ARTIST = "artist"           # Musicians, bands, DJs
    MOVIE = "movie"             # Films, web series
    SPORTS_TEAM = "sports_team" # IPL teams, ISL clubs, etc.
    COMEDIAN = "comedian"       # Stand-up comedians
    THEATRE_GROUP = "theatre_group"  # Theatre companies
    ATTRACTION = "attraction"   # Amusement parks, venues, experiences
    WORKSHOP = "workshop"       # Workshop series / instructors
    RESTAURANT = "restaurant"   # Dining experiences
    BRAND = "brand"             # Shopping/lifestyle events


class EntityStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class Entity(Base):
    __tablename__ = "entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    name_aliases = Column(ARRAY(String), default=[])     # Alternate spellings
    entity_type = Column(String(50), nullable=False)   # EntityType enum value stored as string
    category = Column(String(100))                       # Sub-category (e.g. "Hip-Hop", "Comedy", "IPL")
    sub_categories = Column(ARRAY(String), default=[])
    status = Column(String(20), default=EntityStatus.ACTIVE.value)  # EntityStatus stored as string

    # Platform IDs — stored as JSONB for flexibility
    # e.g. {"spotify_id": "xxx", "tmdb_id": "yyy", "cricbuzz_id": "zzz"}
    external_ids = Column(JSONB, default={})

    # Profile
    image_url = Column(String(500))
    description = Column(Text)
    country = Column(String(50))
    language = Column(String(50))
    genre = Column(String(100))                          # Primary genre
    genres = Column(ARRAY(String), default=[])           # All genres

    # Geographic metadata
    home_city = Column(String(100))
    home_state = Column(String(100))
    # No default — a SQLAlchemy Column default fires whenever the value is
    # None at flush time, even if the caller explicitly passed None to mean
    # "unknown/not applicable." That silently overwrote every non-India
    # market with "India" (e.g. artist_discovery.py's global-chart
    # entities all got tagged primary_market="India" despite explicitly
    # setting None). Every caller must now state the market explicitly.
    primary_market = Column(String(50))

    # Flags
    is_verified = Column(Boolean, default=False)         # Manually verified entry
    is_international = Column(Boolean, default=False)    # International artist/entity
    is_active_on_district = Column(Boolean, default=False)  # Currently on District platform
    is_featured = Column(Boolean, default=False)

    # Zomato District specific
    district_entity_id = Column(String(255))             # ID on District platform if available
    booking_price_range_min = Column(Float)              # Min booking fee (INR)
    booking_price_range_max = Column(Float)              # Max booking fee (INR)
    typical_venue_capacity_min = Column(Integer)
    typical_venue_capacity_max = Column(Integer)

    # Metadata
    data_sources = Column(ARRAY(String), default=[])     # Which sources have data for this entity
    last_enriched_at = Column(TIMESTAMP(timezone=True))
    # Separate from last_enriched_at on purpose: entity_metrics.py's
    # sync uses last_enriched_at (and its "IS NULL first" ordering) to
    # prioritize scoring an entity's composite_score. social_listening.py
    # runs on its own independent 30-entity rotation and previously wrote
    # to that SAME column — meaning whichever worker touched an entity
    # first made it look "already enriched" to the OTHER worker's
    # never-scored-first priority check, silently deprioritizing real
    # composite_score computation for entities social_listening happened
    # to reach first. Each worker now owns its own timestamp column.
    # Per-field source/QID/retrieval-date provenance for enriched data
    data_provenance = Column(JSONB)
    last_social_listened_at = Column(TIMESTAMP(timezone=True))
    # Exact identity (Wikidata-sourced): ISO country name from P27/P495; NULL when unresolved
    nationality = Column(Text)
    signal_ids_resolved_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # ─── Relationships ─────────────────────────────────────────
    metrics = relationship("EntityMetric", back_populates="entity", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="entity")
    predictions = relationship("EntityPrediction", back_populates="entity")
    social_posts = relationship("SocialPost", back_populates="entity")
    trend_signals = relationship("TrendSignal", back_populates="entity")

    __table_args__ = (
        Index("ix_entities_name", "name"),
        Index("ix_entities_type", "entity_type"),
        Index("ix_entities_category", "category"),
        Index("ix_entities_external_ids", "external_ids", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Entity {self.name} ({self.entity_type})>"
