"""add rebuild core tables

Revision ID: 0004_add_rebuild_core_tables
Revises: 0003_add_paper_tables
Create Date: 2026-04-10 09:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_rebuild_core_tables"
down_revision = "0003_add_paper_tables"
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
    if not _table_exists("rebuild_config"):
        op.create_table(
            "rebuild_config",
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )

    if not _table_exists("rebuild_config_history"):
        op.create_table(
            "rebuild_config_history",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=False),
            sa.Column("changed_by", sa.String(length=64), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_rebuild_config_history_key", "rebuild_config_history", ["key"])

    if not _table_exists("rebuild_candles"):
        op.create_table(
            "rebuild_candles",
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
            sa.UniqueConstraint("ticker", "timeframe", "candle_time", name="uq_rebuild_candle_unique"),
        )
    _ensure_index("ix_rebuild_candles_ticker", "rebuild_candles", ["ticker"])
    _ensure_index("ix_rebuild_candles_timeframe", "rebuild_candles", ["timeframe"])
    _ensure_index("ix_rebuild_candles_candle_time", "rebuild_candles", ["candle_time"])

    if not _table_exists("rebuild_signals"):
        op.create_table(
            "rebuild_signals",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("strategy_id", sa.String(length=32), nullable=False),
            sa.Column("timeframe", sa.String(length=8), nullable=False),
            sa.Column("side", sa.String(length=8), nullable=False),
            sa.Column("signal_price", sa.Float(), nullable=False),
            sa.Column("signal_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_rebuild_signals_ticker", "rebuild_signals", ["ticker"])
    _ensure_index("ix_rebuild_signals_strategy_id", "rebuild_signals", ["strategy_id"])

    if not _table_exists("rebuild_orders"):
        op.create_table(
            "rebuild_orders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("signal_id", sa.Integer(), nullable=True),
            sa.Column("external_order_id", sa.String(length=64), nullable=True),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("side", sa.String(length=8), nullable=False),
            sa.Column("order_type", sa.String(length=16), nullable=False),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("filled_quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("reason", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["signal_id"], ["rebuild_signals.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_rebuild_orders_signal_id", "rebuild_orders", ["signal_id"])
    _ensure_index("ix_rebuild_orders_external_order_id", "rebuild_orders", ["external_order_id"])
    _ensure_index("ix_rebuild_orders_ticker", "rebuild_orders", ["ticker"])

    if not _table_exists("rebuild_positions"):
        op.create_table(
            "rebuild_positions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=True),
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
            sa.ForeignKeyConstraint(["order_id"], ["rebuild_orders.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_rebuild_positions_order_id", "rebuild_positions", ["order_id"])
    _ensure_index("ix_rebuild_positions_ticker", "rebuild_positions", ["ticker"])
    _ensure_index("ix_rebuild_positions_strategy_id", "rebuild_positions", ["strategy_id"])


def downgrade() -> None:
    op.drop_index("ix_rebuild_positions_strategy_id", table_name="rebuild_positions")
    op.drop_index("ix_rebuild_positions_ticker", table_name="rebuild_positions")
    op.drop_index("ix_rebuild_positions_order_id", table_name="rebuild_positions")
    op.drop_table("rebuild_positions")

    op.drop_index("ix_rebuild_orders_ticker", table_name="rebuild_orders")
    op.drop_index("ix_rebuild_orders_external_order_id", table_name="rebuild_orders")
    op.drop_index("ix_rebuild_orders_signal_id", table_name="rebuild_orders")
    op.drop_table("rebuild_orders")

    op.drop_index("ix_rebuild_signals_strategy_id", table_name="rebuild_signals")
    op.drop_index("ix_rebuild_signals_ticker", table_name="rebuild_signals")
    op.drop_table("rebuild_signals")

    op.drop_index("ix_rebuild_candles_candle_time", table_name="rebuild_candles")
    op.drop_index("ix_rebuild_candles_timeframe", table_name="rebuild_candles")
    op.drop_index("ix_rebuild_candles_ticker", table_name="rebuild_candles")
    op.drop_table("rebuild_candles")

    op.drop_index("ix_rebuild_config_history_key", table_name="rebuild_config_history")
    op.drop_table("rebuild_config_history")
    op.drop_table("rebuild_config")
