"""add auth audit logs

Revision ID: 0007_add_auth_audit_logs
Revises: 0006_paper_strategy_id
Create Date: 2026-04-10 23:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_add_auth_audit_logs"
down_revision = "0006_paper_strategy_id"
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
    if not _table_exists("rebuild_auth_audit_logs"):
        op.create_table(
            "rebuild_auth_audit_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("ip", sa.String(length=64), nullable=False),
            sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_rebuild_auth_audit_logs_event_type", "rebuild_auth_audit_logs", ["event_type"])
    _ensure_index("ix_rebuild_auth_audit_logs_ip", "rebuild_auth_audit_logs", ["ip"])
    _ensure_index("ix_rebuild_auth_audit_logs_created_at", "rebuild_auth_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_rebuild_auth_audit_logs_created_at", table_name="rebuild_auth_audit_logs")
    op.drop_index("ix_rebuild_auth_audit_logs_ip", table_name="rebuild_auth_audit_logs")
    op.drop_index("ix_rebuild_auth_audit_logs_event_type", table_name="rebuild_auth_audit_logs")
    op.drop_table("rebuild_auth_audit_logs")
