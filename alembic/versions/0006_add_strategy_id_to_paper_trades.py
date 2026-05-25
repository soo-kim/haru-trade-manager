"""add strategy_id to paper_trades

Revision ID: 0006_paper_strategy_id
Revises: 0005_rebuild_perf
Create Date: 2026-04-10 22:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_paper_strategy_id"
down_revision = "0005_rebuild_perf"
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


def upgrade() -> None:
    if not _table_exists("paper_trades"):
        return
    if not _column_exists("paper_trades", "strategy_id"):
        op.add_column(
            "paper_trades",
            sa.Column("strategy_id", sa.String(length=32), nullable=False, server_default="default"),
        )
    if not _index_exists("paper_trades", "ix_paper_trades_strategy_id"):
        op.create_index("ix_paper_trades_strategy_id", "paper_trades", ["strategy_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_paper_trades_strategy_id", table_name="paper_trades")
    op.drop_column("paper_trades", "strategy_id")
