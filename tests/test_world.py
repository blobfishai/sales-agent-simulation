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
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
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
        self.assertEqual(len(reports[0]["semantic_checks"]), 15)
        self.assertEqual(
            sum(check["weight"] for check in reports[0]["semantic_checks"]),
            100.0,
        )
        self.assertTrue(all(check["passed"] for check in reports[0]["semantic_checks"]))
        self.assertEqual(reports[0], reports[1])
        executed = {
            f"{component}.{criterion_id}"
            for component in ("procedure", "state", "changes", "brief")
            for criterion_id in (
                reports[0]["criteria"][component]
                if component == "procedure"
                else reports[0]["criteria"][component]["criteria"]
            )
        }
        self.assertEqual(
            executed, {row["id"] for row in self.task.spec["rubric_criteria"]}
        )

    def test_keyword_stuffing_cannot_replace_a_human_brief(self) -> None:
        world = self.world("keyword-stuffing")
        replaced = False
        for call in self.task.reference["calls"]:
            arguments = call["arguments"]
            if (
                call["server"] == "filesystem"
                and call["name"] == "write_file"
                and arguments["path"].endswith("brief.md")
            ):
                arguments = {
                    **arguments,
                    "content": " ".join(arguments["content"].split()),
                }
                replaced = True
            result = world.call_tool(call["server"], call["name"], arguments)
            self.assertFalse(result["isError"])
        self.assertTrue(replaced)
        report = world.verify(verification_token(self.task.task_id))
        criteria = report["criteria"]["brief"]["criteria"]
        self.assertFalse(report["passed"])
        self.assertFalse(criteria["natural_narrative"])
        self.assertTrue(
            all(passed for name, passed in criteria.items() if name != "natural_narrative")
        )

    def _run_with_changes(self, suffix: str, mutate) -> dict:
        world = self.world(suffix)
        for call in self.task.reference["calls"]:
            arguments = call["arguments"]
            if (
                call["server"] == "filesystem"
                and call["name"] == "write_file"
                and arguments["path"].endswith("changes.json")
            ):
                payload = json.loads(arguments["content"])
                mutate(payload)
                arguments = {
                    **arguments,
                    "content": json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                }
            result = world.call_tool(call["server"], call["name"], arguments)
            self.assertFalse(result["isError"])
        return world.verify(verification_token(self.task.task_id))

    def test_misreported_alternative_timing_is_rejected(self) -> None:
        def flip_timing(payload: dict) -> None:
            model = payload["decision_model"]
            model["decision_timing_status"] = (
                "LATE" if model["decision_timing_status"] == "ON_TIME" else "ON_TIME"
            )

        report = self._run_with_changes("wrong-timing", flip_timing)
        self.assertFalse(report["passed"])
        self.assertFalse(
            report["criteria"]["changes"]["criteria"][
                "decision_model.decision_timing_status"
            ]
        )
        failed = [check["id"] for check in report["semantic_checks"] if not check["passed"]]
        self.assertEqual(failed, ["decision.alternatives"])

    def test_relabelled_unauthorized_alternative_is_rejected(self) -> None:
        expedite_id = next(
            option["id"]
            for option in self.task.spec["decision_options"]
            if option["approval"] == "ADDITIONAL_APPROVAL_REQUIRED"
        )

        def approve_expedite(payload: dict) -> None:
            option = payload["decision_model"]["options"][expedite_id]
            option["approval"] = "APPROVED"
            option["incremental_cost"] = 0

        report = self._run_with_changes("approved-expedite", approve_expedite)
        self.assertFalse(report["passed"])
        criteria = report["criteria"]["changes"]["criteria"]
        self.assertFalse(criteria[f"decision_model.options.{expedite_id}.approval"])
        self.assertFalse(criteria[f"decision_model.options.{expedite_id}.incremental_cost"])

    def test_reference_can_skip_surrounding_sources_and_queries(self) -> None:
        world = self.world("material-only")
        required_investigations = {
            (
                call["server"],
                call["name"],
                json.dumps(call["arguments"], sort_keys=True, separators=(",", ":")),
            )
            for call in self.task.spec["required_investigation_calls"]
        }
        skipped = 0
        for call in self.task.reference["calls"]:
            arguments = call["arguments"]
            if (
                call["server"] == "filesystem"
                and call["name"] == "read_text_file"
                and arguments.get("path") not in self.task.spec["required_document_paths"]
            ):
                skipped += 1
                continue
            if (
                call["server"] == "filesystem"
                and call["name"] == "get_file_info"
                and arguments.get("path") not in self.task.spec["metadata_check_paths"]
            ):
                skipped += 1
                continue
            signature = (
                call["server"],
                call["name"],
                json.dumps(arguments, sort_keys=True, separators=(",", ":")),
            )
            if call.get("purpose") and signature not in required_investigations:
                skipped += 1
                continue
            result = world.call_tool(call["server"], call["name"], arguments)
            self.assertFalse(result["isError"])

        report = world.verify(verification_token(self.task.task_id))
        self.assertGreaterEqual(skipped, 10)
        self.assertTrue(report["passed"])
        self.assertEqual(report["reward"], 1.0)

    def test_material_investigation_accepts_a_semantically_equivalent_query(self) -> None:
        world = self.world("flexible-investigation")
        target = self.task.spec["required_investigation_calls"][0]
        replaced = False
        for call in self.task.reference["calls"]:
            arguments = call["arguments"]
            if (
                not replaced
                and call["server"] == target["server"]
                and call["name"] == target["name"]
                and arguments == target["arguments"]
            ):
                arguments = {
                    **arguments,
                    "limit": 50,
                    "properties": ["salesbench_key", "forecast_status"],
                }
                replaced = True
            result = world.call_tool(call["server"], call["name"], arguments)
            self.assertFalse(result["isError"])
        self.assertTrue(replaced)
        report = world.verify(verification_token(self.task.task_id))
        self.assertTrue(report["passed"])
        self.assertTrue(
            report["criteria"]["procedure"]["task_specific_investigation_completed"]
        )

    def test_outputs_only_are_rejected(self) -> None:
        world = self.world("shortcut")
        for call in self.task.reference["calls"][-2:]:
            world.call_tool(call["server"], call["name"], call["arguments"])
        report = world.verify(verification_token(self.task.task_id))
        self.assertFalse(report["passed"])
        self.assertLessEqual(report["reward"], 0.49)

    def test_correct_result_with_task_specific_evidence_omitted_is_rejected(self) -> None:
        world = self.world("missing-task-investigation")
        required = self.task.spec["required_investigation_calls"][0]
        skipped = False
        for call in self.task.reference["calls"]:
            if (
                not skipped
                and call["server"] == required["server"]
                and call["name"] == required["name"]
                and call["arguments"] == required["arguments"]
            ):
                skipped = True
                continue
            result = world.call_tool(call["server"], call["name"], call["arguments"])
            self.assertFalse(result["isError"])
        self.assertTrue(skipped)
        report = world.verify(verification_token(self.task.task_id))
        self.assertFalse(report["passed"])
        self.assertFalse(
            report["criteria"]["procedure"]["task_specific_investigation_completed"]
        )

    def test_correct_writes_followed_by_late_reads_are_rejected(self) -> None:
        world = self.world("write-first")
        calls = self.task.reference["calls"]
        crm_mutations = [
            call
            for call in calls
            if call["server"] in {"salesforce", "hubspot"}
            and call["name"] in {"updateSobjectRecord", "hubspot_update_object"}
        ]
        outputs = [
            call
            for call in calls
            if call["server"] == "filesystem" and call["name"] == "write_file"
        ]
        investigation = [
            call for call in calls if call not in crm_mutations and call not in outputs
        ]
        for call in [*crm_mutations, *investigation, *outputs]:
            result = world.call_tool(call["server"], call["name"], call["arguments"])
            self.assertFalse(result["isError"])
        report = world.verify(verification_token(self.task.task_id))
        self.assertFalse(report["passed"])
        self.assertFalse(
            report["criteria"]["procedure"]["all_required_evidence_precedes_mutation"]
        )
        self.assertFalse(
            report["criteria"]["procedure"]["all_provider_evidence_precedes_mutation"]
        )

    def test_mutation_acknowledgement_without_postwrite_readback_is_rejected(self) -> None:
        world = self.world("missing-readback")
        skipped_change_id = None
        for call in self.task.reference["calls"]:
            if skipped_change_id is None and call.get("phase") == "postwrite_readback":
                skipped_change_id = call["change_id"]
                continue
            result = world.call_tool(call["server"], call["name"], call["arguments"])
            self.assertFalse(result["isError"])
        self.assertIsNotNone(skipped_change_id)
        report = world.verify(verification_token(self.task.task_id))
        self.assertFalse(report["passed"])
        self.assertFalse(
            report["criteria"]["procedure"]["all_mutations_verified_by_readback"]
        )
        self.assertFalse(
            report["criteria"]["state"]["criteria"][
                f"{skipped_change_id}.postwrite_readback"
            ]
        )

    def test_pristine_noop_world_scores_exactly_zero(self) -> None:
        world = self.world("noop")
        report = world.verify(verification_token(self.task.task_id))
        self.assertFalse(report["passed"])
        self.assertEqual(report["reward"], 0.0)
        self.assertEqual(report["reward_cap_reason"], "no_mcp_interaction")

    def test_failed_read_is_recoverable_but_rejected_mutation_is_not(self) -> None:
        read_world = self.world("recover-read")
        invalid_read = read_world.call_tool("salesforce", "soqlQuery", {})
        self.assertTrue(invalid_read["isError"])
        for call in self.task.reference["calls"]:
            read_world.call_tool(call["server"], call["name"], call["arguments"])
        read_report = read_world.verify(verification_token(self.task.task_id))
        self.assertTrue(read_report["passed"])
        self.assertTrue(read_report["criteria"]["procedure"]["no_rejected_mutation"])

        mutation_world = self.world("reject-mutation")
        change = self.task.spec["expected_changes"][0]
        invalid_arguments = {
            **change["arguments"],
            "id": f"{change['record_id']}-OUT-OF-SCOPE",
        }
        invalid_mutation = mutation_world.call_tool(
            change["system"], change["tool"], invalid_arguments
        )
        self.assertTrue(invalid_mutation["isError"])
        for call in self.task.reference["calls"]:
            mutation_world.call_tool(call["server"], call["name"], call["arguments"])
        mutation_report = mutation_world.verify(verification_token(self.task.task_id))
        self.assertFalse(mutation_report["passed"])
        self.assertFalse(
            mutation_report["criteria"]["procedure"]["no_rejected_mutation"]
        )
        execution = next(
            check
            for check in mutation_report["semantic_checks"]
            if check["id"] == "execution.delivery"
        )
        self.assertFalse(execution["passed"])

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
