"""add paper tables

Revision ID: 0003_add_paper_tables
Revises: 0002_add_core_domain_tables
Create Date: 2026-04-10 05:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_paper_tables"
down_revision = "0002_add_core_domain_tables"
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
    if not _table_exists("paper_portfolio"):
        op.create_table(
            "paper_portfolio",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("avg_price", sa.Float(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_paper_portfolio_ticker", "paper_portfolio", ["ticker"])

    if not _table_exists("paper_orders"):
        op.create_table(
            "paper_orders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("side", sa.String(length=8), nullable=False),
            sa.Column("order_type", sa.String(length=16), nullable=False),
            sa.Column("price", sa.Float(), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="filled"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_paper_orders_ticker", "paper_orders", ["ticker"])

    if not _table_exists("paper_trades"):
        op.create_table(
            "paper_trades",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("side", sa.String(length=8), nullable=False),
            sa.Column("entry_price", sa.Float(), nullable=False),
            sa.Column("exit_price", sa.Float(), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("pnl", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_paper_trades_ticker", "paper_trades", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_paper_trades_ticker", table_name="paper_trades")
    op.drop_table("paper_trades")
    op.drop_index("ix_paper_orders_ticker", table_name="paper_orders")
    op.drop_table("paper_orders")
    op.drop_index("ix_paper_portfolio_ticker", table_name="paper_portfolio")
    op.drop_table("paper_portfolio")
