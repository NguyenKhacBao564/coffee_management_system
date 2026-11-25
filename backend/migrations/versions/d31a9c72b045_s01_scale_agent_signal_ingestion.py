"""S01 scale agent credentials and immutable signal events."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d31a9c72b045"
down_revision: Union[str, None] = "a4e0b078241b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scale_agents",
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column("scale_code", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(display_name) > 0", name="ck_scale_agents_display_name"),
        sa.CheckConstraint("length(scale_code) > 0", name="ck_scale_agents_scale_code"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"]),
        sa.PrimaryKeyConstraint("agent_id"),
        sa.UniqueConstraint("facility_id", "scale_code", name="uq_scale_agents_facility_code"),
        sa.UniqueConstraint("token_hash", name="uq_scale_agents_token_hash"),
    )
    op.create_index("ix_scale_agents_facility_id", "scale_agents", ["facility_id"], unique=False)
    op.create_table(
        "scale_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("vendor_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("schema_version = 1", name="ck_scale_signals_schema_version"),
        sa.CheckConstraint("sequence > 0", name="ck_scale_signals_positive_sequence"),
        sa.CheckConstraint("source = 'canxe2015_ui'", name="ck_scale_signals_source"),
        sa.CheckConstraint("weight_kg >= 1000", name="ck_scale_signals_minimum_weight"),
        sa.ForeignKeyConstraint(["agent_id"], ["scale_agents.agent_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "event_id", name="uq_scale_signals_agent_event"),
        sa.UniqueConstraint("agent_id", "sequence", name="uq_scale_signals_agent_sequence"),
    )
    op.create_index("ix_scale_signals_agent_observed", "scale_signals", ["agent_id", "observed_at_utc"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scale_signals_agent_observed", table_name="scale_signals")
    op.drop_table("scale_signals")
    op.drop_index("ix_scale_agents_facility_id", table_name="scale_agents")
    op.drop_table("scale_agents")
