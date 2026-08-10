"""
LiveIQ — Venue Model
Tracks all venues across India where events are held.
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, ARRAY, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship
from app.core.database import Base


class VenueType(str, enum.Enum):
    STADIUM = "stadium"
    ARENA = "arena"
    AMPHITHEATRE = "amphitheatre"
    THEATRE = "theatre"
    CLUB = "club"
    ROOFTOP = "rooftop"
    OUTDOOR_GROUNDS = "outdoor_grounds"
    CONVENTION_CENTRE = "convention_centre"
    MULTIPLEX = "multiplex"
    RESTAURANT = "restaurant"
    BREWERY = "brewery"
    ART_GALLERY = "art_gallery"
    SPORTS_COMPLEX = "sports_complex"
    PARK = "park"
    OTHER = "other"


class Venue(Base):
    __tablename__ = "venues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    venue_type = Column(String(50))

    # Location
    city = Column(String(100), nullable=False)
    state = Column(String(100))
    country = Column(String(50), default="India")
    address = Column(Text)
    pincode = Column(String(10))
    lat = Column(Float)
    lng = Column(Float)

    # Capacity
    total_capacity = Column(Integer)
    standing_capacity = Column(Integer)
    seated_capacity = Column(Integer)
    vip_capacity = Column(Integer)

    # Suitability for categories
    suitable_categories = Column(ARRAY(String), default=[])  # ['music', 'comedy', 'sports']
    max_decibel_allowed = Column(Float)             # Important for residential areas
    has_parking = Column(Boolean, default=False)
    parking_capacity = Column(Integer)
    is_indoor = Column(Boolean, default=True)
    is_alcohol_permitted = Column(Boolean, default=True)

    # Historical performance
    avg_fill_rate = Column(Float)                   # 0-1
    avg_ticket_price = Column(Float)                # INR
    total_events_hosted = Column(Integer, default=0)
    avg_rating = Column(Float)                      # From social feedback (1-5)

    # Amenities (JSON for flexibility)
    amenities = Column(JSONB, default={})
    # e.g. {"food_stalls": true, "vip_lounge": true, "metro_nearby": true, "sound_system": "world_class"}

    # External IDs
    google_place_id = Column(String(255))
    foursquare_id = Column(String(255))
    bookmyshow_venue_id = Column(String(255))

    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # ─── Relationships ─────────────────────────────────────────
    events = relationship("Event", back_populates="venue")

    __table_args__ = (
        Index("ix_venues_city", "city"),
        Index("ix_venues_type", "venue_type"),
    )

    def __repr__(self) -> str:
        return f"<Venue {self.name}, {self.city}>"
