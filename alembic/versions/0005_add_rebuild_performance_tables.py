"""add rebuild performance tables

Revision ID: 0005_rebuild_perf
Revises: 0004_add_rebuild_core_tables
Create Date: 2026-04-10 21:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_rebuild_perf"
down_revision = "0004_add_rebuild_core_tables"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def _ensure_index(index_name: str, table_name: str, columns: list[str]) -> None:
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    if not _table_exists("rebuild_account_snapshots"):
        op.create_table(
            "rebuild_account_snapshots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("snapshot_type", sa.String(length=32), nullable=False),
            sa.Column("total_assets", sa.Float(), nullable=False),
            sa.Column("cash", sa.Float(), nullable=False),
            sa.Column("stock_value", sa.Float(), nullable=False),
            sa.Column("margin_used", sa.Float(), nullable=False, server_default="0"),
            sa.Column("open_positions", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_rebuild_account_snapshots_snapshot_time", "rebuild_account_snapshots", ["snapshot_time"])
    _ensure_index("ix_rebuild_account_snapshots_snapshot_type", "rebuild_account_snapshots", ["snapshot_type"])

    if not _table_exists("rebuild_cash_flows"):
        op.create_table(
            "rebuild_cash_flows",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("flow_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("total_before", sa.Float(), nullable=False),
            sa.Column("total_after", sa.Float(), nullable=False),
            sa.Column("detected_by", sa.String(length=16), nullable=False, server_default="auto"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_rebuild_cash_flows_flow_time", "rebuild_cash_flows", ["flow_time"])


def downgrade() -> None:
    op.drop_index("ix_rebuild_cash_flows_flow_time", table_name="rebuild_cash_flows")
    op.drop_table("rebuild_cash_flows")
    op.drop_index(
        "ix_rebuild_account_snapshots_snapshot_type",
        table_name="rebuild_account_snapshots",
    )
    op.drop_index(
        "ix_rebuild_account_snapshots_snapshot_time",
        table_name="rebuild_account_snapshots",
    )
    op.drop_table("rebuild_account_snapshots")
