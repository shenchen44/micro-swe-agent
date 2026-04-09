import asyncio
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models.task import Task, TaskArtifact, TaskArtifactType, TaskAttempt, TaskResultStatus, TaskStatus
from app.db.session import SessionLocal
from app.services.comments.formatter import format_issue_failure_comment, format_issue_success_comment, format_pr_body
from app.services.github.auth import GitHubAuthService
from app.services.github.issues import GitHubIssueService
from app.services.github.pulls import GitHubPullRequestService
from app.services.github.repos import build_clone_url
from app.services.openai.agent_loop import AgentLoop, AgentResponseParseError
from app.services.openai.tools import AgentToolbox, ToolExecutionError
from app.services.sandbox.git_ops import checkout_new_branch, clone_repo, commit_all, diff, push_branch, set_remote_url
from app.services.sandbox.limits import enforce_patch_limits, parse_diff_stats
from app.services.sandbox.repo_config import load_repo_config
from app.services.sandbox.runner import SandboxRunner
from app.services.task_runner.orchestrator import build_branch_name, ensure_workspace_root, get_artifact_content, mark_task_failed, transition_task


logger = logging.getLogger(__name__)


def ensure_mapping(value: object) -> dict:
    if isinstance(value, dict):
        return value
    return {}


def _get_raw_webhook(task: Task) -> dict:
    raw_webhook = get_artifact_content(task, TaskArtifactType.raw_webhook)
    if isinstance(raw_webhook, dict):
        return raw_webhook
    raise ValueError("raw_webhook_artifact_missing")


def _build_issue_context(task: Task) -> dict:
    issue_context = {
        "mode": "integration" if task.issue.github_issue_number <= 0 else "issue_fix",
        "title": task.issue.title,
        "body": task.issue.body,
        "issue_number": task.issue.github_issue_number,
        "repository": f"{task.repository.owner}/{task.repository.name}",
        "default_branch": task.repository.default_branch,
    }
    integration_request = get_artifact_content(task, TaskArtifactType.integration_request)
    if isinstance(integration_request, dict):
        issue_context["integration_request"] = integration_request
    return issue_context


def _is_conflict_resolution_task(task: Task) -> bool:
    integration_request = get_artifact_content(task, TaskArtifactType.integration_request)
    return isinstance(integration_request, dict) and integration_request.get("mode") == "conflict_resolution"


def _utcnow() -> datetime:
    return datetime.utcnow()


def _elapsed_ms(start_time: float) -> int:
    return int((perf_counter() - start_time) * 1000)


def _record_attempt(
    db,
    task: Task,
    attempt_index: int,
    result_status: TaskResultStatus,
    diff_text: str,
    *,
    model_summary: dict | None = None,
    patch_text: str | None = None,
    test_command: str | None = None,
    test_exit_code: int | None = None,
    test_stdout: str | None = None,
    test_stderr: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    duration_ms: int | None = None,
    model_duration_ms: int | None = None,
    tool_call_count: int = 0,
    error_text: str | None = None,
    tool_name: str | None = None,
    tool_arguments: dict | None = None,
    raw_response: str | None = None,
) -> None:
    diff_stats = parse_diff_stats(diff_text)
    attempt = TaskAttempt(
        task_id=task.id,
        attempt_index=attempt_index,
        model_summary=model_summary,
        patch_text=patch_text,
        files_changed_count=diff_stats.files_changed_count,
        diff_line_count=diff_stats.diff_line_count,
        test_command=test_command,
        test_exit_code=test_exit_code,
        test_stdout=test_stdout,
        test_stderr=test_stderr,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        model_duration_ms=model_duration_ms,
        tool_call_count=tool_call_count,
        result_status=result_status,
    )
    db.add(attempt)
    db.add(
        TaskArtifact(
            task_id=task.id,
            artifact_type=TaskArtifactType.diff,
            content={"attempt": attempt_index, "diff": diff_text, "error": error_text},
        )
    )
    db.add(
        TaskArtifact(
            task_id=task.id,
            artifact_type=TaskArtifactType.model_response,
            content={
                "attempt": attempt_index,
                "summary": model_summary,
                "patch_text": patch_text,
                "tool_name": tool_name,
                "tool_arguments": tool_arguments,
                "error": error_text,
                "raw_response": raw_response,
            },
        )
    )
    if test_command is not None or test_stdout is not None or test_stderr is not None or test_exit_code is not None:
        db.add(
            TaskArtifact(
                task_id=task.id,
                artifact_type=TaskArtifactType.test_log,
                content={"stdout": test_stdout or "", "stderr": test_stderr or "", "exit_code": test_exit_code},
            )
        )


