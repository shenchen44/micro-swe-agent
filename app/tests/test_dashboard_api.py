from app.db.models.issue import Issue
from app.db.models.repository import Repository
from app.db.models.task import Task, TaskArtifact, TaskArtifactType, TaskStatus


def _build_pr_backed_task(db_session, *, repo_id: int, issue_number: int, pr_number: int, installation_id: int) -> Task:
    issue = Issue(
        repository_id=repo_id,
        github_issue_number=issue_number,
        github_issue_id=issue_number * 1000,
        title=f"Issue {issue_number}",
        body="body",
        labels=[{"name": "bug"}],
        state="open",
        html_url=f"https://github.com/octo/demo-repo/issues/{issue_number}",
    )
    db_session.add(issue)
    db_session.flush()
    task = Task(repository_id=repo_id, issue_id=issue.id, status=TaskStatus.done, attempt_count=1, pr_number=pr_number, branch_name=f"agent/{issue_number}")
    db_session.add(task)
    db_session.flush()
    db_session.add(TaskArtifact(task_id=task.id, artifact_type=TaskArtifactType.raw_webhook, content={"installation": {"id": installation_id}}))
    db_session.add(TaskArtifact(task_id=task.id, artifact_type=TaskArtifactType.model_response, content={"summary": {"root_cause": "cause", "patch_plan": ["change a", "change b"]}}))
    db_session.add(TaskArtifact(task_id=task.id, artifact_type=TaskArtifactType.diff, content={"diff": f"diff --git a/app.py b/app.py\n+task {task.id}\n"}))
    db_session.add(TaskArtifact(task_id=task.id, artifact_type=TaskArtifactType.pr_body, content={"body": "pr body"}))
    db_session.commit()
    db_session.refresh(task)
    return task


def test_dashboard_lists_only_open_pr_items(client, db_session, monkeypatch) -> None:
    repository = Repository(github_repo_id=123, owner="octo", name="demo-repo", default_branch="main", is_active=True)
    db_session.add(repository)
    db_session.flush()
    open_task = _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=7, pr_number=3, installation_id=999)
    _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=8, pr_number=4, installation_id=999)

    class FakeAuthService:
        async def get_installation_token(self, installation_id: int) -> str:
            return "token"

    class FakePullRequestService:
        def __init__(self, token: str) -> None:
            self.token = token

        async def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict:
            return {"state": "open" if pull_number == 3 else "closed"}

    monkeypatch.setattr("app.api.routes.dashboard.GitHubAuthService", FakeAuthService)
    monkeypatch.setattr("app.api.routes.dashboard.GitHubPullRequestService", FakePullRequestService)

    response = client.get("/dashboard/prs")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["task_id"] == open_task.id
    assert payload[0]["pr_number"] == 3
    assert payload[0]["root_cause"] == "cause"
    assert "change a" in payload[0]["changes"]


def test_dashboard_change_summary_falls_back_to_pr_body(client, db_session, monkeypatch) -> None:
    repository = Repository(github_repo_id=123, owner="octo", name="demo-repo", default_branch="main", is_active=True)
    db_session.add(repository)
    db_session.flush()
    task = _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=7, pr_number=3, installation_id=999)
    model_artifact = next(
        artifact for artifact in task.artifacts if artifact.artifact_type == TaskArtifactType.model_response
    )
    model_artifact.content = {"summary": "plain string summary"}
    pr_body_artifact = next(
        artifact for artifact in task.artifacts if artifact.artifact_type == TaskArtifactType.pr_body
    )
    pr_body_artifact.content = {
        "body": "## Summary\nSomething\n\n## Changes\n- Keep API stable\n- Add None handling\n\n## Validation\n- pytest -q"
    }
    db_session.add(model_artifact)
    db_session.add(pr_body_artifact)
    db_session.commit()

    class FakeAuthService:
        async def get_installation_token(self, installation_id: int) -> str:
            return "token"

    class FakePullRequestService:
        def __init__(self, token: str) -> None:
            self.token = token

        async def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict:
            return {"state": "open"}

    monkeypatch.setattr("app.api.routes.dashboard.GitHubAuthService", FakeAuthService)
    monkeypatch.setattr("app.api.routes.dashboard.GitHubPullRequestService", FakePullRequestService)

    response = client.get("/dashboard/prs")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["task_id"] == task.id
    assert payload[0]["changes"] == ["Keep API stable", "Add None handling"]


