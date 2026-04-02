import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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


def _init_git_repo(repo_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_path, check=True, capture_output=True, text=True)


def _make_toolbox(workspace_tmp_dir: Path, *, add_blocked_file: bool = False) -> tuple[Path, AgentToolbox]:
    fixture_repo = Path(__file__).parent / "fixtures" / "toy_repo"
    repo_path = workspace_tmp_dir / "toy_repo"
    shutil.copytree(fixture_repo, repo_path)
    if add_blocked_file:
        blocked_file = repo_path / ".github" / "workflows" / "test.yml"
        blocked_file.parent.mkdir(parents=True, exist_ok=True)
        blocked_file.write_text("name: test\n", encoding="utf-8")
    _init_git_repo(repo_path)
    repo_config = load_repo_config(repo_path)
    toolbox = AgentToolbox(
        repo_path=repo_path,
        repo_config=repo_config,
        issue_context={"title": "test", "body": "test", "issue_number": 1},
        sandbox_runner=LocalRunner(),
    )
    return repo_path, toolbox


def test_write_file_success(workspace_tmp_dir) -> None:
    repo_path, toolbox = _make_toolbox(workspace_tmp_dir)
    new_content = """def format_display_name(name: str | None) -> str:
    if name is None:
        return ""
    return name.strip().title()
"""
    result = toolbox.write_file("app/display.py", new_content)
    assert result["files_changed_count"] == 1
    assert result["diff_line_count"] >= 2
    assert "return \"\"" in (repo_path / "app" / "display.py").read_text(encoding="utf-8")


def test_write_file_blocked_path_fails(workspace_tmp_dir) -> None:
    _, toolbox = _make_toolbox(workspace_tmp_dir, add_blocked_file=True)
    with pytest.raises(ValueError, match=r"path_not_allowed:\.github/workflows/test.yml"):
        toolbox.write_file(".github/workflows/test.yml", "name: changed\n")


def test_write_file_diff_limit_failure_restores_original(workspace_tmp_dir) -> None:
    repo_path, toolbox = _make_toolbox(workspace_tmp_dir)
    toolbox.repo_config.max_diff_lines = 1
    original_content = (repo_path / "app" / "display.py").read_text(encoding="utf-8")
    new_content = """def format_display_name(name: str | None) -> str:
    if name is None:
        return ""
    cleaned = name.strip()
    return cleaned.title()
"""
    with pytest.raises(ValueError, match="diff_lines_limit_exceeded"):
        toolbox.write_file("app/display.py", new_content)
    assert (repo_path / "app" / "display.py").read_text(encoding="utf-8") == original_content
    assert toolbox.git_diff()["diff"] == ""


def test_apply_patch_failure_exposes_git_error(workspace_tmp_dir) -> None:
    _, toolbox = _make_toolbox(workspace_tmp_dir)
    with pytest.raises(RuntimeError, match="git_apply_failed:"):
        toolbox.apply_patch("not a valid patch")


def test_run_tests_tolerates_optional_runner_argument(workspace_tmp_dir) -> None:
    _, toolbox = _make_toolbox(workspace_tmp_dir)
    result = toolbox.run_tests(runner="python -m pytest")
    assert isinstance(result["exit_code"], int)
