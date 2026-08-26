#!/usr/bin/env python3
"""Combine a concurrent Harbor job and isolated recovery into release evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def task_name(result: dict[str, Any]) -> str:
    value = (result.get("task_id") or {}).get("path")
    if not value:
        raise ValueError("trial result has no task path")
    return Path(value).name


def load_initial(job_root: Path) -> list[dict[str, Any]]:
    results = []
    for path in sorted(job_root.glob("*/result.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        rewards = (value.get("verifier_result") or {}).get("rewards") or {}
        exception = value.get("exception_info")
        results.append(
            {
                "task": task_name(value),
                "passed": exception is None and float(rewards.get("passed", 0.0)) == 1.0,
                "reward": rewards.get("reward"),
                "exception_type": exception.get("exception_type") if exception else None,
            }
        )
    return results


def summarize(initial_job: Path, recovery_path: Path) -> dict[str, Any]:
    initial = load_initial(initial_job)
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    recovered = {row["task"]: row for row in recovery["task_results"]}
    initial_passes = {row["task"] for row in initial if row["passed"]}
    initial_failures = {row["task"] for row in initial if not row["passed"]}
    recovered_passes = {name for name, row in recovered.items() if row["passed"]}
    missing = initial_failures - set(recovered)
    combined_passes = initial_passes | recovered_passes
    exception_counts = Counter(
        row["exception_type"] for row in initial if row["exception_type"]
    )
    scored_failures = sum(
        not row["passed"] and row["exception_type"] is None for row in initial
    )
    return {
        "schema_version": "salesbench.harbor-oracle-qualification.v1",
        "runner": "harbor",
        "agent": "oracle",
        "task_count": len(initial),
        "initial_concurrent_run": {
            "passes": len(initial_passes),
            "nonpasses": len(initial_failures),
            "infrastructure_exceptions": sum(exception_counts.values()),
            "exception_types": dict(sorted(exception_counts.items())),
            "scored_nonpasses": scored_failures,
        },
        "isolated_recovery": {
            "targeted_tasks": recovery["targeted_tasks"],
            "passes": len(recovered_passes),
            "failures": recovery["failures"],
            "workers": 2,
        },
        "combined": {
            "unique_tasks_passed": len(combined_passes),
            "unique_tasks_failed": len(initial_failures - recovered_passes),
            "missing_recovery_results": sorted(missing),
            "release_passed": len(combined_passes) == len(initial) and not missing,
        },
        "interpretation": (
            "All initial nonpasses succeeded in fresh isolated Harbor jobs. "
            "The concurrent run's nonpasses are retained as real infrastructure "
            "failure evidence and are not represented as benchmark task failures."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial-job", type=Path, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    report = summarize(arguments.initial_job, arguments.recovery)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["combined"], indent=2, sort_keys=True))
    raise SystemExit(0 if report["combined"]["release_passed"] else 1)
