"""add site_pet_days table

Revision ID: 0010
Revises: 0009
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE pet_service_type AS ENUM ('boarding','daycare','grooming','wash','training'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$"
    )

    op.create_table(
        "site_pet_days",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "location_id",
            UUID(as_uuid=True),
            sa.ForeignKey("locations.id"),
            nullable=False,
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column(
            "service_type",
            ENUM("boarding", "daycare", "grooming", "wash", "training",
                 name="pet_service_type", create_type=False),
            nullable=False,
        ),
        sa.Column("pet_days", sa.Integer, nullable=False),
        sa.Column("revenue_aud", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "sync_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sync_runs.id"),
            nullable=True,
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "location_id", "date", "service_type",
            name="uq_site_pet_days_loc_date_svc",
        ),
    )
    op.create_index(
        "ix_site_pet_days_location_date",
        "site_pet_days",
        ["location_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_site_pet_days_location_date", table_name="site_pet_days")
    op.drop_table("site_pet_days")
    sa.Enum(name="pet_service_type").drop(op.get_bind(), checkfirst=True)
