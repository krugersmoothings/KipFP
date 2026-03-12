"""create all phase-2 tables

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-02 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Enum specs (name -> values) ─────────────────────────────────────────────

ENUM_DEFS: list[tuple[str, tuple[str, ...]]] = [
    ("source_system", ("netsuite", "xero", "manual")),
    ("coa_type", ("netsuite", "xero", "custom")),
    ("consolidation_method", ("full", "equity", "none")),
    ("account_type", ("income", "cogs", "opex", "depreciation", "interest", "tax", "asset", "liability", "equity")),
    ("statement", ("is", "bs", "cf")),
    ("normal_balance", ("debit", "credit")),
    ("sync_status", ("running", "success", "partial", "failed")),
    ("sync_trigger", ("schedule", "manual")),
    ("version_type", ("budget", "forecast", "scenario")),
    ("version_status", ("draft", "approved", "locked")),
    ("wc_driver_type", ("dso", "dpo", "dii", "fixed_balance", "pct_revenue")),
    ("facility_type", ("property_loan", "equipment_loan", "vehicle_loan", "revolving", "overdraft")),
    ("interest_rate_type", ("fixed", "variable")),
    ("interest_calc_method", ("daily", "monthly")),
    ("amort_type", ("interest_only", "principal_and_interest", "bullet", "custom")),
    ("site_budget_driver_type", ("manual", "occupancy_rate", "per_dog_night", "headcount_x_rate", "pct_revenue")),
]


def _enum(name: str) -> PgEnum:
    """Reference an already-created PG enum by name without auto-creating it."""
    return PgEnum(name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    for name, values in ENUM_DEFS:
        PgEnum(*values, name=name, create_type=False).create(bind, checkfirst=True)

    # ── Organisation ────────────────────────────────────────────────────────

    op.create_table(
        "entities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(20), unique=True, nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("source_system", _enum("source_system")),
        sa.Column("source_entity_id", sa.String(100)),
        sa.Column("parent_entity_id", UUID(as_uuid=True), sa.ForeignKey("entities.id")),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("currency", sa.CHAR(3), server_default="AUD"),
        sa.Column("coa_type", _enum("coa_type")),
        sa.Column("consolidation_method", _enum("consolidation_method"), server_default="full"),
        sa.Column("acquisition_date", sa.Date),
    )

    op.create_table(
        "periods",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("fy_year", sa.Integer, nullable=False),
        sa.Column("fy_month", sa.Integer, nullable=False),
        sa.Column("calendar_year", sa.Integer),
        sa.Column("calendar_month", sa.Integer),
        sa.Column("period_start", sa.Date),
        sa.Column("period_end", sa.Date),
        sa.Column("is_locked", sa.Boolean, server_default=sa.text("false")),
        sa.UniqueConstraint("fy_year", "fy_month", name="uq_periods_fy"),
    )

    # ── Chart of Accounts ───────────────────────────────────────────────────

    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("account_type", _enum("account_type")),
        sa.Column("statement", _enum("statement")),
        sa.Column("parent_account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("is_subtotal", sa.Boolean, server_default=sa.text("false")),
        sa.Column("subtotal_formula", JSONB),
        sa.Column("is_elimination", sa.Boolean, server_default=sa.text("false")),
        sa.Column("normal_balance", _enum("normal_balance")),
    )

    # ── Site Level ──────────────────────────────────────────────────────────

    op.create_table(
        "locations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(20), unique=True),
        sa.Column("name", sa.String(200)),
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("entities.id")),
        sa.Column("state", sa.String(3)),
        sa.Column("opened_date", sa.Date),
        sa.Column("closed_date", sa.Date),
        sa.Column("capacity_dogs", sa.Integer),
        sa.Column("netsuite_location_id", sa.String(50)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
    )

    op.create_table(
        "weekly_periods",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("week_start_date", sa.Date, unique=True, nullable=False),
        sa.Column("week_end_date", sa.Date),
        sa.Column("fy_year", sa.Integer),
        sa.Column("fy_month", sa.Integer),
        sa.Column("fy_quarter", sa.Integer),
        sa.Column("calendar_year", sa.Integer),
        sa.Column("calendar_month", sa.Integer),
        sa.Column("days_in_fy_month", sa.Integer),
        sa.Column("days_this_week_in_fy_month", sa.Integer),
        sa.Column("week_label", sa.String(20)),
    )

    # ── Model ───────────────────────────────────────────────────────────────

    op.create_table(
        "budget_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("fy_year", sa.Integer, nullable=False),
        sa.Column("version_type", _enum("version_type"), server_default="budget"),
        sa.Column("status", _enum("version_status"), server_default="draft"),
        sa.Column("base_version_id", UUID(as_uuid=True), sa.ForeignKey("budget_versions.id")),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
    )

    # ── Chart of Accounts mappings ──────────────────────────────────────────

    op.create_table(
        "account_mappings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("source_account_code", sa.String(100), nullable=False),
        sa.Column("source_account_name", sa.String(200)),
        sa.Column("target_account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("multiplier", sa.Numeric(5, 4), server_default="1.0"),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.Column("notes", sa.Text),
    )

    op.create_index(
        "ix_account_mappings_entity_source",
        "account_mappings",
        ["entity_id", "source_account_code"],
    )

    # ── Actuals ─────────────────────────────────────────────────────────────

    op.create_table(
        "sync_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("entities.id")),
        sa.Column("source_system", _enum("source_system")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", _enum("sync_status")),
        sa.Column("records_upserted", sa.Integer, server_default="0"),
        sa.Column("error_detail", sa.Text),
        sa.Column("triggered_by", _enum("sync_trigger"), server_default="manual"),
    )

    op.create_table(
        "je_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("period_id", UUID(as_uuid=True), sa.ForeignKey("periods.id"), nullable=False),
        sa.Column("source_account_code", sa.String(100), nullable=False),
        sa.Column("source_account_name", sa.String(200)),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("sync_run_id", UUID(as_uuid=True), sa.ForeignKey("sync_runs.id"), nullable=False),
        sa.Column("source_ref", sa.String(200)),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id")),
    )

    op.create_index("ix_je_lines_entity_period", "je_lines", ["entity_id", "period_id"])
    op.create_index("ix_je_lines_source_account", "je_lines", ["source_account_code"])

    # ── Model assumptions ───────────────────────────────────────────────────

    op.create_table(
        "model_assumptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("budget_version_id", UUID(as_uuid=True), sa.ForeignKey("budget_versions.id")),
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("entities.id")),
        sa.Column("assumption_key", sa.String(100), nullable=False),
        sa.Column("assumption_value", JSONB, nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id")),
    )

    # ── Working Capital ─────────────────────────────────────────────────────

    op.create_table(
        "wc_drivers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("budget_version_id", UUID(as_uuid=True), sa.ForeignKey("budget_versions.id"), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("driver_type", _enum("wc_driver_type")),
        sa.Column("base_days", sa.Numeric(6, 2)),
        sa.Column("seasonal_factors", JSONB),
        sa.Column("notes", sa.Text),
        sa.Column("last_updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("last_updated_at", sa.DateTime(timezone=True)),
    )

    # ── Debt ────────────────────────────────────────────────────────────────

    op.create_table(
        "debt_facilities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("facility_type", _enum("facility_type")),
        sa.Column("limit_amount", sa.Numeric(18, 2)),
        sa.Column("opening_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("interest_rate_type", _enum("interest_rate_type")),
        sa.Column("base_rate", sa.Numeric(8, 6)),
        sa.Column("margin", sa.Numeric(8, 6), server_default="0"),
        sa.Column("interest_calc_method", _enum("interest_calc_method"), server_default="monthly"),
        sa.Column("amort_type", _enum("amort_type")),
        sa.Column("monthly_repayment", sa.Numeric(18, 2)),
        sa.Column("repayment_day", sa.Integer),
        sa.Column("maturity_date", sa.Date),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
    )

    op.create_table(
        "debt_schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("debt_facilities.id"), nullable=False),
        sa.Column("budget_version_id", UUID(as_uuid=True), sa.ForeignKey("budget_versions.id"), nullable=False),
        sa.Column("period_id", UUID(as_uuid=True), sa.ForeignKey("periods.id"), nullable=False),
        sa.Column("opening_balance", sa.Numeric(18, 2)),
        sa.Column("drawdown", sa.Numeric(18, 2), server_default="0"),
        sa.Column("repayment", sa.Numeric(18, 2), server_default="0"),
        sa.Column("closing_balance", sa.Numeric(18, 2)),
        sa.Column("interest_expense", sa.Numeric(18, 2)),
        sa.Column("interest_rate_applied", sa.Numeric(8, 6)),
    )

    op.create_index("ix_debt_schedules_facility_period", "debt_schedules", ["facility_id", "period_id"])

    # ── Site Budget ─────────────────────────────────────────────────────────

    op.create_table(
        "site_budget_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version_id", UUID(as_uuid=True), sa.ForeignKey("budget_versions.id")),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id")),
        sa.Column("model_line_item", sa.String(100)),
        sa.Column("week_id", UUID(as_uuid=True), sa.ForeignKey("weekly_periods.id")),
        sa.Column("amount", sa.Numeric(18, 2)),
        sa.Column("driver_type", _enum("site_budget_driver_type")),
        sa.Column("driver_params", JSONB),
        sa.Column("entered_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    tables = [
        "site_budget_entries",
        "debt_schedules",
        "debt_facilities",
        "wc_drivers",
        "model_assumptions",
        "je_lines",
        "sync_runs",
        "account_mappings",
        "budget_versions",
        "weekly_periods",
        "locations",
        "accounts",
        "periods",
        "entities",
    ]
    for t in tables:
        op.drop_table(t)

    bind = op.get_bind()
    for name, _ in reversed(ENUM_DEFS):
        PgEnum(name=name, create_type=False).drop(bind, checkfirst=True)
