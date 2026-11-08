"""entity identity: signal_validity, nationality, signal_ids_resolved_at (additive)

Revision ID: a7c2f4e9b1d6
Revises: e5b1d7a3c9f4
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'a7c2f4e9b1d6'
down_revision: Union[str, None] = 'e5b1d7a3c9f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("entity_metrics", sa.Column("signal_validity", JSONB(), nullable=True))
    op.add_column("entities", sa.Column("nationality", sa.Text(), nullable=True))
    op.add_column("entities", sa.Column("signal_ids_resolved_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("entities", "signal_ids_resolved_at")
    op.drop_column("entities", "nationality")
    op.drop_column("entity_metrics", "signal_validity")
