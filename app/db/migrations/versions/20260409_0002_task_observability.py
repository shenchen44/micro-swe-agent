"""add task observability fields

Revision ID: 20260409_0002
Revises: 20260327_0001
Create Date: 2026-04-09 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260409_0002"
down_revision = "20260327_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("total_duration_ms", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("install_duration_ms", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("patch_duration_ms", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("test_duration_ms", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("model_call_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("task_attempts", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_attempts", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_attempts", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("task_attempts", sa.Column("model_duration_ms", sa.Integer(), nullable=True))
    op.add_column("task_attempts", sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("task_attempts", "tool_call_count")
    op.drop_column("task_attempts", "model_duration_ms")
    op.drop_column("task_attempts", "duration_ms")
    op.drop_column("task_attempts", "finished_at")
    op.drop_column("task_attempts", "started_at")

    op.drop_column("tasks", "tool_call_count")
    op.drop_column("tasks", "model_call_count")
    op.drop_column("tasks", "test_duration_ms")
    op.drop_column("tasks", "patch_duration_ms")
    op.drop_column("tasks", "install_duration_ms")
    op.drop_column("tasks", "total_duration_ms")
    op.drop_column("tasks", "finished_at")
    op.drop_column("tasks", "started_at")
