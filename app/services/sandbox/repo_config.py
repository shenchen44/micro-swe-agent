from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(slots=True)
class RepoConfig:
    language: str = "python"
    test_command: str = "pytest -q"
    install_command: str = "pip install -r requirements.txt"
    allowed_paths: list[str] = field(default_factory=lambda: ["app/", "src/", "tests/"])
    blocked_paths: list[str] = field(default_factory=lambda: [".github/", "infra/", "deploy/", "migrations/"])
    max_changed_files: int = 5
    max_diff_lines: int = 200


DANGEROUS_TOKENS = {"rm -rf", "shutdown", "reboot", "mkfs", "dd ", "chmod 777", "curl |", "wget |"}


def validate_command(command: str) -> None:
    normalized = command.lower()
    for token in DANGEROUS_TOKENS:
        if token in normalized:
            raise ValueError(f"dangerous command rejected: {token}")


def load_repo_config(repo_path: Path) -> RepoConfig:
    config_path = repo_path / ".agent.yml"
    if not config_path.exists():
        config = RepoConfig()
    else:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        config = RepoConfig(
            language=data.get("language", "python"),
            test_command=data.get("test_command", "pytest -q"),
            install_command=data.get("install_command", "pip install -r requirements.txt"),
            allowed_paths=data.get("allowed_paths", ["app/", "src/", "tests/"]),
            blocked_paths=data.get("blocked_paths", [".github/", "infra/", "deploy/", "migrations/"]),
            max_changed_files=int(data.get("max_changed_files", 5)),
            max_diff_lines=int(data.get("max_diff_lines", 200)),
        )
    validate_command(config.install_command)
    validate_command(config.test_command)
    if config.language != "python":
        raise ValueError("only python repositories are supported in MVP")
    return config
