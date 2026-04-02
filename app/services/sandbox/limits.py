from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class DiffStats:
    changed_files: list[str]
    diff_line_count: int

    @property
    def files_changed_count(self) -> int:
        return len(self.changed_files)


def parse_diff_stats(diff_text: str) -> DiffStats:
    files: list[str] = []
    diff_lines = 0
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            right = line.split(" b/", 1)[-1]
            files.append(right)
        elif line.startswith("+") or line.startswith("-"):
            if not line.startswith("+++") and not line.startswith("---"):
                diff_lines += 1
    return DiffStats(changed_files=files, diff_line_count=diff_lines)


def is_path_allowed(path: str, allowed_paths: list[str], blocked_paths: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    if any(normalized.startswith(blocked) for blocked in blocked_paths):
        return False
    return any(normalized.startswith(prefix) for prefix in allowed_paths)


def enforce_patch_limits(diff_text: str, allowed_paths: list[str], blocked_paths: list[str], max_changed_files: int, max_diff_lines: int) -> DiffStats:
    stats = parse_diff_stats(diff_text)
    if stats.files_changed_count > max_changed_files:
        raise ValueError("changed_files_limit_exceeded")
    if stats.diff_line_count > max_diff_lines:
        raise ValueError("diff_lines_limit_exceeded")
    for path in stats.changed_files:
        if not is_path_allowed(path, allowed_paths, blocked_paths):
            raise ValueError(f"path_not_allowed:{path}")
    return stats
