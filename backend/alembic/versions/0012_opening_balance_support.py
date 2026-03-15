"""Add opening-balance support: is_opening_balance on je_lines, allow fy_month=0

Revision ID: 0012
Revises: 0011
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "je_lines",
        sa.Column(
            "is_opening_balance",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # The existing unique constraint uses (entity, period, account_code, is_aasb16).
    # Opening-balance rows live in their own period (fy_month=0), so the existing
    # constraint already keeps them unique — no change needed.


def downgrade() -> None:
    op.drop_column("je_lines", "is_opening_balance")
