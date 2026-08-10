"""
All SQLAlchemy models — imported here so Alembic autogenerates migrations correctly.
Import order matters: models with no foreign keys first.
"""

from app.models.user import User, UserRole
from app.models.city import City
from app.models.venue import Venue, VenueType
from app.models.entity import Entity, EntityType, EntityStatus
from app.models.metrics import EntityMetric
from app.models.event import Event, EventCategory, EventStatus, EventSource
from app.models.intelligence import (
    EntityPrediction,
    CompetitorListing,
    SocialPost,
    TrendSignal,
    ExecBriefing,
    AISession,
    AIEmbedding,
)
from app.models.user_data import Watchlist, NotificationRead
from app.models.restaurant import Restaurant

__all__ = [
    "User", "UserRole",
    "City",
    "Venue", "VenueType",
    "Entity", "EntityType", "EntityStatus",
    "EntityMetric",
    "Event", "EventCategory", "EventStatus", "EventSource",
    "EntityPrediction",
    "CompetitorListing",
    "SocialPost",
    "TrendSignal",
    "ExecBriefing",
    "AISession",
    "AIEmbedding",
    "Watchlist",
    "NotificationRead",
    "Restaurant",
]
