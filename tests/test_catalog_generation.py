from __future__ import annotations

import hashlib
import re
import unittest
from collections import Counter

from salesbench.builder import compose_yaml, dataset_card, main_dockerfile, world_dockerfile
from salesbench.catalog import FAMILY_SETTINGS, TASK_SPINES
from salesbench.generation import (
    DOCUMENT_COUNT,
    MINIMUM_TOOL_CALLS,
    TARGET_CHANGE_COUNT,
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
            self.assertEqual(len(task.reference["calls"]), MINIMUM_TOOL_CALLS)
            self.assertGreaterEqual(len(task.reference["calls"]), 100)
            self.assertEqual(len(task.spec["expected_changes"]), TARGET_CHANGE_COUNT)
            self.assertEqual(
                {call["server"] for call in task.reference["calls"]},
                {"filesystem", "salesforce", "hubspot", "gong"},
            )
            self.assertEqual(len(task.spec["decision_options"]), 3)
            self.assertEqual(sum(option["selected"] for option in task.spec["decision_options"]), 1)
            self.assertEqual(len(task.spec["rubric_criteria"]), 281)

    def test_employee_requests_are_high_level_and_reference_workflows_are_unique(self) -> None:
        prompts = [task.prompt for task in self.tasks]
        sequences = [
            tuple(f"{call['server']}.{call['name']}" for call in task.reference["calls"])
            for task in self.tasks
        ]
        self.assertEqual(len(set(prompts)), 100)
        self.assertEqual(len(set(sequences)), 100)
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

    def test_operating_contract_is_discoverable_inside_each_evidence_room(self) -> None:
        for task in self.tasks:
            deliverable_records = [
                content
                for relative, content in task.documents.items()
                if relative.startswith("12_deliverables/")
            ]
            self.assertEqual(len(deliverable_records), 8)
            self.assertTrue(all("workflow_contract" in content for content in deliverable_records))

    def test_seeded_documents_are_deep_and_globally_unique(self) -> None:
        contents = [content for task in self.tasks for content in task.documents.values()]
        self.assertEqual(len(contents), 9_600)
        self.assertGreaterEqual(min(len(content.encode("utf-8")) for content in contents), 5_000)
        self.assertEqual(
            len({hashlib.sha256(content.encode("utf-8")).digest() for content in contents}),
            9_600,
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


if __name__ == "__main__":
    unittest.main()
