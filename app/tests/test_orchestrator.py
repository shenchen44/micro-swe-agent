from app.db.models.issue import Issue
from app.services.task_runner.orchestrator import build_branch_name


def test_build_branch_name_is_unique_per_task_id() -> None:
    issue = Issue(
        repository_id=1,
        github_issue_number=42,
        github_issue_id=4200,
        title="Handle ZeroDivisionError in safe_divide",
        body="body",
        labels=[],
        state="open",
        html_url="https://example.com/issues/42",
    )

    branch_a = build_branch_name(issue, "12345678-aaaa-bbbb-cccc-111111111111")
    branch_b = build_branch_name(issue, "87654321-aaaa-bbbb-cccc-222222222222")

    assert branch_a != branch_b
    assert branch_a.startswith("agent/issue-42-handle-zerodivisionerror-in-safe_divide")
    assert branch_a.endswith("-12345678")
    assert branch_b.endswith("87654321")


def test_build_branch_name_is_readable_and_reasonable_length() -> None:
    issue = Issue(
        repository_id=1,
        github_issue_number=7,
        github_issue_id=700,
        title="This title should still produce a readable branch name even when it is very long",
        body="body",
        labels=[],
        state="open",
        html_url="https://example.com/issues/7",
    )

    branch_name = build_branch_name(issue, "abcdef12-aaaa-bbbb-cccc-333333333333")

    assert branch_name.startswith("agent/issue-7-")
    assert branch_name.endswith("-abcdef12")
    assert len(branch_name) <= 70
