#!/usr/bin/env python3
"""Live conformance checks for the four SalesBench MCP surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import select
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parent
if not (SOURCE_ROOT / "salesbench").exists():
    sys.path.insert(0, str(SOURCE_ROOT / "world"))
else:
    sys.path.insert(0, str(SOURCE_ROOT))

from salesbench.contracts import CONTRACT_PINS, TOOLS_BY_SERVER  # noqa: E402
from salesbench.runtime.world import SalesWorld  # noqa: E402

try:  # The public runtime bundle intentionally omits the generator package.
    from salesbench.generation import RELEASE_VERSION  # noqa: E402
except ImportError:  # pragma: no cover - exercised from the packaged HF world
    RELEASE_VERSION = "3.3.0"


def tls_context() -> ssl.SSLContext:
    candidates = (
        Path("/etc/ssl/cert.pem"),
        Path("/etc/ssl/certs/ca-certificates.crt"),
        Path("/opt/homebrew/etc/openssl@3/cert.pem"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ssl.create_default_context(cafile=str(candidate))
    return ssl.create_default_context()


TLS_CONTEXT = tls_context()


class StdioMCP:
    def __init__(self, allowed_root: Path) -> None:
        pin = CONTRACT_PINS["filesystem"]
        package = f"{pin['package']}@{pin['version']}"
        self.process = subprocess.Popen(
            ["npx", "-y", package, str(allowed_root)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.next_id = 0

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.next_id += 1
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self.next_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 90
        assert self.process.stdout is not None
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.process.stdout], [], [], 1)
            if not ready:
                if self.process.poll() is not None:
                    stderr = self.process.stderr.read() if self.process.stderr else ""
                    raise RuntimeError(f"upstream MCP exited {self.process.returncode}: {stderr}")
                continue
            line = self.process.stdout.readline()
            if not line:
                continue
            response = json.loads(line)
            if response.get("id") == self.next_id:
                if response.get("error"):
                    raise RuntimeError(json.dumps(response["error"]))
                return response["result"]
        raise TimeoutError(f"no response to {method}")

    def notify(self, method: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.process.stdin.flush()


def schema_shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: schema_shape(item)
            for key, item in value.items()
            if key not in {"$schema", "description", "title"}
        }
    if isinstance(value, list):
        return [schema_shape(item) for item in value]
    return value


def contract_shape(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool.get("name"),
        "inputSchema": schema_shape(tool.get("inputSchema", {})),
        "outputSchema": schema_shape(tool.get("outputSchema", {})),
        "annotations": tool.get("annotations", {}),
    }


def text_result(result: dict[str, Any]) -> str:
    assert result.get("content") and result["content"][0].get("type") == "text"
    text = result["content"][0]["text"]
    assert result.get("structuredContent") == {"content": text}
    return text


def fetch(url: str) -> tuple[str, str]:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is required for immutable upstream source conformance")
    completed = subprocess.run(
        [curl, "-fsSL", "--retry", "2", url],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    body = completed.stdout
    return body.decode("utf-8"), hashlib.sha256(body).hexdigest()


def hosted_probe(url: str) -> dict[str, Any]:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": CONTRACT_PINS["protocol_version"],
                "capabilities": {},
                "clientInfo": {"name": "salesbench-conformance", "version": "1.0.0"},
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json, text/event-stream")
    try:
        with urllib.request.urlopen(request, timeout=30, context=TLS_CONTEXT) as response:
            status = response.status
            headers = response.headers
    except urllib.error.HTTPError as error:
        status = error.code
        headers = error.headers
    return {
        "url": url,
        "status": status,
        "auth_gate_present": status in {401, 403},
        "www_authenticate_present": bool(headers.get("WWW-Authenticate")),
    }


def source_checks() -> dict[str, Any]:
    sf_url = "https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/sobject-all.html"
    sf_text, sf_digest = fetch(sf_url)
    sf_fragments = [
        "getObjectSchema", "soqlQuery", "find", "getUserInfo",
        "listRecentSobjectRecords", "getRelatedRecords", "createSobjectRecord",
        "updateSobjectRecord", "updateRelatedRecord", "deleteSobjectRecord",
        "deleteRelatedRecord", "object-name", "sobject-name", "relationship-path",
    ]

    hs_base = (
        "https://raw.githubusercontent.com/axonops/hubspot-mcp/"
        f"{CONTRACT_PINS['hubspot']['commit']}/src/hubspot_mcp/tools"
    )
    hs_sources: dict[str, str] = {}
    hs_digests: dict[str, str] = {}
    for filename in (
        "objects.py", "associations.py", "engagements.py", "misc.py",
        "owners.py", "pipelines.py", "properties.py",
    ):
        value, digest = fetch(f"{hs_base}/{filename}")
        hs_sources[filename] = value
        hs_digests[filename] = digest
    hs_text = "\n".join(hs_sources.values())
    hs_fragments = [f"async def {name}" for name in TOOLS_BY_SERVER["hubspot"]]

    gong_url = (
        "https://raw.githubusercontent.com/gonimbly/gong-mcp/"
        f"{CONTRACT_PINS['gong']['commit']}/src/tools/entities.ts"
    )
    gong_text, gong_digest = fetch(gong_url)
    gong_fragments = [
        '"gong_ask_account"', '"gong_ask_deal"', '"gong_generate_brief"',
        "crmAccountId", "crmDealId", "briefName", "crmEntityType",
        "crmEntityId", 'z.enum(["THIS_WEEK", "THIS_MONTH", "THIS_QUARTER", "THIS_YEAR"])',
    ]
    return {
        "salesforce": {
            "source": sf_url,
            "sha256": sf_digest,
            "required_fragments": {item: item in sf_text for item in sf_fragments},
        },
        "hubspot": {
            "source_commit": CONTRACT_PINS["hubspot"]["commit"],
            "source_sha256": hs_digests,
            "required_fragments": {item: item in hs_text for item in hs_fragments},
        },
        "gong": {
            "source": gong_url,
            "sha256": gong_digest,
            "required_fragments": {item: item in gong_text for item in gong_fragments},
            "official_names_drop_open_source_prefix": True,
        },
    }


def filesystem_conformance() -> dict[str, Any]:
    if shutil.which("npx") is None:
        raise RuntimeError("npx is required for pinned filesystem MCP conformance")
    with tempfile.TemporaryDirectory(prefix="salesbench-conformance-") as raw:
        root = Path(raw)
        actual_root = root / "actual"
        documents = root / "documents"
        output = root / "output"
        state = root / "state"
        actual_root.mkdir()
        documents.mkdir()
        fixture = "SalesBench conformance\nLine two with $1,250.00.\n"
        (actual_root / "fixture.txt").write_text(fixture, encoding="utf-8")
        (documents / "fixture.txt").write_text(fixture, encoding="utf-8")
        spec = root / "spec.json"
        seed = root / "seed.json"
        spec.write_text(
            json.dumps(
                {
                    "task_id": "conformance",
                    "task_number": 0,
                    "as_of": "2026-08-26",
                    "fixed_file_timestamp": "2026-08-26T12:00:00.000Z",
                    "verify_token_sha256": "unused",
                    "reference_tool_calls": 0,
                    "required_document_paths": [],
                    "metadata_check_paths": [],
                    "deliverables": [],
                    "expected_changes": [],
                    "reference_calls": [],
                    "brief_sections": [],
                    "forbidden_claims": [],
                    "title": "Conformance",
                    "company": "Synthetic",
                }
            ),
            encoding="utf-8",
        )
        seed.write_text(
            json.dumps(
                {
                    "salesforce": {"user": {}, "objects": {}},
                    "hubspot": {"account_details": {}, "objects": {}, "associations": []},
                    "gong": {"accounts": {}, "deals": {}, "brief_templates": []},
                }
            ),
            encoding="utf-8",
        )
        mock = SalesWorld(documents, output, state, spec, seed)
        upstream = StdioMCP(actual_root)
        try:
            initialized = upstream.send(
                "initialize",
                {
                    "protocolVersion": CONTRACT_PINS["protocol_version"],
                    "capabilities": {},
                    "clientInfo": {"name": "salesbench-conformance", "version": "1.0.0"},
                },
            )
            upstream.notify("notifications/initialized")
            actual_tools = {
                tool["name"]: tool for tool in upstream.send("tools/list")["tools"]
            }
            contracts = {
                name: name in actual_tools
                and contract_shape(actual_tools[name]) == contract_shape(expected)
                for name, expected in TOOLS_BY_SERVER["filesystem"].items()
            }
            actual_read = upstream.send(
                "tools/call",
                {"name": "read_text_file", "arguments": {"path": str(actual_root / "fixture.txt")}},
            )
            mock_read = mock.call_tool(
                "filesystem", "read_text_file", {"path": "/workspace/documents/fixture.txt"}
            )
            actual_write_path = actual_root / "result.txt"
            actual_write = upstream.send(
                "tools/call",
                {"name": "write_file", "arguments": {"path": str(actual_write_path), "content": "grounded\n"}},
            )
            mock_write = mock.call_tool(
                "filesystem",
                "write_file",
                {"path": "/workspace/output/result.txt", "content": "grounded\n"},
            )
            behavior = {
                "read_text_file": text_result(actual_read) == text_result(mock_read) == fixture,
                "write_file": (
                    text_result(actual_write) == f"Successfully wrote to {actual_write_path}"
                    and text_result(mock_write) == "Successfully wrote to /workspace/output/result.txt"
                    and actual_write_path.read_text() == (output / "result.txt").read_text()
                ),
            }
            for name, arguments in (
                ("directory_tree", {"path": "/workspace/documents", "excludePatterns": []}),
                ("search_files", {"path": "/workspace/documents", "pattern": "**/*.txt", "excludePatterns": []}),
                ("get_file_info", {"path": "/workspace/documents/fixture.txt"}),
                ("list_allowed_directories", {}),
            ):
                result = mock.call_tool("filesystem", name, arguments)
                behavior[name] = (
                    not result.get("isError")
                    and result.get("structuredContent") == {"content": result["content"][0]["text"]}
                )
        finally:
            upstream.close()
    return {
        "pin": CONTRACT_PINS["filesystem"],
        "initialize": initialized,
        "contract_checks": contracts,
        "behavior_checks": behavior,
        "passed": all(contracts.values()) and all(behavior.values()),
    }


def run(report_path: Path | None = None) -> dict[str, Any]:
    filesystem = filesystem_conformance()
    sources = source_checks()
    probes = {
        "salesforce": hosted_probe(CONTRACT_PINS["salesforce"]["endpoint"]),
        "hubspot": hosted_probe(CONTRACT_PINS["hubspot"]["official_endpoint"]),
        "gong": hosted_probe(CONTRACT_PINS["gong"]["official_endpoint"]),
    }
    source_passed = all(
        all(section["required_fragments"].values()) for section in sources.values()
    )
    probes_passed = all(probe["auth_gate_present"] for probe in probes.values())
    result = {
        "schema_version": "salesbench.conformance.v1",
        "benchmark_version": RELEASE_VERSION,
        "filesystem_live_package": filesystem,
        "vendor_source_contracts": sources,
        "hosted_endpoint_probes": probes,
        "claims": {
            "filesystem_exact_tools_list_subset": filesystem["passed"],
            "vendor_tool_names_and_input_keys_present_at_pins": source_passed,
            "three_hosted_vendor_mcp_endpoints_live_and_auth_gated": probes_passed,
            "offline_outputs_use_mcp_content_and_structured_content": all(
                filesystem["behavior_checks"].values()
            ),
            "authenticated_hosted_tools_list_compared": False,
        },
        "limitations": [
            "Tenant-authenticated tools/list was not available for the three hosted vendor servers.",
            "HubSpot response envelopes are deterministic CRM v3/v4 fixtures rather than live tenant data.",
            "Gong synthesized insight text is seeded and does not invoke Gong proprietary AI generation.",
        ],
        "passed": filesystem["passed"] and source_passed and probes_passed,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    outcome = run(parse_args().report)
    raise SystemExit(0 if outcome["passed"] else 1)
