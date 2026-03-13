"""add unique constraint to je_lines for upsert

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-03 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_je_lines_entity_period_account",
        "je_lines",
        ["entity_id", "period_id", "source_account_code"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_je_lines_entity_period_account",
        "je_lines",
        type_="unique",
    )
