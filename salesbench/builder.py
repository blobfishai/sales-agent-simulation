#!/usr/bin/env python3
"""Build the SalesBench-100 Harbor task packs and Hugging Face release."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import shutil
import stat
import zipfile
from collections import Counter
from difflib import SequenceMatcher
from email import policy
from email.parser import Parser
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from .catalog import FAMILY_SETTINGS
from .contracts import CONTRACT_PINS, TOOLS_BY_SERVER
from .decision_specs import DECISION_RULES
from .generation import (
    DOCUMENT_COUNT,
    EVIDENCE_ROLES,
    FIXED_FILE_TIMESTAMP,
    MAX_REFERENCE_TOOL_CALLS,
    MAX_TARGET_CHANGE_COUNT,
    METADATA_CHECK_COUNT,
    MIN_REFERENCE_TOOL_CALLS,
    MIN_TARGET_CHANGE_COUNT,
    REQUIRED_TEXT_DOCUMENT_COUNT,
    RELEASE_VERSION,
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


def write_asset(path: Path, value: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_format_error(relative: str, content: str | bytes) -> str | None:
    """Parse each released export according to its native extension."""

    suffix = Path(relative).suffix.casefold()
    folder = relative.split("/", 1)[0]
    supplemental = folder[:2].isdigit() and int(folder[:2]) >= 13
    try:
        if suffix == ".pdf":
            if not isinstance(content, bytes) or not content.startswith(b"%PDF-1.4"):
                return "PDF magic is invalid"
            if not content.rstrip().endswith(b"%%EOF") or b"xref\n" not in content:
                return "PDF cross-reference or trailer is invalid"
            return None
        if suffix == ".xlsx":
            if not isinstance(content, bytes):
                return "XLSX asset is not binary"
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                if not {"[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"} <= names:
                    return "XLSX package is missing required workbook parts"
                ElementTree.fromstring(archive.read("xl/workbook.xml"))
                ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            return None
        if not isinstance(content, str):
            return f"{suffix} asset must be UTF-8 text"
        if supplemental:
            if len(content.encode("utf-8")) < 800:
                return "supplemental evidence must contain at least 800 bytes"
            if suffix == ".json":
                value = json.loads(content)
                if not isinstance(value, dict) or not value.get("case_id"):
                    return "supplemental JSON is missing its case identity"
            elif suffix == ".csv":
                rows = list(csv.DictReader(io.StringIO(content)))
                if len(rows) < 8 or not all(row.get("case_id") for row in rows):
                    return "supplemental CSV lacks case-linked rows"
            elif suffix == ".eml":
                message = Parser(policy=policy.default).parsestr(content)
                if not message.get("From") or not message.get("To") or not message.get("Subject"):
                    return "supplemental EML envelope headers are incomplete"
                if len(message.get_content()) < 500:
                    return "supplemental EML body is too shallow"
            elif suffix in {".md", ".log", ".yaml"}:
                if "case" not in content.casefold() or "\x00" in content:
                    return "supplemental evidence lacks case context or contains NUL bytes"
            else:
                return f"unsupported supplemental extension {suffix}"
            return None
        if suffix == ".json":
            value = json.loads(content)
            if not isinstance(value, dict) or len(value.get("records", [])) != 8:
                return "JSON register must contain exactly eight records"
        elif suffix == ".csv":
            rows = list(csv.DictReader(io.StringIO(content)))
            if len(rows) != 8:
                return "CSV register must contain exactly eight rows"
            if not all(json.loads(row["evidence_json"]) for row in rows):
                return "CSV evidence_json cell is empty"
        elif suffix == ".eml":
            message = Parser(policy=policy.default).parsestr(content)
            if not message.get("From") or not message.get("To") or not message.get("Subject"):
                return "EML envelope headers are incomplete"
            body = message.get_content()
            rows = [line[2:] for line in body.splitlines() if line.startswith("- {")]
            if len(rows) != 8 or not all(isinstance(json.loads(row), dict) for row in rows):
                return "EML register must contain eight JSON evidence bullets"
        elif suffix == ".html":
            match = re.search(r"<pre>(.*?)</pre>", content, re.DOTALL | re.IGNORECASE)
            if not content.casefold().startswith("<!doctype html>") or not match:
                return "HTML export must contain a doctype and preformatted payload"
            value = json.loads(html.unescape(match.group(1)))
            if len(value.get("records", [])) != 8:
                return "HTML register must contain exactly eight records"
        elif suffix == ".xml":
            root = ElementTree.fromstring(content)
            records_section = next(
                (
                    section
                    for section in root.findall("section")
                    if section.attrib.get("name") == "records"
                ),
                None,
            )
            if records_section is None or len(json.loads(records_section.text or "[]")) != 8:
                return "XML register must contain exactly eight records"
        elif suffix in {".md", ".txt"}:
            if content.count('"portfolio_key": "SBP-') != 8 or "\x00" in content:
                return "text register must contain eight portfolio records and no NUL bytes"
        else:
            return f"unsupported text-native extension {suffix}"
    except (
        csv.Error,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        ElementTree.ParseError,
        zipfile.BadZipFile,
    ) as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


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
expected_changes = {len(task.spec['expected_changes'])}
reference_tool_calls = {len(task.reference['calls'])}
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
if request_id != len(REFERENCE["calls"]):
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
        write_asset(source, content)
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
        "world_id": "salesbench-multi-crm-mcp-v3",
        "prompt": task.prompt,
        "context_files": hf_context_paths,
        "rubric": {
            "type": "deterministic",
            "required_document_reads": REQUIRED_TEXT_DOCUMENT_COUNT,
            "metadata_checks": METADATA_CHECK_COUNT,
            "authorized_mutations": len(task.spec["expected_changes"]),
            "required_deliverables": ["changes.json", "brief.md"],
            "score_weights": {"procedure": 0.20, "state": 0.45, "changes": 0.25, "brief": 0.10},
            "gates": [
                "all_evidence_read_in_full",
                "all_required_evidence_precedes_mutation",
                "all_provider_evidence_precedes_mutation",
                "vendor_evidence_cross_checked",
                "entire_business_state_exact",
                "authorized_mutations_each_called_once",
                "no_delete_or_neighbor_mutation",
                "exact_structured_change_log",
                "fully_grounded_brief",
                "deliverables_written_through_mcp",
            ],
            "criteria": task.spec["rubric_criteria"],
            "decision_options": task.spec["decision_options"],
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
            "reference_tool_calls": len(task.reference["calls"]),
            "contract_pins": CONTRACT_PINS,
            "semantic_action_signature": semantic_action_signature(task),
            "evidence_roles": list(EVIDENCE_ROLES),
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
        "reference_tool_calls": len(task.reference["calls"]),
        "authorized_mutations": len(task.spec["expected_changes"]),
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


def maximum_sequence_similarity(values: list[tuple[str, ...]]) -> dict[str, Any]:
    maximum = 0.0
    pair: list[int | None] = [None, None]
    for left in range(len(values)):
        for right in range(left + 1, len(values)):
            score = SequenceMatcher(
                a=values[left], b=values[right], autojunk=False
            ).ratio()
            if score > maximum:
                maximum = score
                pair = [left, right]
    return {"maximum_sequence_match": round(maximum, 6), "pair_indices": pair}


def semantic_action_signature(task: GeneratedTask) -> str:
    """Hash provider objects and governed fields, excluding IDs and read order."""

    nodes: Counter[tuple[Any, ...]] = Counter()
    for call in task.reference["calls"]:
        server = call["server"]
        tool = call["name"]
        arguments = call["arguments"]
        if server == "salesforce" and tool == "soqlQuery":
            query = arguments["query"]
            object_match = re.search(r"\bFROM\s+(\w+)", query, re.IGNORECASE)
            fields = query.split("FROM", 1)[0].split("SELECT", 1)[1].strip()
            nodes[(server, tool, object_match.group(1) if object_match else "", fields)] += 1
        elif tool == "updateSobjectRecord":
            nodes[
                (
                    server,
                    tool,
                    arguments["sobject-name"],
                    tuple(sorted(arguments["body"])),
                )
            ] += 1
        elif tool in {"hubspot_get_object", "hubspot_update_object"}:
            fields = arguments.get("properties", {})
            if isinstance(fields, dict):
                fields = sorted(fields)
            nodes[(server, tool, arguments["object_type"], tuple(fields))] += 1
        else:
            nodes[(server, tool)] += 1
    return hashlib.sha256(
        repr(sorted(nodes.items())).encode("utf-8")
    ).hexdigest()


def semantic_call_sequence(task: GeneratedTask) -> tuple[str, ...]:
    """Normalize IDs while retaining the business resource and field shape."""

    tokens: list[str] = []
    for call in task.reference["calls"]:
        server = call["server"]
        tool = call["name"]
        arguments = call["arguments"]
        if server == "filesystem" and tool in {"read_text_file", "get_file_info"}:
            path = Path(str(arguments.get("path", "")))
            tokens.append(f"{server}.{tool}:{path.parent.name}:{path.suffix}")
        elif server == "salesforce" and tool == "soqlQuery":
            query = str(arguments.get("query", ""))
            object_match = re.search(r"\bFROM\s+(\w+)", query, re.IGNORECASE)
            fields = query.split("FROM", 1)[0].split("SELECT", 1)[-1].strip()
            tokens.append(
                f"{server}.{tool}:{object_match.group(1) if object_match else ''}:{fields}"
            )
        elif tool == "updateSobjectRecord":
            tokens.append(
                f"{server}.{tool}:{arguments['sobject-name']}:"
                f"{','.join(sorted(arguments['body']))}"
            )
        elif tool in {"hubspot_get_object", "hubspot_update_object"}:
            fields = arguments.get("properties", {})
            if isinstance(fields, dict):
                fields = sorted(fields)
            tokens.append(
                f"{server}.{tool}:{arguments['object_type']}:{','.join(fields)}"
            )
        elif server == "gong":
            tokens.append(f"{server}.{tool}:{arguments.get('crmEntityType', '')}")
        else:
            tokens.append(f"{server}.{tool}")
    return tuple(tokens)


def _declares_evidence_role(content: str, role: str) -> bool:
    return any(
        marker in content
        for marker in (
            f'"evidence_role": "{role}"',
            f'evidence_role,"""{role}"""',
            f'&quot;evidence_role&quot;: &quot;{role}&quot;',
            f",{role},",
        )
    )


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
configs:
- config_name: default
  data_files:
  - split: test
    path: data/tasks.jsonl
---

# {RELEASE_NAME}

{RELEASE_NAME} is a synthetic long-horizon sales-agent benchmark with 100 original workflows across Salesforce, HubSpot, Gong, and a seeded evidence room. Each task begins with a high-level employee request and has its own authored causal rule and provider transition. Identity, operating facts, authority, governed policy, live-system indexes, and exceptions are separated so no mounted business asset publishes a selected option or precomputed change. Every task has 28 independently inspectable assets across 11 native formats. The evidence—not a fixed quota—determines 5–12 authorized CRM mutations and 68–103 calls, including an exact post-write readback for every mutation.

## Public release

- Runnable Harbor world: <https://hub.harborframework.com/datasets/{HARBOR_ORG}/{RELEASE_SLUG}>
- Dataset and test assets: <https://huggingface.co/datasets/{HF_ORG}/{RELEASE_SLUG}>
- Benchmark page: <https://blobfish.ai/benchmarks/{RELEASE_SLUG}>
- Builder and verifier source: <https://github.com/blobfishai/sales-agent-simulation>

## Contents

- `data/tasks.jsonl`: portable task records with prompts, context paths, deterministic rubric metadata, and public gold output.
- `tasks/`: one readable JSON record per workflow.
- `task_files/`: 2,800 unique task-scoped assets across PDF, Excel, email, Slack/Drive-style JSON, structured exports, controls, and audit records.
- `world/`: the four-surface offline MCP world and verifier.
- `contracts/`: pinned contract metadata and exact published tool schemas.
- `trajectories/`: accepted tool traces produced by the qualification run.
- `reports/`: build, qualification, MCP-conformance, and container-probe evidence.

## Objective release gates

| Gate | Required |
|---|---:|
| Tasks | 100 |
| Workflow families | 10 |
| Agent-visible assets per task | 28 across 11 native formats |
| Authorized mutations per task | 5–12; at least six distinct workload sizes |
| Reference MCP calls per task | 68–103 |
| Unique tool-name sequences | 100/100 |
| Unique semantic action graphs | 100/100 |
| Authored causal decision rules | 100/100 unique |
| Task-specific deterministic criteria | 301–420 |
| Precomputed answer objects in business evidence | 0 |
| Evidence and provider reads before mutation | required |
| Exact post-write readback per mutation | required |
| Verifier network/model/clock/random calls | 0 |
| Oracle and replay passes | 100/100 each |
| False accepts across ten negative controls | 0 |
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
        "document_count": report["document_count"] == 2_800,
        "all_documents_unique": report["unique_document_sha256_count"] == 2_800,
        "minimum_document_bytes": report["minimum_document_bytes"] >= 800,
        "reference_call_range": (
            report["reference_tool_calls_per_task"]["minimum"] >= MIN_REFERENCE_TOOL_CALLS
            and report["reference_tool_calls_per_task"]["maximum"] <= MAX_REFERENCE_TOOL_CALLS
        ),
        "mutation_range": (
            report["authorized_mutations_per_task"]["minimum"] == MIN_TARGET_CHANGE_COUNT
            and report["authorized_mutations_per_task"]["maximum"] == MAX_TARGET_CHANGE_COUNT
            and len(report["authorized_mutations_per_task"]["distinct_counts"]) >= 6
        ),
        "prompt_similarity": report["prompt_uniqueness"]["maximum_jaccard_5_shingle"] < 0.80,
        "prompt_skeletons_all_unique": report["prompt_skeletons_unique"] == 100,
        "duplicate_prompts": report["exact_duplicate_prompts"] == 0,
        "unique_reference_sequences": report["unique_reference_tool_name_sequences"] == 100,
        "unique_semantic_call_sequences": report["unique_semantic_call_sequences"] == 100,
        "unique_semantic_action_graphs": report["unique_semantic_action_graphs"] == 100,
        "semantic_sequence_similarity": (
            report["semantic_sequence_similarity"]["maximum_sequence_match"] < 0.85
        ),
        "evidence_role_coverage": report["causal_evidence"]["every_task_has_one_of_each_role_per_portfolio_key"],
        "no_precomputed_answer_keys": not report["causal_evidence"]["precomputed_answer_hits"],
        "no_single_file_transition_answer": not report["causal_evidence"]["single_file_complete_transition_hits"],
        "read_before_write_control": report["causal_evidence"]["required_evidence_precedes_mutation"],
        "task_specific_investigation_control": report["causal_evidence"]["task_specific_investigation_precedes_mutation"],
        "provider_prewrite_control": report["causal_evidence"]["provider_evidence_precedes_each_mutation"],
        "postwrite_readback_control": report["causal_evidence"]["each_mutation_has_exact_postwrite_readback"],
        "outputs_follow_readback": report["causal_evidence"]["deliverables_follow_all_readbacks"],
        "unique_decision_rules": report["causal_evidence"]["unique_authored_decision_rules"] == 100,
        "hold_partition": report["causal_evidence"]["every_portfolio_is_exactly_changed_or_held"],
        "no_selected_option_leak": not report["causal_evidence"]["selected_option_leaks"],
        "no_amount_result_leak": not report["causal_evidence"]["derived_amount_leaks"],
        "asset_formats_parse": not report["asset_format_validation"]["invalid_assets"],
        "required_servers": report["required_mcp_servers"] == ["filesystem", "gong", "hubspot", "salesforce"],
    }
    rejected = [name for name, passed in failures.items() if not passed]
    if rejected:
        raise ValueError(f"release build gates failed: {rejected}")


def _causal_trace_audit(task: GeneratedTask) -> dict[str, bool]:
    calls = task.reference["calls"]
    mutation_indexes = [
        index
        for index, call in enumerate(calls)
        if call.get("phase") == "authorized_mutation"
    ]
    if not mutation_indexes:
        return {
            "task_specific_investigation_precedes_mutation": False,
            "required_evidence_precedes_mutation": False,
            "provider_evidence_precedes_each_mutation": False,
            "each_mutation_has_exact_postwrite_readback": False,
            "deliverables_follow_all_readbacks": False,
        }
    first_mutation = min(mutation_indexes)
    task_specific_investigation_precedes = all(
        any(
            index < first_mutation
            and call["server"] == required["server"]
            and call["name"] == required["name"]
            and call["arguments"] == required["arguments"]
            for index, call in enumerate(calls)
        )
        for required in task.spec["required_investigation_calls"]
    )
    full_read_indexes = {
        call["arguments"].get("path"): index
        for index, call in enumerate(calls)
        if call["server"] == "filesystem"
        and call["name"] == "read_text_file"
        and "head" not in call["arguments"]
        and "tail" not in call["arguments"]
    }
    all_documents_precede = all(
        path in full_read_indexes and full_read_indexes[path] < first_mutation
        for path in task.spec["required_document_paths"]
    )
    provider_prewrite = True
    postwrite = True
    postwrite_indexes: list[int] = []
    for change in task.spec["expected_changes"]:
        exact_mutations = [
            index
            for index, call in enumerate(calls)
            if call.get("phase") == "authorized_mutation"
            and call.get("change_id") == change["id"]
            and call["server"] == change["system"]
            and call["name"] == change["tool"]
            and call["arguments"] == change["arguments"]
        ]
        if len(exact_mutations) != 1:
            provider_prewrite = False
            postwrite = False
            continue
        mutation_index = exact_mutations[0]
        evidence_indexes = [
            index
            for index, call in enumerate(calls)
            if call.get("phase") == "prewrite_provider_evidence"
            and call.get("change_id") == change["id"]
        ]
        if (
            len(evidence_indexes) != 3
            or {calls[index]["server"] for index in evidence_indexes}
            != {"salesforce", "hubspot", "gong"}
            or any(index >= mutation_index for index in evidence_indexes)
            or any(
                full_read_indexes.get(path, mutation_index) >= mutation_index
                for path in change["evidence_sources"]
            )
        ):
            provider_prewrite = False
        expected = change["postwrite_evidence"]
        exact_readbacks = [
            index
            for index, call in enumerate(calls)
            if call.get("phase") == "postwrite_readback"
            and call.get("change_id") == change["id"]
            and call["server"] == expected["server"]
            and call["name"] == expected["name"]
            and call["arguments"] == expected["arguments"]
        ]
        if len(exact_readbacks) != 1 or exact_readbacks[0] <= mutation_index:
            postwrite = False
        else:
            postwrite_indexes.append(exact_readbacks[0])
    output_indexes = [
        index
        for index, call in enumerate(calls)
        if call["server"] == "filesystem" and call["name"] == "write_file"
    ]
    outputs_after_readback = (
        len(output_indexes) == 2
        and len(postwrite_indexes) == len(task.spec["expected_changes"])
        and min(output_indexes) > max(postwrite_indexes)
    )
    return {
        "task_specific_investigation_precedes_mutation": task_specific_investigation_precedes,
        "required_evidence_precedes_mutation": all_documents_precede,
        "provider_evidence_precedes_each_mutation": provider_prewrite,
        "each_mutation_has_exact_postwrite_readback": postwrite,
        "deliverables_follow_all_readbacks": outputs_after_readback,
    }


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
    reference_sequences: list[tuple[str, ...]] = []
    semantic_sequences: list[tuple[str, ...]] = []
    semantic_signatures: list[str] = []
    criterion_counts: list[int] = []
    reference_call_counts: list[int] = []
    mutation_counts: list[int] = []
    precomputed_answer_hits: list[dict[str, str]] = []
    single_file_transition_hits: list[dict[str, str]] = []
    selected_option_leaks: list[dict[str, str]] = []
    derived_amount_leaks: list[dict[str, str]] = []
    invalid_assets: list[dict[str, str]] = []
    asset_format_counts: Counter[str] = Counter()
    trace_audits: list[dict[str, bool]] = []
    decision_rule_signatures: set[tuple[str, str, str]] = set()
    evidence_role_coverage = True
    portfolio_partition_complete = True
    forbidden_answer_keys = (
        '"decision"',
        '"eligible_for_requested_workflow"',
        '"decision_code"',
        '"authorized_record_id"',
        '"authorized_field"',
        '"required_value"',
    )

    for task in tasks:
        record, index_entry = create_task_pack(tasks_root, hf_root, task)
        records.append(record)
        index.append(index_entry)
        prompts.append(task.prompt)
        servers.update(call["server"] for call in task.reference["calls"])
        reference_sequences.append(
            tuple(f"{call['server']}.{call['name']}" for call in task.reference["calls"])
        )
        semantic_sequences.append(semantic_call_sequence(task))
        semantic_signatures.append(semantic_action_signature(task))
        criterion_counts.append(len(task.spec["rubric_criteria"]))
        reference_call_counts.append(len(task.reference["calls"]))
        mutation_counts.append(len(task.spec["expected_changes"]))
        trace_audits.append(_causal_trace_audit(task))
        rule = DECISION_RULES[task.spine.slug]
        decision_rule_signatures.add(
            (rule.observation_key, rule.authority_key, rule.method)
        )
        changed_keys = {
            change["portfolio_key"] for change in task.spec["expected_changes"]
        }
        held_keys = {hold["portfolio_key"] for hold in task.spec["expected_holds"]}
        expected_keys = {
            f"SBP-{task.spec['task_number']:03d}-{slot:02d}"
            for slot in range(1, 17)
        }
        if changed_keys & held_keys or changed_keys | held_keys != expected_keys:
            portfolio_partition_complete = False
        for portfolio_slot in range(1, 17):
            portfolio_key = f"SBP-{task.spec['task_number']:03d}-{portfolio_slot:02d}"
            matching_documents = [
                content
                for content in task.documents.values()
                if isinstance(content, str) and portfolio_key in content
            ]
            if len(matching_documents) != len(EVIDENCE_ROLES):
                evidence_role_coverage = False
            for role in EVIDENCE_ROLES:
                if sum(
                    _declares_evidence_role(content, role)
                    for content in matching_documents
                ) != 1:
                    evidence_role_coverage = False
        for relative, content in task.documents.items():
            asset_format_counts[Path(relative).suffix.casefold()] += 1
            if error := _asset_format_error(relative, content):
                invalid_assets.append(
                    {"task_id": task.task_id, "path": relative, "error": error}
                )
            blob = content if isinstance(content, bytes) else content.encode("utf-8")
            document_hashes.add(hashlib.sha256(blob).hexdigest())
            document_sizes.append(len(blob))
            if isinstance(content, bytes):
                continue
            for forbidden in forbidden_answer_keys:
                if forbidden in content:
                    precomputed_answer_hits.append(
                        {"task_id": task.task_id, "path": relative, "key": forbidden}
                    )
            if '"selected":' in content:
                selected_option_leaks.append(
                    {"task_id": task.task_id, "path": relative}
                )
            for change in task.spec["expected_changes"]:
                if (
                    change["value_kind"] == "amount"
                    and str(change["after"]) in content
                ):
                    derived_amount_leaks.append(
                        {
                            "task_id": task.task_id,
                            "path": relative,
                            "change_id": change["id"],
                        }
                    )
                if all(
                    str(value) in content
                    for value in (
                        change["record_id"],
                        change["field"],
                        change["after"],
                        "approved_within_policy",
                    )
                ):
                    single_file_transition_hits.append(
                        {
                            "task_id": task.task_id,
                            "path": relative,
                            "change_id": change["id"],
                        }
                    )

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
        shutil.copytree(
            ROOT / "tests",
            hf_root / "tests",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                "*.pyo",
                ".DS_Store",
                "*.swp",
                "*.swo",
                "*~",
            ),
        )
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
        "authorized_mutations_per_task": {
            "minimum": min(mutation_counts),
            "maximum": max(mutation_counts),
            "distinct_counts": sorted(set(mutation_counts)),
            "distribution": dict(sorted(Counter(mutation_counts).items())),
        },
        "reference_tool_calls_per_task": {
            "minimum": min(reference_call_counts),
            "maximum": max(reference_call_counts),
            "distinct_counts": sorted(set(reference_call_counts)),
        },
        "reference_tool_calls_total": sum(reference_call_counts),
        "unique_reference_tool_name_sequences": len(set(reference_sequences)),
        "unique_semantic_call_sequences": len(set(semantic_sequences)),
        "unique_semantic_action_graphs": len(set(semantic_signatures)),
        "reference_sequence_similarity": maximum_sequence_similarity(reference_sequences),
        "semantic_sequence_similarity": maximum_sequence_similarity(semantic_sequences),
        "required_mcp_servers": sorted(servers),
        "tool_counts_by_server": {server: len(tools) for server, tools in TOOLS_BY_SERVER.items()},
        "prompt_uniqueness": maximum_pair_similarity(prompts),
        "prompt_skeletons_unique": len({prompt_skeleton(prompt) for prompt in prompts}),
        "exact_duplicate_prompts": len(prompts) - len(set(prompts)),
        "exact_duplicate_documents": len(document_sizes) - len(document_hashes),
        "asset_format_validation": {
            "scope": "native PDF/XLSX packages plus validated UTF-8 communication, control, and structured-export formats",
            "format_counts": dict(sorted(asset_format_counts.items())),
            "invalid_assets": invalid_assets,
        },
        "criteria_per_task": {
            "minimum": min(criterion_counts),
            "maximum": max(criterion_counts),
        },
        "causal_evidence": {
            "evidence_roles": list(EVIDENCE_ROLES),
            "every_task_has_one_of_each_role_per_portfolio_key": evidence_role_coverage,
            "precomputed_answer_hits": precomputed_answer_hits,
            "single_file_complete_transition_hits": single_file_transition_hits,
            "selected_option_leaks": selected_option_leaks,
            "derived_amount_leaks": derived_amount_leaks,
            "required_evidence_precedes_mutation": all(
                audit["required_evidence_precedes_mutation"]
                for audit in trace_audits
            ),
            "task_specific_investigation_precedes_mutation": all(
                audit["task_specific_investigation_precedes_mutation"]
                for audit in trace_audits
            ),
            "provider_evidence_precedes_each_mutation": all(
                audit["provider_evidence_precedes_each_mutation"]
                for audit in trace_audits
            ),
            "each_mutation_has_exact_postwrite_readback": all(
                audit["each_mutation_has_exact_postwrite_readback"]
                for audit in trace_audits
            ),
            "deliverables_follow_all_readbacks": all(
                audit["deliverables_follow_all_readbacks"]
                for audit in trace_audits
            ),
            "unique_authored_decision_rules": len(decision_rule_signatures),
            "every_portfolio_is_exactly_changed_or_held": portfolio_partition_complete,
        },
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
            try:
                report_value = json.loads(evidence.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                report_value = {}
            report_version = report_value.get("benchmark_version") or report_value.get("version")
            # Unversioned and prior-version evidence is not portable to this
            # release.  Omitting it is safer than displaying stale provenance.
            if report_version != RELEASE_VERSION:
                continue
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
description = "100 high-level sales operations requests with evidence-determined multi-system trajectories."
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
