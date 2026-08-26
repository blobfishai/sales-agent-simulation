from __future__ import annotations

import unittest

from salesbench.contracts import CONTRACT_PINS, TOOLS_BY_SERVER


class ContractTests(unittest.TestCase):
    def test_tool_counts_and_names_are_unique(self) -> None:
        self.assertEqual(
            {server: len(tools) for server, tools in TOOLS_BY_SERVER.items()},
            {"filesystem": 6, "salesforce": 11, "hubspot": 15, "gong": 3},
        )
        names = [
            (server, name)
            for server, tools in TOOLS_BY_SERVER.items()
            for name in tools
        ]
        self.assertEqual(len(names), len(set(names)))

    def test_every_tool_has_executable_json_schema(self) -> None:
        for server, tools in TOOLS_BY_SERVER.items():
            for name, tool in tools.items():
                with self.subTest(server=server, tool=name):
                    schema = tool["inputSchema"]
                    self.assertEqual(schema["type"], "object")
                    self.assertIsInstance(schema["properties"], dict)
                    self.assertIn("readOnlyHint", tool["annotations"])

    def test_gong_is_strictly_read_only(self) -> None:
        self.assertTrue(
            all(tool["annotations"]["readOnlyHint"] for tool in TOOLS_BY_SERVER["gong"].values())
        )

    def test_contracts_are_immutable_pins(self) -> None:
        self.assertEqual(CONTRACT_PINS["protocol_version"], "2025-06-18")
        for server in ("filesystem", "salesforce", "hubspot", "gong"):
            pin = CONTRACT_PINS[server]
            self.assertRegex(pin["commit"], r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
