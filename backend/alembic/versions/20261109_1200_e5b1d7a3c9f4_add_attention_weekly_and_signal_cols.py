"""entity_attention_weekly + google-trends-relative and news-confidence columns (additive)

Revision ID: e5b1d7a3c9f4
Revises: d4a9c3e5f1b2
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP

revision: str = 'e5b1d7a3c9f4'
down_revision: Union[str, None] = 'd4a9c3e5f1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entity_attention_weekly",
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),            # ISO week Monday (UTC)
        sa.Column("wikipedia_views_en", sa.BigInteger()),
        sa.Column("wikipedia_views_hi", sa.BigInteger()),
        sa.Column("total", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("retrieved_at", TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("entity_id", "week_start"),
    )
    op.create_index("ix_attention_weekly_week", "entity_attention_weekly", ["week_start"])
    for name, typ in [("google_trend_relative", sa.Float()), ("google_trend_topic", sa.Text()),
                      ("google_trend_basis", sa.String(10)), ("news_confidence", sa.String(30)),
                      ("news_sample_titles", JSONB())]:
        op.add_column("entity_metrics", sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    for name in ["news_sample_titles", "news_confidence", "google_trend_basis", "google_trend_topic", "google_trend_relative"]:
        op.drop_column("entity_metrics", name)
    op.drop_index("ix_attention_weekly_week", table_name="entity_attention_weekly")
    op.drop_table("entity_attention_weekly")
