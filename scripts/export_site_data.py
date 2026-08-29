#!/usr/bin/env python3
"""Export a compact, inspectable SalesBench payload for the Blobfish website."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from salesbench.contracts import CONTRACT_PINS, TOOLSETS
from salesbench.generation import generate_all


HF_BASE = "https://huggingface.co/datasets/SamuelChien821/salesbench-100"
SAMPLE_ORDINALS = set(range(1, 101))


def compact(value: str, limit: int = 300) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 1].rstrip() + "…"


def asset_rows(task: Any) -> list[dict[str, Any]]:
    changes = task.spec["expected_changes"]
    primary = {change["primary_source"]: change for change in changes}
    corroborating = {change["corroborating_source"]: change for change in changes}
    rows: list[dict[str, Any]] = []
    for relative, content in sorted(task.documents.items()):
        absolute = f"/workspace/documents/{relative}"
        change = primary.get(absolute) or corroborating.get(absolute)
        role = "primary" if absolute in primary else "corroborating" if absolute in corroborating else "context"
        rows.append(
            {
                "path": absolute,
                "folder": relative.split("/", 1)[0],
                "name": Path(relative).name,
                "format": Path(relative).suffix.removeprefix(".").upper(),
                "bytes": len(content.encode("utf-8")),
                "preview": compact(content),
                "changeId": change["id"] if change else None,
                "issue": change["reason"] if change else "Control or contextual evidence; no mutation authorized by this record.",
                "role": role,
                "system": change["system"] if change else None,
            }
        )
    return rows


def summarize_observation(entry: dict[str, Any]) -> str:
    tool = entry["tool"]
    arguments = entry.get("arguments", {})
    observation = str(entry.get("observation", ""))
    if tool == "read_text_file":
        return f"Read {len(observation.encode('utf-8')):,} bytes from {arguments.get('path')}."
    if tool == "write_file":
        return f"Wrote {arguments.get('content_bytes', 0):,} bytes; SHA-256 {str(arguments.get('content_sha256', ''))[:12]}…."
    return compact(observation, 240)


def trajectory(release: Path) -> dict[str, Any] | None:
    trace_path = release / "huggingface" / "trajectories" / "salesbench-001.jsonl"
    if not trace_path.is_file():
        alternatives = sorted((release / "huggingface" / "trajectories").glob("sb100-001-*.jsonl"))
        trace_path = alternatives[0] if alternatives else trace_path
    if not trace_path.is_file():
        return None
    task_id = trace_path.stem
    entries = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line]
    events = []
    for entry in entries:
        sequence = int(entry["sequence"])
        stage = "Orient" if sequence <= 3 else "Evidence" if sequence <= 107 else "Systems" if sequence <= 161 else "Deliver"
        events.append(
            {
                "type": "tool",
                "index": sequence,
                "call": sequence,
                "stage": stage,
                "server": entry["server"],
                "tool": entry["tool"],
                "arguments": entry["arguments"],
                "outcome": "ok" if entry["ok"] else "error",
                "result": summarize_observation(entry),
            }
        )
    return {
        "taskId": task_id,
        "title": "Northwind Q3 commit inspection",
        "model": "Reference oracle",
        "harness": "Harbor oracle adapter",
        "passed": True,
        "score": 100.0,
        "categoryScores": {"procedure": 100, "state": 100, "changes": 100, "brief": 100},
        "toolCalls": len(entries),
        "documentsRead": 96,
        "inputTokens": 0,
        "outputTokens": 0,
        "costUsd": 0.0,
        "transcriptUrl": f"{HF_BASE}/blob/main/trajectories/{task_id}.jsonl",
        "verifierUrl": f"{HF_BASE}/blob/main/reports/qualification.json",
        "events": events,
        "failedChecks": [],
    }


def export(release: Path, output: Path) -> dict[str, Any]:
    tasks = generate_all()
    summaries = []
    samples: dict[str, Any] = {}
    for ordinal, task in enumerate(tasks, start=1):
        summary = {
            "id": task.task_id,
            "ordinal": ordinal,
            "title": task.spine.title,
            "family": task.spine.family,
            "company": task.spine.company,
            "industry": task.spine.industry,
            "region": task.spine.region,
            "period": task.spine.period,
            "requester": task.spine.requester,
            "summary": task.spine.narrative,
            "documents": len(task.documents),
            "referenceToolCalls": len(task.reference["calls"]),
            "mutations": len(task.spec["expected_changes"]),
            "sample": ordinal in SAMPLE_ORDINALS,
            "datasetUrl": f"{HF_BASE}/blob/main/tasks/{task.task_id}.json",
        }
        summaries.append(summary)
        if ordinal in SAMPLE_ORDINALS:
            samples[task.task_id] = {
                **summary,
                "prompt": task.prompt,
                "changes": [
                    {
                        key: change[key]
                        for key in (
                            "id", "system", "object_type", "record_id", "field",
                            "before", "after", "reason", "primary_source",
                            "corroborating_source", "gong_evidence_id", "owner", "deadline",
                        )
                    }
                    for change in task.spec["expected_changes"]
                ],
                "assets": asset_rows(task),
                "options": task.spec["decision_options"],
                "gradedCriteria": [
                    criterion["description"] for criterion in task.spec["rubric_criteria"]
                ],
                "criterionWeights": task.spec["rubric_criteria"],
                "scoring": {
                    "criteriaPerTask": 281,
                    "procedureWeight": 20,
                    "stateWeight": 45,
                    "changesWeight": 25,
                    "briefWeight": 10,
                    "fullPassRequiresEveryCriterion": True,
                },
            }

    build = json.loads((release / "reports" / "build.json").read_text(encoding="utf-8"))
    qualification = json.loads((release / "reports" / "qualification.json").read_text(encoding="utf-8"))
    leaderboard = [
        {
            "rank": "REF",
            "name": "Reference oracle",
            "harness": "Harbor oracle adapter",
            "kind": "reference",
            "tasks": 100,
            "score": 100.0,
            "strictPassRate": 100.0,
            "procedure": 100.0,
            "state": 100.0,
            "changes": 100.0,
            "brief": 100.0,
            "averageCalls": 163,
            "averageCost": 0.0,
            "note": "Solvability proof; excluded from model ranking",
        }
    ]
    model_report_path = release / "reports" / "model-evaluation.json"
    if model_report_path.is_file():
        model_report = json.loads(model_report_path.read_text(encoding="utf-8"))
        if (
            model_report.get("benchmark_version") != build["version"]
            or model_report.get("coverage", {}).get("full_benchmark_run") is not True
            or model_report.get("coverage", {}).get("task_count") != 100
        ):
            model_report = None
    else:
        model_report = None
    if model_report is not None:
        result = model_report["result"]
        model = model_report["model"]
        coverage = model_report["coverage"]
        categories = result["category_scores"]
        leaderboard.append(
            {
                "rank": 1,
                "name": model["name"],
                "harness": f"Harbor Codex adapter · {model['reasoning_effort']} reasoning",
                "kind": "model",
                "tasks": coverage["task_count"],
                "score": round(result["criteria_score"] * 100, 4),
                "strictPassRate": 100.0 if result["strict_pass"] else 0.0,
                "procedure": round(categories["procedure"] * 100, 4),
                "state": round(categories["state"] * 100, 4),
                "changes": round(categories["changes"] * 100, 4),
                "brief": round(categories["brief"] * 100, 4),
                "averageCalls": result["successful_tool_calls"],
                "averageCost": result["cost_usd"],
                "note": "Full 100-task measured run over this exact release.",
            }
        )
    payload = {
        "schemaVersion": "salesbench.site.v1",
        "benchmark": {
            "name": "SalesBench-100",
            "version": build["version"],
            "tasks": 100,
            "families": 10,
            "documents": 9_600,
            "documentsPerTask": 96,
            "referenceCallsPerTask": 163,
            "mutationsPerTask": 12,
            "criteriaPerTask": 281,
            "deterministicVerifier": True,
            "exactDuplicateDocuments": build["exact_duplicate_documents"],
            "minimumDocumentBytes": build["minimum_document_bytes"],
            "medianDocumentBytes": build["median_document_bytes"],
            "maximumDocumentBytes": build["maximum_document_bytes"],
            "qualificationExecutions": qualification["executions"],
            "oraclePasses": qualification["oracle"]["passes"],
            "negativeFalseAccepts": sum(
                row["false_accepts"] for row in qualification["negative_controls"].values()
            ),
            "mcp": CONTRACT_PINS,
            "links": {
                "harbor": "https://hub.harborframework.com/datasets/blobfishai/salesbench-100",
                "huggingFace": HF_BASE,
                "source": "https://github.com/blobfishai/sales-agent-simulation",
            },
        },
        "leaderboard": leaderboard,
        "tasks": summaries,
        "samples": samples,
        "tools": [
            {"server": server, **tool}
            for server, definitions in TOOLSETS.items()
            for tool in definitions
        ],
        "trajectory": trajectory(release),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, default=Path("dist/salesbench-100"))
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    result = export(arguments.release, arguments.output)
    print(json.dumps({"tasks": len(result["tasks"]), "samples": len(result["samples"]), "tools": len(result["tools"]), "trajectory_events": len((result["trajectory"] or {}).get("events", []))}, indent=2))
