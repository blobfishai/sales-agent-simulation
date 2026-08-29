from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from salesbench.catalog import TASK_SPINES
from salesbench.generation import generate_task


class HTTPServerTests(unittest.TestCase):
    def test_vendor_endpoints_are_separated(self) -> None:
        task = generate_task(TASK_SPINES[0], 1)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            documents = root / "documents"
            for relative, content in task.documents.items():
                target = documents / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, bytes):
                    target.write_bytes(content)
                else:
                    target.write_text(content, encoding="utf-8")
            spec = root / "spec.json"
            seed = root / "seed.json"
            spec.write_text(json.dumps(task.spec), encoding="utf-8")
            seed.write_text(json.dumps(task.seed), encoding="utf-8")
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            environment = os.environ.copy()
            environment.update(
                {
                    "SALESBENCH_HOST": "127.0.0.1",
                    "SALESBENCH_PORT": str(port),
                    "SALESBENCH_DOCUMENTS": str(documents),
                    "SALESBENCH_OUTPUT": str(root / "output"),
                    "SALESBENCH_STATE": str(root / "state"),
                    "SALESBENCH_SPEC": str(spec),
                    "SALESBENCH_SEED": str(seed),
                }
            )
            process = subprocess.Popen(
                [sys.executable, "-m", "salesbench.runtime.server"],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                time.sleep(0.3)
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=5
                ) as response:
                    self.assertEqual(json.loads(response.read())["task_id"], task.task_id)
                expected_counts = {
                    "filesystem": 6,
                    "salesforce": 11,
                    "hubspot": 15,
                    "gong": 3,
                }
                for server, count in expected_counts.items():
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{port}/mcp/{server}",
                        data=json.dumps(
                            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(request, timeout=5) as response:
                        payload = json.loads(response.read())
                    self.assertEqual(len(payload["result"]["tools"]), count)
                unauthorized = urllib.request.Request(
                    f"http://127.0.0.1:{port}/verify", data=b"{}", method="POST"
                )
                with self.assertRaises(urllib.error.HTTPError) as captured:
                    urllib.request.urlopen(unauthorized, timeout=5)
                self.assertEqual(captured.exception.code, 404)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
