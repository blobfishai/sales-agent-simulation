#!/usr/bin/env python3
"""Retry failed Harbor trials as isolated task invocations with checkpoints."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


WRITE_LOCK = threading.Lock()


def load_failed_tasks(job_root: Path) -> list[Path]:
    tasks: list[Path] = []
    for result_path in sorted(job_root.glob("*/result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        rewards = (result.get("verifier_result") or {}).get("rewards") or {}
        if result.get("exception_info") or float(rewards.get("passed", 0.0)) != 1.0:
            task_value = result.get("task_id", {}).get("path")
            if not task_value:
                raise ValueError(f"failed trial lacks local task path: {result_path}")
            tasks.append(Path(task_value))
    return tasks


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def latest_job_result(task_jobs: Path) -> Path:
    candidates = sorted(task_jobs.glob("*/result.json"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"Harbor produced no result under {task_jobs}")
    return candidates[-1]


def execute(task_path: Path, jobs_root: Path) -> dict[str, Any]:
    task_name = task_path.name
    destination = jobs_root / task_name
    started = time.monotonic()
    completed = subprocess.run(
        [
            "harbor", "run", "-p", str(task_path), "-a", "oracle",
            "-n", "1", "-k", "1", "-o", str(destination), "--yes", "--quiet",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    elapsed = round(time.monotonic() - started, 3)
    result_path: Path | None = None
    result: dict[str, Any] = {}
    try:
        result_path = latest_job_result(destination)
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    stats = result.get("stats", {})
    evals = stats.get("evals", {})
    metrics = next(iter(evals.values()), {}).get("metrics", [{}])[0] if evals else {}
    passed = (
        completed.returncode == 0
        and stats.get("n_errored_trials") == 0
        and float(metrics.get("passed", 0.0)) == 1.0
        and float(metrics.get("reward", 0.0)) == 1.0
    )
    return {
        "task": task_name,
        "task_path": str(task_path),
        "passed": passed,
        "returncode": completed.returncode,
        "elapsed_seconds": elapsed,
        "result_path": str(result_path) if result_path else None,
        "stats": stats,
        "output_tail": completed.stdout[-4000:],
    }


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    failed = load_failed_tasks(arguments.failed_job)
    existing: dict[str, Any] = {}
    if arguments.report.is_file():
        prior = json.loads(arguments.report.read_text(encoding="utf-8"))
        existing = {
            row["task"]: row for row in prior.get("task_results", []) if row.get("passed")
        }
    pending = [path for path in failed if path.name not in existing]
    results = dict(existing)
    with ThreadPoolExecutor(max_workers=arguments.workers) as executor:
        futures = {
            executor.submit(execute, task, arguments.jobs_root): task for task in pending
        }
        for future in as_completed(futures):
            value = future.result()
            with WRITE_LOCK:
                results[value["task"]] = value
                snapshot = {
                    "schema_version": "salesbench.harbor-recovery.v1",
                    "source_job": str(arguments.failed_job),
                    "targeted_tasks": len(failed),
                    "completed_tasks": len(results),
                    "passes": sum(row["passed"] for row in results.values()),
                    "failures": sum(not row["passed"] for row in results.values()),
                    "task_results": [results[name] for name in sorted(results)],
                }
                atomic_json(arguments.report, snapshot)
                print(
                    json.dumps(
                        {
                            "task": value["task"],
                            "passed": value["passed"],
                            "completed": len(results),
                            "target": len(failed),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
    report = json.loads(arguments.report.read_text(encoding="utf-8"))
    report["release_passed"] = (
        report["completed_tasks"] == report["targeted_tasks"] and report["failures"] == 0
    )
    atomic_json(arguments.report, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--failed-job", type=Path, required=True)
    parser.add_argument("--jobs-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    return parser.parse_args()


if __name__ == "__main__":
    outcome = run(parse_args())
    print(json.dumps({key: outcome[key] for key in ("targeted_tasks", "passes", "failures", "release_passed")}, indent=2))
    raise SystemExit(0 if outcome["release_passed"] else 1)
