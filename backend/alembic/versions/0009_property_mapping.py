"""add property_mappings table and extend source_system enum

Revision ID: 0009
Revises: 0008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE source_system ADD VALUE IF NOT EXISTS 'bigquery'")

    op.create_table(
        "property_mappings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("bigquery_property_id", sa.Integer, nullable=False),
        sa.Column("bigquery_property_name", sa.String(200), nullable=True),
        sa.Column("bigquery_url_slug", sa.String(100), nullable=True),
        sa.Column(
            "location_id",
            UUID(as_uuid=True),
            sa.ForeignKey("locations.id"),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            server_default="true",
            nullable=False,
        ),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_property_mappings_bq_id",
        "property_mappings",
        ["bigquery_property_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_property_mappings_bq_id", table_name="property_mappings")
    op.drop_table("property_mappings")
