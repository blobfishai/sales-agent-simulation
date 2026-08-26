#!/usr/bin/env python3
"""Build the SalesBench-100 Harbor task packs and Hugging Face release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .catalog import FAMILY_SETTINGS
from .contracts import CONTRACT_PINS, TOOLS_BY_SERVER
from .generation import (
    DOCUMENT_COUNT,
    FIXED_FILE_TIMESTAMP,
    METADATA_CHECK_COUNT,
    MINIMUM_TOOL_CALLS,
    RELEASE_VERSION,
    TARGET_CHANGE_COUNT,
    GeneratedTask,
    generate_all,
    verification_token,
)


RELEASE_NAME = "SalesBench-100"
RELEASE_SLUG = "salesbench-100"
HARBOR_ORG = "blobfishai"
HF_ORG = "SamuelChien821"
DATA_LICENSE = "CC-BY-4.0"
CODE_LICENSE = "Apache-2.0"
ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = (
    "__init__.py",
    "scoring.py",
    "server.py",
    "world.py",
)


def write_text(path: Path, value: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def task_toml(task: GeneratedTask) -> str:
    servers = "\n".join(
        f'''[[environment.mcp_servers]]
name = "{server}"
transport = "streamable-http"
url = "http://world:8972/mcp/{server}"
'''
        for server in ("filesystem", "salesforce", "hubspot", "gong")
    )
    return f'''schema_version = "1.4"

[task]
name = "{HARBOR_ORG}/{task.task_id}"
version = "{RELEASE_VERSION}"
description = "{task.spec['family_label']}: {task.spine.title}"
authors = []
keywords = ["sales", "salesforce", "hubspot", "gong", "mcp", "long-horizon"]

[metadata]
benchmark = "{RELEASE_NAME}"
benchmark_version = "{RELEASE_VERSION}"
task_id = "{task.task_id}"
workflow_family = "{task.spine.family}"
document_count = {DOCUMENT_COUNT}
expected_changes = {TARGET_CHANGE_COUNT}
minimum_tool_calls = {MINIMUM_TOOL_CALLS}
deterministic_verifier = true
synthetic_data = true
data_license = "{DATA_LICENSE}"
code_license = "{CODE_LICENSE}"

[verifier]
timeout_sec = 240.0

[agent]
timeout_sec = 5400.0

[environment]
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 4096
gpus = 0

{servers}'''


def compose_yaml() -> str:
    return """services:
  main:
    depends_on:
      world:
        condition: service_healthy
    volumes:
      - type: volume
        source: salesbench_output
        target: /workspace/output

  world:
    build:
      context: .
      dockerfile: world/Dockerfile
    environment:
      SALESBENCH_DOCUMENTS: /workspace/documents
      SALESBENCH_OUTPUT: /workspace/output
      SALESBENCH_STATE: /workspace/state
      SALESBENCH_SPEC: /opt/salesbench/spec.json
      SALESBENCH_SEED: /opt/salesbench/seed.json
    expose:
      - "8972"
    volumes:
      - type: volume
        source: salesbench_output
        target: /workspace/output
      - type: volume
        source: salesbench_state
        target: /workspace/state
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8972/health', timeout=2)"]
      interval: 2s
      timeout: 5s
      retries: 60
      start_period: 2s

volumes:
  salesbench_output:
  salesbench_state:
"""


def main_dockerfile() -> str:
    return """FROM python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17
WORKDIR /workspace
COPY tool /usr/local/bin/tool
COPY documents /workspace/documents
RUN chmod 0755 /usr/local/bin/tool && mkdir -p /workspace/output
CMD ["sleep", "infinity"]
"""


def world_dockerfile() -> str:
    return """FROM python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17
