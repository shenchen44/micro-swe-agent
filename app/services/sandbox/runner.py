import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings


@dataclass(slots=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


class SandboxRunner:
    """Runs install and test commands inside a disposable Docker container."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def _venv_activate_prefix(self) -> str:
        return ". .venv/bin/activate"

    def _build_shell_command(self, command: str, *, create_venv: bool) -> str:
        steps = ["cd /workspace"]
        if create_venv:
            steps.append("python -m venv .venv")
            steps.append(self._venv_activate_prefix())
            steps.append("python -m pip install --upgrade pip")
        else:
            steps.append(self._venv_activate_prefix())
        steps.append(command)
        return " && ".join(steps)

    def _resolve_mount_path(self, repo_path: Path) -> Path:
        host_root = self.settings.docker_bind_host_root
        container_root = self.settings.docker_bind_container_root
        if not host_root or not container_root:
            return repo_path

        try:
            relative_path = repo_path.resolve().relative_to(Path(container_root))
        except ValueError:
            return repo_path

        return Path(host_root).expanduser().resolve() / relative_path

    def run(self, repo_path: Path, command: str, *, create_venv: bool = False) -> CommandResult:
        shell_command = self._build_shell_command(command, create_venv=create_venv)
        mount_path = self._resolve_mount_path(repo_path)
        process = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--memory",
                self.settings.sandbox_memory_limit,
                "--cpus",
                str(self.settings.sandbox_cpu_limit),
                "-v",
                f"{mount_path}:/workspace",
                self.settings.sandbox_base_image,
                "sh",
                "-lc",
                shell_command,
            ],
            text=True,
            capture_output=True,
            timeout=self.settings.sandbox_timeout_seconds,
            check=False,
        )
        return CommandResult(exit_code=process.returncode, stdout=process.stdout, stderr=process.stderr)

    def install_dependencies(self, repo_path: Path, install_command: str) -> CommandResult:
        return self.run(repo_path, install_command, create_venv=True)

    def run_tests(self, repo_path: Path, test_command: str) -> CommandResult:
        return self.run(repo_path, test_command, create_venv=False)
