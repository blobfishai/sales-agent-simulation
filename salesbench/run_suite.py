#!/usr/bin/env python3
"""Execute all SalesBench tasks against oracle, replay, and negative controls."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from .generation import MINIMUM_TOOL_CALLS, verification_token
from .runtime.world import SalesWorld


ROOT = Path(__file__).resolve().parents[1]


def checked_call(
    world: SalesWorld,
    server: str,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result = world.call_tool(server, name, deepcopy(arguments))
    if result.get("isError"):
        raise RuntimeError(f"{server}.{name} failed: {result}")
    return result


def oracle(world: SalesWorld, spec: dict[str, Any], reference: dict[str, Any]) -> None:
    del spec
    for call in reference["calls"]:
        checked_call(world, call["server"], call["name"], call["arguments"])


def shortcut(world: SalesWorld, spec: dict[str, Any], reference: dict[str, Any]) -> None:
    del spec
    for call in reference["calls"][-2:]:
        checked_call(world, call["server"], call["name"], call["arguments"])


def incomplete_evidence(
    world: SalesWorld,
    spec: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    missing_path = spec["required_document_paths"][-1]
    skipped = False
    for call in reference["calls"]:
        if (
            not skipped
            and call["server"] == "filesystem"
            and call["name"] == "read_text_file"
            and call["arguments"].get("path") == missing_path
        ):
            skipped = True
            continue
        checked_call(world, call["server"], call["name"], call["arguments"])


def collateral_mutation(
    world: SalesWorld,
    spec: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    first = spec["expected_changes"][0]
    injected = False
    for call in reference["calls"]:
        arguments = deepcopy(call["arguments"])
        if (
            not injected
            and call["server"] == first["system"]
            and call["name"] == first["tool"]
            and arguments == first["arguments"]
        ):
            if call["server"] == "salesforce":
                arguments["body"]["SalesBench_Unauthorized__c"] = "collateral-edit"
            else:
                arguments["properties"]["salesbench_unauthorized"] = "collateral-edit"
            injected = True
        checked_call(world, call["server"], call["name"], arguments)


def fabricated_outputs(
    world: SalesWorld,
    spec: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    del spec
    for call in reference["calls"][:-2]:
        checked_call(world, call["server"], call["name"], call["arguments"])
    changes = deepcopy(reference["changes"])
    changes["changes"][0]["after"] = "$99,999,999"
    checked_call(
        world,
        "filesystem",
        "write_file",
        {
            "path": "/workspace/output/changes.json",
            "content": json.dumps(changes, ensure_ascii=False, indent=2) + "\n",
        },
    )
    checked_call(
        world,
        "filesystem",
        "write_file",
        {
            "path": "/workspace/output/brief.md",
            "content": reference["brief_text"] + "\nGong record updated.\n",
        },
    )


Runner = Callable[[SalesWorld, dict[str, Any], dict[str, Any]], None]


def execute(
    task_dir: Path,
    runner: Runner,
    *,
    trace_destination: Path | None = None,
) -> dict[str, Any]:
    world_dir = task_dir / "environment" / "world"
    spec_path = world_dir / "spec.json"
    seed_path = world_dir / "seed.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    reference = json.loads(
        (task_dir / "solution" / "reference.json").read_text(encoding="utf-8")
    )
    with tempfile.TemporaryDirectory(prefix=f"{spec['task_id']}-") as raw:
        temporary = Path(raw)
        world = SalesWorld(
            task_dir / "environment" / "documents",
            temporary / "output",
            temporary / "state",
            spec_path,
            seed_path,
        )
        runner(world, spec, reference)
        report = world.verify(verification_token(spec["task_id"]))
        if trace_destination:
            trace_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(world.trace_path, trace_destination)
    return report


def failed_criteria(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    criteria = report.get("criteria", {})
    for category, value in criteria.items():
        nested = value.get("criteria", {}) if isinstance(value, dict) else value
        if isinstance(nested, dict):
            failures.extend(
                f"{category}.{name}" for name, passed in nested.items() if not passed
            )
    return sorted(failures)


def run(release: Path) -> dict[str, Any]:
    tasks_root = release / "harbor" / "tasks"
    hf_root = release / "huggingface"
    task_dirs = sorted(path for path in tasks_root.iterdir() if path.is_dir())
    if len(task_dirs) != 100:
        raise ValueError(f"expected 100 generated tasks, found {len(task_dirs)}")

    negative_runners: list[tuple[str, Runner]] = [
        ("shortcut", shortcut),
        ("incomplete_evidence", incomplete_evidence),
        ("collateral_mutation", collateral_mutation),
        ("fabricated_outputs", fabricated_outputs),
    ]
    oracle_passes = 0
    replay_matches = 0
    false_accepts = {name: 0 for name, _ in negative_runners}
    failure_samples: dict[str, list[dict[str, Any]]] = {
        name: [] for name, _ in negative_runners
    }
    task_results: list[dict[str, Any]] = []

    for task_dir in task_dirs:
        trace_path = hf_root / "trajectories" / f"{task_dir.name}.jsonl"
        first = execute(task_dir, oracle, trace_destination=trace_path)
        replay = execute(task_dir, oracle)
        oracle_passes += int(first["passed"])
        deterministic = first == replay
        replay_matches += int(deterministic)
        negatives: dict[str, Any] = {}
        for name, runner in negative_runners:
            negative = execute(task_dir, runner)
            false_accepts[name] += int(negative["passed"])
            summary = {
                "passed": negative["passed"],
                "reward": negative["reward"],
                "successful_tool_calls": negative["successful_tool_calls"],
                "failed_criteria": failed_criteria(negative),
                "report_sha256": negative["report_sha256"],
            }
            negatives[name] = summary
            if not negative["passed"] and len(failure_samples[name]) < 5:
                failure_samples[name].append({"task_id": task_dir.name, **summary})
        task_results.append(
            {
                "task_id": task_dir.name,
                "oracle_passed": first["passed"],
                "oracle_reward": first["reward"],
                "oracle_successful_tool_calls": first["successful_tool_calls"],
                "oracle_report_sha256": first["report_sha256"],
                "replay_report_sha256": replay["report_sha256"],
                "deterministic_replay_match": deterministic,
                "negative_executions": negatives,
            }
        )

    report = {
        "schema_version": "salesbench.qualification.v1",
        "benchmark": "SalesBench-100",
        "version": "1.0.0",
        "task_count": len(task_dirs),
        "executions": len(task_dirs) * (2 + len(negative_runners)),
        "oracle": {
            "executions": len(task_dirs),
            "passes": oracle_passes,
            "failures": len(task_dirs) - oracle_passes,
            "expected_tool_calls_per_task": MINIMUM_TOOL_CALLS,
        },
        "determinism": {
            "replays": len(task_dirs),
            "exact_report_matches": replay_matches,
            "mismatches": len(task_dirs) - replay_matches,
        },
        "negative_controls": {
            name: {
                "executions": len(task_dirs),
                "false_accepts": count,
                "correct_rejections": len(task_dirs) - count,
            }
            for name, count in false_accepts.items()
        },
        "failure_samples": failure_samples,
        "release_passed": (
            oracle_passes == len(task_dirs)
            and replay_matches == len(task_dirs)
            and not any(false_accepts.values())
        ),
        "task_results": task_results,
    }
    for target in (
        release / "reports" / "qualification.json",
        hf_root / "reports" / "qualification.json",
    ):
        write = json.dumps(report, indent=2, sort_keys=True) + "\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(write, encoding="utf-8")
    print(
        json.dumps(
            {
                "release_passed": report["release_passed"],
                "executions": report["executions"],
                "oracle": report["oracle"],
                "determinism": report["determinism"],
                "negative_controls": report["negative_controls"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--release",
        type=Path,
        default=ROOT / "dist" / "salesbench-100",
    )
    return parser.parse_args()


def main() -> None:
    result = run(parse_args().release)
    raise SystemExit(0 if result["release_passed"] else 1)


if __name__ == "__main__":
    main()