WORKDIR /opt/salesbench
COPY world/salesbench ./salesbench
COPY world/spec.json world/seed.json ./
COPY documents /workspace/documents
RUN mkdir -p /workspace/output /workspace/state && chmod -R a-w /workspace/documents
EXPOSE 8972
CMD ["python3", "-m", "salesbench.runtime.server"]
"""


def tool_cli() -> str:
    return r'''#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

BASE = os.environ.get("SALESBENCH_MCP_URL", "http://world:8972/mcp")

def request(server, method, params=None, request_id=1):
    value = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        value["params"] = params
    req = urllib.request.Request(f"{BASE}/{server}", method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    with urllib.request.urlopen(req, json.dumps(value).encode("utf-8"), timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise SystemExit(json.dumps(payload["error"]))
    return payload["result"]

if len(sys.argv) == 3 and sys.argv[1] == "list":
    print(json.dumps(request(sys.argv[2], "tools/list"), indent=2, ensure_ascii=False))
elif len(sys.argv) == 5 and sys.argv[1] == "call":
    result = request(sys.argv[2], "tools/call", {"name": sys.argv[3], "arguments": json.loads(sys.argv[4])})
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get("isError"):
        raise SystemExit(1)
else:
    raise SystemExit("usage: tool list SERVER | tool call SERVER TOOL '{\"argument\":\"value\"}'")
'''


def solution_script() -> str:
    return r'''#!/usr/bin/env python3
import json
import os
import urllib.request
from pathlib import Path

REFERENCE = json.loads((Path(__file__).resolve().parent / "reference.json").read_text())
BASE = os.environ.get("SALESBENCH_MCP_URL", "http://world:8972/mcp")
request_id = 0

def call(server, name, arguments):
    global request_id
    request_id += 1
    message = {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(f"{BASE}/{server}", method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json, text/event-stream")
    with urllib.request.urlopen(request, json.dumps(message).encode("utf-8"), timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("result") or {}
    if payload.get("error") or result.get("isError"):
        raise RuntimeError(json.dumps(payload, ensure_ascii=False))

for entry in REFERENCE["calls"]:
    call(entry["server"], entry["name"], entry["arguments"])
print(json.dumps({"task_id": REFERENCE["task_id"], "successful_tool_calls": request_id}))
if request_id != ''' + str(MINIMUM_TOOL_CALLS) + r''':
    raise SystemExit("reference trajectory length changed")
'''


def test_script(token: str) -> str:
    return f'''#!/bin/bash
set -eu
python3 - <<'PYEOF'
import json
import os
import urllib.request

report = {{"passed": False, "reward": 0.0, "error": "verifier did not return"}}
try:
    request = urllib.request.Request("http://world:8972/verify", method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("X-Verify-Token", "{token}")
    with urllib.request.urlopen(request, b"{{}}", timeout=180) as response:
        report = json.loads(response.read().decode("utf-8"))
except Exception as error:
    report = {{"passed": False, "reward": 0.0, "error": repr(error)}}
reward = {{"reward": float(report.get("reward", 0.0)), "passed": 1.0 if report.get("passed") else 0.0}}
logs = os.environ.get("HARBOR_LOGS") or os.environ.get("VERIFIER_LOG_DIR") or "/logs"
root = os.path.join(logs, "verifier")
os.makedirs(root, exist_ok=True)
with open(os.path.join(root, "report.json"), "w", encoding="utf-8") as stream:
    json.dump(report, stream, indent=2, sort_keys=True)
with open(os.path.join(root, "reward.json"), "w", encoding="utf-8") as stream:
    json.dump(reward, stream, sort_keys=True)
with open(os.path.join(root, "reward.txt"), "w", encoding="utf-8") as stream:
    stream.write(f"{{reward['reward']}}\\n")
print(json.dumps({{"passed": bool(report.get("passed")), "reward": reward["reward"]}}))
PYEOF
'''


def copy_world_package(world_dir: Path) -> None:
    package = world_dir / "salesbench"
    runtime = package / "runtime"
    write_text(package / "__init__.py", '"""SalesBench Harbor runtime."""\n')
    shutil.copy2(ROOT / "salesbench" / "contracts.py", package / "contracts.py")
    for name in RUNTIME_FILES:
        runtime.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "salesbench" / "runtime" / name, runtime / name)
    write_text(world_dir / "Dockerfile", world_dockerfile())


def create_task_pack(
    tasks_root: Path,
    hf_root: Path,
    task: GeneratedTask,
) -> tuple[dict[str, Any], dict[str, Any]]:
    task_dir = tasks_root / task.task_id
    environment = task_dir / "environment"
    documents = environment / "documents"
    world_dir = environment / "world"
    token = verification_token(task.task_id)

    write_text(task_dir / "task.toml", task_toml(task))
    write_text(task_dir / "instruction.md", task.prompt)
    write_text(environment / "Dockerfile", main_dockerfile())
    write_text(environment / "docker-compose.yaml", compose_yaml())
    write_text(environment / "tool", tool_cli(), executable=True)
    copy_world_package(world_dir)
    write_json(world_dir / "spec.json", task.spec)
    write_json(world_dir / "seed.json", task.seed)

    hf_context_paths: list[str] = []
    for relative, content in sorted(task.documents.items()):
        source = documents / relative
        write_text(source, content)
        timestamp = 1_788_777_600  # 2026-08-26 12:00:00 UTC, fixed.
        os.utime(source, (timestamp, timestamp))
        target = hf_root / "task_files" / task.task_id / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, target)
        hf_context_paths.append(f"task_files/{task.task_id}/{relative}")

    write_json(task_dir / "solution" / "reference.json", task.reference)
    write_text(task_dir / "solution" / "solve.py", solution_script(), executable=True)
    write_text(
        task_dir / "solution" / "solve.sh",
        '#!/bin/bash\nset -eu\npython3 "$(dirname "$0")/solve.py"\n',
        executable=True,
    )
    write_text(task_dir / "tests" / "test.sh", test_script(token), executable=True)

    record = {
        "task_id": task.task_id,
        "task_name": task.spine.title,
        "world_id": "salesbench-multi-crm-mcp-v1",
        "prompt": task.prompt,
        "context_files": hf_context_paths,
        "rubric": {
            "type": "deterministic",
            "minimum_tool_calls": MINIMUM_TOOL_CALLS,
            "required_document_reads": DOCUMENT_COUNT,
            "metadata_checks": METADATA_CHECK_COUNT,
            "authorized_mutations": TARGET_CHANGE_COUNT,
            "required_deliverables": ["changes.json", "brief.md"],
            "score_weights": {"procedure": 0.20, "state": 0.45, "changes": 0.25, "brief": 0.10},
            "gates": [
                "all_evidence_read_in_full",
                "vendor_evidence_cross_checked",
                "entire_business_state_exact",
                "authorized_mutations_each_called_once",
                "no_delete_or_neighbor_mutation",
                "exact_structured_change_log",
                "fully_grounded_brief",
                "deliverables_written_through_mcp",
            ],
        },
        "gold_output": {
            "changes": task.reference["changes"],
            "brief_markdown": task.reference["brief_text"],
        },
        "metadata": {
            "benchmark": RELEASE_NAME,
            "version": RELEASE_VERSION,
            "grading": "deterministic",
            "llm_judge": False,
            "workflow_family": task.spine.family,
            "company": task.spine.company,
            "industry": task.spine.industry,
            "region": task.spine.region,
            "period": task.spine.period,
            "synthetic": True,
            "document_count": DOCUMENT_COUNT,
            "reference_tool_calls": MINIMUM_TOOL_CALLS,
            "contract_pins": CONTRACT_PINS,
            "data_license": DATA_LICENSE,
            "code_license": CODE_LICENSE,
        },
    }
    write_json(hf_root / "tasks" / f"{task.task_id}.json", record)
    index = {
        "task_id": task.task_id,
        "title": task.spine.title,
        "workflow_family": task.spine.family,
        "company": task.spine.company,
        "task_pack": f"tasks/{task.task_id}",
        "harbor_name": f"{HARBOR_ORG}/{task.task_id}",
        "documents": DOCUMENT_COUNT,
        "reference_tool_calls": MINIMUM_TOOL_CALLS,
        "authorized_mutations": TARGET_CHANGE_COUNT,
    }
    return record, index


PACK_IGNORE_SUFFIXES = (".pyc", ".swp", ".swo", "~")


def harbor_content_digest(task_dir: Path) -> str:
    """Replicate the Harbor publisher's task content hash (packager.py).

    Files: task.toml, instruction.md, README.md, trajectory.json plus the
    environment/, tests/, solution/, and steps/ trees, filtered by the default
    ignore set, sorted by POSIX relative path, digested as "rel\\0sha256\\n".
    """
    task_dir = task_dir.resolve()
    files: list[Path] = []
    for single in ("task.toml", "instruction.md", "README.md", "trajectory.json"):
        path = task_dir / single
        if path.is_file():
            files.append(path)
    for directory in ("environment", "tests", "solution", "steps"):
        root = task_dir / directory
        if root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
    files = [
        path
        for path in files
        if "__pycache__" not in path.parts
        and path.name != ".DS_Store"
        and not path.name.endswith(PACK_IGNORE_SUFFIXES)
    ]
    files.sort(key=lambda path: path.relative_to(task_dir).as_posix())
    outer = hashlib.sha256()
    for path in files:
        relative = path.relative_to(task_dir).as_posix()
        outer.update(f"{relative}\0{sha256_file(path)}\n".encode("utf-8"))
    return outer.hexdigest()


def prompt_skeleton(value: str) -> str:
    """Litbench-style prompt skeleton: numbers, IDs, and amounts normalized."""
    value = re.sub(r"\d[\d,.]*", "<N>", value)
    value = re.sub(r"[A-Z]{2,}[-A-Z0-9]+", "<ID>", value)
    value = re.sub(r"\$\S+", "<AMT>", value)
    value = re.sub(r"\s+", " ", value)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def shingles(value: str, size: int = 5) -> set[tuple[str, ...]]:
    tokens = words(value)
    return {
        tuple(tokens[index : index + size])
        for index in range(max(0, len(tokens) - size + 1))
    }


def maximum_pair_similarity(values: Iterable[str]) -> dict[str, Any]:
    sets = [shingles(value) for value in values]
    maximum = 0.0
    pair: list[int | None] = [None, None]
    for left in range(len(sets)):
        for right in range(left + 1, len(sets)):
            union = sets[left] | sets[right]
            score = len(sets[left] & sets[right]) / len(union) if union else 1.0
            if score > maximum:
                maximum = score
                pair = [left, right]
    return {"maximum_jaccard_5_shingle": round(maximum, 6), "pair_indices": pair}


def dataset_card() -> str:
    return f"""---
