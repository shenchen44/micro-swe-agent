from datetime import datetime

from app.db.models.issue import Issue
from app.db.models.repository import Repository
from app.db.models.task import Task, TaskAttempt, TaskResultStatus, TaskStatus


def test_list_tasks_accepts_legacy_string_model_summary(client, db_session) -> None:
    repository = Repository(
        github_repo_id=123,
        owner="octo",
        name="demo-repo",
        default_branch="main",
        is_active=True,
    )
    db_session.add(repository)
    db_session.flush()

    issue = Issue(
        repository_id=repository.id,
        github_issue_number=7,
        github_issue_id=456,
        title="Handle None display name",
        body="When display_name is None, formatting crashes.",
        labels=[{"name": "bug"}],
        state="open",
        html_url="https://github.com/octo/demo-repo/issues/7",
    )
    db_session.add(issue)
    db_session.flush()

    task = Task(
        repository_id=repository.id,
        issue_id=issue.id,
        status=TaskStatus.failed,
        attempt_count=1,
        total_duration_ms=3210,
        install_duration_ms=480,
        patch_duration_ms=950,
        test_duration_ms=1780,
        model_call_count=2,
        tool_call_count=5,
    )
    db_session.add(task)
    db_session.flush()

    db_session.add(
        TaskAttempt(
            task_id=task.id,
            attempt_index=1,
            model_summary="Fixed safe_divide function to handle ZeroDivisionError by returning None instead of raising an exception.",
            patch_text="",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            duration_ms=1111,
            model_duration_ms=222,
            tool_call_count=3,
            result_status=TaskResultStatus.failed,
        )
    )
    db_session.commit()

    response = client.get("/tasks")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["attempts"][0]["model_summary"].startswith("Fixed safe_divide function")
    assert payload[0]["total_duration_ms"] == 3210
    assert payload[0]["model_call_count"] == 2
    assert payload[0]["attempts"][0]["tool_call_count"] == 3
