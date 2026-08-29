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

from .generation import RELEASE_VERSION, verification_token
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


def noop(world: SalesWorld, spec: dict[str, Any], reference: dict[str, Any]) -> None:
    """Pristine world: the agent never touches any MCP surface."""
    del world, spec, reference


def state_only(world: SalesWorld, spec: dict[str, Any], reference: dict[str, Any]) -> None:
    """Investigate, mutate, and read back correctly, but omit the employee handoff."""

    del spec
    for call in reference["calls"]:
        if call["server"] == "filesystem" and call["name"] == "write_file":
            continue
        checked_call(world, call["server"], call["name"], call["arguments"])


def incomplete_read(
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


def write_before_read(
    world: SalesWorld,
    spec: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    """Reach the exact final state, but investigate only after mutating it."""

    del spec
    mutations = [
        call
        for call in reference["calls"]
        if call["server"] in {"salesforce", "hubspot"}
        and call["name"] in {"updateSobjectRecord", "hubspot_update_object"}
    ]
    outputs = [
        call
        for call in reference["calls"]
        if call["server"] == "filesystem" and call["name"] == "write_file"
    ]
    investigation = [
        call
        for call in reference["calls"]
        if call not in mutations and call not in outputs
    ]
    for call in [*mutations, *investigation, *outputs]:
        checked_call(world, call["server"], call["name"], call["arguments"])


def missing_readback(
    world: SalesWorld,
    spec: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    """Complete the result but trust one mutation acknowledgement without verification."""

    del spec
    skipped = False
    for call in reference["calls"]:
        if not skipped and call.get("phase") == "postwrite_readback":
            skipped = True
            continue
        checked_call(world, call["server"], call["name"], call["arguments"])
    if not skipped:
        raise RuntimeError("reference trajectory had no post-write readback")


def unauthorized_write(
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


def unauthorized_delete(
    world: SalesWorld,
    spec: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    """Complete the oracle work, then delete one off-scope control record."""
    for call in reference["calls"]:
        checked_call(world, call["server"], call["name"], call["arguments"])
    control_account = next(
        row
        for row in world.state["salesforce"]["objects"]["Account"]
        if str(row.get("SalesBenchKey__c", "")).startswith("CTRL-")
    )
    checked_call(
        world,
        "salesforce",
        "deleteSobjectRecord",
        {"sobject-name": "Account", "id": control_account["Id"]},
    )


def wrong_evidence(
    world: SalesWorld,
    spec: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    """Reach the exact business result after substituting irrelevant evidence."""

    required = next(
        candidate
        for candidate in spec["required_investigation_calls"]
        if sum(
            call["server"] == candidate["server"]
            and call["name"] == candidate["name"]
            and call["arguments"] == candidate["arguments"]
            for call in reference["calls"]
        )
        == 1
    )
    replaced = False
    for call in reference["calls"]:
        if (
            not replaced
            and call["server"] == required["server"]
            and call["name"] == required["name"]
            and call["arguments"] == required["arguments"]
        ):
            checked_call(
                world,
                "filesystem",
                "search_files",
                {
                    "path": "/workspace/documents",
                    "pattern": "**/*.obsolete",
                    "excludePatterns": [],
                },
            )
            replaced = True
            continue
        checked_call(world, call["server"], call["name"], call["arguments"])
    if not replaced:
        raise RuntimeError("no uniquely required investigation call was available")


def wrong_value(
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


def wrong_decision(
    world: SalesWorld,
    spec: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    """Reach the exact CRM state but report the shortcut alternative as selected."""

    for call in reference["calls"]:
        if call["server"] == "filesystem" and call["name"] == "write_file":
            continue
        checked_call(world, call["server"], call["name"], call["arguments"])
    changes = deepcopy(reference["changes"])
    wrong_option = spec["decision_options"][1]["id"]
    changes["decision_summary"]["selected_option_id"] = wrong_option
    changes["changes"][0]["selected_option_id"] = wrong_option
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
            "content": reference["brief_text"],
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
        if category == "procedure" and isinstance(value, dict):
            nested = value
        else:
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
        ("state_only", state_only),
        ("incomplete_read", incomplete_read),
        ("write_before_read", write_before_read),
        ("missing_readback", missing_readback),
        ("unauthorized_write", unauthorized_write),
        ("wrong_evidence", wrong_evidence),
        ("wrong_value", wrong_value),
        ("wrong_decision", wrong_decision),
        ("noop", noop),
    ]
    oracle_passes = 0
    replay_matches = 0
    noop_nonzero_rewards = 0
    false_accepts = {name: 0 for name, _ in negative_runners}
    oracle_call_counts: list[int] = []
    failure_samples: dict[str, list[dict[str, Any]]] = {
        name: [] for name, _ in negative_runners
    }
    task_results: list[dict[str, Any]] = []

    for task_dir in task_dirs:
        trace_path = hf_root / "trajectories" / f"{task_dir.name}.jsonl"
        first = execute(task_dir, oracle, trace_destination=trace_path)
        replay = execute(task_dir, oracle)
        oracle_call_counts.append(first["successful_tool_calls"])
        oracle_passes += int(first["passed"])
        deterministic = first == replay
        replay_matches += int(deterministic)
        negatives: dict[str, Any] = {}
        for name, runner in negative_runners:
            negative = execute(task_dir, runner)
            false_accepts[name] += int(negative["passed"])
            if name == "noop" and negative["reward"] != 0.0:
                noop_nonzero_rewards += 1
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
        "version": RELEASE_VERSION,
        "task_count": len(task_dirs),
        "executions": len(task_dirs) * (2 + len(negative_runners)),
        "oracle": {
            "executions": len(task_dirs),
            "passes": oracle_passes,
            "failures": len(task_dirs) - oracle_passes,
            "reference_tool_calls_per_task": {
                "minimum": min(oracle_call_counts),
                "maximum": max(oracle_call_counts),
                "distinct_counts": sorted(set(oracle_call_counts)),
            },
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
        "noop_nonzero_rewards": noop_nonzero_rewards,
        "failure_samples": failure_samples,
        "release_passed": (
            oracle_passes == len(task_dirs)
            and replay_matches == len(task_dirs)
            and not any(false_accepts.values())
            and noop_nonzero_rewards == 0
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
    from .builder import seal_release_manifest

    seal_release_manifest(release)
    print(
        json.dumps(
            {
                "release_passed": report["release_passed"],
                "executions": report["executions"],
                "oracle": report["oracle"],
                "determinism": report["determinism"],
                "negative_controls": report["negative_controls"],
                "noop_nonzero_rewards": report["noop_nonzero_rewards"],
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
