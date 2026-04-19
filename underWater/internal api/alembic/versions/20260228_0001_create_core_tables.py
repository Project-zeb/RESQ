"""create core tables

Revision ID: 20260228_0001
Revises:
Create Date: 2026-02-28 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260228_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=True),
        sa.Column("severity", sa.String(length=128), nullable=True),
        sa.Column("urgency", sa.String(length=128), nullable=True),
        sa.Column("certainty", sa.String(length=128), nullable=True),
        sa.Column("area", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("issued_at", sa.String(length=64), nullable=True),
        sa.Column("effective_at", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.String(length=64), nullable=True),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("source", "external_id", name="uq_alert_source_external_id"),
    )
    op.create_index("idx_alerts_issued_at", "alerts", ["issued_at"])
    op.create_index("idx_alerts_source", "alerts", ["source"])

    op.create_table(
        "source_runs",
        sa.Column("source", sa.String(length=120), primary_key=True),
        sa.Column("last_status", sa.String(length=32), nullable=False),
        sa.Column("last_attempt_at", sa.String(length=64), nullable=False),
        sa.Column("last_success_at", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("records_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("source_runs")
    op.drop_index("idx_alerts_source", table_name="alerts")
    op.drop_index("idx_alerts_issued_at", table_name="alerts")
    op.drop_table("alerts")
