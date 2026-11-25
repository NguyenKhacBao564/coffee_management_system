"""Drum processing tables and drum_operator role.

Revision ID: e7a31c9d0f46
Revises: e7a31c9d0f45
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a31c9d0f46"
down_revision = "e7a31c9d0f45"
branch_labels = depends_on = None


def upgrade():
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin', 'manager', 'staff', 'drum_operator')",
    )

    op.create_table(
        "drums",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("drum_code", sa.String(32), nullable=False),
        sa.Column("drum_name", sa.String(120), nullable=False),
        sa.Column("capacity_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="idle"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("facility_id", "drum_code", name="uq_drums_facility_code"),
        sa.CheckConstraint("status IN ('idle', 'running', 'maintenance')", name="ck_drums_status"),
    )
    op.create_index("ix_drums_facility_id", "drums", ["facility_id"])

    op.create_table(
        "drum_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("drum_id", sa.Integer(), sa.ForeignKey("drums.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("batch_code", sa.String(64), nullable=False),
        sa.Column("coffee_type", sa.String(120), nullable=True),
        sa.Column("initial_weight_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("cycle_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("operator_name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="in_progress"),
        sa.Column("final_moisture_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("final_discharged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discharge_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('in_progress', 'completed', 'cancelled')", name="ck_drum_runs_status"),
    )
    op.create_index("ix_drum_runs_facility_status", "drum_runs", ["facility_id", "status"])
    op.create_index("ix_drum_runs_drum_id", "drum_runs", ["drum_id"])

    op.create_table(
        "drum_periodic_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("drum_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("operator_name", sa.String(120), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("moisture_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("temperature_celsius", sa.Numeric(5, 2), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delay_seconds", sa.Integer(), nullable=True),
        sa.Column("compliance_status", sa.String(32), nullable=False, server_default="on_time"),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("compliance_status IN ('on_time', 'late', 'anomalous')", name="ck_drum_logs_compliance"),
    )
    op.create_index("ix_drum_periodic_logs_run_id", "drum_periodic_logs", ["run_id"])

    op.create_table(
        "drum_inspections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("drum_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inspector_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("inspector_name", sa.String(120), nullable=False),
        sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sample_moisture_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("sample_temperature_celsius", sa.Numeric(5, 2), nullable=False),
        sa.Column("nearest_log_id", sa.Integer(), sa.ForeignKey("drum_periodic_logs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("moisture_diff", sa.Numeric(5, 2), nullable=True),
        sa.Column("temperature_diff", sa.Numeric(5, 2), nullable=True),
        sa.Column("evaluation", sa.String(32), nullable=False, server_default="passed"),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("evaluation IN ('passed', 'warning', 'failed')", name="ck_drum_inspections_evaluation"),
    )
    op.create_index("ix_drum_inspections_run_id", "drum_inspections", ["run_id"])


def downgrade():
    op.drop_table("drum_inspections")
    op.drop_table("drum_periodic_logs")
    op.drop_table("drum_runs")
    op.drop_table("drums")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin', 'manager', 'staff')",
    )

