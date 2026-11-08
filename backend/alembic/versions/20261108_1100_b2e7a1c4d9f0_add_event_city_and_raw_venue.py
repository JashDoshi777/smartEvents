"""add events.city and events.venue_name_raw (evidence for venue/city linking)

Revision ID: b2e7a1c4d9f0
Revises: b5e7f1a2c3d4
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2e7a1c4d9f0'
down_revision: Union[str, None] = 'b5e7f1a2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("city", sa.String(100), nullable=True))
    op.add_column("events", sa.Column("venue_name_raw", sa.String(255), nullable=True))
    op.create_index("ix_events_city", "events", ["city"])


def downgrade() -> None:
    op.drop_index("ix_events_city", table_name="events")
    op.drop_column("events", "venue_name_raw")
    op.drop_column("events", "city")
