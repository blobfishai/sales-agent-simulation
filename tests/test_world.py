from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from salesbench.generation import TASK_SPINES, generate_task, verification_token
from salesbench.runtime.world import SalesWorld


class WorldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.task = generate_task(TASK_SPINES[0], 1)
        self.documents = self.root / "documents"
        for relative, content in self.task.documents.items():
            path = self.documents / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.spec_path = self.root / "spec.json"
        self.seed_path = self.root / "seed.json"
        self.spec_path.write_text(json.dumps(self.task.spec), encoding="utf-8")
        self.seed_path.write_text(json.dumps(self.task.seed), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def world(self, suffix: str) -> SalesWorld:
        return SalesWorld(
            self.documents,
            self.root / f"output-{suffix}",
            self.root / f"state-{suffix}",
            self.spec_path,
            self.seed_path,
        )

    def test_reference_trajectory_passes_and_replays_exactly(self) -> None:
        reports = []
        for suffix in ("one", "two"):
            world = self.world(suffix)
            for call in self.task.reference["calls"]:
                result = world.call_tool(call["server"], call["name"], call["arguments"])
                self.assertFalse(result["isError"])
                self.assertEqual(
                    result["structuredContent"]["content"], result["content"][0]["text"]
                )
            reports.append(world.verify(verification_token(self.task.task_id)))
        self.assertTrue(reports[0]["passed"])
        self.assertEqual(reports[0]["reward"], 1.0)
        self.assertEqual(reports[0], reports[1])

    def test_outputs_only_are_rejected(self) -> None:
        world = self.world("shortcut")
        for call in self.task.reference["calls"][-2:]:
            world.call_tool(call["server"], call["name"], call["arguments"])
        report = world.verify(verification_token(self.task.task_id))
        self.assertFalse(report["passed"])
        self.assertLessEqual(report["reward"], 0.49)

    def test_pristine_noop_world_scores_exactly_zero(self) -> None:
        world = self.world("noop")
        report = world.verify(verification_token(self.task.task_id))
        self.assertFalse(report["passed"])
        self.assertEqual(report["reward"], 0.0)
        self.assertEqual(report["reward_cap_reason"], "no_mcp_interaction")

    def test_unauthorized_delete_fails_verification(self) -> None:
        world = self.world("delete")
        for call in self.task.reference["calls"]:
            world.call_tool(call["server"], call["name"], call["arguments"])
        target = next(
            row
            for row in world.state["salesforce"]["objects"]["Account"]
            if str(row.get("SalesBenchKey__c", "")).startswith("CTRL-")
        )
        result = world.call_tool(
            "salesforce",
            "deleteSobjectRecord",
            {"sobject-name": "Account", "id": target["Id"]},
        )
        self.assertFalse(result["isError"])
        report = world.verify(verification_token(self.task.task_id))
        self.assertFalse(report["passed"])
        state_criteria = report["criteria"]["state"]["criteria"]
        self.assertFalse(state_criteria["no_delete_tool_succeeded"])
        self.assertFalse(state_criteria["entire_business_state_exact"])

    def test_verifier_capability_is_not_public(self) -> None:
        world = self.world("token")
        with self.assertRaises(PermissionError):
            world.verify(None)
        with self.assertRaises(PermissionError):
            world.verify("wrong")


if __name__ == "__main__":
    unittest.main()
