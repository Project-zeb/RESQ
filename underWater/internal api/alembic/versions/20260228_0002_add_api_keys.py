"""add api keys table

Revision ID: 20260228_0002
Revises: 20260228_0001
Create Date: 2026-02-28 00:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260228_0002"
down_revision: Union[str, None] = "20260228_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.String(length=64), nullable=True),
        sa.Column("revoked_at", sa.String(length=64), nullable=True),
        sa.Column("last_used_at", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("idx_api_keys_role", "api_keys", ["role"])


def downgrade() -> None:
    op.drop_index("idx_api_keys_role", table_name="api_keys")
    op.drop_table("api_keys")
