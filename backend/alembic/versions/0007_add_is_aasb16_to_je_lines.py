"""add is_aasb16 column to je_lines and update unique constraint

Revision ID: 0007
Revises: 0006
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "je_lines",
        sa.Column("is_aasb16", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.drop_constraint("uq_je_lines_entity_period_account", "je_lines", type_="unique")

    op.create_unique_constraint(
        "uq_je_lines_entity_period_account_aasb16",
        "je_lines",
        ["entity_id", "period_id", "source_account_code", "is_aasb16"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_je_lines_entity_period_account_aasb16", "je_lines", type_="unique")

    op.execute(
        "DELETE FROM je_lines WHERE is_aasb16 = true"
    )

    op.create_unique_constraint(
        "uq_je_lines_entity_period_account",
        "je_lines",
        ["entity_id", "period_id", "source_account_code"],
    )

    op.drop_column("je_lines", "is_aasb16")
