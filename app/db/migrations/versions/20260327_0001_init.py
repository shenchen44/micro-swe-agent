"""initial schema

Revision ID: 20260327_0001
Revises: None
Create Date: 2026-03-27 00:00:01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_0001"
down_revision = None
branch_labels = None
depends_on = None


task_status = sa.Enum(
    "received",
    "triaged",
    "sandbox_ready",
    "patching",
    "testing",
    "retrying",
    "ready_for_pr",
    "pr_opened",
    "failed",
    "done",
    name="taskstatus",
)

task_result_status = sa.Enum("success", "failed", "skipped", name="taskresultstatus")
task_artifact_type = sa.Enum(
    "raw_webhook",
    "issue_snapshot",
    "repo_tree",
    "prompt",
    "model_response",
    "diff",
    "test_log",
    "pr_body",
    name="taskartifacttype",
)


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_repositories_github_repo_id", "repositories", ["github_repo_id"], unique=True)
    op.create_index("ix_repositories_owner", "repositories", ["owner"], unique=False)
    op.create_index("ix_repositories_name", "repositories", ["name"], unique=False)

    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("github_issue_number", sa.Integer(), nullable=False),
        sa.Column("github_issue_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("html_url", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_issues_repository_id", "issues", ["repository_id"], unique=False)
    op.create_index("ix_issues_github_issue_number", "issues", ["github_issue_number"], unique=False)
    op.create_index("ix_issues_github_issue_id", "issues", ["github_issue_id"], unique=True)

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", task_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("branch_name", sa.Text(), nullable=True),
        sa.Column("base_commit", sa.Text(), nullable=True),
        sa.Column("head_commit", sa.Text(), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tasks_repository_id", "tasks", ["repository_id"], unique=False)
    op.create_index("ix_tasks_issue_id", "tasks", ["issue_id"], unique=False)
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)

    op.create_table(
        "task_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_index", sa.Integer(), nullable=False),
        sa.Column("model_summary", sa.JSON(), nullable=True),
        sa.Column("patch_text", sa.Text(), nullable=True),
        sa.Column("files_changed_count", sa.Integer(), nullable=True),
        sa.Column("diff_line_count", sa.Integer(), nullable=True),
        sa.Column("test_command", sa.Text(), nullable=True),
        sa.Column("test_exit_code", sa.Integer(), nullable=True),
        sa.Column("test_stdout", sa.Text(), nullable=True),
        sa.Column("test_stderr", sa.Text(), nullable=True),
        sa.Column("result_status", task_result_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_attempts_task_id", "task_attempts", ["task_id"], unique=False)

    op.create_table(
        "task_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", task_artifact_type, nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_artifacts_task_id", "task_artifacts", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_task_artifacts_task_id", table_name="task_artifacts")
    op.drop_table("task_artifacts")
    op.drop_index("ix_task_attempts_task_id", table_name="task_attempts")
    op.drop_table("task_attempts")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_issue_id", table_name="tasks")
    op.drop_index("ix_tasks_repository_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_issues_github_issue_id", table_name="issues")
    op.drop_index("ix_issues_github_issue_number", table_name="issues")
    op.drop_index("ix_issues_repository_id", table_name="issues")
    op.drop_table("issues")
    op.drop_index("ix_repositories_name", table_name="repositories")
    op.drop_index("ix_repositories_owner", table_name="repositories")
    op.drop_index("ix_repositories_github_repo_id", table_name="repositories")
    op.drop_table("repositories")
    task_artifact_type.drop(op.get_bind(), checkfirst=False)
    task_result_status.drop(op.get_bind(), checkfirst=False)
    task_status.drop(op.get_bind(), checkfirst=False)