license: cc-by-4.0
task_categories:
- text-generation
- question-answering
language:
- en
tags:
- sales
- salesforce
- hubspot
- gong
- agents
- mcp
- deterministic-evaluation
pretty_name: {RELEASE_NAME}
size_categories:
- n<1K
---

# {RELEASE_NAME}

{RELEASE_NAME} is a synthetic long-horizon sales-agent benchmark with 100 original workflows across Salesforce, HubSpot, Gong, and a seeded evidence room. Every task has 96 production-style source records, 12 authorized CRM mutations, two deliverables, and a 163-call accepted MCP trajectory.

## Public release

- Runnable Harbor world: <https://hub.harborframework.com/datasets/{HARBOR_ORG}/{RELEASE_SLUG}>
- Dataset and test assets: <https://huggingface.co/datasets/{HF_ORG}/{RELEASE_SLUG}>
- Benchmark page: <https://blobfish.ai/benchmarks/{RELEASE_SLUG}>
- Builder and verifier source: <https://github.com/blobfishai/sales-agent-simulation>

## Contents

- `data/tasks.jsonl`: portable task records with prompts, context paths, deterministic rubric metadata, and public gold output.
- `tasks/`: one readable JSON record per workflow.
- `task_files/`: 9,600 unique seeded artifacts across Markdown, text, JSON, CSV, email, XML, and HTML.
- `world/`: the four-surface offline MCP world and verifier.
- `contracts/`: pinned contract metadata and exact published tool schemas.
- `trajectories/`: accepted tool traces produced by the qualification run.
- `reports/`: build, qualification, MCP-conformance, and container-probe evidence.

