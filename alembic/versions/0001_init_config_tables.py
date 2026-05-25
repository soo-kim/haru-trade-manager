"""init config tables

Revision ID: 0001_init_config_tables
Revises:
Create Date: 2026-04-10 03:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_init_config_tables"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("config"):
        op.create_table(
            "config",
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )

    if not _table_exists("config_history"):
        op.create_table(
            "config_history",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=False),
            sa.Column("changed_by", sa.String(length=64), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if _table_exists("config_history") and not _index_exists("config_history", "ix_config_history_key"):
        op.create_index("ix_config_history_key", "config_history", ["key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_config_history_key", table_name="config_history")
    op.drop_table("config_history")
    op.drop_table("config")