def test_dashboard_root_cause_falls_back_to_pr_body_and_diff_summary(client, db_session, monkeypatch) -> None:
    repository = Repository(github_repo_id=123, owner="octo", name="demo-repo", default_branch="main", is_active=True)
    db_session.add(repository)
    db_session.flush()
    task = _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=9, pr_number=5, installation_id=999)

    model_artifact = next(
        artifact for artifact in task.artifacts if artifact.artifact_type == TaskArtifactType.model_response
    )
    model_artifact.content = {"summary": "plain string summary"}
    pr_body_artifact = next(
        artifact for artifact in task.artifacts if artifact.artifact_type == TaskArtifactType.pr_body
    )
    pr_body_artifact.content = {
        "body": "## Root Cause\nThe function did not handle None inputs before attempting division.\n\n## Validation\n- pytest -q"
    }
    diff_artifact = next(
        artifact for artifact in task.artifacts if artifact.artifact_type == TaskArtifactType.diff
    )
    diff_artifact.content = {
        "diff": (
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,2 +1,4 @@\n"
            "-    return a / b\n"
            "+    if a is None or b is None:\n"
            "+        return None\n"
            "+    return a / b\n"
            "diff --git a/tests/test_app.py b/tests/test_app.py\n"
            "--- a/tests/test_app.py\n"
            "+++ b/tests/test_app.py\n"
            "@@ -1,2 +1,5 @@\n"
            "+def test_safe_divide_none():\n"
            "+    assert safe_divide(None, 2) is None\n"
        )
    }
    db_session.add(model_artifact)
    db_session.add(pr_body_artifact)
    db_session.add(diff_artifact)
    db_session.commit()

    class FakeAuthService:
        async def get_installation_token(self, installation_id: int) -> str:
            return "token"

    class FakePullRequestService:
        def __init__(self, token: str) -> None:
            self.token = token

        async def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict:
            return {"state": "open"}

    monkeypatch.setattr("app.api.routes.dashboard.GitHubAuthService", FakeAuthService)
    monkeypatch.setattr("app.api.routes.dashboard.GitHubPullRequestService", FakePullRequestService)

    response = client.get("/dashboard/prs")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["task_id"] == task.id
    assert payload[0]["root_cause"] == "The function did not handle None inputs before attempting division."
    assert payload[0]["changes"] == [
        "Updated app.py",
        "Updated tests in tests/test_app.py",
        "Added handling for None-like edge cases",
        "Kept the patch small at about 6 changed diff lines",
    ]


def test_dashboard_ignores_generic_summary_placeholders(client, db_session, monkeypatch) -> None:
    repository = Repository(github_repo_id=123, owner="octo", name="demo-repo", default_branch="main", is_active=True)
    db_session.add(repository)
    db_session.flush()
    task = _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=10, pr_number=6, installation_id=999)

    model_artifact = next(
        artifact for artifact in task.artifacts if artifact.artifact_type == TaskArtifactType.model_response
    )
    model_artifact.content = {"summary": {"root_cause": "Issue-specific bug", "patch_plan": ["Minimal targeted patch"]}}
    diff_artifact = next(
        artifact for artifact in task.artifacts if artifact.artifact_type == TaskArtifactType.diff
    )
    diff_artifact.content = {
        "diff": (
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,2 +1,4 @@\n"
            "-    return a / b\n"
            "+    if a is None or b is None:\n"
            "+        return None\n"
            "+    return a / b\n"
        )
    }
    db_session.add(model_artifact)
    db_session.add(diff_artifact)
    db_session.commit()

    class FakeAuthService:
        async def get_installation_token(self, installation_id: int) -> str:
            return "token"

    class FakePullRequestService:
        def __init__(self, token: str) -> None:
            self.token = token

        async def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict:
            return {"state": "open"}

    monkeypatch.setattr("app.api.routes.dashboard.GitHubAuthService", FakeAuthService)
    monkeypatch.setattr("app.api.routes.dashboard.GitHubPullRequestService", FakePullRequestService)

    response = client.get("/dashboard/prs")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["task_id"] == task.id
    assert payload[0]["root_cause"] == "Adjusted behavior in app.py and validated the fix with a focused patch."
    assert payload[0]["changes"] == [
        "Updated app.py",
        "Added handling for None-like edge cases",
        "Kept the patch small at about 4 changed diff lines",
    ]


