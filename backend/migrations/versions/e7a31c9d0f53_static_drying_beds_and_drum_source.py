"""Add static drying beds, static bed batches, stirrings, and drum run coffee source linking.

Revision ID: e7a31c9d0f53
Revises: e7a31c9d0f52
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a31c9d0f53"
down_revision = "e7a31c9d0f52"
branch_labels = depends_on = None


def upgrade():
    # 1. Bảng sàn sấy tĩnh (Static Drying Beds)
    op.create_table(
        "static_drying_beds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bed_number", sa.Integer(), nullable=False),
        sa.Column("bed_code", sa.String(32), nullable=False),
        sa.Column("bed_name", sa.String(120), nullable=False),
        sa.Column("location_type", sa.String(32), nullable=False, server_default="indoor"),
        sa.Column("capacity_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("facility_id", "bed_code", name="uq_static_beds_facility_code"),
        sa.UniqueConstraint("facility_id", "bed_number", name="uq_static_beds_facility_number"),
    )
    op.create_index("ix_static_drying_beds_facility_id", "static_drying_beds", ["facility_id"])

    # 2. Bảng mẻ cà trên sàn sấy tĩnh (Static Bed Batches)
    op.create_table(
        "static_bed_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bed_id", sa.Integer(), sa.ForeignKey("static_drying_beds.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("batch_code", sa.String(64), nullable=False),
        sa.Column("coffee_type", sa.String(120), nullable=True),
        sa.Column("input_weight_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("water_drained_status", sa.String(32), nullable=False),  # 'drained' / 'wet'
        sa.Column("raw_material_status", sa.String(32), nullable=False),   # 'fresh' / 'spoiled'
        sa.Column("estimated_spoiled_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="on_bed"),  # 'on_bed' / 'discharged' / 'cancelled'
        sa.Column("discharged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discharge_drain_status", sa.String(32), nullable=True),  # 'even' / 'uneven'
        sa.Column("discharge_note", sa.String(500), nullable=True),
        sa.Column("total_bed_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("operator_name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_static_bed_batches_facility_status", "static_bed_batches", ["facility_id", "status"])
    op.create_index("ix_static_bed_batches_bed_id", "static_bed_batches", ["bed_id"])

    # 3. Bảng lượt đảo cà trên sàn sấy tĩnh (Static Bed Stirrings)
    op.create_table(
        "static_bed_stirrings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("static_bed_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stirring_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("stirring_method", sa.String(64), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("operator_name", sa.String(120), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_static_bed_stirrings_batch_id", "static_bed_stirrings", ["batch_id"])

    # 4. Thêm các cột liên kết nguồn cà vào drum_runs
    op.add_column("drum_runs", sa.Column("source_type", sa.String(32), nullable=True))
    op.add_column("drum_runs", sa.Column("source_bed_id", sa.Integer(), sa.ForeignKey("static_drying_beds.id", ondelete="SET NULL"), nullable=True))
    op.add_column("drum_runs", sa.Column("source_bed_number", sa.Integer(), nullable=True))
    op.add_column("drum_runs", sa.Column("source_bed_batch_id", sa.Integer(), sa.ForeignKey("static_bed_batches.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_drum_runs_source_bed_batch_id", "drum_runs", ["source_bed_batch_id"])

    # 5. Khởi tạo 4 sàn sấy tĩnh mặc định cho cơ sở hiện có
    op.execute("""
        INSERT INTO static_drying_beds (facility_id, bed_number, bed_code, bed_name, location_type, capacity_kg, is_active, created_at)
        SELECT f.id, s.num, 'SAN-0' || s.num, 'Sàn sấy tĩnh số ' || s.num || ' (Xưởng trong)', 'indoor', 2500, true, now()
        FROM facilities f
        CROSS JOIN (VALUES (1), (2), (3), (4)) AS s(num)
        ON CONFLICT DO NOTHING;
    """)


def downgrade():
    op.drop_index("ix_drum_runs_source_bed_batch_id", table_name="drum_runs")
    op.drop_column("drum_runs", "source_bed_batch_id")
    op.drop_column("drum_runs", "source_bed_number")
    op.drop_column("drum_runs", "source_bed_id")
    op.drop_column("drum_runs", "source_type")

    op.drop_table("static_bed_stirrings")
    op.drop_table("static_bed_batches")
    op.drop_table("static_drying_beds")