## Objective release gates

| Gate | Required |
|---|---:|
| Tasks | 100 |
| Workflow families | 10 |
| Documents per task | 96 |
| Authorized mutations per task | 12 |
| Reference MCP calls per task | 163 |
| Verifier network/model/clock/random calls | 0 |
| Oracle and replay passes | 100/100 each |
| False accepts across six negative controls | 0 |
| Reward for the pristine no-op control | exactly 0.0 |

Measured results live in `reports/qualification.json`. Reference traces are implementation proofs, not model scores.

## Contract fidelity

The world keeps Salesforce, HubSpot, Gong, and filesystem as separate MCP endpoints. Names and input JSON Schemas are pinned to official hosted documentation or real open-source implementations at immutable commits recorded in `contracts/upstream-pins.json`. The Gong surface is read-only. Output envelopes mirror the corresponding MCP/API JSON shapes, with documented offline simplifications.

## Data and licensing

All people, entities, records, messages, amounts, and commercial facts are synthetic. CRMArena, SCUBA, AutomationBench, Harvey Labs, and Apex Accounting informed quality and packaging analysis only; their task text and data are not included. Synthetic task data is {DATA_LICENSE}; generator/runtime code is {CODE_LICENSE}. Third-party contract facts retain their upstream terms.
"""


def source_readme() -> str:
    return f"""# {RELEASE_NAME} source

