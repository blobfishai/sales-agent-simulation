from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

from salesbench.builder import (
    build,
    compose_yaml,
    dataset_card,
    main_dockerfile,
    maximum_sequence_similarity,
    semantic_call_sequence,
    world_dockerfile,
)
from salesbench.catalog import FAMILY_SETTINGS, TASK_SPINES
from salesbench.decision_specs import DECISION_RULES
from salesbench.generation import (
    DOCUMENT_COUNT,
    EVIDENCE_ROLES,
    MAX_REFERENCE_TOOL_CALLS,
    MAX_TARGET_CHANGE_COUNT,
    MIN_REFERENCE_TOOL_CALLS,
    MIN_TARGET_CHANGE_COUNT,
    FIXED_XLSX_ZIP_TIMESTAMP,
    generate_all,
)


class CatalogGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = generate_all()

    def test_exactly_one_hundred_original_spines(self) -> None:
        self.assertEqual(len(TASK_SPINES), 100)
        self.assertEqual(len({spine.slug for spine in TASK_SPINES}), 100)
        self.assertEqual(len({spine.title for spine in TASK_SPINES}), 100)
        self.assertEqual(
            Counter(spine.family for spine in TASK_SPINES),
            Counter({family: 10 for family in FAMILY_SETTINGS}),
        )

    def test_every_task_has_long_horizon_structure(self) -> None:
        for task in self.tasks:
            self.assertEqual(len(task.documents), DOCUMENT_COUNT)
            self.assertGreaterEqual(len(task.reference["calls"]), MIN_REFERENCE_TOOL_CALLS)
            self.assertLessEqual(len(task.reference["calls"]), MAX_REFERENCE_TOOL_CALLS)
            self.assertEqual(task.spec["reference_tool_calls"], len(task.reference["calls"]))
            self.assertEqual(len(task.spec["required_investigation_calls"]), 5)
            self.assertGreaterEqual(len(task.spec["reference_investigation_calls"]), 6)
            self.assertLessEqual(len(task.spec["reference_investigation_calls"]), 11)
            self.assertEqual(
                len(task.spec["investigation_purposes"]),
                len(task.spec["required_investigation_calls"]),
            )
            self.assertGreaterEqual(len(task.spec["expected_changes"]), MIN_TARGET_CHANGE_COUNT)
            self.assertLessEqual(len(task.spec["expected_changes"]), MAX_TARGET_CHANGE_COUNT)
            self.assertEqual(
                {call["server"] for call in task.reference["calls"]},
                {"filesystem", "salesforce", "hubspot", "gong"},
            )
            self.assertEqual(len(task.spec["decision_options"]), 3)
            self.assertEqual(sum(option["selected"] for option in task.spec["decision_options"]), 1)
            self.assertGreaterEqual(len(task.spec["required_document_paths"]), 10)
            self.assertLessEqual(len(task.spec["required_document_paths"]), 12)
            self.assertEqual(len(task.spec["reference_document_paths"]), 24)
            self.assertEqual(len(task.spec["metadata_check_paths"]), 4)
            self.assertEqual(len(task.spec["reference_metadata_check_paths"]), 8)
            self.assertEqual(len(task.spec["rubric_criteria"]), 14)
            self.assertEqual(
                sum(row["weight"] for row in task.spec["rubric_criteria"]),
                100,
            )
            self.assertEqual(
                len({row["id"] for row in task.spec["rubric_criteria"]}),
                len(task.spec["rubric_criteria"]),
            )
        mutation_counts = {
            len(task.spec["expected_changes"])
            for task in self.tasks
        }
        self.assertGreaterEqual(len(mutation_counts), 6)
        self.assertEqual(
            len(
                {
                    tuple(row["description"] for row in task.spec["rubric_criteria"])
                    for task in self.tasks
                }
            ),
            100,
        )

    def test_employee_requests_are_high_level_and_reference_workflows_are_unique(self) -> None:
        prompts = [task.prompt for task in self.tasks]
        sequences = [
            tuple(f"{call['server']}.{call['name']}" for call in task.reference["calls"])
            for task in self.tasks
        ]
        self.assertEqual(len(set(prompts)), 100)
        self.assertEqual(len(set(sequences)), 100)
        self.assertLess(
            maximum_sequence_similarity(sequences)["maximum_sequence_match"],
            0.95,
        )
        semantic_sequences = [semantic_call_sequence(task) for task in self.tasks]
        self.assertEqual(len(set(semantic_sequences)), 100)
        self.assertLess(
            maximum_sequence_similarity(semantic_sequences)["maximum_sequence_match"],
            0.85,
        )
        for prompt in prompts:
            self.assertGreaterEqual(len(prompt.split()), 45)
            self.assertLessEqual(len(prompt.split()), 120)
            self.assertIsNone(
                re.search(
                    r"required procedure|return exactly|write exactly|evidence room contains exactly|this is task|^\s*\d+\.",
                    prompt,
                    re.IGNORECASE | re.MULTILINE,
                )
            )

    def test_semantic_action_graphs_are_unique_not_just_read_order(self) -> None:
        def node(call: dict) -> tuple:
            server = call["server"]
            tool = call["name"]
            arguments = call["arguments"]
            if server == "salesforce" and tool == "soqlQuery":
                query = arguments["query"]
                object_match = re.search(r"\bFROM\s+(\w+)", query, re.IGNORECASE)
                self.assertIsNotNone(object_match)
                fields = query.split("FROM", 1)[0].split("SELECT", 1)[1].strip()
                return server, tool, object_match.group(1), fields
            if tool == "updateSobjectRecord":
                return (
                    server,
                    tool,
                    arguments["sobject-name"],
                    tuple(sorted(arguments["body"])),
                )
            if tool in {"hubspot_get_object", "hubspot_update_object"}:
                fields = arguments.get("properties", {})
                if isinstance(fields, dict):
                    fields = sorted(fields)
                return server, tool, arguments["object_type"], tuple(fields)
            return server, tool, ""

        signatures = []
        for task in self.tasks:
            histogram = Counter(node(call) for call in task.reference["calls"])
            signatures.append(json.dumps(sorted(histogram.items()), sort_keys=True))
        self.assertEqual(len(set(signatures)), 100)

    def test_every_derived_value_is_reconstructible_from_split_inputs(self) -> None:
        for task in self.tasks:
            rule = DECISION_RULES[task.spine.slug]
            for change in task.spec["expected_changes"]:
                observed = change["decision_inputs"]["observed"]
                authority = change["decision_inputs"]["authority"]
                self.assertIn(rule.observation_key, observed)
                self.assertIn(rule.authority_key, authority)
                self.assertEqual(change["decision_method"], rule.method)
                self.assertEqual(len(change["evidence_sources"]), len(EVIDENCE_ROLES))
                kind = change["value_kind"]
                if kind == "static":
                    expected = authority[
                        f"approved_{change['system']}_outcome"
                    ]
                elif kind == "amount":
                    expected = round(
                        (observed["gross_measure"] - observed["excluded_measure"])
                        * authority["approved_rate"]
                    )
                    if change["system"] == "hubspot":
                        expected = str(expected)
                elif kind == "date":
                    expected = max(
                        observed["buyer_supported_date"],
                        authority["first_policy_compliant_date"],
                    )
                elif kind == "owner":
                    self.assertTrue(authority["owner_active"])
                    self.assertGreater(authority["remaining_capacity"], 0)
                    expected = authority["candidate_owner_id"]
                elif kind == "risk":
                    self.assertGreaterEqual(
                        observed["independent_mentions"],
                        authority["minimum_independent_mentions"],
                    )
                    expected = observed["candidate_risk_code"]
                elif kind == "signal":
                    self.assertNotEqual(
                        observed["buyer_supported_action"],
                        observed["seller_only_inference"],
                    )
                    expected = observed["buyer_supported_action"]
                elif kind == "role":
                    self.assertGreaterEqual(
                        observed["independent_sources"], authority["minimum_sources"]
                    )
                    expected = observed["corroborated_role"]
                elif kind == "cross_id":
                    expected = authority[
                        "matched_hubspot_id"
                        if change["system"] == "salesforce"
                        else "matched_salesforce_id"
                    ]
                elif kind == "account":
                    self.assertFalse(authority["alias_alone_sufficient"])
                    expected = observed["legal_account_name"]
                else:  # pragma: no cover - protects future action kinds
                    self.fail(f"unsupported value kind {kind}")
                self.assertEqual(expected, change["after"], (task.task_id, change["id"]))

    def test_all_one_hundred_causal_rules_are_authored_and_distinct(self) -> None:
        self.assertEqual(set(DECISION_RULES), {spine.slug for spine in TASK_SPINES})
        signatures = {
            (rule.observation_key, rule.authority_key, rule.method)
            for rule in DECISION_RULES.values()
        }
        self.assertEqual(len(signatures), 100)
        self.assertNotIn(
            "apply the governed outcome only after the five-way eligibility join",
            {rule.method for rule in DECISION_RULES.values()},
        )

    def test_fx_rate_table_is_shared_by_currency_not_randomized_per_row(self) -> None:
        atlas = next(
            task for task in self.tasks if task.spine.slug == "atlas-apac-currency"
        )
        rates_by_currency: dict[str, set[float]] = {}
        for change in atlas.spec["expected_changes"]:
            inputs = change["decision_inputs"]
            currency = inputs["observed"]["transaction_currency"]
            rates_by_currency.setdefault(currency, set()).add(
                inputs["authority"]["approved_rate"]
            )
        self.assertTrue(rates_by_currency)
        self.assertTrue(all(len(rates) == 1 for rates in rates_by_currency.values()))

    def test_decision_options_holds_and_readbacks_are_task_specific(self) -> None:
        option_ids: list[str] = []
        for task in self.tasks:
            options = task.spec["decision_options"]
            option_ids.extend(option["id"] for option in options)
            text_documents = [
                content for content in task.documents.values() if isinstance(content, str)
            ]
            self.assertNotIn('"selected":', "\n".join(text_documents))
            changed = {
                change["portfolio_key"] for change in task.spec["expected_changes"]
            }
            held = {hold["portfolio_key"] for hold in task.spec["expected_holds"]}
            expected_keys = {
                f"SBP-{task.spec['task_number']:03d}-{slot:02d}"
                for slot in range(1, 17)
            }
            self.assertFalse(changed & held)
            self.assertEqual(changed | held, expected_keys)
            self.assertEqual(len(held), task.spec["expected_hold_count"])

            calls = task.reference["calls"]
            mutations = [
                (index, call)
                for index, call in enumerate(calls)
                if call.get("phase") == "authorized_mutation"
            ]
            self.assertEqual(len(mutations), task.spec["expected_change_count"])
            for index, mutation in mutations:
                readback = calls[index + 1]
                self.assertEqual(readback.get("phase"), "postwrite_readback")
                self.assertEqual(readback.get("change_id"), mutation.get("change_id"))
        self.assertEqual(len(option_ids), 300)
        self.assertEqual(len(set(option_ids)), 300)

    def test_operating_histories_are_bounded_and_amount_answers_are_not_seeded(self) -> None:
        for task in self.tasks:
            combined = "\n".join(
                content for content in task.documents.values() if isinstance(content, str)
            )
            events = re.findall(r"EVT-\d{3}-\d{3}-\d+", combined)
            self.assertGreaterEqual(len(events), 16 * 5)
            self.assertLessEqual(len(events), 16 * 6)
            self.assertEqual(len(events), len(set(events)))
            for change in task.spec["expected_changes"]:
                if change["value_kind"] == "amount":
                    self.assertNotIn(str(change["after"]), combined)

    def test_operating_contract_is_discoverable_inside_each_evidence_room(self) -> None:
        for task in self.tasks:
            deliverable_records = [
                content
                for relative, content in task.documents.items()
                if relative.startswith("12_deliverables/")
            ]
            self.assertEqual(len(deliverable_records), 1)
            self.assertTrue(all("workflow_contract" in content for content in deliverable_records))

    def test_business_evidence_does_not_publish_a_precomputed_change(self) -> None:
        forbidden_keys = (
            '"decision"',
            '"eligible_for_requested_workflow"',
            '"decision_code"',
            '"authorized_record_id"',
            '"authorized_field"',
            '"required_value"',
        )
        for task in self.tasks:
            text_documents = [
                content for content in task.documents.values() if isinstance(content, str)
            ]
            combined = "\n".join(text_documents)
            for forbidden in forbidden_keys:
                self.assertNotIn(forbidden, combined, (task.task_id, forbidden))
            for change in task.spec["expected_changes"]:
                for content in text_documents:
                    leaked_complete_transition = all(
                        str(value) in content
                        for value in (
                            change["record_id"],
                            change["field"],
                            change["after"],
                            "approved_within_policy",
                        )
                    )
                    self.assertFalse(
                        leaked_complete_transition,
                        (task.task_id, change["id"]),
                    )

    def test_each_portfolio_key_requires_six_independent_evidence_roles(self) -> None:
        for task in self.tasks:
            for portfolio_slot in range(1, 17):
                portfolio_key = f"SBP-{task.spec['task_number']:03d}-{portfolio_slot:02d}"
                records = [
                    content
                    for content in task.documents.values()
                    if isinstance(content, str) and portfolio_key in content
                ]
                self.assertEqual(len(records), len(EVIDENCE_ROLES))
                for role in EVIDENCE_ROLES:
                    declarations = (
                        f'"evidence_role": "{role}"',
                        f'evidence_role,"""{role}"""',
                        f'&quot;evidence_role&quot;: &quot;{role}&quot;',
                        f',{role},',
                    )
                    self.assertEqual(
                        sum(
                            any(declaration in content for declaration in declarations)
                            for content in records
                        ),
                        1,
                        (task.task_id, portfolio_key, role),
                    )

    def test_seeded_documents_are_deep_and_globally_unique(self) -> None:
        contents = [content for task in self.tasks for content in task.documents.values()]
        self.assertEqual(len(contents), 2_800)
        blobs = [
            content if isinstance(content, bytes) else content.encode("utf-8")
            for content in contents
        ]
        self.assertGreaterEqual(min(len(content) for content in blobs), 800)
        self.assertEqual(
            len({hashlib.sha256(content).digest() for content in blobs}),
            2_800,
        )
        for task in self.tasks:
            suffixes = {Path(relative).suffix for relative in task.documents}
            self.assertGreaterEqual(len(suffixes), 9)
            self.assertIn(".pdf", suffixes)
            self.assertIn(".xlsx", suffixes)

    def test_xlsx_packages_are_byte_reproducible_and_timestamp_pinned(self) -> None:
        rebuilt = generate_all()
        first_xlsx = {
            (task.task_id, relative): content
            for task in self.tasks
            for relative, content in task.documents.items()
            if relative.endswith(".xlsx")
        }
        rebuilt_xlsx = {
            (task.task_id, relative): content
            for task in rebuilt
            for relative, content in task.documents.items()
            if relative.endswith(".xlsx")
        }
        self.assertEqual(first_xlsx, rebuilt_xlsx)
        self.assertEqual(len(first_xlsx), 200)
        for content in first_xlsx.values():
            self.assertIsInstance(content, bytes)
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                self.assertTrue(archive.infolist())
                self.assertTrue(
                    all(
                        member.date_time == FIXED_XLSX_ZIP_TIMESTAMP
                        for member in archive.infolist()
                    )
                )

    def test_seeded_documents_are_baked_into_public_harbor_images(self) -> None:
        compose = compose_yaml()
        self.assertNotIn("source: ./documents", compose)
        self.assertIn("context: .", compose)
        self.assertIn("dockerfile: world/Dockerfile", compose)
        self.assertIn("COPY documents /workspace/documents", main_dockerfile())
        self.assertIn("COPY documents /workspace/documents", world_dockerfile())

    def test_hugging_face_viewer_targets_only_the_task_jsonl(self) -> None:
        card = dataset_card()
        self.assertIn("configs:\n- config_name: default", card)
        self.assertIn("split: test\n    path: data/tasks.jsonl", card)

    def test_built_hugging_face_jsonl_contains_one_object_per_task(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "salesbench-100"
            build(output)
            rows = [
                json.loads(line)
                for line in (output / "huggingface" / "data" / "tasks.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            copied_reports = {
                path.name
                for path in (output / "reports").glob("*.json")
            }
            copied_runtime_residue = [
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
                and (
                    "__pycache__" in path.parts
                    or path.suffix in {".pyc", ".pyo", ".swp", ".swo"}
                    or path.name == ".DS_Store"
                    or path.name.endswith("~")
                )
            ]
        self.assertEqual(len(rows), 100)
        self.assertTrue(all(isinstance(row, dict) for row in rows))
        self.assertEqual(len({row["task_id"] for row in rows}), 100)
        self.assertTrue(
            all(len(row["rubric"]["criteria"]) == 14 for row in rows)
        )
        self.assertTrue(
            all(
                sum(criterion["weight"] for criterion in row["rubric"]["criteria"])
                == 100
                for row in rows
            )
        )
        self.assertTrue(
            all(
                10 <= row["rubric"]["required_document_reads"] <= 12
                and row["rubric"]["reference_document_reads"] == 24
                and row["rubric"]["call_order_policy"].startswith(
                    "The reference trajectory is illustrative, not graded."
                )
                for row in rows
            )
        )
        self.assertIn("conformance.json", copied_reports)
        self.assertNotIn("harbor-registry-qualification.json", copied_reports)
        self.assertNotIn("model-evaluation.json", copied_reports)
        self.assertEqual(copied_runtime_residue, [])


if __name__ == "__main__":
    unittest.main()
