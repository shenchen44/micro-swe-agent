import logging
import uuid
from pathlib import Path

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.models.issue import Issue
from app.db.models.repository import Repository
from app.db.models.task import Task, TaskArtifact, TaskArtifactType, TaskStatus
from app.services.task_runner.state_machine import transition_or_raise


logger = logging.getLogger(__name__)

ACTIVE_TASK_STATUSES = {
    TaskStatus.received,
    TaskStatus.triaged,
    TaskStatus.sandbox_ready,
    TaskStatus.patching,
    TaskStatus.testing,
    TaskStatus.retrying,
    TaskStatus.ready_for_pr,
    TaskStatus.pr_opened,
}


def _task_options() -> list:
    """Common options for loading task relationships."""
    return [selectinload(Task.attempts), selectinload(Task.artifacts), selectinload(Task.repository), selectinload(Task.issue)]


def get_task_query() -> Select[tuple[Task]]:
    return select(Task).options(*_task_options()).order_by(Task.created_at.desc())


def _get_latest_artifact(task: Task, artifact_type: TaskArtifactType) -> TaskArtifact | None:
    """Get the latest artifact of a specific type, searching in reverse order."""
    return next(
        (artifact for artifact in reversed(task.artifacts) if artifact.artifact_type == artifact_type),
        None,
    )


def get_artifact_content(task: Task, artifact_type: TaskArtifactType) -> dict | str | None:
    """Get the content of the latest artifact of a specific type."""
    artifact = _get_latest_artifact(task, artifact_type)
    return artifact.content if artifact else None


def upsert_repository_and_issue(db: Session, payload: dict) -> tuple[Repository, Issue]:
    repo_payload = payload["repository"]
    issue_payload = payload["issue"]

    repository = db.scalar(select(Repository).where(Repository.github_repo_id == repo_payload["id"]))
    if repository is None:
        repository = Repository(
            github_repo_id=repo_payload["id"],
            owner=repo_payload["owner"]["login"],
            name=repo_payload["name"],
            default_branch=repo_payload.get("default_branch") or "main",
            is_active=True,
        )
        db.add(repository)
        db.flush()
    else:
        repository.owner = repo_payload["owner"]["login"]
        repository.name = repo_payload["name"]
        repository.default_branch = repo_payload.get("default_branch") or repository.default_branch

    issue = db.scalar(select(Issue).where(Issue.github_issue_id == issue_payload["id"]))
    label_snapshot = issue_payload.get("labels", [])
    if issue is None:
        issue = Issue(
            repository_id=repository.id,
            github_issue_number=issue_payload["number"],
            github_issue_id=issue_payload["id"],
            title=issue_payload["title"],
            body=issue_payload["body"],
            labels=label_snapshot,
            state=issue_payload["state"],
            html_url=issue_payload["html_url"],
        )
        db.add(issue)
        db.flush()
    else:
        issue.title = issue_payload["title"]
        issue.body = issue_payload["body"]
        issue.labels = label_snapshot
        issue.state = issue_payload["state"]
        issue.html_url = issue_payload["html_url"]
        issue.repository_id = repository.id

    return repository, issue


def has_active_task_for_issue(db: Session, issue_id: int) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.issue_id == issue_id, Task.status.in_(ACTIVE_TASK_STATUSES))
    )
    return bool(count)


def create_task_from_webhook(db: Session, payload: dict) -> Task:
    repository, issue = upsert_repository_and_issue(db, payload)
    if has_active_task_for_issue(db, issue.id):
        raise ValueError("active_task_exists")

    task = Task(repository_id=repository.id, issue_id=issue.id, status=TaskStatus.received)
    db.add(task)
    db.flush()

    db.add(
        TaskArtifact(
            task_id=task.id,
            artifact_type=TaskArtifactType.raw_webhook,
            content=payload,
        )
    )
    db.add(
        TaskArtifact(
            task_id=task.id,
            artifact_type=TaskArtifactType.issue_snapshot,
            content={
                "title": issue.title,
                "body": issue.body,
                "labels": issue.labels,
                "html_url": issue.html_url,
            },
        )
    )
    transition_task(db, task, TaskStatus.triaged)
    db.commit()
    db.refresh(task)
    return task