def test_dashboard_ignores_generic_pr_body_changes(client, db_session, monkeypatch) -> None:
    repository = Repository(github_repo_id=123, owner="octo", name="demo-repo", default_branch="main", is_active=True)
    db_session.add(repository)
    db_session.flush()
    task = _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=11, pr_number=7, installation_id=999)

    model_artifact = next(
        artifact for artifact in task.artifacts if artifact.artifact_type == TaskArtifactType.model_response
    )
    model_artifact.content = {"summary": {"root_cause": "Issue-specific bug", "patch_plan": ["Minimal targeted patch"]}}
    pr_body_artifact = next(
        artifact for artifact in task.artifacts if artifact.artifact_type == TaskArtifactType.pr_body
    )
    pr_body_artifact.content = {
        "body": (
            "## Summary\nFixes #11 by applying a minimal patch.\n\n"
            "## Root Cause\nIssue-specific bug\n\n"
            "## Changes\n- Minimal targeted patch\n"
        )
    }
    diff_artifact = next(
        artifact for artifact in task.artifacts if artifact.artifact_type == TaskArtifactType.diff
    )
    diff_artifact.content = {
        "diff": (
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,2 +1,4 @@\n"
            "-    return a / b\n"
            "+    if a is None or b is None:\n"
            "+        return None\n"
            "+    return a / b\n"
            "diff --git a/tests/test_app.py b/tests/test_app.py\n"
            "--- a/tests/test_app.py\n"
            "+++ b/tests/test_app.py\n"
            "@@ -1,2 +1,5 @@\n"
            "+def test_safe_divide_none():\n"
            "+    assert safe_divide(None, 2) is None\n"
        )
    }
    db_session.add(model_artifact)
    db_session.add(pr_body_artifact)
    db_session.add(diff_artifact)
    db_session.commit()

    class FakeAuthService:
        async def get_installation_token(self, installation_id: int) -> str:
            return "token"

    class FakePullRequestService:
        def __init__(self, token: str) -> None:
            self.token = token

        async def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict:
            return {"state": "open"}

    monkeypatch.setattr("app.api.routes.dashboard.GitHubAuthService", FakeAuthService)
    monkeypatch.setattr("app.api.routes.dashboard.GitHubPullRequestService", FakePullRequestService)

    response = client.get("/dashboard/prs")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["task_id"] == task.id
    assert "Minimal targeted patch" not in payload[0]["changes"]
    assert payload[0]["changes"] == [
        "Updated app.py",
        "Updated tests in tests/test_app.py",
        "Added handling for None-like edge cases",
        "Kept the patch small at about 6 changed diff lines",
    ]


