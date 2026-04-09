import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from app.services.openai.agent_loop import AgentLoop
from app.services.openai.tools import AgentToolbox
from app.services.sandbox.git_ops import diff
from app.services.sandbox.limits import parse_diff_stats
from app.services.sandbox.repo_config import load_repo_config


class LocalRunner:
    def run_tests(self, repo_path: Path, test_command: str):
        command_tokens = shlex.split(test_command)
        if command_tokens[:2] == ["python", "-m"]:
            command = [sys.executable, "-m", *command_tokens[2:]]
        elif command_tokens and command_tokens[0] == "pytest":
            command = [sys.executable, "-m", "pytest", *command_tokens[1:]]
        else:
            command = command_tokens
        process = subprocess.run(
            command,
            cwd=repo_path,
            text=True,
            capture_output=True,
            check=False,
        )
        return type("Result", (), {"exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr})()


def _prepare_repo(run_root: Path, fixture_name: str) -> Path:
    fixture_repo = Path(__file__).resolve().parent.parent / "app" / "tests" / "fixtures" / fixture_name
    repo_path = run_root / fixture_name
    if repo_path.exists():
        shutil.rmtree(repo_path)
    shutil.copytree(fixture_repo, repo_path)
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "benchmarks@example.com"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "benchmarks"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    return repo_path


def run_case(case: dict, output_dir: Path) -> dict:
    case_root = output_dir / case["name"]
    case_root.mkdir(parents=True, exist_ok=True)
    repo_path = _prepare_repo(case_root, case["repo_fixture"])
    repo_config = load_repo_config(repo_path)
    toolbox = AgentToolbox(
        repo_path=repo_path,
        repo_config=repo_config,
        issue_context=case["issue"],
        sandbox_runner=LocalRunner(),
    )
    started = time.perf_counter()
    result = AgentLoop().run(toolbox)
    duration_ms = int((time.perf_counter() - started) * 1000)
    if result.patch_text and not diff(repo_path).strip():
        toolbox.apply_patch(result.patch_text)
    test_result = toolbox.run_tests()
    diff_text = diff(repo_path)
    diff_stats = parse_diff_stats(diff_text)
    return {
        "name": case["name"],
        "status": "success" if test_result["exit_code"] == 0 else "failed",
        "duration_ms": duration_ms,
        "model_call_count": result.model_call_count,
        "tool_call_count": result.tool_call_count,
        "files_changed_count": diff_stats.files_changed_count,
        "diff_line_count": diff_stats.diff_line_count,
        "test_exit_code": test_result["exit_code"],
    }


def build_summary(results: list[dict]) -> dict:
    total = len(results)
    success = sum(1 for item in results if item["status"] == "success")
    avg_duration_ms = int(sum(item["duration_ms"] for item in results) / total) if total else 0
    return {
        "total": total,
        "success": success,
        "success_rate": round(success / total, 2) if total else 0,
        "avg_duration_ms": avg_duration_ms,
    }


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    benchmark_file = root / "app" / "tests" / "fixtures" / "benchmarks.json"
    output_dir = root / "benchmark_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = json.loads(benchmark_file.read_text(encoding="utf-8"))
    results = [run_case(case, output_dir) for case in cases]
    payload = {"summary": build_summary(results), "results": results}
    (output_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
