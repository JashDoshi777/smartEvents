"""composite v3: score_confidence, signals_used, score_version on entity_metrics (additive, nullable)

Revision ID: b3d9e6a1c4f7
Revises: a7c2f4e9b1d6
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'b3d9e6a1c4f7'
down_revision: Union[str, None] = 'a7c2f4e9b1d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE entity_metrics ADD COLUMN IF NOT EXISTS score_confidence double precision")
    op.execute("ALTER TABLE entity_metrics ADD COLUMN IF NOT EXISTS signals_used jsonb")
    op.execute("ALTER TABLE entity_metrics ADD COLUMN IF NOT EXISTS score_version varchar(10)")


def downgrade() -> None:
    op.drop_column("entity_metrics", "score_version")
    op.drop_column("entity_metrics", "signals_used")
    op.drop_column("entity_metrics", "score_confidence")
