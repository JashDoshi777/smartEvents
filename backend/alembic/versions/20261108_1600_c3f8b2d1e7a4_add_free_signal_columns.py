"""entity_metrics: wikipedia pageview columns + signal_provenance

Revision ID: c3f8b2d1e7a4
Revises: b2e7a1c4d9f0
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'c3f8b2d1e7a4'
down_revision: Union[str, None] = 'b2e7a1c4d9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("entity_metrics", sa.Column("wikipedia_views_30d", sa.BigInteger(), nullable=True))
    op.add_column("entity_metrics", sa.Column("wikipedia_views_7d", sa.BigInteger(), nullable=True))
    op.add_column("entity_metrics", sa.Column("signal_provenance", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("entity_metrics", "signal_provenance")
    op.drop_column("entity_metrics", "wikipedia_views_7d")
    op.drop_column("entity_metrics", "wikipedia_views_30d")
