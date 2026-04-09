from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.db.models.task import TaskArtifactType, TaskResultStatus, TaskStatus


class TaskAttemptRead(BaseModel):
    id: int
    attempt_index: int
    model_summary: dict | str | None
    patch_text: str | None
    files_changed_count: int | None
    diff_line_count: int | None
    test_command: str | None
    test_exit_code: int | None
    test_stdout: str | None
    test_stderr: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    model_duration_ms: int | None
    tool_call_count: int
    result_status: TaskResultStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskArtifactRead(BaseModel):
    id: int
    artifact_type: TaskArtifactType
    content: dict | str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskRead(BaseModel):
    id: str
    repository_id: int
    issue_id: int
    status: TaskStatus
    attempt_count: int
    branch_name: str | None
    base_commit: str | None
    head_commit: str | None
    pr_number: int | None
    failure_reason: dict | None
    started_at: datetime | None
    finished_at: datetime | None
    total_duration_ms: int | None
    install_duration_ms: int | None
    patch_duration_ms: int | None
    test_duration_ms: int | None
    model_call_count: int
    tool_call_count: int
    created_at: datetime
    updated_at: datetime
    attempts: list[TaskAttemptRead] = []
    artifacts: list[TaskArtifactRead] = []

    model_config = ConfigDict(from_attributes=True)
