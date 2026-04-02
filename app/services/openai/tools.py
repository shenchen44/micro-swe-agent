import json
import subprocess
from pathlib import Path

from app.services.sandbox.git_ops import apply_patch as git_apply_patch
from app.services.sandbox.git_ops import diff as git_diff
from app.services.sandbox.git_ops import resolve_repo_path
from app.services.sandbox.git_ops import replace_in_tracked_file, reverse_patch, write_tracked_file
from app.services.sandbox.limits import enforce_patch_limits
from app.services.sandbox.limits import is_path_allowed
from app.services.sandbox.repo_config import RepoConfig
from app.services.sandbox.runner import SandboxRunner


class ToolExecutionError(RuntimeError):
    def __init__(self, tool_name: str, arguments: dict, message: str, diff_text: str) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.arguments = arguments
        self.diff_text = diff_text


class AgentToolbox:
    def __init__(self, repo_path: Path, repo_config: RepoConfig, issue_context: dict, sandbox_runner: SandboxRunner | None = None) -> None:
        self.repo_path = repo_path
        self.repo_config = repo_config
        self.issue_context = issue_context
        self.sandbox_runner = sandbox_runner or SandboxRunner()

    def list_files(self, path: str = ".", limit: int = 200) -> dict:
        root = self.repo_path / path
        files = [str(item.relative_to(self.repo_path)).replace("\\", "/") for item in root.rglob("*") if item.is_file()]
        return {"files": files[:limit]}

    def search_code(self, query: str, glob: str | None = None, limit: int = 50) -> dict:
        command = ["rg", "--line-number", "--hidden", "--glob", glob or "*", query, str(self.repo_path)]
        try:
            process = subprocess.run(command, text=True, capture_output=True, check=False)
        except FileNotFoundError:
            return {"matches": []}
        matches = []
        for line in process.stdout.splitlines()[:limit]:
            path, line_no, content = line.split(":", 2)
            matches.append({"path": str(Path(path).relative_to(self.repo_path)).replace("\\", "/"), "line": int(line_no), "content": content})
        return {"matches": matches}

    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
        file_path = resolve_repo_path(self.repo_path, path)
        lines = file_path.read_text(encoding="utf-8").splitlines()
        start = (start_line - 1) if start_line else 0
        end = end_line if end_line else len(lines)
        return {"path": path, "content": "\n".join(lines[start:end])}

    def _validate_edit_path(self, path: str) -> None:
        normalized = path.replace("\\", "/")
        if not is_path_allowed(normalized, self.repo_config.allowed_paths, self.repo_config.blocked_paths):
            raise ValueError(f"path_not_allowed:{normalized}")

    def _diff_result(self) -> dict:
        diff_text = git_diff(self.repo_path)
        stats = enforce_patch_limits(
            diff_text,
            self.repo_config.allowed_paths,
            self.repo_config.blocked_paths,
            self.repo_config.max_changed_files,
            self.repo_config.max_diff_lines,
        )
        return {
            "files_changed_count": stats.files_changed_count,
            "diff_line_count": stats.diff_line_count,
            "diff": diff_text,
        }

    def write_file(self, path: str, content: str) -> dict:
        self._validate_edit_path(path)
        original_content = resolve_repo_path(self.repo_path, path).read_text(encoding="utf-8")
        write_tracked_file(self.repo_path, path, content)
        try:
            return self._diff_result()
        except Exception:
            write_tracked_file(self.repo_path, path, original_content)
            raise

    def replace_in_file(self, path: str, old_text: str, new_text: str) -> dict:
        self._validate_edit_path(path)
        original_content = resolve_repo_path(self.repo_path, path).read_text(encoding="utf-8")
        replace_in_tracked_file(self.repo_path, path, old_text, new_text)
        try:
            return self._diff_result()
        except Exception:
            write_tracked_file(self.repo_path, path, original_content)
            raise

    def apply_patch(self, unified_diff: str) -> dict:
        git_apply_patch(self.repo_path, unified_diff)
        try:
            return self._diff_result()
        except Exception:
            reverse_patch(self.repo_path, unified_diff)
            raise

    def git_diff(self) -> dict:
        return {"diff": git_diff(self.repo_path)}

    def run_tests(self, runner: str | None = None) -> dict:
        result = self.sandbox_runner.run_tests(self.repo_path, self.repo_config.test_command)
        return {"exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr}

    def get_issue_context(self) -> dict:
        return self.issue_context

    def get_repo_config(self) -> dict:
        return {
            "language": self.repo_config.language,
            "test_command": self.repo_config.test_command,
            "install_command": self.repo_config.install_command,
            "allowed_paths": self.repo_config.allowed_paths,
            "blocked_paths": self.repo_config.blocked_paths,
            "max_changed_files": self.repo_config.max_changed_files,
            "max_diff_lines": self.repo_config.max_diff_lines,
        }

    @staticmethod
    def tool_schemas() -> list[dict]:
        return [
            {"type": "function", "function": {"name": "list_files", "description": "List repository files", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": []}}},
            {"type": "function", "function": {"name": "search_code", "description": "Search code with ripgrep", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "glob": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}}},
            {"type": "function", "function": {"name": "read_file", "description": "Read a repository file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}}},
            {"type": "function", "function": {"name": "write_file", "description": "Rewrite an existing repository file with full UTF-8 content after reading it first", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
            {"type": "function", "function": {"name": "replace_in_file", "description": "Replace a specific text snippet inside an existing repository file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}},
            {"type": "function", "function": {"name": "apply_patch", "description": "Apply a unified diff patch", "parameters": {"type": "object", "properties": {"unified_diff": {"type": "string"}}, "required": ["unified_diff"]}}},
            {"type": "function", "function": {"name": "git_diff", "description": "Get current git diff", "parameters": {"type": "object", "properties": {}, "required": []}}},
            {"type": "function", "function": {"name": "run_tests", "description": "Run repository tests using the configured test command", "parameters": {"type": "object", "properties": {"runner": {"type": "string"}}, "required": []}}},
            {"type": "function", "function": {"name": "get_issue_context", "description": "Get issue context", "parameters": {"type": "object", "properties": {}, "required": []}}},
            {"type": "function", "function": {"name": "get_repo_config", "description": "Get repository config", "parameters": {"type": "object", "properties": {}, "required": []}}},
        ]

    def dispatch(self, name: str, arguments_json: str) -> dict:
        args = json.loads(arguments_json or "{}")
        try:
            return getattr(self, name)(**args)
        except Exception as exc:
            raise ToolExecutionError(
                tool_name=name,
                arguments=args,
                message=f"tool_call_failed:{name}: {exc}",
                diff_text=git_diff(self.repo_path),
            ) from exc
