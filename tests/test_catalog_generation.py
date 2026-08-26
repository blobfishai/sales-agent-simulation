from __future__ import annotations

import hashlib
import unittest
from collections import Counter

from salesbench.builder import compose_yaml, main_dockerfile, world_dockerfile
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


if __name__ == "__main__":
    unittest.main()
