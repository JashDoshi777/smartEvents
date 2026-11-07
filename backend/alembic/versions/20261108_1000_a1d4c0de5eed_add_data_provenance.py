"""add data_provenance JSONB to entities, cities, venues

Revision ID: a1d4c0de5eed
Revises: 6a84506f70da
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'a1d4c0de5eed'
down_revision: Union[str, None] = '6a84506f70da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("entities", "cities", "venues")


def upgrade() -> None:
    for t in TABLES:
        op.add_column(t, sa.Column("data_provenance", JSONB, nullable=True))


def downgrade() -> None:
    for t in TABLES:
        op.drop_column(t, "data_provenance")
