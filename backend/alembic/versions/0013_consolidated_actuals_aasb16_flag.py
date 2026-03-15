"""Add include_aasb16 column to consolidated_actuals for separate AASB16 storage

Revision ID: 0013
Revises: 0012
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consolidated_actuals",
        sa.Column("include_aasb16", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("consolidated_actuals", "include_aasb16")
