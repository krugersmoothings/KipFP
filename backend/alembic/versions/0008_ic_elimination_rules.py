"""add ic_elimination_rules table

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ic_elimination_rules",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column(
            "entity_a_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            nullable=False,
        ),
        sa.Column("account_code_a", sa.String(100), nullable=False),
        sa.Column(
            "entity_b_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            nullable=False,
        ),
        sa.Column("account_code_b", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column(
            "tolerance",
            sa.Numeric(18, 2),
            server_default="10.00",
            nullable=False,
        ),
        sa.Column("notes", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ic_elimination_rules")
