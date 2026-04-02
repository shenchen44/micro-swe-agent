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
    created_at: datetime
    updated_at: datetime
    attempts: list[TaskAttemptRead] = []
    artifacts: list[TaskArtifactRead] = []

    model_config = ConfigDict(from_attributes=True)
