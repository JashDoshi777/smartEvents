"""
LiveIQ — Restaurant/Venue Model (Master Data)
Real dining & nightlife venue listings — restaurants, cafes, bars,
pubs, and nightclubs — from Foursquare Places API and OpenStreetMap
(via Overpass), the two Zomato-adjacent data sources this project can
legally use (Zomato's own public API has been closed to new developers
for years; scraping Zomato's site directly was assessed as materially
riskier than scraping District's own site and was not pursued).

Table is named `restaurants` (kept from when it only covered sit-down
restaurants) but now covers all venue_type values — not renamed, to
avoid unnecessary migration churn for what's just a naming nuance.

Cross-source design: the two sources rarely share a stable common ID,
so a venue found in BOTH sources near the same coordinates is
stored as ONE row with both source IDs populated (foursquare_place_id
AND osm_id) rather than fabricating a merge — matching is done by
proximity + fuzzy name match at sync time (see restaurant_sync.py),
never guessed. A venue found in only one source has the other
source's ID column simply NULL.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Float, ARRAY, TIMESTAMP, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, BIGINT
from app.core.database import Base


class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)

    # 'restaurant' | 'cafe' | 'bar' | 'nightclub' — real, from whichever
    # source's amenity/category tag identified it; OSM's 'pub' is
    # collapsed into 'bar' at the client level (see overpass_client.py).
    # When both sources tag the same physical venue, Foursquare's
    # category (the more specific-search-driven of the two) wins, since
    # that's literally what was searched for to find it in that pass.
    venue_type = Column(String(20), nullable=False, server_default="restaurant")

    # Source IDs — at least one is always populated; either may be NULL.
    foursquare_place_id = Column(String(100), unique=True, nullable=True)
    osm_id = Column(BIGINT, nullable=True)
    osm_type = Column(String(10), nullable=True)  # 'node' or 'way' — OSM ids aren't globally unique without this

    # Location
    city = Column(String(100), nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    formatted_address = Column(String(500))

    # Cuisine / category — real tags from whichever source(s) had them,
    # never guessed. Foursquare gives category names, OSM gives cuisine
    # tags; both stored, since they aren't always equivalent vocabularies.
    foursquare_categories = Column(ARRAY(String), default=list)
    osm_cuisines = Column(ARRAY(String), default=list)

    # Contact — real, from either source, whichever had it. Widened from
    # 50 to 255: real OSM `phone` tags can legitimately contain multiple
    # numbers separated by `;` (a venue with a landline + mobile), which
    # exceeded 50 chars and crashed the upsert for real Kolkata venues.
    phone = Column(String(255))
    website = Column(String(500))
    opening_hours = Column(String(255))  # OSM's free-text opening_hours syntax; Foursquare doesn't reliably return this on Pro-tier fields

    # Explicitly no `rating` column — neither source provides a real,
    # free-tier rating (Foursquare's is Premium-only and wasn't
    # requested; OSM has no rating concept at all). Do not add one
    # without a real source backing it.

    scraped_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("osm_type", "osm_id", name="uq_restaurant_osm"),
        Index("ix_restaurants_city", "city"),
        Index("ix_restaurants_foursquare_place_id", "foursquare_place_id"),
    )

    def __repr__(self) -> str:
        return f"<Restaurant {self.name} ({self.city})>"
