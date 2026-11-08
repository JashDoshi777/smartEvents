"""scheduler: job_runs (execution log) + job_locks (lease lock)

Revision ID: d4a9c3e5f1b2
Revises: c3f8b2d1e7a4
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP

revision: str = 'd4a9c3e5f1b2'
down_revision: Union[str, None] = 'c3f8b2d1e7a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_name", sa.String(100), nullable=False),
        sa.Column("started_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", TIMESTAMP(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rows_affected", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column("trigger", sa.String(20)),
        sa.Column("detail", JSONB()),
    )
    op.create_index("ix_job_runs_job_name", "job_runs", ["job_name"])
    op.create_index("ix_job_runs_started_at", "job_runs", ["started_at"])
    op.create_table(
        "job_locks",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("holder", sa.String(100)),
        sa.Column("locked_until", TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("job_locks")
    op.drop_index("ix_job_runs_started_at", table_name="job_runs")
    op.drop_index("ix_job_runs_job_name", table_name="job_runs")
    op.drop_table("job_runs")
