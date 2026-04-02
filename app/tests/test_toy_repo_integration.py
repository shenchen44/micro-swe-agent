import shutil
import subprocess
import sys
from pathlib import Path

from app.services.comments.formatter import format_pr_body
from app.services.openai.tools import AgentToolbox
from app.services.sandbox.repo_config import load_repo_config


class LocalRunner:
    def run_tests(self, repo_path: Path, test_command: str):
        process = subprocess.run(
            [sys.executable, *test_command.split()[1:]],
            cwd=repo_path,
            text=True,
            capture_output=True,
            check=False,
        )
        return type("Result", (), {"exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr})()


def test_toy_repo_minimal_closure(workspace_tmp_dir) -> None:
    fixture_repo = Path(__file__).parent / "fixtures" / "toy_repo"
    repo_path = workspace_tmp_dir / "toy_repo"
    shutil.copytree(fixture_repo, repo_path)
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    repo_config = load_repo_config(repo_path)
    toolbox = AgentToolbox(
        repo_path=repo_path,
        repo_config=repo_config,
        issue_context={
            "title": "Handle None display name",
            "body": "Calling format_display_name(None) should not crash.",
            "issue_number": 1,
        },
        sandbox_runner=LocalRunner(),
    )
    new_content = """def format_display_name(name: str | None) -> str:
    if name is None:
        return ""
    return name.strip().title()
"""
    write_result = toolbox.write_file("app/display.py", new_content)
    assert write_result["files_changed_count"] == 1
    test_result = toolbox.run_tests()
    assert test_result["exit_code"] == 0
    pr_body = format_pr_body(
        issue_number=1,
        root_cause="format_display_name assumed name was always a string.",
        changes=["Return an empty string when name is None", "Preserve existing formatting behavior for strings"],
        validation_summary="toy repo pytest passed",
    )
    assert "Fixes #1" in pr_body
