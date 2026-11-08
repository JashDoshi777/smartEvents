"""additive hot-path indexes (latest-metric DISTINCT ON, market scope, notifications, social)

Revision ID: b5e7f1a2c3d4
Revises: a1d4c0de5eed
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'b5e7f1a2c3d4'
down_revision: Union[str, None] = 'a1d4c0de5eed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (name, DDL tail). All additive + IF NOT EXISTS; tables are small so a plain
# (non-CONCURRENTLY) build is instantaneous.
INDEXES = [
    # latest_metric(): DISTINCT ON (entity_id) ORDER BY entity_id, time DESC [WHERE composite_score IS NOT NULL]
    ("ix_entity_metrics_entity_time_desc", "entity_metrics (entity_id, time DESC)"),
    ("ix_entity_metrics_scored_entity_time", "entity_metrics (entity_id, time DESC) WHERE composite_score IS NOT NULL"),
    # market_clause(): primary_market / is_international filters
    ("ix_entities_market_intl", "entities (primary_market, is_international)"),
    ("ix_entities_type_name", "entities (entity_type, name)"),
    # events by entity + date (psychology exposure window, genre-by-city)
    ("ix_events_entity_date", "events (entity_id, event_date DESC)"),
    ("ix_events_venue_date", "events (venue_id, event_date)"),
    # notifications: current-signal DISTINCT ON + read-state lookups
    ("ix_trend_signals_entity_type_detected", "trend_signals (entity_id, signal_type, detected_at DESC)"),
    ("ix_notification_reads_user_signal", "notification_reads (user_id, trend_signal_id)"),
    # social: crisis-alert window scan + per-entity recent posts
    ("ix_social_posts_entity_analyzed", "social_posts (entity_id, analyzed_at DESC)"),
    # login lookup is case-insensitive
    ("ix_users_email_lower", "users (lower(email))"),
]


def upgrade() -> None:
    for name, tail in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {tail}")


def downgrade() -> None:
    for name, _ in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
