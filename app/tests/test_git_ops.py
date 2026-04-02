import subprocess
from pathlib import Path

import pytest

from app.services.sandbox.git_ops import commit_all, push_branch


def test_push_branch_surfaces_stderr(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "push", "-u", "origin", "agent/test"],
            output="",
            stderr="remote: write access to repository not granted\nfatal: Authentication failed",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="git_push_failed: remote: write access to repository not granted"):
        push_branch(Path("/tmp/repo"), "agent/test")


def test_commit_all_only_stages_requested_source_files(workspace_tmp_dir) -> None:
    repo_path = workspace_tmp_dir / "repo"
    (repo_path / "app").mkdir(parents=True)
    (repo_path / "tests").mkdir(parents=True)
    (repo_path / "app" / "main.py").write_text("def answer():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_path, check=True, capture_output=True, text=True)

    (repo_path / "app" / "main.py").write_text("def answer():\n    return 2\n", encoding="utf-8")
    (repo_path / ".venv" / "bin").mkdir(parents=True)
    (repo_path / ".venv" / "bin" / "activate").write_text("activate", encoding="utf-8")
    (repo_path / "__pycache__").mkdir(parents=True)
    (repo_path / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"pyc")
    (repo_path / "tests" / "__pycache__").mkdir(parents=True)
    (repo_path / "tests" / "__pycache__" / "test_main.cpython-311.pyc").write_bytes(b"pyc")
    (repo_path / ".pytest_cache").mkdir(parents=True)
    (repo_path / ".pytest_cache" / "README.md").write_text("cache", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True, text=True)

    head = commit_all(
        repo_path,
        "fix: update answer",
        include_paths=[
            "app/main.py",
            ".venv/bin/activate",
            "__pycache__/main.cpython-311.pyc",
            "tests/__pycache__/test_main.cpython-311.pyc",
            ".pytest_cache/README.md",
        ],
    )

    assert head
    committed_files = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert committed_files == ["app/main.py"]