async def process_task(task_id: str) -> None:
    settings = get_settings()
    db = SessionLocal()
    task_started_clock = perf_counter()
    try:
        task = db.scalar(
            select(Task)
            .where(Task.id == task_id)
            .options(selectinload(Task.issue), selectinload(Task.repository), selectinload(Task.artifacts), selectinload(Task.attempts))
        )
        if task is None:
            return
        if task.started_at is None:
            task.started_at = _utcnow()
        task.finished_at = None
        db.add(task)
        db.commit()

        raw_webhook = _get_raw_webhook(task)
        installation_id = raw_webhook["installation"]["id"]
        auth_service = GitHubAuthService()
        installation_token = await auth_service.get_installation_token(installation_id)
        workspace_root = ensure_workspace_root()

        transition_task(db, task, TaskStatus.sandbox_ready)
        db.commit()

        temp_dir_obj = tempfile.TemporaryDirectory(dir=workspace_root, ignore_cleanup_errors=True)
        try:
            temp_dir = temp_dir_obj.name
            repo_path = Path(temp_dir) / task.repository.name
            authenticated_clone_url = build_clone_url(task.repository.owner, task.repository.name, installation_token)
            clone_repo(authenticated_clone_url, repo_path)
            set_remote_url(repo_path, "origin", authenticated_clone_url)
            branch_name = build_branch_name(task.issue, task.id)
            base_commit = checkout_new_branch(repo_path, branch_name, task.repository.default_branch)
            task.branch_name = branch_name
            task.base_commit = base_commit
            db.add(task)
            db.commit()

            repo_config = load_repo_config(repo_path)
            sandbox = SandboxRunner()
            install_started = perf_counter()
            install_result = sandbox.install_dependencies(repo_path, repo_config.install_command)
            task.install_duration_ms = _elapsed_ms(install_started)
            db.add(
                TaskArtifact(
                    task_id=task.id,
                    artifact_type=TaskArtifactType.install_log,
                    content={
                        "command": repo_config.install_command,
                        "exit_code": install_result.exit_code,
                        "stdout": install_result.stdout,
                        "stderr": install_result.stderr,
                    },
                )
            )
            db.commit()
            if install_result.exit_code != 0:
                raise RuntimeError(
                    f"install_failed: stdout={install_result.stdout.strip()} stderr={install_result.stderr.strip()}"
                )

            agent = AgentLoop()
            transition_task(db, task, TaskStatus.patching)
            db.commit()

            successful_result = None
            successful_attempt_index = None
            successful_diff_text = ""
            for attempt_index in range(1, settings.max_attempts + 1):
                attempt_started_at = _utcnow()
                attempt_started_clock = perf_counter()
                task.attempt_count = attempt_index
                db.add(task)
                db.commit()

                toolbox = AgentToolbox(
                    repo_path=repo_path,
                    repo_config=repo_config,
                    issue_context=_build_issue_context(task),
                    sandbox_runner=sandbox,
                )
                result = None
                tool_name = None
                tool_arguments = None
                error_text = None
                raw_response = None
                model_started = perf_counter()

                try:
                    result = agent.run(toolbox)
                    model_duration_ms = _elapsed_ms(model_started)
                    task.model_call_count += result.model_call_count
                    task.tool_call_count += result.tool_call_count
                    diff_before_patch_text = diff(repo_path)
                    if result.patch_text and not diff_before_patch_text.strip():
                        toolbox.apply_patch(result.patch_text)

                    diff_text = diff(repo_path)
                    enforce_patch_limits(
                        diff_text,
                        repo_config.allowed_paths,
                        repo_config.blocked_paths,
                        repo_config.max_changed_files,
                        repo_config.max_diff_lines,
                    )

                    transition_task(db, task, TaskStatus.testing)
                    test_started = perf_counter()
                    test_result = sandbox.run_tests(repo_path, repo_config.test_command)
                    task.patch_duration_ms = (task.patch_duration_ms or 0) + model_duration_ms
                    test_duration_ms = _elapsed_ms(test_started)
                    task.test_duration_ms = (task.test_duration_ms or 0) + test_duration_ms
                    _record_attempt(
                        db,
                        task,
                        attempt_index,
                        TaskResultStatus.success if test_result.exit_code == 0 else TaskResultStatus.failed,
                        diff_text,
                        model_summary=result.summary,
                        patch_text=result.patch_text,
                        test_command=repo_config.test_command,
                        test_exit_code=test_result.exit_code,
                        test_stdout=test_result.stdout,
                        test_stderr=test_result.stderr,
                        started_at=attempt_started_at,
                        finished_at=_utcnow(),
                        duration_ms=_elapsed_ms(attempt_started_clock),
                        model_duration_ms=model_duration_ms,
                        tool_call_count=result.tool_call_count,
                    )
                    db.commit()

                    if test_result.exit_code == 0:
                        transition_task(db, task, TaskStatus.ready_for_pr)
                        successful_result = result
                        successful_attempt_index = attempt_index
                        successful_diff_text = diff_text
                        break

                    if attempt_index < settings.max_attempts:
                        transition_task(db, task, TaskStatus.retrying)
                        db.commit()
                        transition_task(db, task, TaskStatus.patching)
                        db.commit()
                    else:
                        mark_task_failed(db, task, "tests_failed", {"attempts": attempt_index})
                        db.commit()
                except Exception as exc:
                    diff_text = diff(repo_path)
                    error_text = str(exc)
                    model_duration_ms = _elapsed_ms(model_started)
                    task.patch_duration_ms = (task.patch_duration_ms or 0) + model_duration_ms
                    test_command = None
                    test_exit_code = None
                    test_stdout = None
                    test_stderr = None
                    if isinstance(exc, ToolExecutionError):
                        tool_name = exc.tool_name
                        tool_arguments = exc.arguments
                        diff_text = exc.diff_text
                    if isinstance(exc, AgentResponseParseError):
                        raw_response = exc.raw_response
                        tool_name = "final_response"
                    if diff_text.strip():
                        test_started = perf_counter()
                        test_result = sandbox.run_tests(repo_path, repo_config.test_command)
                        test_command = repo_config.test_command
                        test_exit_code = test_result.exit_code
                        test_stdout = test_result.stdout
                        test_stderr = test_result.stderr
                        test_duration_ms = _elapsed_ms(test_started)
                        task.test_duration_ms = (task.test_duration_ms or 0) + test_duration_ms
                    _record_attempt(
                        db,
                        task,
                        attempt_index,
                        TaskResultStatus.failed,
                        diff_text,
                        model_summary=result.summary if result is not None else None,
                        patch_text=result.patch_text if result is not None else None,
                        test_command=test_command,
                        test_exit_code=test_exit_code,
                        test_stdout=test_stdout,
                        test_stderr=test_stderr,
                        started_at=attempt_started_at,
                        finished_at=_utcnow(),
                        duration_ms=_elapsed_ms(attempt_started_clock),
                        model_duration_ms=model_duration_ms,
                        tool_call_count=result.tool_call_count if result is not None else 0,
                        error_text=error_text,
                        tool_name=tool_name,
                        tool_arguments=tool_arguments,
                        raw_response=raw_response,
                    )
                    db.commit()
                    if attempt_index < settings.max_attempts:
                        transition_task(db, task, TaskStatus.retrying)
                        db.commit()
                        transition_task(db, task, TaskStatus.patching)
                        db.commit()
                    else:
                        mark_task_failed(
                            db,
                            task,
                            "patch_failed",
                            {
                                "attempts": attempt_index,
                                "error": error_text,
                                "tool_name": tool_name,
                                "tool_arguments": tool_arguments,
                                "raw_response": raw_response,
                            },
                        )
                        db.commit()

            should_comment_on_issue = task.issue.github_issue_number > 0

            if successful_result is None:
                if should_comment_on_issue:
                    issue_service = GitHubIssueService(installation_token)
                    await issue_service.create_comment(
                        task.repository.owner,
                        task.repository.name,
                        task.issue.github_issue_number,
                        format_issue_failure_comment(task.failure_reason["reason"], task.attempt_count),
                    )
                task.finished_at = _utcnow()
                task.total_duration_ms = _elapsed_ms(task_started_clock)
                db.commit()
                return

            try:
                changed_files = parse_diff_stats(successful_diff_text).changed_files
                commit_message = f"fix: resolve issue #{task.issue.github_issue_number}"
                head_commit = commit_all(repo_path, commit_message, include_paths=changed_files)
                task.head_commit = head_commit
                db.add(task)
                db.commit()

                set_remote_url(repo_path, "origin", authenticated_clone_url)
                push_branch(repo_path, branch_name)

                summary_map = ensure_mapping(successful_result.summary)
                pr_body_summary_map = ensure_mapping(successful_result.pr_body_summary)
                root_cause = pr_body_summary_map.get("root_cause") or summary_map.get("root_cause") or "Issue-specific bug"
                changes = pr_body_summary_map.get("changes") or summary_map.get("patch_plan") or ["Minimal targeted patch"]
                pr_body = format_pr_body(
                    issue_number=task.issue.github_issue_number,
                    root_cause=root_cause,
                    changes=changes,
                    validation_summary="pytest passed",
                )
                db.add(TaskArtifact(task_id=task.id, artifact_type=TaskArtifactType.pr_body, content={"body": pr_body}))
                db.commit()

                pr_service = GitHubPullRequestService(installation_token)
                pr = await pr_service.create_pull_request(
                    owner=task.repository.owner,
                    repo=task.repository.name,
                    title=successful_result.pr_title,
                    body=pr_body,
                    head=branch_name,
                    base=task.repository.default_branch,
                )
                task.pr_number = pr["number"]
                transition_task(db, task, TaskStatus.pr_opened)
                db.commit()

                if _is_conflict_resolution_task(task):
                    integration_request = ensure_mapping(get_artifact_content(task, TaskArtifactType.integration_request))
                    source_task_ids = integration_request.get("source_task_ids") or []
                    source_pr_numbers = integration_request.get("source_pr_numbers") or []
                    if source_task_ids:
                        source_task = db.get(Task, source_task_ids[0])
                        if source_task is not None:
                            db.add(
                                TaskArtifact(
                                    task_id=source_task.id,
                                    artifact_type=TaskArtifactType.resolution_link,
                                    content={
                                        "resolved_task_id": task.id,
                                        "resolved_pr_number": pr["number"],
                                        "resolved_pr_url": pr["html_url"],
                                    },
                                )
                            )
                            db.add(
                                TaskArtifact(
                                    task_id=task.id,
                                    artifact_type=TaskArtifactType.resolution_link,
                                    content={
                                        "source_task_id": source_task.id,
                                        "source_pr_number": source_pr_numbers[0] if source_pr_numbers else source_task.pr_number,
                                    },
                                )
                            )
                            db.commit()
                            issue_service = GitHubIssueService(installation_token)
                            source_pr_number = source_pr_numbers[0] if source_pr_numbers else source_task.pr_number
                            if source_pr_number:
                                await issue_service.create_comment(
                                    task.repository.owner,
                                    task.repository.name,
                                    source_pr_number,
                                    (
                                        "micro-swe-agent generated a conflict-resolved follow-up PR.\n\n"
                                        f"- Original PR: #{source_pr_number}\n"
                                        f"- Replacement PR: {pr['html_url']}\n"
                                        "- Please review and merge the replacement PR instead of this conflicted one.\n"
                                    ),
                                )

                if should_comment_on_issue:
                    issue_service = GitHubIssueService(installation_token)
                    await issue_service.create_comment(
                        task.repository.owner,
                        task.repository.name,
                        task.issue.github_issue_number,
                        format_issue_success_comment(pr["html_url"], successful_attempt_index or task.attempt_count, True),
                    )
                    await issue_service.add_labels(task.repository.owner, task.repository.name, pr["number"], [settings.pr_review_label])
                transition_task(db, task, TaskStatus.done)
                task.finished_at = _utcnow()
                task.total_duration_ms = _elapsed_ms(task_started_clock)
                db.commit()
                return
            except Exception as exc:
                mark_task_failed(
                    db,
                    task,
                    "pr_failed",
                    {
                        "attempts": successful_attempt_index,
                        "error": str(exc),
                        "branch_name": task.branch_name,
                        "head_commit": task.head_commit,
                    },
                )
                task.finished_at = _utcnow()
                task.total_duration_ms = _elapsed_ms(task_started_clock)
                db.commit()
        finally:
            temp_dir_obj.cleanup()
    except Exception as exc:
        logger.exception("task processing failed", extra={"task_id": task_id})
        task = db.get(Task, task_id)
        if task is not None:
            mark_task_failed(db, task, "worker_exception", {"error": str(exc)})
            task.finished_at = _utcnow()
            task.total_duration_ms = _elapsed_ms(task_started_clock)
            db.commit()
    finally:
        db.close()


async def poll_forever() -> None:
    settings = get_settings()
    while True:
        db = SessionLocal()
        try:
            task = db.scalar(
                select(Task)
                .where(Task.status == TaskStatus.triaged)
                .order_by(Task.created_at.asc())
                .options(selectinload(Task.issue), selectinload(Task.repository), selectinload(Task.artifacts))
            )
            if task is not None:
                await process_task(task.id)
        finally:
            db.close()
        await asyncio.sleep(settings.worker_poll_interval)


def main() -> None:
    asyncio.run(poll_forever())


if __name__ == "__main__":
    main()
