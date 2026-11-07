"""
LiveIQ — City Model
Intelligence profile for each tracked Indian city.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from app.core.database import Base


class City(Base):
    __tablename__ = "cities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    state = Column(String(100))
    country = Column(String(50), default="India")
    tier = Column(Integer)                          # 1=metro, 2=major, 3=emerging, 4=small

    # Demographics
    population = Column(Integer)                    # City population
    metro_population = Column(Integer)              # Metro area population
    avg_monthly_income = Column(Float)              # INR
    youth_population_pct = Column(Float)            # % aged 18-35 (key audience)

    # Geo
    lat = Column(Float)
    lng = Column(Float)

    # Event market characteristics
    top_categories = Column(ARRAY(String), default=[])   # Most popular categories in this city
    active_venues_count = Column(Integer, default=0)
    avg_event_ticket_price = Column(Float)          # Average across all categories, INR

    # Platform presence
    active_on_district = Column(Boolean, default=False)  # Is District live in this city?
    district_events_count = Column(Integer, default=0)
    competitor_events_count = Column(Integer, default=0)

    # Seasonality metadata
    festival_months = Column(JSONB, default={})
    # e.g. {"high_demand": [10, 11, 12, 1, 2], "low_demand": [6, 7, 8], "festivals": {"diwali": 10}}

    # Weather risk (for outdoor events)
    monsoon_months = Column(ARRAY(Integer), default=[])  # Months when outdoor events are risky
    avg_temperature_jun_sep = Column(Float)         # Average temp during monsoon (Celsius)

    # Market intelligence
    nightlife_score = Column(Float)                 # 0-100, active nightlife market
    sports_affinity_score = Column(Float)           # 0-100, sports-loving city
    arts_culture_score = Column(Float)              # 0-100, arts/theatre affinity
    comedy_market_size = Column(Float)              # 0-100
    music_market_size = Column(Float)               # 0-100

    # Metadata
    google_trends_geo_code = Column(String(20))     # e.g. "IN-MH" for Maharashtra
    mapbox_bbox = Column(JSONB)                     # Bounding box for map rendering
    # Per-field source/QID/retrieval-date provenance for enriched data
    data_provenance = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<City {self.name} (Tier {self.tier})>"
