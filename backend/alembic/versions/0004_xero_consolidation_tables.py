"""add api_credentials, consolidated_actuals, consolidation_runs tables

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("service", sa.String(50), nullable=False),
        sa.Column("credential_key", sa.String(100), nullable=False),
        sa.Column("credential_value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "consolidated_actuals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("period_id", UUID(as_uuid=True), sa.ForeignKey("periods.id"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("entities.id"), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("is_group_total", sa.Boolean(), server_default="false"),
        sa.Column("calculated_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_consolidated_actuals_period_account",
        "consolidated_actuals",
        ["period_id", "account_id"],
    )

    op.create_table(
        "consolidation_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("period_id", UUID(as_uuid=True), sa.ForeignKey("periods.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("running", "success", "failed", name="consolidation_status"),
        ),
        sa.Column("bs_balanced", sa.Boolean(), nullable=True),
        sa.Column("bs_variance", sa.Numeric(18, 2), nullable=True),
        sa.Column("ic_alerts", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("consolidation_runs")
    op.execute("DROP TYPE IF EXISTS consolidation_status")
    op.drop_index("ix_consolidated_actuals_period_account")
    op.drop_table("consolidated_actuals")
    op.drop_table("api_credentials")