def create_integration_task(
    db: Session,
    source_tasks: list[Task],
    guidance: str | None = None,
    *,
    mode: str = "integration",
) -> Task:
    if not source_tasks:
        raise ValueError("source_tasks_required")
    repository_id = source_tasks[0].repository_id
    if any(task.repository_id != repository_id for task in source_tasks):
        raise ValueError("integration_tasks_must_share_repository")

    raw_webhook_artifact = _get_latest_artifact(source_tasks[0], TaskArtifactType.raw_webhook)
    if raw_webhook_artifact is None:
        raise ValueError("source_task_missing_raw_webhook")

    pr_numbers = [task.pr_number for task in source_tasks if task.pr_number is not None]
    if mode == "conflict_resolution":
        issue_title = f"Resolve conflict for PR {', '.join(f'#{number}' for number in pr_numbers) or 'selected agent change'}"
        body_sections = ["Create a conflict-resolved patch on top of the current default branch for the selected PR."]
    else:
        issue_title = f"Integrate PRs {', '.join(f'#{number}' for number in pr_numbers) or 'selected agent changes'}"
        body_sections = ["Create a conflict-free integration patch that combines the selected PRs."]
    if guidance:
        body_sections.append(f"User guidance:\n{guidance}")
    source_pr_contexts: list[dict] = []
    for task in source_tasks:
        latest_diff_artifact = _get_latest_artifact(task, TaskArtifactType.diff)
        latest_model_artifact = _get_latest_artifact(task, TaskArtifactType.model_response)
        latest_pr_body_artifact = _get_latest_artifact(task, TaskArtifactType.pr_body)
        summary = latest_model_artifact.content.get("summary") if latest_model_artifact and isinstance(latest_model_artifact.content, dict) else None
        diff_text = latest_diff_artifact.content.get("diff") if latest_diff_artifact and isinstance(latest_diff_artifact.content, dict) else ""
        pr_body = latest_pr_body_artifact.content.get("body") if latest_pr_body_artifact and isinstance(latest_pr_body_artifact.content, dict) else ""
        source_pr_contexts.append(
            {
                "task_id": task.id,
                "pr_number": task.pr_number,
                "branch_name": task.branch_name,
                "issue_number": task.issue.github_issue_number,
                "issue_title": task.issue.title,
                "issue_body": task.issue.body,
                "summary": summary if isinstance(summary, dict) else {},
                "pr_body": pr_body,
                "diff": diff_text,
            }
        )
        body_sections.append(
            "\n".join(
                [
                    f"Source task: {task.id}",
                    f"PR number: {task.pr_number or 'n/a'}",
                    f"Branch: {task.branch_name or 'n/a'}",
                    f"Summary: {summary}",
                    "Diff:",
                    diff_text or "(no diff captured)",
                ]
            )
        )

    issue = Issue(
        repository_id=repository_id,
        github_issue_number=0,
        github_issue_id=-(uuid.uuid4().int % 10**12),
        title=issue_title,
        body="\n\n---\n\n".join(body_sections),
        labels=[{"name": "integration"}],
        state="open",
        html_url="",
    )
    db.add(issue)
    db.flush()

    task = Task(repository_id=repository_id, issue_id=issue.id, status=TaskStatus.received)
    db.add(task)
    db.flush()

    raw_webhook = raw_webhook_artifact.content if isinstance(raw_webhook_artifact.content, dict) else {}
    db.add(TaskArtifact(task_id=task.id, artifact_type=TaskArtifactType.raw_webhook, content=raw_webhook))
    db.add(
        TaskArtifact(
            task_id=task.id,
            artifact_type=TaskArtifactType.issue_snapshot,
            content={"title": issue.title, "body": issue.body, "labels": issue.labels, "html_url": issue.html_url},
        )
    )
    db.add(
        TaskArtifact(
            task_id=task.id,
            artifact_type=TaskArtifactType.integration_request,
            content={
                "source_task_ids": [task_item.id for task_item in source_tasks],
                "source_pr_numbers": pr_numbers,
                "guidance": guidance or "",
                "mode": mode,
                "base_branch": source_tasks[0].repository.default_branch,
                "source_prs": source_pr_contexts,
            },
        )
    )
    transition_task(db, task, TaskStatus.triaged)
    db.commit()
    db.refresh(task)
    return task


def create_conflict_resolution_task(db: Session, source_task: Task, guidance: str | None = None) -> Task:
    if source_task.pr_number is None:
        raise ValueError("conflict_resolution_requires_pr_backed_task")
    return create_integration_task(db, [source_task], guidance, mode="conflict_resolution")


def transition_task(db: Session, task: Task, target_status: TaskStatus, failure_reason: dict | None = None) -> Task:
    task.status = transition_or_raise(task.status, target_status)
    if failure_reason is not None:
        task.failure_reason = failure_reason
    db.add(task)
    db.flush()
    return task


def mark_task_failed(db: Session, task: Task, reason: str, details: dict | None = None) -> Task:
    failure_payload = {"reason": reason, "details": details or {}}
    if task.status != TaskStatus.failed:
        task.status = TaskStatus.failed
    task.failure_reason = failure_payload
    db.add(task)
    db.flush()
    return task


def build_branch_name(issue: Issue, task_id: str) -> str:
    title_slug = "-".join(issue.title.lower().split())[:40].strip("-") or "issue"
    task_suffix = task_id[:8]
    return f"agent/issue-{issue.github_issue_number}-{title_slug}-{task_suffix}"


def ensure_workspace_root() -> Path:
    settings = get_settings()
    root = Path(settings.workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    return root