This repository contains the deterministic generator, four-server MCP world,
qualification suite, and publication tooling for {RELEASE_NAME}.

```bash
python3 -m salesbench.builder
python3 -m salesbench.run_suite
python3 -m unittest discover -s tests -v
```

Generated artifacts are written to `dist/{RELEASE_SLUG}` and ignored by Git.
Generation is deterministic and makes no network calls.

- Harbor: <https://hub.harborframework.com/datasets/{HARBOR_ORG}/{RELEASE_SLUG}>
- Hugging Face: <https://huggingface.co/datasets/{HF_ORG}/{RELEASE_SLUG}>
- Benchmark: <https://blobfish.ai/benchmarks/{RELEASE_SLUG}>
"""


def _copy_public_world(hf_root: Path) -> None:
    package = hf_root / "world" / "salesbench"
    runtime = package / "runtime"
    write_text(package / "__init__.py", '"""SalesBench public runtime."""\n')
    shutil.copy2(ROOT / "salesbench" / "contracts.py", package / "contracts.py")
    for name in RUNTIME_FILES:
        runtime.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "salesbench" / "runtime" / name, runtime / name)


def _validate_report(report: dict[str, Any]) -> None:
    expected_families = {family: 10 for family in FAMILY_SETTINGS}
    failures = {
        "task_count": report["task_count"] == 100,
        "family_distribution": report["tasks_per_workflow_family"] == expected_families,
        "document_count": report["document_count"] == 9_600,
        "all_documents_unique": report["unique_document_sha256_count"] == 9_600,
        "minimum_document_bytes": report["minimum_document_bytes"] >= 5_000,
        "minimum_reference_calls": report["reference_tool_calls_per_task"] >= 100,
        "exact_reference_calls": report["reference_tool_calls_per_task"] == MINIMUM_TOOL_CALLS,
        "exact_changes": report["authorized_mutations_per_task"] == TARGET_CHANGE_COUNT,
        "prompt_similarity": report["prompt_uniqueness"]["maximum_jaccard_5_shingle"] < 0.80,
        "prompt_skeletons_all_unique": report["prompt_skeletons_unique"] == 100,
        "duplicate_prompts": report["exact_duplicate_prompts"] == 0,
        "required_servers": report["required_mcp_servers"] == ["filesystem", "gong", "hubspot", "salesforce"],
    }
    rejected = [name for name, passed in failures.items() if not passed]
    if rejected:
        raise ValueError(f"release build gates failed: {rejected}")


def build(output: Path) -> dict[str, Any]:
    output = output.resolve()
    if output.name != RELEASE_SLUG:
        raise ValueError(f"refusing to replace unexpected output path: {output}")
    if output.exists():
        shutil.rmtree(output)
    tasks_root = output / "harbor" / "tasks"
    hf_root = output / "huggingface"
    tasks_root.mkdir(parents=True)
    hf_root.mkdir(parents=True)

    tasks = generate_all()
    records: list[dict[str, Any]] = []
    index: list[dict[str, Any]] = []
    document_hashes: set[str] = set()
    document_sizes: list[int] = []
    prompts: list[str] = []
    servers: set[str] = set()

    for task in tasks:
        record, index_entry = create_task_pack(tasks_root, hf_root, task)
        records.append(record)
        index.append(index_entry)
        prompts.append(task.prompt)
        servers.update(call["server"] for call in task.reference["calls"])
        for content in task.documents.values():
            document_hashes.add(hashlib.sha256(content.encode("utf-8")).hexdigest())
            document_sizes.append(len(content.encode("utf-8")))

    write_text(
        hf_root / "data" / "tasks.jsonl",
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
    )
    write_text(hf_root / "README.md", dataset_card())
    write_text(
        hf_root / "LICENSE-DATA",
        "Creative Commons Attribution 4.0 International\nhttps://creativecommons.org/licenses/by/4.0/\n",
    )
    shutil.copy2(ROOT / "LICENSE", hf_root / "LICENSE-CODE")
    write_json(hf_root / "contracts" / "upstream-pins.json", CONTRACT_PINS)
    for server, definitions in TOOLS_BY_SERVER.items():
        write_json(hf_root / "contracts" / f"{server}-tools.json", {"tools": list(definitions.values())})
    _copy_public_world(hf_root)
    (hf_root / "tests").mkdir(parents=True, exist_ok=True)
    if (ROOT / "tests").exists():
        shutil.copytree(ROOT / "tests", hf_root / "tests", dirs_exist_ok=True)
    if (ROOT / "salesbench" / "run_suite.py").exists():
        shutil.copy2(
            ROOT / "salesbench" / "run_suite.py",
            hf_root / "tests" / "run_suite.py",
        )

    family_counts = Counter(task.spine.family for task in tasks)
    sorted_sizes = sorted(document_sizes)
    report = {
        "schema_version": "salesbench.build.v1",
        "benchmark": RELEASE_NAME,
        "version": RELEASE_VERSION,
        "task_count": len(tasks),
        "workflow_family_count": len(FAMILY_SETTINGS),
        "tasks_per_workflow_family": dict(sorted(family_counts.items())),
        "documents_per_task": DOCUMENT_COUNT,
        "document_count": len(document_sizes),
        "unique_document_sha256_count": len(document_hashes),
        "minimum_document_bytes": min(document_sizes),
        "median_document_bytes": sorted_sizes[len(sorted_sizes) // 2],
        "maximum_document_bytes": max(document_sizes),
        "total_document_bytes": sum(document_sizes),
        "authorized_mutations_per_task": TARGET_CHANGE_COUNT,
        "reference_tool_calls_per_task": MINIMUM_TOOL_CALLS,
        "reference_tool_calls_total": len(tasks) * MINIMUM_TOOL_CALLS,
        "required_mcp_servers": sorted(servers),
        "tool_counts_by_server": {server: len(tools) for server, tools in TOOLS_BY_SERVER.items()},
        "prompt_uniqueness": maximum_pair_similarity(prompts),
        "prompt_skeletons_unique": len({prompt_skeleton(prompt) for prompt in prompts}),
        "exact_duplicate_prompts": len(prompts) - len(set(prompts)),
        "exact_duplicate_documents": len(document_sizes) - len(document_hashes),
        "fixed_file_timestamp": FIXED_FILE_TIMESTAMP,
        "verifier": {
            "deterministic": True,
            "model_calls": 0,
            "network_calls": 0,
            "wall_clock_reads": 0,
            "random_calls": 0,
            "whole_business_state_exact": True,
        },
        "contract_pins": CONTRACT_PINS,
    }
    _validate_report(report)
    write_json(output / "reports" / "build.json", report)
    write_json(hf_root / "reports" / "build.json", report)
    for report_name in (
        "conformance.json",
        "harbor-oracle-qualification.json",
        "harbor-registry-qualification.json",
        "model-evaluation.json",
    ):
        evidence = ROOT / "reports" / report_name
        if evidence.is_file():
            shutil.copy2(evidence, output / "reports" / report_name)
            shutil.copy2(evidence, hf_root / "reports" / report_name)
    write_json(output / "task-index.json", index)

    task_rows = sorted(
        (
            f"{HARBOR_ORG}/{task_dir.name}",
            harbor_content_digest(task_dir),
        )
        for task_dir in tasks_root.iterdir()
        if task_dir.is_dir()
    )
    dataset_toml = (
        f'''[dataset]
name = "{HARBOR_ORG}/{RELEASE_SLUG}"
version = "{RELEASE_VERSION}"
description = "100 synthetic Salesforce, HubSpot, Gong, and RevOps tasks with deterministic 163-call trajectories."
authors = []
keywords = ["sales", "salesforce", "hubspot", "gong", "mcp", "long-horizon"]
'''
        + "".join(
            f'\n[[tasks]]\nname = "{name}"\ndigest = "sha256:{digest}"\n'
            for name, digest in task_rows
        )
    )
    write_text(output / "harbor" / "dataset" / "dataset.toml", dataset_toml)
    write_text(output / "harbor" / "README.md", source_readme())

    seal_release_manifest(output)
    return report


def seal_release_manifest(output: Path) -> dict[str, Any]:
    manifest_path = output / "release-manifest.json"
    release_files = sorted(
        path
        for path in output.rglob("*")
        if path.is_file() and path != manifest_path
    )
    manifest = {
        "schema_version": "salesbench.release.v1",
        "benchmark": RELEASE_NAME,
        "version": RELEASE_VERSION,
        "files": [
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in release_files
        ],
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(manifest_path, manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / RELEASE_SLUG,
    )
    return parser.parse_args()


def main() -> None:
    report = build(parse_args().output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
