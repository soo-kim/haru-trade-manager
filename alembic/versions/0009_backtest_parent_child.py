"""add backtest parent child run fields

Revision ID: 0009_backtest_parent_child
Revises: 0008_market_data_backtest
Create Date: 2026-07-02 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_backtest_parent_child"
down_revision = "0008_market_data_backtest"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def _ensure_index(index_name: str, table_name: str, columns: list[str]) -> None:
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    if not _table_exists("backtest_runs"):
        return
    if not _column_exists("backtest_runs", "run_type"):
        op.add_column(
            "backtest_runs",
            sa.Column("run_type", sa.String(length=32), nullable=False, server_default="single"),
        )
    if not _column_exists("backtest_runs", "parent_run_id"):
        op.add_column("backtest_runs", sa.Column("parent_run_id", sa.String(length=64), nullable=True))
    if not _column_exists("backtest_runs", "ticker"):
        op.add_column("backtest_runs", sa.Column("ticker", sa.String(length=16), nullable=True))

    _ensure_index("ix_backtest_runs_run_type", "backtest_runs", ["run_type"])
    _ensure_index("ix_backtest_runs_parent_run_id", "backtest_runs", ["parent_run_id"])
    _ensure_index("ix_backtest_runs_ticker", "backtest_runs", ["ticker"])

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    foreign_keys = inspector.get_foreign_keys("backtest_runs")
    if not any(fk.get("name") == "fk_backtest_runs_parent_run_id" for fk in foreign_keys):
        op.create_foreign_key(
            "fk_backtest_runs_parent_run_id",
            "backtest_runs",
            "backtest_runs",
            ["parent_run_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    if not _table_exists("backtest_runs"):
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    foreign_keys = inspector.get_foreign_keys("backtest_runs")
    if any(fk.get("name") == "fk_backtest_runs_parent_run_id" for fk in foreign_keys):
        op.drop_constraint("fk_backtest_runs_parent_run_id", "backtest_runs", type_="foreignkey")
    for index_name in ["ix_backtest_runs_ticker", "ix_backtest_runs_parent_run_id", "ix_backtest_runs_run_type"]:
        if _index_exists("backtest_runs", index_name):
            op.drop_index(index_name, table_name="backtest_runs")
    for column_name in ["ticker", "parent_run_id", "run_type"]:
        if _column_exists("backtest_runs", column_name):
            op.drop_column("backtest_runs", column_name)
