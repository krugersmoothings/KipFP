"""add site_budget_assumptions and site_weekly_budget tables

Revision ID: 0011
Revises: 0010
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_budget_assumptions",
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
            "location_id",
            UUID(as_uuid=True),
            sa.ForeignKey("locations.id"),
            nullable=False,
        ),
        sa.Column("fy_year", sa.Integer, nullable=False),
        # Revenue drivers
        sa.Column("price_growth_pct", sa.Numeric(6, 4), server_default="0.03"),
        sa.Column("pet_day_growth_pct", sa.Numeric(6, 4), server_default="0.02"),
        sa.Column("bath_price", sa.Numeric(8, 2), nullable=True),
        sa.Column("other_services_per_pet_day", sa.Numeric(8, 4), nullable=True),
        sa.Column("membership_pct_revenue", sa.Numeric(6, 4), nullable=True),
        # Labour drivers
        sa.Column("mpp_mins", sa.Numeric(6, 2), nullable=True),
        sa.Column("min_daily_hours", sa.Numeric(6, 2), nullable=True),
        sa.Column("wage_increase_pct", sa.Numeric(6, 4), server_default="0.05"),
        # Fixed cost drivers
        sa.Column("cogs_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("rent_monthly", sa.Numeric(10, 2), nullable=True),
        sa.Column("rent_growth_pct", sa.Numeric(6, 4), server_default="0.03"),
        sa.Column("utilities_monthly", sa.Numeric(10, 2), nullable=True),
        sa.Column("utilities_growth_pct", sa.Numeric(6, 4), server_default="0.03"),
        sa.Column("rm_monthly", sa.Numeric(10, 2), nullable=True),
        sa.Column("rm_growth_pct", sa.Numeric(6, 4), server_default="0.05"),
        sa.Column("it_monthly", sa.Numeric(10, 2), nullable=True),
        sa.Column("it_growth_pct", sa.Numeric(6, 4), server_default="0.05"),
        sa.Column("general_monthly", sa.Numeric(10, 2), nullable=True),
        sa.Column("general_growth_pct", sa.Numeric(6, 4), server_default="0.05"),
        sa.Column("advertising_pct_revenue", sa.Numeric(6, 4), nullable=True),
        # Metadata
        sa.Column(
            "assumptions_locked",
            sa.Boolean,
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "last_updated_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "version_id", "location_id",
            name="uq_site_budget_assumptions_version_location",
        ),
    )

    op.create_table(
        "site_weekly_budget",
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
            "location_id",
            UUID(as_uuid=True),
            sa.ForeignKey("locations.id"),
            nullable=False,
        ),
        sa.Column(
            "week_id",
            UUID(as_uuid=True),
            sa.ForeignKey("weekly_periods.id"),
            nullable=False,
        ),
        # Prior year inputs
        sa.Column("prior_year_pet_days_boarding", sa.Integer, nullable=True),
        sa.Column("prior_year_pet_days_daycare", sa.Integer, nullable=True),
        sa.Column("prior_year_pet_days_grooming", sa.Integer, nullable=True),
        sa.Column("prior_year_pet_days_wash", sa.Integer, nullable=True),
        sa.Column("prior_year_pet_days_training", sa.Integer, nullable=True),
        sa.Column("prior_year_revenue", sa.Numeric(12, 2), nullable=True),
        # Calculated outputs
        sa.Column("budget_pet_days_boarding", sa.Integer, nullable=True),
        sa.Column("budget_pet_days_daycare", sa.Integer, nullable=True),
        sa.Column("budget_pet_days_grooming", sa.Integer, nullable=True),
        sa.Column("budget_pet_days_wash", sa.Integer, nullable=True),
        sa.Column("budget_pet_days_training", sa.Integer, nullable=True),
        sa.Column("budget_revenue", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_labour", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_cogs", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_rent", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_utilities", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_rm", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_it", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_general", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_advertising", sa.Numeric(12, 2), nullable=True),
        # Override
        sa.Column(
            "is_overridden",
            sa.Boolean,
            server_default="false",
            nullable=False,
        ),
        sa.Column("override_revenue", sa.Numeric(12, 2), nullable=True),
        sa.Column("override_labour", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "version_id", "location_id", "week_id",
            name="uq_site_weekly_budget_version_loc_week",
        ),
    )
    op.create_index(
        "ix_site_weekly_budget_version_location",
        "site_weekly_budget",
        ["version_id", "location_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_site_weekly_budget_version_location",
        table_name="site_weekly_budget",
    )
    op.drop_table("site_weekly_budget")
    op.drop_table("site_budget_assumptions")
