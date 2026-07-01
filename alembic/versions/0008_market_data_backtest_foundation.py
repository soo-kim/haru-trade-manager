"""add market data and backtest foundation tables

Revision ID: 0008_market_data_backtest
Revises: 0007_add_auth_audit_logs
Create Date: 2026-07-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_market_data_backtest"
down_revision = "0007_add_auth_audit_logs"
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
    if not _table_exists("candle_collection_state"):
        op.create_table(
            "candle_collection_state",
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("timeframe", sa.String(length=8), nullable=False),
            sa.Column("first_candle_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_candle_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("consecutive_error_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="unknown"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("ticker", "timeframe"),
        )
    _ensure_index("ix_candle_collection_state_timeframe", "candle_collection_state", ["timeframe"])
    _ensure_index("ix_candle_collection_state_last_candle_time", "candle_collection_state", ["last_candle_time"])
    _ensure_index("ix_candle_collection_state_last_error_at", "candle_collection_state", ["last_error_at"])

    if not _table_exists("backtest_runs"):
        op.create_table(
            "backtest_runs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=True),
            sa.Column("strategy_id", sa.String(length=64), nullable=False),
            sa.Column("timeframe", sa.String(length=8), nullable=False),
            sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("params_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("slippage_pct", sa.Float(), nullable=False, server_default="0"),
            sa.Column("commission_pct", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("meta_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("summary_json", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_backtest_runs_strategy_id", "backtest_runs", ["strategy_id"])
    _ensure_index("ix_backtest_runs_timeframe", "backtest_runs", ["timeframe"])
    _ensure_index("ix_backtest_runs_start_at", "backtest_runs", ["start_at"])
    _ensure_index("ix_backtest_runs_end_at", "backtest_runs", ["end_at"])
    _ensure_index("ix_backtest_runs_status", "backtest_runs", ["status"])

    if not _table_exists("backtest_trades"):
        op.create_table(
            "backtest_trades",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("entry_signal_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("entry_price", sa.Float(), nullable=False),
            sa.Column("exit_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("exit_price", sa.Float(), nullable=False),
            sa.Column("side", sa.String(length=8), nullable=False),
            sa.Column("pnl", sa.Float(), nullable=False),
            sa.Column("return_pct", sa.Float(), nullable=False),
            sa.Column("exit_reason", sa.String(length=32), nullable=False),
            sa.Column("bars_held", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["backtest_runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_backtest_trades_run_id", "backtest_trades", ["run_id"])
    _ensure_index("ix_backtest_trades_ticker", "backtest_trades", ["ticker"])
    _ensure_index("ix_backtest_trades_entry_time", "backtest_trades", ["entry_time"])
    _ensure_index("ix_backtest_trades_exit_time", "backtest_trades", ["exit_time"])
    _ensure_index("ix_backtest_trades_exit_reason", "backtest_trades", ["exit_reason"])

    if not _table_exists("backtest_equity_points"):
        op.create_table(
            "backtest_equity_points",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("equity", sa.Float(), nullable=False),
            sa.Column("drawdown", sa.Float(), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["backtest_runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_backtest_equity_points_run_id", "backtest_equity_points", ["run_id"])
    _ensure_index("ix_backtest_equity_points_timestamp", "backtest_equity_points", ["timestamp"])


def downgrade() -> None:
    for index_name, table_name in [
        ("ix_backtest_equity_points_timestamp", "backtest_equity_points"),
        ("ix_backtest_equity_points_run_id", "backtest_equity_points"),
        ("ix_backtest_trades_exit_reason", "backtest_trades"),
        ("ix_backtest_trades_exit_time", "backtest_trades"),
        ("ix_backtest_trades_entry_time", "backtest_trades"),
        ("ix_backtest_trades_ticker", "backtest_trades"),
        ("ix_backtest_trades_run_id", "backtest_trades"),
        ("ix_backtest_runs_status", "backtest_runs"),
        ("ix_backtest_runs_end_at", "backtest_runs"),
        ("ix_backtest_runs_start_at", "backtest_runs"),
        ("ix_backtest_runs_timeframe", "backtest_runs"),
        ("ix_backtest_runs_strategy_id", "backtest_runs"),
        ("ix_candle_collection_state_last_error_at", "candle_collection_state"),
        ("ix_candle_collection_state_last_candle_time", "candle_collection_state"),
        ("ix_candle_collection_state_timeframe", "candle_collection_state"),
    ]:
        if _table_exists(table_name) and _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
    for table_name in ["backtest_equity_points", "backtest_trades", "backtest_runs", "candle_collection_state"]:
        if _table_exists(table_name):
            op.drop_table(table_name)
