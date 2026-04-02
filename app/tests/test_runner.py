import subprocess
from pathlib import Path

from app.core.config import get_settings
from app.services.sandbox.runner import SandboxRunner


def test_install_dependencies_bootstraps_repo_local_venv(workspace_tmp_dir, monkeypatch) -> None:
    repo_path = workspace_tmp_dir / "repo"
    repo_path.mkdir()
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        shell_command = command[-1]
        if "python -m venv .venv" in shell_command:
            (repo_path / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(command, 0, stdout="install ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = SandboxRunner()
    result = runner.install_dependencies(repo_path, "pip install -r requirements.txt")

    assert result.exit_code == 0
    assert (repo_path / ".venv").exists()
    shell_command = commands[0][-1]
    assert "cd /workspace" in shell_command
    assert "python -m venv .venv" in shell_command
    assert ". .venv/bin/activate" in shell_command
    assert "python -m pip install --upgrade pip" in shell_command
    assert shell_command.endswith("pip install -r requirements.txt")


def test_run_tests_uses_repo_local_venv(workspace_tmp_dir, monkeypatch) -> None:
    repo_path = workspace_tmp_dir / "repo"
    (repo_path / ".venv" / "bin").mkdir(parents=True)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="tests ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = SandboxRunner()
    result = runner.run_tests(repo_path, "python -m pytest -q")

    assert result.exit_code == 0
    shell_command = commands[0][-1]
    assert "python -m venv .venv" not in shell_command
    assert ". .venv/bin/activate" in shell_command
    assert shell_command.endswith("python -m pytest -q")


def test_install_then_run_tests_reuses_repo_local_venv(workspace_tmp_dir, monkeypatch) -> None:
    repo_path = workspace_tmp_dir / "repo"
    repo_path.mkdir()

    def fake_run(command, **kwargs):
        shell_command = command[-1]
        marker_path = repo_path / ".venv" / "pytest-installed"
        if "python -m venv .venv" in shell_command:
            (repo_path / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
            marker_path.write_text("yes", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="install ok", stderr="")
        if ". .venv/bin/activate" in shell_command and "python -m pytest -q" in shell_command:
            if marker_path.exists():
                return subprocess.CompletedProcess(command, 0, stdout="tests ok", stderr="")
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="/usr/local/bin/python: No module named pytest")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = SandboxRunner()
    install_result = runner.install_dependencies(repo_path, "pip install pytest")
    test_result = runner.run_tests(repo_path, "python -m pytest -q")

    assert install_result.exit_code == 0
    assert (repo_path / ".venv").exists()
    assert test_result.exit_code == 0


def test_run_maps_container_workspace_to_host_path(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("DOCKER_BIND_CONTAINER_ROOT", "/app")
    monkeypatch.setenv("DOCKER_BIND_HOST_ROOT", "/Users/example/project")
    get_settings.cache_clear()

    runner = SandboxRunner()
    result = runner.run(Path("/app/.workspaces/task/repo"), "python -m pytest -q")

    assert result.exit_code == 0
    assert commands
    volume_index = commands[0].index("-v") + 1
    assert commands[0][volume_index] == "/Users/example/project/.workspaces/task/repo:/workspace"
    get_settings.cache_clear()
