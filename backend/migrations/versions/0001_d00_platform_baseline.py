"""D00 baseline; business tables will arrive with their task."""

revision = "0001_d00_platform_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic's version table is the only schema change in D00.
    pass


def downgrade() -> None:
    pass
