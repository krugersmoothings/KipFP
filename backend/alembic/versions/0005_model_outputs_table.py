"""add model_outputs table for budget engine results

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CF pseudo-accounts for model output rendering
    op.execute("""
        INSERT INTO accounts (id, code, name, account_type, statement, sort_order, is_subtotal)
        VALUES
          (gen_random_uuid(), 'CF-OPERATING', 'Operating Cash Flow',  NULL, 'cf', 9010, false),
          (gen_random_uuid(), 'CF-INVESTING', 'Investing Cash Flow',  NULL, 'cf', 9020, false),
          (gen_random_uuid(), 'CF-FINANCING', 'Financing Cash Flow',  NULL, 'cf', 9030, false),
          (gen_random_uuid(), 'CF-NET',       'Net Cash Flow',        NULL, 'cf', 9040, true)
        ON CONFLICT (code) DO NOTHING
    """)

    op.create_table(
        "model_outputs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("budget_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "period_id",
            UUID(as_uuid=True),
            sa.ForeignKey("periods.id"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            nullable=True,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_unique_constraint(
        "uq_model_outputs_version_period_account_entity",
        "model_outputs",
        ["version_id", "period_id", "account_id", "entity_id"],
    )

    op.create_index(
        "ix_model_outputs_version_period",
        "model_outputs",
        ["version_id", "period_id"],
    )


def downgrade() -> None:
    op.drop_table("model_outputs")
