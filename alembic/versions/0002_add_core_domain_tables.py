"""add core domain tables

Revision ID: 0002_add_core_domain_tables
Revises: 0001_init_config_tables
Create Date: 2026-04-10 04:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_core_domain_tables"
down_revision = "0001_init_config_tables"
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
    if not _table_exists("symbols"):
        op.create_table(
            "symbols",
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("market", sa.String(length=16), nullable=False),
            sa.Column("in_universe", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="normal"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("ticker"),
        )

    if not _table_exists("candles"):
        op.create_table(
            "candles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("timeframe", sa.String(length=8), nullable=False),
            sa.Column("candle_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("open", sa.Float(), nullable=False),
            sa.Column("high", sa.Float(), nullable=False),
            sa.Column("low", sa.Float(), nullable=False),
            sa.Column("close", sa.Float(), nullable=False),
            sa.Column("volume", sa.Float(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("ticker", "timeframe", "candle_time", name="uq_candle_unique"),
        )
    _ensure_index("ix_candles_ticker", "candles", ["ticker"])
    _ensure_index("ix_candles_timeframe", "candles", ["timeframe"])
    _ensure_index("ix_candles_candle_time", "candles", ["candle_time"])

    if not _table_exists("signals"):
        op.create_table(
            "signals",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("strategy_id", sa.String(length=32), nullable=False),
            sa.Column("timeframe", sa.String(length=8), nullable=False),
            sa.Column("signal_type", sa.String(length=16), nullable=False, server_default="entry"),
            sa.Column("side", sa.String(length=8), nullable=False, server_default="buy"),
            sa.Column("signal_price", sa.Float(), nullable=False),
            sa.Column("signal_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_signals_ticker", "signals", ["ticker"])
    _ensure_index("ix_signals_strategy_id", "signals", ["strategy_id"])

    if not _table_exists("positions"):
        op.create_table(
            "positions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("strategy_id", sa.String(length=32), nullable=False),
            sa.Column("state", sa.String(length=16), nullable=False, server_default="OPEN"),
            sa.Column("entry_price", sa.Float(), nullable=False),
            sa.Column("stop_price", sa.Float(), nullable=False),
            sa.Column("take_profit_price", sa.Float(), nullable=False),
            sa.Column("trailing_stop_price", sa.Float(), nullable=True),
            sa.Column("highest_price", sa.Float(), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("remaining_quantity", sa.Float(), nullable=False),
            sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("closed_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("close_reason", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_positions_ticker", "positions", ["ticker"])
    _ensure_index("ix_positions_strategy_id", "positions", ["strategy_id"])

    if not _table_exists("orders"):
        op.create_table(
            "orders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("position_id", sa.Integer(), nullable=True),
            sa.Column("external_order_id", sa.String(length=64), nullable=True),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("strategy_id", sa.String(length=32), nullable=False),
            sa.Column("side", sa.String(length=8), nullable=False),
            sa.Column("order_type", sa.String(length=16), nullable=False),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("filled_quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("reason", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_orders_position_id", "orders", ["position_id"])
    _ensure_index("ix_orders_external_order_id", "orders", ["external_order_id"])
    _ensure_index("ix_orders_ticker", "orders", ["ticker"])
    _ensure_index("ix_orders_strategy_id", "orders", ["strategy_id"])

    if not _table_exists("account_snapshots"):
        op.create_table(
            "account_snapshots",
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
    _ensure_index("ix_account_snapshots_snapshot_time", "account_snapshots", ["snapshot_time"])
    _ensure_index("ix_account_snapshots_snapshot_type", "account_snapshots", ["snapshot_type"])

    if not _table_exists("cash_flows"):
        op.create_table(
            "cash_flows",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("flow_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("total_before", sa.Float(), nullable=False),
            sa.Column("total_after", sa.Float(), nullable=False),
            sa.Column("detected_by", sa.String(length=16), nullable=False, server_default="auto"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_cash_flows_flow_time", "cash_flows", ["flow_time"])


def downgrade() -> None:
    op.drop_index("ix_cash_flows_flow_time", table_name="cash_flows")
    op.drop_table("cash_flows")

    op.drop_index("ix_account_snapshots_snapshot_type", table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_snapshot_time", table_name="account_snapshots")
    op.drop_table("account_snapshots")

    op.drop_index("ix_orders_strategy_id", table_name="orders")
    op.drop_index("ix_orders_ticker", table_name="orders")
    op.drop_index("ix_orders_external_order_id", table_name="orders")
    op.drop_index("ix_orders_position_id", table_name="orders")
    op.drop_table("orders")

    op.drop_index("ix_positions_strategy_id", table_name="positions")
    op.drop_index("ix_positions_ticker", table_name="positions")
    op.drop_table("positions")

    op.drop_index("ix_signals_strategy_id", table_name="signals")
    op.drop_index("ix_signals_ticker", table_name="signals")
    op.drop_table("signals")

    op.drop_index("ix_candles_candle_time", table_name="candles")
    op.drop_index("ix_candles_timeframe", table_name="candles")
    op.drop_index("ix_candles_ticker", table_name="candles")
    op.drop_table("candles")

    op.drop_table("symbols")
