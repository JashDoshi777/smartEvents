"""
LiveIQ — User Model
Multi-role user management for the platform.
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from app.core.database import Base


class UserRole(str, enum.Enum):
    EXECUTIVE = "executive"     # CEO, VP — full access + reports
    ANALYST = "analyst"         # Data/Business analyst — full except settings
    BOOKER = "booker"           # Talent booking manager
    MARKETING = "marketing"     # Marketing manager
    VIEWER = "viewer"           # Read-only stakeholder


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255))
    full_name = Column(String(255))
    role = Column(String(20), default=UserRole.ANALYST.value)  # Store as string 'analyst'

    # Auth
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # Bumped on logout/rotation to invalidate every refresh token issued
    # before the bump — a stateless JWT can't be deleted, so revocation
    # works by embedding this value in the token and rejecting any token
    # whose embedded version no longer matches the user's current one.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")

    # OAuth (Google login)
    google_id = Column(String(255), unique=True, nullable=True)
    avatar_url = Column(String(500))

    # Preferences
    preferences = Column(JSONB, default={})
    # e.g. {"default_city": "Mumbai", "alert_emails": true, "favorite_categories": ["music"]}

    # Metadata
    last_login_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_users_email", "email"),
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