def test_dashboard_surfaces_merge_conflict_status(client, db_session, monkeypatch) -> None:
    repository = Repository(github_repo_id=123, owner="octo", name="demo-repo", default_branch="main", is_active=True)
    db_session.add(repository)
    db_session.flush()
    task = _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=12, pr_number=8, installation_id=999)

    class FakeAuthService:
        async def get_installation_token(self, installation_id: int) -> str:
            return "token"

    class FakePullRequestService:
        def __init__(self, token: str) -> None:
            self.token = token

        async def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict:
            return {"state": "open", "mergeable": False, "mergeable_state": "dirty"}

    monkeypatch.setattr("app.api.routes.dashboard.GitHubAuthService", FakeAuthService)
    monkeypatch.setattr("app.api.routes.dashboard.GitHubPullRequestService", FakePullRequestService)

    response = client.get("/dashboard/prs")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["task_id"] == task.id
    assert payload[0]["merge_status"] == "conflicting"
    assert payload[0]["merge_status_label"] == "Conflict"
    assert payload[0]["merge_conflict"] is True


def test_dashboard_creates_integration_task(client, db_session) -> None:
    repository = Repository(github_repo_id=123, owner="octo", name="demo-repo", default_branch="main", is_active=True)
    db_session.add(repository)
    db_session.flush()
    task_a = _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=7, pr_number=3, installation_id=999)
    task_b = _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=8, pr_number=4, installation_id=999)

    response = client.post("/dashboard/integrations", json={"task_ids": [task_a.id, task_b.id], "guidance": "Prefer task A naming."})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "triaged"

    integration_task = db_session.get(Task, payload["id"])
    assert integration_task is not None
    assert integration_task.issue.github_issue_number == 0
    integration_artifact = next(
        artifact for artifact in integration_task.artifacts if artifact.artifact_type == TaskArtifactType.integration_request
    )
    assert integration_artifact.content["source_task_ids"] == [task_a.id, task_b.id]
    assert integration_artifact.content["mode"] == "integration"
    assert integration_artifact.content["base_branch"] == "main"
    assert len(integration_artifact.content["source_prs"]) == 2
    assert integration_artifact.content["source_prs"][0]["pr_number"] == 3


def test_dashboard_merge_pr_endpoint(client, db_session, monkeypatch) -> None:
    repository = Repository(github_repo_id=123, owner="octo", name="demo-repo", default_branch="main", is_active=True)
    db_session.add(repository)
    db_session.flush()
    task = _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=7, pr_number=3, installation_id=999)

    class FakeAuthService:
        async def get_installation_token(self, installation_id: int) -> str:
            assert installation_id == 999
            return "token"

    class FakePullRequestService:
        def __init__(self, token: str) -> None:
            self.token = token

        async def merge_pull_request(self, owner: str, repo: str, pull_number: int, merge_method: str = "squash") -> dict:
            assert owner == "octo"
            assert repo == "demo-repo"
            assert pull_number == 3
            return {"merged": True, "sha": "abc123"}

    monkeypatch.setattr("app.api.routes.dashboard.GitHubAuthService", FakeAuthService)
    monkeypatch.setattr("app.api.routes.dashboard.GitHubPullRequestService", FakePullRequestService)

    response = client.post(f"/dashboard/prs/{task.id}/merge")
    assert response.status_code == 200
    assert response.json()["merged"] is True


def test_dashboard_creates_conflict_resolution_task(client, db_session) -> None:
    repository = Repository(github_repo_id=123, owner="octo", name="demo-repo", default_branch="main", is_active=True)
    db_session.add(repository)
    db_session.flush()
    task = _build_pr_backed_task(db_session, repo_id=repository.id, issue_number=13, pr_number=9, installation_id=999)

    response = client.post(f"/dashboard/prs/{task.id}/resolve-conflict", json={"guidance": "Preserve the current API surface."})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "triaged"

    resolution_task = db_session.get(Task, payload["id"])
    assert resolution_task is not None
    artifact = next(
        item for item in resolution_task.artifacts if item.artifact_type == TaskArtifactType.integration_request
    )
    assert artifact.content["mode"] == "conflict_resolution"
    assert artifact.content["source_task_ids"] == [task.id]
    assert artifact.content["guidance"] == "Preserve the current API surface."


def test_dashboard_page_renders(client) -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "PR Review Workspace" in response.text
